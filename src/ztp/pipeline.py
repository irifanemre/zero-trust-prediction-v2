"""Boru hattı — 7.2 diyagramı: müşteri bazında izole çalışır (17.1); bilgi grafı ortak, gözlem grafı ve baseline izole."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ztp.config import TenantConfig
from ztp.data.dataset import Dataset
from ztp.deception import UNATTRIBUTED_COLUMNS, HoneytokenRegistry
from ztp.detection.catalog import export_catalog
from ztp.detection.engine import DetectionEngine, Hit
from ztp.features import extract_device_day, extract_features
from ztp.feedback import LabelStore
from ztp.graph.analysis import DeepGraphAnalyzer, GraphFindings
from ztp.graph.knowledge import KnowledgeGraph
from ztp.graph.observation import ObservationGraphBuilder
from ztp.graph.store import NetworkXGraphStore
from ztp.identity import IdentityResolver, Pseudonymizer
from ztp.integrations import CaseSink, build_sinks
from ztp.metrics import HealthMonitor, MetricsCollector
from ztp.peers import PeerGroups
from ztp.prediction import PredictionLayer
from ztp.prediction_model import LogisticModel, calibration_report, rows_to_matrix
from ztp.profile import ProfileEngine
from ztp.quality import DataQualityMonitor
from ztp.reporting.llm import LLMReporter
from ztp.reporting.template import TemplateReporter, describe_hit
from ztp.response import tiered_response
from ztp.schema import DAY, EVENT_COLUMNS, to_utc_naive
from ztp.scoring import RiskResult, RiskScorer
from ztp.state import StateStore, hits_from_records, hits_to_records

LOG = logging.getLogger(__name__)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if math.isnan(float(o)) else float(o)
    if isinstance(o, float) and math.isnan(o):
        return None
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


class ZeroTrustPredictionPipeline:
    """Müşteri bazında boru hattı. İki çalışma biçimi:
    - `run(start, end, warmup)`: toplu — Dataset içindeki tüm olaylar gün gün işlenir (doğrulama/ısınma).
    - `run_incremental(day, events)`: artımlı — durum deposundan yüklenir, yalnızca o günün ham olayları işlenir, kaydedilir.
    İki biçim aynı gün-işleme çekirdeğini (`_run_day`) kullanır ve eşdeğer sonuç üretir (tests/test_state.py)."""

    def __init__(
        self,
        cfg: TenantConfig,
        data: Dataset,
        catalog: List[dict],
        out_dir: Path,
        state: Optional[StateStore] = None,
        sinks: Optional[List[CaseSink]] = None,
    ):
        self.cfg, self.data, self.catalog = cfg, data, catalog
        self.out = out_dir / cfg.tenant_id
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "cases").mkdir(exist_ok=True)
        export_catalog(catalog, self.out / "detections")
        self.state = state
        self.sinks = sinks if sinks is not None else build_sinks(cfg.sinks, self.out)
        self.health = HealthMonitor()
        self.pseud = Pseudonymizer(cfg.pseudonym_secret, self.out / "audit.jsonl")
        self.labels = LabelStore(self.out / "labels.json")
        self.kg = KnowledgeGraph()
        self.engine = DetectionEngine(cfg, catalog, describe=describe_hit)
        self.llm = LLMReporter(cfg)
        self.cases: List[dict] = []
        self.dq_last: dict = {}
        self.final_risk: Dict[str, Dict[pd.Timestamp, float]] = defaultdict(dict)
        self.events_by_day: Dict[pd.Timestamp, pd.DataFrame] = {}
        # aldatma katmanı: yapılandırmadaki tuzak listesi veri paketindekini ezer (kritik varlıklarla aynı kural); boşsa kapalı
        self.honeytokens = HoneytokenRegistry.from_config(cfg.honeytokens or getattr(data, "honeytokens", None))
        self.honeytoken_unattributed = pd.DataFrame(columns=UNATTRIBUTED_COLUMNS)
        self._init_components()

    # ------------------------------------------------------------------ kurulum
    def _init_components(self) -> None:
        d = self.data
        for c in ("hire_date", "resignation_notice_date", "resignation_date", "role_change_date", "privilege_grant_date"):
            d.directory[c] = pd.to_datetime(d.directory[c])
        self.crit = list(self.cfg.critical_assets) or list(d.critical_assets)
        self.resolver = IdentityResolver(d.directory, d.ip_leases)
        self.dq = DataQualityMonitor(self.cfg)
        self.peers = PeerGroups(d.directory, self.cfg.min_peer_group)
        self.profile = ProfileEngine(self.cfg, d.directory, d.leaves, self.peers)
        self.pred = PredictionLayer(self.cfg, d.directory, d.leaves)
        self.store = NetworkXGraphStore()
        self.graph_builder = ObservationGraphBuilder(self.store, self.crit)
        self.deep = DeepGraphAnalyzer(self.cfg, self.store, self.kg, self.crit, int((~d.directory.is_service.astype(bool)).sum()))
        self.scorer = RiskScorer(self.cfg, self.kg, self.labels)
        self.metrics = MetricsCollector(self.cfg, d.ground_truth, self.catalog)

    def _ingest(self, events: pd.DataFrame) -> pd.DataFrame:
        """Ham olaylar → kimlik çözümleme → veri kalitesi istatistikleri → varlık-gün ve cihaz-gün türevleri (gün sırasıyla).
        Türev yapılar gün gün eklenir ki 'geçmiş yalnızca geçmişten' kuralı toplu koşuda da korunsun."""
        t0 = time.perf_counter()
        ev = events.copy()
        ev["time"] = to_utc_naive(ev["time"])
        ev["received_time"] = to_utc_naive(ev["received_time"])
        ev = self.resolver.resolve(ev)
        if self.honeytokens:
            # tuzak etkileşimi: etiketle; tuzak hesap kullanımını kaynağına (cihaz sahibi → IP kiralaması) atfet
            ev, lost = self.honeytokens.apply(ev, self.profile.owner_of_device, self.resolver.leases, self.resolver.service_sids)
            if len(lost):
                parts = [f for f in (self.honeytoken_unattributed, lost) if len(f)]
                self.honeytoken_unattributed = pd.concat(parts, ignore_index=True)
                self.health.warnings.append(f"tuzak etkileşimi atfedilemedi: {len(lost)} olay (honeytoken_unattributed.csv)")
                LOG.warning("Aldatma katmanı: %d tuzak etkileşimi kimliğe atfedilemedi", len(lost))
        self.health.time("kimlik_eslestirme", t0)
        if ev.empty:
            return ev
        lat = (ev["received_time"] - ev["time"]).dt.total_seconds() / 60
        self.health.data_latency_min = {s: round(float(v), 1) for s, v in lat.groupby(ev["source"]).median().items()}
        t0 = time.perf_counter()
        self.dq.ingest(DataQualityMonitor.daily_stats(ev))
        self.health.time("veri_kalitesi", t0)
        t0 = time.perf_counter()
        feats = extract_features(ev, self.crit)
        device_day = extract_device_day(ev)
        for day in sorted(set(feats["day"]) | set(device_day["day"])):
            self.profile.append(feats[feats["day"] == day], device_day[device_day["day"] == day])
        self.health.time("ozellik_cikarimi", t0)
        return ev

    # ------------------------------------------------------------------ toplu koşu
    def run(self, start: pd.Timestamp, end: pd.Timestamp, warmup_days: int) -> None:
        self.events = self._ingest(self.data.events)
        self.events_by_day = {k: g for k, g in self.events.groupby(self.events["time"].dt.normalize())}
        LOG.info(
            "Hazırlık: %d olay, %d varlık-gün, %d kullanıcı, akran grupları=%s",
            len(self.events),
            len(self.profile.feats),
            self.data.directory.shape[0],
            dict(Counter(self.peers.key_of.values())),
        )

        # Kapsama ölçümü yalnızca DEĞERLENDİRME penceresiyle kesişen senaryolar üzerinden yapılır (ısınma/geçmiş dönemde vaka üretilmez)
        def _overlaps(g: dict) -> bool:
            w = g.get("pencere") or [g.get("baslangic_tarihi"), g.get("olay_tarihi")]
            return pd.Timestamp(w[1]) >= start - 7 * DAY and pd.Timestamp(w[0]) <= end + 7 * DAY

        self.metrics.gt = [g for g in self.metrics.gt if _overlaps(g)]
        self.metrics.eval_range = (start, end)
        # Graf: değerlendirme öncesi geçmiş (uzun pencere) kenarları — akran kıyası için tüm popülasyon (Prensip 2)
        t0 = time.perf_counter()
        for day, ev in self.events_by_day.items():
            if day < start - warmup_days * DAY:
                self.graph_builder.ingest_day(ev)
        self.health.time("graf_olusturma", t0)
        day = start - warmup_days * DAY
        while day <= end:
            self._run_day(day, produce_cases=day >= start)
            day += DAY
        self._write_outputs(end)
        if self.state is not None:
            self.save_state(end)

    # ------------------------------------------------------------------ artımlı koşu (günlük servis)
    def run_incremental(self, day: pd.Timestamp, events: pd.DataFrame, force: bool = False) -> List[dict]:
        """Durumu yükle → günün olaylarını türet → günü işle → budama → durumu kaydet. İdempotent: su seviyesi geçilmiş
        bir gün `force` olmadan yeniden işlenmez."""
        if self.state is None:
            raise RuntimeError("Artımlı koşu için durum deposu (StateStore) gerekir")
        day = pd.Timestamp(day).normalize()
        wm = self.state.watermark
        if wm is not None and day <= wm and not force:
            raise ValueError(f"{day.date()} zaten işlendi (su seviyesi {wm.date()}); yeniden işlemek için force=True")
        self.load_state()
        ev = self._ingest(events)
        ev_day = ev[ev["time"].dt.normalize() == day] if len(ev) else ev
        self.events_by_day = {day: ev_day}
        self.metrics.eval_range = (day, day)
        n_before = len(self.cases)
        self._run_day(day, produce_cases=True)
        cutoff = day - (self.cfg.long_window_days + 7) * DAY
        self.profile.prune(cutoff)
        self.pred.prune(cutoff)
        self.dq.prune(cutoff)
        self.store.prune(cutoff)
        self.save_state(day)
        self._write_outputs(day)
        return self.cases[n_before:]

    # ------------------------------------------------------------------ öğrenen tahmin modeli (11.8 / 14.5 / 14.6)
    def train_prediction_model(self, min_rows: Optional[int] = None, holdout_frac: float = 0.3) -> dict:
        """Tahmin satırları + gerçekleşmeler (etiket deposu; test verisinde cevap anahtarı) ile lojistik model eğitir.
        Zamansal ayrım: günlerin son `holdout_frac` kısmı eğitime girmez; modelin görmediği günlerde kalibrasyon raporlanır.
        Giriş şartı (14.5): en az `supervised_min_labels` satır ve her sınıftan ≥5 örnek; sağlanmazsa model kurulmaz."""
        rows = self.pred.rows
        min_rows = self.cfg.supervised_min_labels if min_rows is None else min_rows
        report: dict = dict(satir=len(rows), esik=min_rows, egitildi=False)
        if len(rows) < min_rows:
            report["neden"] = f"yetersiz satır ({len(rows)} < {min_rows})"
            return report
        labels = self.labels if self.labels.labels else None
        y = np.array(self.metrics.outcomes(rows, labels=labels), dtype=int)
        days = sorted({r["gun"] for r in rows})
        n_hold = max(1, int(round(len(days) * holdout_frac)))
        cut = days[-n_hold] if len(days) > n_hold else days[-1]
        tr = np.array([r["gun"] < cut for r in rows])
        X = rows_to_matrix(rows)
        try:
            model = LogisticModel.fit(X[tr], y[tr])
        except ValueError as exc:
            report["neden"] = str(exc)
            return report
        p_tr, p_ho = model.predict_many(X[tr]), model.predict_many(X[~tr]) if (~tr).any() else np.array([])
        h_ho = np.array([r["p7_sezgisel"] for r, keep in zip(rows, ~tr) if keep])
        report.update(
            egitildi=True,
            kaynak="analist_etiketi" if labels else "cevap_anahtari",
            holdout=dict(baslangic=cut, gun=n_hold, satir=int((~tr).sum()), pozitif=int(y[~tr].sum())),
            egitim=calibration_report(p_tr, y[tr]),
            holdout_model=calibration_report(p_ho, y[~tr]) if len(p_ho) else None,
            holdout_sezgisel=calibration_report(h_ho, y[~tr]) if len(h_ho) else None,
            model=model.to_dict(),
            katsayilar=dict(zip(model.features, [round(c, 3) for c in model.coef])),
        )
        self.pred.model = model
        if self.state is not None:
            self.state.put("prediction_model", model.to_dict())
        (self.out / "prediction_model.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
        )
        return report

    # ------------------------------------------------------------------ durum
    def save_state(self, day: pd.Timestamp) -> None:
        st = self.state
        assert st is not None
        t0 = time.perf_counter()
        st.put_frame("features", self.profile.feats)
        st.put_frame("device_day", self.profile.device_day)
        st.put_frame("dq_daily", self.dq.stats_df)
        st.put("graph_edges", self.store.export_edges())
        st.put("hits", hits_to_records(self.scorer.hit_log))
        st.put("pool", [(d.isoformat(), v) for d, v in self.scorer.pool])
        st.put("last_queued", {sid: d.isoformat() for sid, d in self.scorer.last_queued.items()})
        st.put("risk_series", {sid: {d.isoformat(): v for d, v in s.items()} for sid, s in self.pred.risk_series.items()})
        st.put("final_risk", {sid: {d.isoformat(): v for d, v in s.items()} for sid, s in self.final_risk.items()})
        st.put("pseudonyms", self.pseud.forward)
        st.put("behavioral_conflict", self.peers.behavioral_conflict)
        st.put("queue_history", {d.isoformat(): q for d, q in self.metrics.queue_by_day.items()})
        st.put(
            "alerts_by_sid", {sid: [(d.isoformat(), sorted(r)) for d, r in v] for sid, v in self.metrics.alerts_by_sid.items()}
        )
        st.put("daily_metrics", self.metrics.daily)
        st.put("alert_volume", self.health.alert_volume)
        cutoff = (day - (self.cfg.long_window_days + 7) * DAY).date().isoformat()
        st.put("pred_rows", [r for r in self.pred.rows if r["gun"] >= cutoff])
        if self.pred.model is not None:
            st.put("prediction_model", self.pred.model.to_dict())
        st.set_watermark(day)
        self.health.time("durum_kaydi", t0)
        LOG.info("Durum kaydedildi: %s (su seviyesi %s)", st.path, day.date())

    def load_state(self) -> bool:
        st = self.state
        assert st is not None
        if st.watermark is None:
            return False
        t0 = time.perf_counter()
        feats = st.get_frame("features")
        device_day = st.get_frame("device_day")
        if feats is not None and len(feats):
            self.profile.feats = feats.drop(columns=["peer", "foreign_device_flag"], errors="ignore")
            # türev kolonlar ve yapılar yeniden kurulur (kayıtlı bayraklar korunur)
            self.profile.feats["peer"] = feats["peer"] if "peer" in feats else self.profile.feats["sid"].map(self.peers.key)
            self.profile.feats["foreign_device_flag"] = feats["foreign_device_flag"] if "foreign_device_flag" in feats else 0
            self.profile.by_day = {d: g for d, g in self.profile.feats.groupby("day")}
        if device_day is not None and len(device_day):
            self.profile.device_day = device_day
            for r in device_day.itertuples(index=False):
                if int(r.edr_count) > 0:
                    self.profile.edr_days[r.device].add(pd.Timestamp(r.day))
                if r.ad_users:
                    self.profile.ad_users_on_device[(r.device, pd.Timestamp(r.day))] = set(r.ad_users)
            self.profile._account_device_rows(device_day)
            self.profile._refresh_shared_devices()
        dq = st.get_frame("dq_daily")
        if dq is not None and len(dq):
            self.dq.ingest(dq)
        self.store.import_edges(st.get("graph_edges", []))
        self.scorer.hit_log = defaultdict(list, hits_from_records(st.get("hits", []), Hit))
        self.scorer.pool = deque((pd.Timestamp(d), v) for d, v in st.get("pool", []))
        self.scorer.last_queued = {sid: pd.Timestamp(d) for sid, d in st.get("last_queued", {}).items()}
        self.pred.risk_series = defaultdict(
            dict, {sid: {pd.Timestamp(d): v for d, v in s.items()} for sid, s in st.get("risk_series", {}).items()}
        )
        self.final_risk = defaultdict(
            dict, {sid: {pd.Timestamp(d): v for d, v in s.items()} for sid, s in st.get("final_risk", {}).items()}
        )
        self.pseud.forward = dict(st.get("pseudonyms", {}))
        self.pseud.reverse = {p: s for s, p in self.pseud.forward.items()}
        self.peers.behavioral_conflict = dict(st.get("behavioral_conflict", {}))
        self.metrics.queue_by_day = {pd.Timestamp(d): q for d, q in st.get("queue_history", {}).items()}
        self.metrics.alerts_by_sid = defaultdict(
            list, {sid: [(pd.Timestamp(d), set(r)) for d, r in v] for sid, v in st.get("alerts_by_sid", {}).items()}
        )
        self.metrics.daily = list(st.get("daily_metrics", []))
        self.health.alert_volume = dict(st.get("alert_volume", {}))
        self.pred.rows = list(st.get("pred_rows", []))
        model = st.get("prediction_model")
        if model:
            try:
                self.pred.model = LogisticModel.from_dict(model)
            except ValueError as exc:  # sürüm uyumsuz model kullanılmaz; sezgisel model devam eder (geri alınabilirlik, 14.6)
                LOG.warning("Tahmin modeli yüklenmedi: %s", exc)
        self.health.time("durum_yukleme", t0)
        LOG.info("Durum yüklendi: %s (su seviyesi %s, %d varlık-gün)", st.path, st.watermark.date(), len(self.profile.feats))
        return True

    def _run_day(self, day: pd.Timestamp, produce_cases: bool) -> None:
        cfg = self.cfg
        ev_day = self.events_by_day.get(day)
        if ev_day is None:
            ev_day = pd.DataFrame(columns=EVENT_COLUMNS)
        # 1) veri kalitesi
        t0 = time.perf_counter()
        dq = self.dq.assess(day)
        self.dq_last = dq
        self.health.time("veri_kalitesi", t0)
        # 2) graf oluşturma (düşük maliyet, tüm kullanıcılar)
        t0 = time.perf_counter()
        self.graph_builder.ingest_day(ev_day)
        self.health.time("graf_olusturma", t0)
        # 3) UEBA: baseline + sinyaller + tespitler
        t0 = time.perf_counter()
        self.pred.bind_features(self.profile.feats)
        ctx = self.profile.context(day)
        today = self.profile.today(day)
        signals, explains, evidences, hits_today = {}, {}, {}, {}
        for _, row in today.iterrows():
            sid = row["sid"]
            s, ex, evid = self.profile.signals(ctx, row)
            signals[sid], explains[sid], evidences[sid] = s, ex, evid
            if s.get("zehirleme_suphesi"):
                self.metrics.flags[sid].add("zehirleme_suphesi")
            hits_today[sid] = self.engine.evaluate(
                day, sid, self.pseud.pseudo(sid), s, evid, dq, ("UEBA", "veri-kalitesi", "aldatma"), ex
            )
        self.health.time("ueba", t0)
        # 4) Prediction: geçici günlük risk (UEBA) → yörünge/rejim sinyalleri → prediction tespitleri
        t0 = time.perf_counter()
        results: Dict[str, RiskResult] = {}
        for sid in signals:
            self.scorer.add_hits(sid, hits_today[sid])
            prov = self.scorer.compute(sid, day, signals[sid])
            # risk serisine GÜNÜN taze UEBA sinyali yazılır (7 günlük pencere/bozunum değil): yörünge yeni kanıtla ölçülür
            self.pred.record_risk(sid, day, sum(h.weight * h.severity for h in prov.hits if h.day == day))
            cur_pct = float(np.searchsorted(np.sort([v for _, v in self.scorer.pool]), prov.raw) / max(1, len(self.scorer.pool)))
            ps, pex, pev = self.pred.signals(sid, day, signals[sid], ctx, cur_pct)
            signals[sid].update(ps)
            explains[sid].update(pex)
            evidences[sid].update(pev)
            ph = self.engine.evaluate(
                day, sid, self.pseud.pseudo(sid), signals[sid], evidences[sid], dq, ("Prediction",), explains[sid]
            )
            hits_today[sid].extend(ph)
            self.scorer.add_hits(sid, ph)
            results[sid] = self.scorer.compute(sid, day, signals[sid])
            self.final_risk[sid][day] = results[sid].raw
        self.health.time("prediction", t0)
        # 5) kalibrasyon + alarm bütçesi
        t0 = time.perf_counter()
        self.scorer.calibrate(day, results)
        queue = self.scorer.select_queue(day, results)
        self.health.time("skorlama", t0)
        self.health.rule_errors = self.engine.errors
        self.health.profile_fresh[str(day.date())] = f"baseline {len(ctx.p_med)} kullanıcı, pencere {cfg.long_window_days}g"
        if not produce_cases:
            return
        # 6) derin graf analizi (yalnızca riskli alt küme) → ilişkisel tespitler → birleşik skor → vaka
        t0 = time.perf_counter()
        risky = set(queue)
        cases_today = []
        for sid in queue:
            r = results[sid]
            gf, gsig = self.deep.analyze(sid, day, risky, [h for h in r.hits if h.day == day], self.pseud.pseudo)
            signals[sid].update(gsig)
            rel_hits = self.engine.evaluate(
                day,
                sid,
                self.pseud.pseudo(sid),
                signals[sid],
                {"graf": [f"graf:{sid[-6:]}@{day.date()}"]},
                dq,
                ("iliskisel",),
                explains[sid],
            )
            if rel_hits:
                self.scorer.add_hits(sid, rel_hits)
                r = self.scorer.compute(sid, day, signals[sid])
                r.percentile, r.critical = results[sid].percentile, results[sid].critical
                results[sid] = r
            cases_today.append(self._build_case(sid, day, r, gf, signals[sid], explains[sid], evidences[sid]))
        self.health.time("derin_graf_ve_rapor", t0)
        self.health.record_volume(day, len(queue))
        self.metrics.record_day(
            day, results, queue, len([s for s in self.engine.suppressed_log if s["gun"] == str(day.date())]), len(ev_day)
        )
        self._write_queue(day, cases_today, dq)
        for sink in self.sinks:  # 17.6 SOAR / ticketing entegrasyonu — takma adlı vaka, gerçek kimlik gönderilmez
            for c in cases_today:
                sink.emit({k: v for k, v in c.items() if k not in ("_sid", "rapor")})
        LOG.info(
            "%s: aktif=%d tespitli=%d kuyruk=%d kritik=%d askıda_kaynak=%s",
            day.date(),
            len(results),
            sum(1 for r in results.values() if r.raw > 0),
            len(queue),
            sum(1 for s in queue if results[s].critical),
            [k for k, v in dq.items() if v["durum"] == "askida"],
        )

    # ------------------------------------------------------------------
    def _counterfactual(self, sid: str, day: pd.Timestamp, r: RiskResult, gf: GraphFindings, s: dict) -> List[dict]:
        """ "Bu kanıt olmasaydı risk kaç olurdu?" — her kural için skor yeniden hesaplanır.

        Toplamsal katkı listesi (`tespitler[].katki`) bunu gösteremez, çünkü skor ÇARPIMSALDIR: bir tespiti
        çıkarmak kendi puanını düşürmekle kalmaz, tetiklediği farklı-taktik (×2,5) ya da 3-tespit (×2,0)
        çarpanını da düşürebilir. Skorlama koduna dokunulmaz: donmuş `RiskScorer.compute` aynı kalır, yalnız
        o kullanıcının tespit geçmişi geçici olarak süzülüp çağrılır.

        Yüzdelik, günün havuzuyla (bu kullanıcının kendi skoru dahil) yaklaşık hesaplanır; amaç sıralama değil,
        analiste hangi kanıtın vakayı taşıdığını göstermektir."""
        cfg = self.cfg
        pool = np.sort(np.array([v for _, v in self.scorer.pool], dtype=float)) if self.scorer.pool else np.array([])

        def risk_of(raw: float) -> float:
            pct = float(np.searchsorted(pool, raw, side="left") / len(pool)) if len(pool) else 0.0
            return 100.0 * (cfg.fusion_temporal_weight * pct + cfg.fusion_structural_weight * gf.structural_score)

        base_risk = risk_of(r.raw)
        saved = self.scorer.hit_log[sid]
        out: List[dict] = []
        for rid in sorted({h.rule_id for h in r.hits}):
            self.scorer.hit_log[sid] = [h for h in saved if h.rule_id != rid]
            try:
                alt = self.scorer.compute(sid, day, s)
            finally:
                self.scorer.hit_log[sid] = saved
            out.append(
                dict(
                    kural=rid,
                    ham_olmadan=round(alt.raw, 1),
                    ham_dusus_yuzde=int(round(100 * (r.raw - alt.raw) / r.raw)) if r.raw else 0,
                    risk_olmadan=int(round(risk_of(alt.raw))),
                    risk_dusus=int(round(base_risk - risk_of(alt.raw))),
                    kaybolan_carpanlar=sorted(set(r.multipliers) - set(alt.multipliers)),
                )
            )
        # Sıralama ham skordaki düşüşe göre: yüzdelik üst uçta doygundur (kurumun en riskli kullanıcısında
        # kanıt çıkarmak yüzdeliği az oynatır), ham skor ise kanıtın gerçek ağırlığını gösterir.
        return sorted(out, key=lambda d: -d["ham_dusus_yuzde"])

    def _confidence(self, sid: str, day: pd.Timestamp, s: dict, dq: dict) -> dict:
        """Skorun yanında GÜVEN: 'risk 82' ile 'risk 82, güven düşük' aynı şey değildir.

        Düşüren etkenler: askıya alınmış kaynak (o gün o telemetri yok), kısa kişisel profil (baseline oturmamış),
        küçük akran grubu (karşılaştırma zayıf), zehirleme şüphesi (kısa pencere uzun pencereden kopmuş).
        Mimarideki veri kalitesi katmanı kuralı tamamen susturur; bu alan ise susturulmayan vakanın ne kadar
        sağlam zemine bastığını analiste söyler (9. madde)."""
        reasons: List[str] = []
        askida = [k for k, v in (dq or {}).items() if v.get("durum") == "askida"]
        if askida:
            reasons.append(f"askıda kaynak: {', '.join(sorted(askida))}")
        profil = int(s.get("profil_gun", 0) or 0)
        if profil < 30:
            reasons.append(f"kişisel profil {profil} gün (<30)")
        akran = sum(1 for v in self.peers.key_of.values() if v == self.peers.key(sid))
        if akran and akran < self.cfg.min_peer_group:
            reasons.append(f"akran grubu {akran} kişi (<{self.cfg.min_peer_group})")
        if s.get("zehirleme_suphesi"):
            reasons.append("zehirleme şüphesi: 7g medyanı 90g'den kopuk")
        seviye = "yuksek" if not reasons else ("dusuk" if len(reasons) >= 2 or askida else "orta")
        return dict(seviye=seviye, nedenler=reasons)

    def _build_case(self, sid: str, day: pd.Timestamp, r: RiskResult, gf: GraphFindings, s: dict, ex: dict, evid: dict) -> dict:
        cfg = self.cfg
        pseudo = self.pseud.pseudo(sid)
        u = self.data.directory.set_index("sid").loc[sid]
        combined = 100.0 * (cfg.fusion_temporal_weight * r.percentile + cfg.fusion_structural_weight * gf.structural_score)
        prev_raw = self.final_risk[sid].get(day - 7 * DAY, 0.0)
        delta = int(round(100 * (r.raw - prev_raw) / max(r.raw, prev_raw, 1.0)))
        hits = []
        for h in sorted(r.hits, key=lambda h: -r.contributions.get(f"{h.rule_id}@{h.day.date()}", 0)):
            hits.append(
                dict(
                    kural=h.rule_id,
                    ad=h.ad,
                    katman=h.katman,
                    gun=str(h.day.date()),
                    siddet=round(h.severity, 3),
                    agirlik=h.weight,
                    katki=round(r.contributions.get(f"{h.rule_id}@{h.day.date()}", 0), 2),
                    kanit=h.evidence,
                    attack=h.attack,
                    aciklama=h.aciklama or describe_hit(h, ex),
                    runbook=h.runbook,
                )
            )
        counterfactual = self._counterfactual(sid, day, r, gf, s)
        timeline = []
        if ex.get("rejim_degisimi"):
            timeline.append(f"{s.get('rejim_degisim_gun')} gün önce — {ex['rejim_degisimi']}")
        if ex.get("yetki_artisi"):
            timeline.append(f"yetki — {ex['yetki_artisi']}")
        if ex.get("sessizlik"):
            timeline.append(f"sessizlik — {ex['sessizlik']}")
        for h in sorted(r.hits, key=lambda h: h.day):
            timeline.append(f"{(day - h.day).days} gün önce — {h.ad}" if h.day != day else f"bugün — {h.ad}")
        seen = set()
        timeline = [t for t in timeline if not (t in seen or seen.add(t))][:8]
        case = dict(
            case_id=f"C-{day.strftime('%Y%m%d')}-{pseudo[2:]}",
            musteri=cfg.tenant_id,
            gun=str(day.date()),
            kullanici=pseudo,
            _sid=sid,
            departman=str(u["dept"]),
            risk=int(round(combined)),
            delta_7g=delta,
            yuzdelik=round(r.percentile, 4),
            ham_skor=round(r.raw, 2),
            yapisal_skor=gf.structural_score,
            kritik=bool(r.critical),
            carpanlar=r.multipliers,
            tespitler=hits,
            baglam={k: v for k, v in ex.items() if k not in ("tahmin_7g",)},
            tahmin_7g=ex.get("tahmin_7g", dict(olasilik=s.get("tahmin_7g_olasilik", 0), bilesenler={})),
            graf=dict(
                cihazlar=gf.devices,
                paylasilan_cihazlar=gf.shared_devices,
                kritik_yollar=gf.paths_to_critical,
                etki_alani=gf.blast_radius,
                ortak_noktalar=gf.common_points,
                teknikler=gf.techniques,
            ),
            karsit_olgu=counterfactual,
            guven=self._confidence(sid, day, s, self.dq_last),
            zaman_cizelgesi=timeline,
            kanit_serileri={k: v for k, v in evid.items() if k in ("risk_serisi", "rejim", "yetki", "silence")},
            mudahale=tiered_response(combined, r.critical),
        )
        if self.llm.kb:
            case["attack_baglami"] = [
                dict(teknik=p.technique, ad=p.name, taktik=p.tactic, ozet=p.summary, onlem=p.mitigations, kaynak=p.source)
                for p in self.llm.kb.retrieve(t for h in hits for t in h["attack"])
            ]
        summary = self.llm.summarize(case)
        case["ozet"], case["ozet_kaynagi"], case["guvenlik"] = summary.text, summary.source, summary.security
        case["rapor"] = TemplateReporter.render(case)
        self.cases.append(case)
        with open(self.out / "cases" / f"{case['case_id']}.json", "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in case.items() if k != "_sid"}, f, ensure_ascii=False, indent=2, default=_json_default)
        return case

    def _write_queue(self, day: pd.Timestamp, cases: List[dict], dq: dict) -> None:
        with open(self.out / f"queue_{day.date()}.txt", "w", encoding="utf-8") as f:
            f.write(
                f"İNCELEME KUYRUĞU — {self.cfg.tenant_id} — {day.date()} — bütçe {self.cfg.alarm_budget_per_day}, kuyruk {len(cases)}\n"
            )
            f.write("Veri kalitesi: " + ", ".join(f"{k}={v['durum']}" for k, v in dq.items()) + "\n\n")
            for c in cases:
                f.write(c["rapor"] + "\n\n")

    def _write_outputs(self, last_day: pd.Timestamp) -> None:
        summ = self.metrics.summary(
            self.labels, self.engine.shadow_log, self.engine.suppressed_log, self.engine, last_day, prediction_rows=self.pred.rows
        )
        summ["llm"] = dict(cagri=self.llm.calls, token=self.llm.tokens, backend=self.cfg.llm_backend)
        summ["kimlik_eslestirme"] = dict(cozumsuz=self.resolver.unresolved_by_source, kuyruk=len(self.resolver.unresolved_queue))
        (self.out / "metrics.json").write_text(
            json.dumps(summ, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
        )
        (self.out / "health.json").write_text(
            json.dumps(self.health.snapshot(self.dq_last), ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
        )
        (self.out / "coverage_report.json").write_text(
            json.dumps(summ["kapsama"]["detay"], ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
        )
        with open(self.out / "shadow_log.jsonl", "w", encoding="utf-8") as f:
            for s in self.engine.shadow_log:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        with open(self.out / "suppressed.jsonl", "w", encoding="utf-8") as f:
            for s in self.engine.suppressed_log:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        self.resolver.unresolved_queue.to_csv(self.out / "unresolved_identity_queue.csv", index=False)
        if self.honeytokens:  # kaybolan tuzak kanıtı yoktur: atfedilemeyen etkileşimler analist kuyruğuna dosya olarak düşer
            self.honeytoken_unattributed.to_csv(self.out / "honeytoken_unattributed.csv", index=False)
        # 20.1 erişim ayrımı: gerçek kimlik eşlemesi ayrı, kısıtlı dosyada (üretimde ayrı yetki alanı / vault)
        vault = {
            p: dict(sid=s, display_name=str(self.data.directory.set_index("sid").loc[s, "display_name"]))
            for s, p in self.pseud.forward.items()
        }
        (self.out / "identity_vault.RESTRICTED.json").write_text(
            json.dumps(vault, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._print_summary(summ)

    def _print_summary(self, summ: dict) -> None:
        print("\n" + "=" * 100)
        print(f"ÇALIŞMA ÖZETİ — müşteri {self.cfg.tenant_id} — çıktı dizini: {self.out}")
        print("=" * 100)
        print(
            f"Vaka hacmi: toplam {summ['vaka_hacmi']['toplam']} / {summ['vaka_hacmi']['gun']} gün (günlük ort. {summ['vaka_hacmi']['gunluk_ort']}, bütçe {summ['vaka_hacmi']['butce']})"
        )
        print(
            f"Gölge mod uyarıları: {summ['golge_mod']['uyari']} (analiste iletilmedi)  |  Bastırılan: {summ['bastirma']['bastirilan']} (oran {summ['bastirma']['oran']})"
        )
        print(f"Kimlik: çözümlenemeyen={summ['kimlik_eslestirme']['cozumsuz']}  |  LLM: {summ['llm']}")
        print(
            f"Kural sağlığı: devre dışı={list(summ['kural_sagligi']['devre_disi'])} 30g tetiklenmeyen={summ['kural_sagligi']['gun30_tetiklenmeyen']} DQ askıda atlanan={summ['kural_sagligi']['dq_askida_atlanan']}"
        )
        print(f"Bileşen katkısı (skor payı): {summ['bilesen_katkisi']}")
        cal = summ.get("tahmin_kalibrasyonu")
        if cal:
            for k in ("sezgisel", "model"):
                if k in cal:
                    c = cal[k]
                    print(
                        f"Tahmin kalibrasyonu ({k}, {cal['kaynak']}): n={c['n']} pozitif={c['pozitif']} Brier={c['brier']} "
                        f"(taban {c['brier_taban']}, beceri {c['brier_beceri']}) AUC={c['auc']} ECE={c['ece']}"
                    )
        lp = summ.get("etiketli_veri_precision")
        if lp:
            print(
                f"Etiketli veri precision@N: {lp['precision_at_n']} ({lp['dogru']} doğru / {lp['kuyruk_varlik_gun']} kuyruk varlık-günü; {lp['insider_sayisi']} bilinen insider)"
                f" | sıralı prefiks: "
                + ", ".join(f"{k}={lp[k]}" for k in ("precision@1", "precision@3", "precision@5", "precision@10"))
                + f" | kullanıcı bazında: {lp['kullanici_bazinda']}"
            )
        if summ["kapsama"]["senaryo"]:
            print(f"\nKAPSAMA (19.6): {summ['kapsama']['tespit']}/{summ['kapsama']['senaryo']} pozitif senaryo yakalandı")
            detay = summ["kapsama"]["detay"]
            if len(detay) > 12:  # CERT gibi çok örnekli setlerde senaryo tipine göre özet
                agg = defaultdict(lambda: Counter())
                erk = defaultdict(list)
                for c in detay:
                    key = c["senaryo"].rsplit("-", 1)[0]
                    agg[key][("KISMİ" if "kısmi pencere" in c["sonuc"] else c["sonuc"].split(" ")[0])] += 1
                    if c["erkenlik_gun"] is not None:
                        erk[key].append(c["erkenlik_gun"])
                for key, cnt in sorted(agg.items()):
                    n = sum(cnt.values())
                    print(
                        f"  {key:<22} n={n:<3} "
                        + " ".join(f"{k}={v}" for k, v in sorted(cnt.items()))
                        + (f"  erkenlik(gün) medyan={np.median(erk[key]):.0f}" if erk[key] else "")
                    )
                for c in detay:
                    if c["sonuc"].startswith("GEÇTİ"):
                        print(f"    ✓ {c['senaryo']:<34} kuyruk={c['gercek_sonuc']} erkenlik={c['erkenlik_gun']}")
            else:
                for c in detay:
                    print(
                        f"  {c['sonuc']:<48} {c['senaryo']:<40} beklenen={c['beklenen_tespit']} gerçek={c['gercek_sonuc']} erkenlik={c['erkenlik_gun']} bayrak={c['bayraklar']}"
                    )
        print(f"\nSağlık uyarıları: {self.health.warnings or 'yok'}")
        print(f"Katman süreleri (sn): {dict((k, round(v, 1)) for k, v in self.health.layer_time.items())}")
        print(
            "\nHatırlatma: precision@N ve analist mutabakatı ETİKET gerektirir → --label ile vaka kapatın; recall üretim hedefi değildir (1.3)."
        )
