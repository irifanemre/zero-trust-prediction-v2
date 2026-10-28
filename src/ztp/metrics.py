"""Sistem sağlığı (17.5) ve ölçüm (1.3 / 19.4 / 19.6): kapsama, erkenlik, precision@k, kural sağlığı, bileşen katkısı."""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from ztp.config import TenantConfig
from ztp.detection.engine import DetectionEngine
from ztp.feedback import LabelStore
from ztp.prediction_model import calibration_report
from ztp.schema import DAY
from ztp.scoring import RiskResult
from ztp.stats import mad, robust_z


class HealthMonitor:
    """En tehlikeli başarısızlık modu: sistemin sessizce durup 'olay yok' görünmesi — uyarı hacmi bir sağlık metriğidir."""

    def __init__(self):
        self.layer_time: Dict[str, float] = defaultdict(float)
        self.alert_volume: Dict[str, int] = {}
        self.rule_errors: Counter = Counter()
        self.data_latency_min: Dict[str, float] = {}
        self.profile_fresh: Dict[str, str] = {}
        self.warnings: List[str] = []

    def time(self, layer: str, t0: float) -> None:
        self.layer_time[layer] += time.perf_counter() - t0

    def record_volume(self, day: pd.Timestamp, n: int) -> None:
        self.alert_volume[str(day.date())] = n
        # referans: haftanın aynı günleri (hafta sonu düşüşü sistem durması değildir); yoksa son 7 gün
        hist = [
            self.alert_volume[str((day - 7 * k * DAY).date())]
            for k in range(1, 5)
            if str((day - 7 * k * DAY).date()) in self.alert_volume
        ]
        if len(hist) >= 2:  # ilk hafta referans yok — uyarı üretilmez
            z = robust_z(n, float(np.median(hist)), mad(hist), 1.0)
            if z < -3 and n < 0.5 * float(np.median(hist)):
                self.warnings.append(
                    f"{day.date()}: uyarı hacmi ani düştü ({n} vs referans medyan {np.median(hist):.0f}) — sistem durmuş olabilir"
                )

    def snapshot(self, dq_last: dict) -> dict:
        return dict(
            katman_sureleri_sn={k: round(v, 2) for k, v in self.layer_time.items()},
            uyari_hacmi=self.alert_volume,
            kural_hatalari=dict(self.rule_errors),
            veri_gecikmesi_dk=self.data_latency_min,
            profil_guncelligi=self.profile_fresh,
            son_veri_kalitesi=dq_last,
            uyarilar=self.warnings,
        )


class MetricsCollector:
    def __init__(self, cfg: TenantConfig, ground_truth: List[dict], catalog: List[dict]):
        self.cfg, self.gt, self.catalog = cfg, ground_truth, catalog
        self.daily: List[dict] = []
        self.first_alert: Dict[str, Tuple[pd.Timestamp, List[str]]] = {}
        self.alerts_by_sid: Dict[str, List[Tuple[pd.Timestamp, Set[str]]]] = defaultdict(list)
        self.rule_hits: Counter = Counter()
        self.rule_last_hit: Dict[str, pd.Timestamp] = {}
        self.contrib: Counter = Counter()
        self.total_hits = 0
        self.flags: Dict[str, Set[str]] = defaultdict(set)
        self.hits_by_sid: Dict[str, List[Tuple[pd.Timestamp, str]]] = defaultdict(list)  # kuyruğa girmese de tetiklenen
        self.queue_by_day: Dict[pd.Timestamp, List[str]] = {}
        self.eval_range: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None

    def record_day(
        self, day: pd.Timestamp, results: Dict[str, RiskResult], queue: List[str], suppressed: int, total_events: int
    ) -> None:
        crit = sum(1 for s in queue if results[s].critical)
        self.queue_by_day[day] = list(queue)
        self.daily.append(
            dict(
                gun=str(day.date()),
                aktif_kullanici=len(results),
                tespitli=sum(1 for r in results.values() if r.raw > 0),
                kuyruk=len(queue),
                butce=self.cfg.alarm_budget_per_day,
                kritik=crit,
                bastirilan=suppressed,
                olay=total_events,
            )
        )
        for sid in queue:
            r = results[sid]
            rules = {h.rule_id for h in r.hits}
            self.alerts_by_sid[sid].append((day, rules))
            self.first_alert.setdefault(sid, (day, sorted(rules)))
            for k, v in r.contributions.items():
                self.contrib[k.split("@")[0]] += v
        for r in results.values():
            for h in r.hits:
                if h.day == day:
                    self.rule_hits[h.rule_id] += 1
                    self.rule_last_hit[h.rule_id] = day
                    self.total_hits += 1
                    self.hits_by_sid[r.sid].append((day, h.rule_id))

    @staticmethod
    def _window(g: dict, grace_days: int = 7) -> Tuple[pd.Timestamp, pd.Timestamp]:
        """Senaryo penceresi: [başlangıç − 7g, bitiş + 7g] dışındaki uyarılar tespit sayılmaz (yanlış pozitiftir)."""
        w = g.get("pencere") or [g.get("baslangic_tarihi"), g.get("olay_tarihi")]
        return pd.Timestamp(w[0]) - grace_days * DAY, pd.Timestamp(w[1]) + grace_days * DAY

    def labeled_precision(self) -> Optional[dict]:
        """19.4: etiketli test verisinde (CERT cevap anahtarı / sentetik senaryolar) kuyruğa giren her varlık-gün için
        otomatik doğruluk. Üretimde bu ölçüm analist etiketiyle yapılır; burada cevap anahtarı 'etiket' rolündedir."""
        if not self.gt:
            return None
        windows = defaultdict(list)
        for g in self.gt:
            if not g.get("negatif"):
                windows[g["sid"]].append(self._window(g))
        tp = fp = 0
        by_day = defaultdict(lambda: [0, 0])
        for sid, alerts in self.alerts_by_sid.items():
            for d, _ in alerts:
                hit = any(a <= d <= b for a, b in windows.get(sid, []))
                tp += hit
                fp += not hit
                by_day[str(d.date())][0 if hit else 1] += 1
        n = tp + fp
        # precision@k: kuyruk sıralı olduğundan ilk k'nın doğruluğu (farklı analist kapasiteleri için)
        at_k = {}
        for k in (1, 3, 5, 10):
            t = f = 0
            for day, ranked in self.queue_by_day.items():
                for sid in ranked[:k]:
                    hit = any(a <= day <= b for a, b in windows.get(sid, []))
                    t += hit
                    f += not hit
            at_k[f"precision@{k}"] = round(t / (t + f), 3) if (t + f) else None
        users_q = set(self.alerts_by_sid)
        users_tp = {
            sid for sid in users_q if any(a <= d <= b for d, _ in self.alerts_by_sid[sid] for a, b in windows.get(sid, []))
        }
        return dict(
            kuyruk_varlik_gun=n,
            dogru=tp,
            yanlis=fp,
            precision_at_n=round(tp / n, 3) if n else None,
            **at_k,
            kullanici_bazinda=dict(
                kuyruga_giren_kullanici=len(users_q),
                insider=len(users_tp),
                precision=round(len(users_tp) / len(users_q), 3) if users_q else None,
            ),
            insider_sayisi=len(windows),
            gunluk={k: dict(dogru=v[0], yanlis=v[1]) for k, v in sorted(by_day.items())},
        )

    def coverage(self) -> List[dict]:
        """19.6 Saldırı simülasyonu kaydı: teknik, kaynak, beklenen tespit, gerçek sonuç, erkenlik, sonuç."""
        rows = []
        for g in self.gt:
            sid = g["sid"]
            w0, w1 = self._window(g)
            alerts = [(d, r) for d, r in self.alerts_by_sid.get(sid, []) if w0 <= d <= w1]
            fired = set().union(*(r for _, r in alerts)) if alerts else set()
            first = min((d for d, _ in alerts), default=None)
            inc = pd.Timestamp(g["olay_tarihi"])
            expected = set(g.get("beklenen", []))
            if g.get("negatif"):
                # negatif kontrol: olay gününde/sonrasında kuyruğa girmemeli
                bad = [d for d, _ in alerts if d >= pd.Timestamp(g["baslangic_tarihi"])]
                rows.append(
                    dict(
                        senaryo=g["senaryo"],
                        aktor=g["aktor"],
                        teknikler=g["teknikler"],
                        veri_kaynagi=g["veri_kaynagi"],
                        beklenen_tespit="(hiçbiri — negatif kontrol)",
                        gercek_sonuc=("tetiklendi" if bad else "tetiklenmedi"),
                        erkenlik_gun=None,
                        sonuc=("KALDI (yanlış pozitif)" if bad else "GEÇTİ"),
                        bayraklar=sorted(self.flags.get(sid, [])),
                    )
                )
                continue
            hit_exp = expected & fired
            all_fired = {r for d, r in self.hits_by_sid.get(sid, []) if w0 <= d <= w1}
            first_hit = min((d for d, r in self.hits_by_sid.get(sid, []) if r in expected and w0 <= d <= w1), default=None)
            earliness = int((inc - first).days) if first is not None else None
            partial = ""
            if self.eval_range and (w0 + 7 * DAY < self.eval_range[0] or w1 - 7 * DAY > self.eval_range[1]):
                partial = " [kısmi pencere: senaryonun bir kısmı değerlendirme dönemi dışında]"
            if expected & all_fired and not hit_exp:
                sonuc = "BÜTÇE DIŞI (beklenen tespit tetiklendi, kuyruğa girmedi)"
                earliness = int((inc - first_hit).days) if first_hit is not None else earliness
            elif not alerts:
                sonuc = "KALDI (tetiklenmedi)"
            elif expected and not hit_exp:
                sonuc = "REVİZYON GEREKLİ (kuyruğa girdi ama beklenen kural değil)"
            else:
                sonuc = "GEÇTİ"
            sonuc += partial if not sonuc.startswith("GEÇTİ") else ""
            rows.append(
                dict(
                    senaryo=g["senaryo"],
                    aktor=g["aktor"],
                    teknikler=g["teknikler"],
                    veri_kaynagi=g["veri_kaynagi"],
                    beklenen_tespit=sorted(expected),
                    gercek_sonuc=("kuyruk: " + ", ".join(sorted(fired))) if fired else "kuyruğa girmedi",
                    tetiklenen_tum_kurallar=sorted(all_fired),
                    ilk_uyari=str(first.date()) if first is not None else None,
                    olay_tarihi=str(inc.date()),
                    erkenlik_gun=earliness,
                    sonuc=sonuc,
                    bayraklar=sorted(self.flags.get(sid, [])),
                )
            )
        return rows

    def outcomes(self, rows: List[dict], horizon_days: int = 7, labels: Optional[LabelStore] = None) -> List[int]:
        """Her tahmin satırı için gerçekleşme: kullanıcı [gün, gün+ufuk] içinde doğrulanmış vakaya konu oldu mu?
        Etiketli test verisinde cevap anahtarı penceresi (aktif senaryo), üretimde analistin 'gerçek_pozitif' etiketi kullanılır."""
        windows = defaultdict(list)
        if labels is not None and labels.labels:
            for lab in labels.labels:
                if lab["karar"] == "gercek_pozitif" and lab.get("sid"):
                    d = pd.Timestamp(lab["gun"])
                    windows[lab["sid"]].append((d, d))
        else:
            for g in self.gt:
                if not g.get("negatif"):
                    w = g.get("pencere") or [g.get("baslangic_tarihi"), g.get("olay_tarihi")]
                    windows[g["sid"]].append((pd.Timestamp(w[0]), pd.Timestamp(w[1])))
        out = []
        for r in rows:
            d = pd.Timestamp(r["gun"])
            out.append(int(any(a <= d + horizon_days * DAY and b >= d for a, b in windows.get(r["sid"], []))))
        return out

    def rule_matrix(self, engine: DetectionEngine, last_day: pd.Timestamp) -> List[dict]:
        """Kural sağlığı ve kapsama matrisi (r5.2 dersi): 22 kuralın yarısı hiç tetiklenmiyor, ama rapor bunu
        "kural var" diye gösteriyordu. Her kural için ayrı ayrı: kaç kez tetiklendi, kaç KUYRUĞA GİREN vakaya
        katıldı, bunların kaçı gerçek (etiketli veride cevap anahtarı penceresi), gerektirdiği telemetri ve
        **doğrulama durumu**. Böylece sınanmamış kural "çalışıyor" diye sunulmaz.

        Durumlar: `dogrulandi` (en az bir gerçek vakaya katıldı) · `kismen` (tetiklendi ama hiç gerçek vakaya
        katılmadı) · `sinanmadi` (hiç tetiklenmedi; nedeni ayrıca yazılır)."""
        windows = {g["sid"]: [] for g in self.gt if not g.get("negatif")}
        for g in self.gt:
            if not g.get("negatif"):
                windows[g["sid"]].append(self._window(g))
        tp_cases: Counter = Counter()
        fp_cases: Counter = Counter()
        for sid, alerts in self.alerts_by_sid.items():
            for day, rules in alerts:
                real = any(a <= day <= b for a, b in windows.get(sid, []))
                for rid in rules:
                    (tp_cases if real else fp_cases)[rid] += 1
        by_id = {r["id"]: r for r in self.catalog}
        out: List[dict] = []
        for rid in sorted(by_id):
            rule = by_id[rid]
            hits = int(self.rule_hits.get(rid, 0))
            tp, fp = int(tp_cases.get(rid, 0)), int(fp_cases.get(rid, 0))
            if tp:
                durum, neden = "dogrulandi", ""
            elif hits:
                durum, neden = "kismen", "tetiklendi, hiç gerçek vakaya katılmadı"
            else:
                durum = "sinanmadi"
                neden = (
                    engine.disabled.get(rid)
                    or ("gölge modda" if rule.get("durum") == "golge-modda" else "")
                    or (f"kaynak askıda kaldı ({engine.skipped_dq[rid]} gün)" if engine.skipped_dq.get(rid) else "")
                    or "bu veride desen görülmedi"
                )
            last = self.rule_last_hit.get(rid)
            out.append(
                dict(
                    kural=rid,
                    katman=rule["katman"],
                    yasam_dongusu=rule["durum"],
                    tetiklenme=hits,
                    vaka_gercek=tp,
                    vaka_yanlis=fp,
                    katki_payi=round(self.contrib.get(rid, 0.0) / (sum(self.contrib.values()) or 1.0), 4),
                    son_tetiklenme=str(last.date()) if last is not None else None,
                    gun_once=(last_day - last).days if last is not None else None,
                    gerekli_telemetri=list(rule["veri_kaynaklari"]),
                    dogrulama=durum,
                    not_=neden,
                )
            )
        return out

    @staticmethod
    def _matrix_summary(matrix: List[dict]) -> dict:
        """Tek bakışta: kaç kural gerçekten doğrulandı, kaçı yalnız gürültü üretti, kaçı hiç sınanmadı (ve neden)."""
        c = Counter(r["dogrulama"] for r in matrix)
        nedenler = Counter(r["not_"].split(" (")[0] for r in matrix if r["dogrulama"] == "sinanmadi")
        return dict(
            kural=len(matrix),
            dogrulandi=c["dogrulandi"],
            kismen=c["kismen"],
            sinanmadi=c["sinanmadi"],
            sinanmama_nedeni=dict(nedenler),
        )

    def prediction_calibration(self, rows: List[dict], labels: Optional[LabelStore] = None) -> Optional[dict]:
        """19.4/19.5: 7 günlük olasılığın kalibrasyonu (Brier, beceri skoru, AUC, güvenilirlik). Modelsiz hâl (sezgisel) kontrol grubu olarak
        her zaman raporlanır (14.6)."""
        if not rows:
            return None
        y = self.outcomes(rows, labels=labels)
        rep = dict(kaynak=("analist_etiketi" if (labels is not None and labels.labels) else "cevap_anahtari"))
        rep["sezgisel"] = calibration_report([r["p7_sezgisel"] for r in rows], y)
        if any(r.get("p7") != r.get("p7_sezgisel") for r in rows):
            rep["model"] = calibration_report([r["p7"] for r in rows], y)
        return rep

    def summary(
        self,
        labels: LabelStore,
        shadow_log: List[dict],
        suppressed_log: List[dict],
        engine: DetectionEngine,
        last_day: pd.Timestamp,
        prediction_rows: Optional[List[dict]] = None,
    ) -> dict:
        cov = self.coverage()
        positives = [c for c in cov if "negatif" not in c["senaryo"].lower()]
        detected = sum(1 for c in positives if c["sonuc"].startswith("GEÇTİ"))
        stale = [
            r["id"]
            for r in engine.rules
            if r["durum"] == "yayinda"
            and (r["id"] not in self.rule_last_hit or (last_day - self.rule_last_hit[r["id"]]).days > 30)
        ]
        total_c = sum(self.contrib.values()) or 1.0
        Counter(s["gun"] for s in shadow_log)
        return dict(
            gunluk=self.daily,
            kapsama=dict(
                senaryo=len(positives),
                tespit=detected,
                oran=round(detected / len(positives), 2) if positives else None,
                detay=cov,
            ),
            erkenlik_gun={c["senaryo"]: c["erkenlik_gun"] for c in positives},
            vaka_hacmi=dict(
                toplam=sum(d["kuyruk"] for d in self.daily),
                gun=len(self.daily),
                gunluk_ort=round(np.mean([d["kuyruk"] for d in self.daily]), 2) if self.daily else 0,
                butce=self.cfg.alarm_budget_per_day,
            ),
            precision_at_n=labels.metrics(),
            etiketli_veri_precision=self.labeled_precision(),
            kural_sagligi=dict(
                tetiklenme=dict(self.rule_hits),
                gun30_tetiklenmeyen=stale,
                devre_disi=engine.disabled,
                dq_askida_atlanan=dict(engine.skipped_dq),
                hatalar=dict(engine.errors),
                matris=(matrix := self.rule_matrix(engine, last_day)),
                kapsama_ozeti=self._matrix_summary(matrix),
            ),
            bastirma=dict(
                bastirilan=len(suppressed_log),
                toplam_tespit=self.total_hits + len(suppressed_log),
                oran=round(len(suppressed_log) / max(1, self.total_hits + len(suppressed_log)), 3),
            ),
            golge_mod=dict(
                uyari=len(shadow_log),
                gunluk_ort=round(len(shadow_log) / max(1, len(self.daily)), 2),
                kurallar=dict(Counter(s["kural"] for s in shadow_log)),
                yayina_giris_kriteri=f"precision ≥ %{self.cfg.shadow_min_precision * 100:.0f} ve günlük ort. ≤ {self.cfg.shadow_max_daily_alerts} (etiket gerekli)",
            ),
            bilesen_katkisi={k: round(v / total_c, 3) for k, v in sorted(self.contrib.items(), key=lambda kv: -kv[1])},
            tahmin_kalibrasyonu=self.prediction_calibration(prediction_rows or [], labels if labels.labels else None),
            recall_notu="Recall yalnızca etiketli test verisinde (CERT/sentetik) ölçülür; üretim hedefi değildir (1.3).",
        )
