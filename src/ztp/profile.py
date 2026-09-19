"""UEBA katmanı — 11.4: kişisel robust baseline (ANA, ADR-001), Isolation Forest (DESTEK), akran kıyası (BAĞLAM)."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ztp.config import TenantConfig
from ztp.deception import KIND_ACCOUNT, KIND_DEVICE, KIND_RESOURCE
from ztp.features import DEVICE_DAY_COLUMNS, FEATURE_FLOOR, NUM_FEATURES, SEASONAL_FEATURES
from ztp.peers import PeerGroups
from ztp.schema import DAY, SENSITIVE_APPS
from ztp.stats import (
    CircularStats,
    age_weights,
    circular_deviation_z,
    circular_stats,
    drift_suspicion,
    jaccard,
    negbin_sf,
    poisson_sf,
    robust_z,
)


@dataclass
class DayContext:
    day: pd.Timestamp
    p_med: pd.DataFrame
    p_mad: pd.DataFrame
    p_var: pd.DataFrame
    p_n: pd.Series
    s_med: pd.DataFrame
    s_n: pd.Series
    peer_med: pd.DataFrame
    peer_mad: pd.DataFrame
    p_sets: Dict[str, Dict[str, frozenset]]
    peer_sets: Dict[str, Dict[str, frozenset]]
    p_circ: Dict[str, CircularStats]
    peer_circ: Dict[str, CircularStats]
    season: pd.DataFrame  # (peer, dow) × özellik → çarpan
    silent_devices: Dict[str, str]  # sid → sessiz cihaz
    if_pct: Dict[str, float]
    if_top: Dict[str, List[Tuple[str, float]]]
    last_active: Dict[str, pd.Timestamp]


class ProfileEngine:
    def __init__(self, cfg: TenantConfig, directory: pd.DataFrame, leaves: pd.DataFrame, peers: PeerGroups):
        self.cfg, self.peers = cfg, peers
        self.dir = directory.set_index("sid")
        self.leaves = leaves
        # cihaz sahipliği: atanmış cihaz (AD/EDR kaydı); laboratuvar/kiosk makineleri kimseye atanmamıştır
        self.owner_of_device: Dict[str, str] = {
            d: sid for d, sid in zip(directory["primary_device"], directory["sid"]) if isinstance(d, str)
        }
        self._primary = dict(zip(directory["sid"], directory["primary_device"]))
        self.feats: pd.DataFrame = pd.DataFrame()
        self.device_day: pd.DataFrame = pd.DataFrame(columns=DEVICE_DAY_COLUMNS)
        self.by_day: Dict[pd.Timestamp, pd.DataFrame] = {}
        self.edr_days: Dict[str, Set[pd.Timestamp]] = defaultdict(set)
        self.ad_users_on_device: Dict[Tuple[str, pd.Timestamp], Set[str]] = {}
        self.shared_devices: Set[str] = set()
        self._dev_stats: Dict[str, list] = {}  # cihaz → [toplam oturum, sahibin oturumu, kullanıcı kümesi]

    # ---- artımlı besleme ------------------------------------------------------
    def append(self, feats: pd.DataFrame, device_day: pd.DataFrame) -> None:
        """Yeni gün(ler)in varlık-gün özelliklerini ve cihaz-gün tablosunu ekler. Türev yapılar (EDR gün kümesi,
        cihazdaki kullanıcılar, paylaşımlı cihazlar, yabancı cihaz bayrağı) yalnızca GEÇMİŞ veriden üretilir —
        toplu ve artımlı koşu aynı sonucu verir (gelecek bilgisi sızmaz)."""
        if device_day is not None and len(device_day):
            parts = [f for f in (self.device_day, device_day[DEVICE_DAY_COLUMNS]) if len(f)]
            self.device_day = pd.concat(parts, ignore_index=True).drop_duplicates(["device", "day"], keep="last")
            for r in device_day.itertuples(index=False):
                if int(r.edr_count) > 0:
                    self.edr_days[r.device].add(pd.Timestamp(r.day))
                if r.ad_users:
                    self.ad_users_on_device[(r.device, pd.Timestamp(r.day))] = set(r.ad_users)
            self._account_device_rows(device_day)
            self._refresh_shared_devices()
        if feats is None or feats.empty:
            return
        f = feats.copy()
        f["peer"] = f["sid"].map(self.peers.key)
        f["foreign_device_flag"] = [self._foreign(sid, devs) for sid, devs in zip(f["sid"], f["devices"])]
        self.feats = pd.concat([self.feats, f], ignore_index=True) if len(self.feats) else f
        if self.feats.duplicated(["sid", "day"]).any():
            self.feats = self.feats.drop_duplicates(["sid", "day"], keep="last").reset_index(drop=True)
        for d, g in f.groupby("day"):
            self.by_day[d] = self.feats[self.feats["day"] == d] if d in self.by_day else g

    def prune(self, before: pd.Timestamp) -> None:
        """Uzun pencere dışına çıkan veriyi düşürür (saklama süresi; bellek sınırı)."""
        if len(self.feats):
            self.feats = self.feats[self.feats["day"] >= before].reset_index(drop=True)
        self.by_day = {d: g for d, g in self.by_day.items() if d >= before}
        if len(self.device_day):
            self.device_day = self.device_day[self.device_day["day"] >= before].reset_index(drop=True)
        for dev in list(self.edr_days):
            self.edr_days[dev] = {d for d in self.edr_days[dev] if d >= before}
        self.ad_users_on_device = {k: v for k, v in self.ad_users_on_device.items() if k[1] >= before}
        self._dev_stats = {}
        self._account_device_rows(self.device_day)  # budama sonrası istatistikler kalan tablodan yeniden kurulur
        self._refresh_shared_devices()

    def _account_device_rows(self, rows: pd.DataFrame) -> None:
        """Cihaz istatistiklerini artımlı günceller: toplam oturum, sahibin oturumu, farklı kullanıcı kümesi."""
        for r in rows.itertuples(index=False):
            if not r.ad_users:
                continue
            st = self._dev_stats.setdefault(r.device, [0, 0, set()])
            owner = self.owner_of_device.get(r.device)
            for u, n in r.ad_users.items():
                st[0] += int(n)
                st[2].add(u)
                if owner == u:
                    st[1] += int(n)

    def _refresh_shared_devices(self) -> None:
        """Laboratuvar/kiosk: ≥3 farklı kullanıcı VE atanmış sahibinin oturum payı <%50 (atanmış PC'de sahip baskındır)."""
        self.shared_devices = {d for d, (n, own, users) in self._dev_stats.items() if len(users) >= 3 and (own / max(n, 1)) < 0.5}

    def _foreign(self, sid: str, devices) -> int:
        """Akran bağlam düzelticisi (11.4) için: kullanıcı o gün atanmamış/yabancı bir cihaz kullandı mı?"""
        mine = self._primary.get(sid)
        return int(
            any((d != mine) and (d not in self.shared_devices) and (self.owner_of_device.get(d) != sid) for d in (devices or ()))
        )

    def today(self, day: pd.Timestamp) -> pd.DataFrame:
        return self.by_day.get(day, self.feats.iloc[0:0])

    @property
    def empty_frame(self) -> pd.DataFrame:
        return self.feats.iloc[0:0]

    def context(self, day: pd.Timestamp) -> DayContext:
        cfg = self.cfg
        f = self.feats
        hist = f[(f["day"] < day) & (f["day"] >= day - cfg.long_window_days * DAY)]
        # 9.3 rol değişimi: kişisel baseline sıfırlanır — yalnızca rol değişiminden sonraki veri kullanılır
        rc = self.dir["role_change_date"].dropna()
        if len(rc):
            cut = hist["sid"].map(rc)
            hist = hist[cut.isna() | (hist["day"] >= cut)]
        short = hist[hist["day"] >= day - cfg.short_window_days * DAY]
        gp = hist.groupby("sid")
        p_med = gp[NUM_FEATURES].median()
        p_mad = (hist[NUM_FEATURES] - gp[NUM_FEATURES].transform("median")).abs().groupby(hist["sid"]).median()
        p_var = gp[NUM_FEATURES].var().fillna(0)
        p_sum = gp["usb_count"].sum()
        w6_sum = hist[hist["day"] >= day - 6 * DAY].groupby("sid")[["usb_count", "files_accessed", "bytes_out"]].sum()
        peer_foreign_rate = hist.groupby("peer")["foreign_device_flag"].mean().to_dict()
        p_n = gp.size()
        gs = short.groupby("sid")
        s_med, s_n = gs[NUM_FEATURES].median(), gs.size()
        gpe = hist.groupby("peer")
        peer_med = gpe[NUM_FEATURES].median()
        peer_mad = (hist[NUM_FEATURES] - gpe[NUM_FEATURES].transform("median")).abs().groupby(hist["peer"]).median()

        def union(s):
            return frozenset().union(*s)

        p_sets = {c: gp[c].agg(union).to_dict() for c in ("apps", "devices", "countries", "resources")}
        peer_sets = {c: gpe[c].agg(union).to_dict() for c in ("apps", "devices", "countries", "resources")}
        p_circ = {s: cs for s, cs in gp["first_logon_hour"].agg(circular_stats).items() if cs is not None}
        peer_circ = {p: cs for p, cs in gpe["first_logon_hour"].agg(circular_stats).items() if cs is not None}
        # 10.5 mevsimsellik: akran grubunun haftanın günü çarpanı (kişisel veriden daha stabil)
        by_dow = hist.groupby(["peer", "dow"])[sorted(SEASONAL_FEATURES)].median()
        overall = hist.groupby("peer")[sorted(SEASONAL_FEATURES)].median()
        season = (by_dow / overall.reindex(by_dow.index.get_level_values(0)).values).clip(0.3, 3.0).fillna(1.0)
        # tespit #10: cihazdan EDR beklenir (son 7 günün ≥4'ünde vardı), bugün cihazdan AD oturumu var ama EDR akışı yok
        silent = {}
        today = self.today(day)
        for dev, days in self.edr_days.items():
            recent = sum(1 for k in range(1, 8) if (day - k * DAY) in days)
            if recent >= 4 and day not in days:
                for sid in self.ad_users_on_device.get((dev, day), ()):
                    silent[sid] = dev
        last_active = hist.groupby("sid")["day"].max().to_dict()
        self.peers.fit_behavioral(hist, day, cfg.behavioral_peer_min_days)
        if_pct, if_top = self._isolation_forest(hist, today, p_med, p_mad)
        ctx = DayContext(
            day,
            p_med,
            p_mad,
            p_var,
            p_n,
            s_med,
            s_n,
            peer_med,
            peer_mad,
            p_sets,
            peer_sets,
            p_circ,
            peer_circ,
            season,
            silent,
            if_pct,
            if_top,
            last_active,
        )
        ctx.p_sum = p_sum
        ctx.w6_sum = w6_sum
        ctx.peer_foreign_rate = peer_foreign_rate
        return ctx

    def _isolation_forest(self, hist, today, p_med, p_mad):
        """DESTEK dedektör (ADR-001): tanımlanmamış türden çok boyutlu anomali. Skoru kural skorunu ezmez, eklenir (14.6);
        her çıktı 'hangi özellik ne kadar katkı verdi' ile açıklanır (SHAP eşdeğeri: kişisel robust-z sıralaması)."""
        if len(hist) < 200 or today.empty:
            return {}, {}
        X = np.log1p(hist[NUM_FEATURES].clip(lower=0).values.astype(float))
        model = IsolationForest(n_estimators=100, contamination="auto", random_state=0).fit(X)
        hist_scores = np.sort(model.score_samples(X))
        Xt = np.log1p(today[NUM_FEATURES].clip(lower=0).values.astype(float))
        st = model.score_samples(Xt)
        pct = {}
        top = {}
        for sid, sc, (_, row) in zip(today["sid"], st, today.iterrows()):
            pct[sid] = float(np.searchsorted(hist_scores, sc) / len(hist_scores))  # düşük skor = anomali → küçük yüzdelik
            pct[sid] = 1.0 - pct[sid]
            if sid in p_med.index:
                zs = []
                for c in NUM_FEATURES:
                    z = robust_z(float(row[c]), float(p_med.loc[sid, c]), float(p_mad.loc[sid, c]), FEATURE_FLOOR[c])
                    if not math.isnan(z):
                        zs.append((c, round(z, 2)))
                zs.sort(key=lambda t: -abs(t[1]))
                top[sid] = zs[:3]
        return pct, top

    # ---- sinyal üretimi (varlık-gün) ---------------------------------------------
    def signals(self, ctx: DayContext, row: pd.Series) -> Tuple[dict, dict, dict]:
        """Döndürür: (sinyaller, açıklama, kanıt). Her sinyal tespit kataloğundaki koşullarda isimle kullanılır."""
        cfg, day, sid = self.cfg, ctx.day, row["sid"]
        u = self.dir.loc[sid]
        s: Dict[str, Any] = {}
        ex: Dict[str, Any] = {}
        evid: Dict[str, list] = {k: list(v) for k, v in (row["evidence"] or {}).items()}
        hesap_yasi = int((day - u["hire_date"]).days)
        profil_baslangic = u["hire_date"] if pd.isna(u["role_change_date"]) else max(u["hire_date"], u["role_change_date"])
        p_n = int(ctx.p_n.get(sid, 0))
        profil_gun = int(min((day - profil_baslangic).days, p_n))
        w_peer, w_pers = age_weights(min(hesap_yasi, profil_gun))
        if not cfg.peer_context and sid in ctx.p_med.index and profil_gun >= 14:  # 19.5 ablasyon: yalnızca kişisel baseline
            w_peer, w_pers = 0.0, 1.0
        if sid not in ctx.p_med.index:
            w_peer, w_pers = 1.0, 0.0
        peer = self.peers.key(sid)
        has_peer = peer in ctx.peer_med.index
        dow = int(row["dow"])
        s.update(
            hesap_yasi_gun=hesap_yasi,
            profil_gun=profil_gun,
            servis_hesabi=int(bool(u["is_service"])),
            ayricalikli=int(bool(u["is_privileged"])),
            akran_agirligi=w_peer,
            kisisel_agirlik=w_pers,
        )
        ex.update(
            akran_grubu=peer,
            departman=u["dept"],
            hesap_yasi=hesap_yasi,
            profil_gun=profil_gun,
            agirlik=f"akran {w_peer:.2f} / kişisel {w_pers:.2f}",
        )

        def season_factor(feature: str) -> float:
            try:
                return float(ctx.season.loc[(peer, dow), feature])
            except KeyError:
                return 1.0

        def blended(feature: str) -> Tuple[float, float, float]:
            """(beklenen, ölçek(MAD), akran medyanı). Beklenen = w_kişisel·kişisel + w_akran·akran; mevsimsellik çarpanı uygulanır."""
            pv = float(ctx.p_med.loc[sid, feature]) if sid in ctx.p_med.index else float("nan")
            pm = float(ctx.p_mad.loc[sid, feature]) if sid in ctx.p_mad.index else float("nan")
            gv = float(ctx.peer_med.loc[peer, feature]) if has_peer else float("nan")
            gm = float(ctx.peer_mad.loc[peer, feature]) if has_peer else float("nan")
            if math.isnan(pv) and math.isnan(gv):
                return float("nan"), float("nan"), float("nan")
            if math.isnan(pv):
                exp, sc = gv, gm
            elif math.isnan(gv):
                exp, sc = pv, pm
            else:
                exp, sc = w_pers * pv + w_peer * gv, w_pers * pm + w_peer * gm
            sf = season_factor(feature) if feature in SEASONAL_FEATURES else 1.0
            exp *= sf
            sc = max(sc if not math.isnan(sc) else 0.0, 0.1 * abs(exp), FEATURE_FLOOR[feature])
            return exp, sc, (gv * sf if not math.isnan(gv) else float("nan"))

        # 10.3 dairesel istatistik — giriş saati
        h = row["first_logon_hour"]
        if h is not None and not math.isnan(h):
            zp = circular_deviation_z(h, ctx.p_circ[sid]) if (sid in ctx.p_circ and ctx.p_circ[sid].n >= 5) else float("nan")
            zg = circular_deviation_z(h, ctx.peer_circ[peer]) if peer in ctx.peer_circ else float("nan")
            if math.isnan(zp) and math.isnan(zg):
                z = float("nan")
            elif math.isnan(zp):
                z = zg
            elif math.isnan(zg):
                z = zp
            else:
                z = w_pers * zp + w_peer * zg
            s["saat_sapmasi_z"] = z
            ex["giris_saati"] = f"{int(h):02d}:{int((h % 1) * 60):02d}"
            if sid in ctx.p_circ:
                cs = ctx.p_circ[sid]
                ex["normal_giris"] = (
                    f"{int(cs.mean_hour):02d}:{int((cs.mean_hour % 1) * 60):02d} ± {cs.circ_std_hours:.1f}s (κ={cs.kappa:.1f})"
                )
        else:
            s["saat_sapmasi_z"] = float("nan")
        s["mesai_disi_orani"] = float(row["offhours_ratio"])
        k_off = int(row["offhours_logon_count"])
        exp_off, _, _ = blended("offhours_logon_count")
        s["mesai_disi_giris_sayisi"] = k_off
        s["mesai_disi_giris_poisson_p"] = (
            poisson_sf(k_off, max(exp_off if not math.isnan(exp_off) else 0.2, 0.2)) if k_off > 0 else 1.0
        )
        s["mesai_disi_dosya_orani"] = float(row["file_offhours_ratio"])
        s["mesai_disi_saatler"] = list(row["offhours_hours"] or [])
        # 10.1 robust z — veri hacmi
        exp_b, sc_b, peer_b = blended("bytes_out")
        s["veri_hacmi_z"] = robust_z(float(row["bytes_out"]), exp_b, sc_b, FEATURE_FLOOR["bytes_out"])
        s["veri_hacmi_akran_kati"] = (
            float(row["bytes_out"]) / max(peer_b if not math.isnan(peer_b) else exp_b, 1.0) if not math.isnan(exp_b) else 0.0
        )
        ex["normal_hacim_mb"], ex["bugun_hacim_mb"] = (
            round(exp_b / 1e6, 1) if not math.isnan(exp_b) else None,
            round(float(row["bytes_out"]) / 1e6, 1),
        )
        # 10.2 Poisson / negatif binom — sayım verileri
        exp_f, _, peer_f = blended("files_accessed")
        var_f = float(ctx.p_var.loc[sid, "files_accessed"]) if sid in ctx.p_var.index else float("nan")
        k_f = int(row["files_accessed"])
        s["dosya_sayisi"] = k_f
        s["dosya_sayisi_poisson_p"] = negbin_sf(k_f, max(exp_f, 0.5), var_f) if not math.isnan(exp_f) else 1.0
        s["dosya_sayisi_akran_kati"] = (
            k_f / max(peer_f if not math.isnan(peer_f) else exp_f, 0.5) if not math.isnan(exp_f) else 0.0
        )
        ex["normal_dosya"], ex["bugun_dosya"] = round(exp_f, 1) if not math.isnan(exp_f) else None, k_f
        # taşınabilir medya (#17): sayım + "ilk kez" (küme sorusu gibi: kişisel geçmişte hiç USB yok)
        k_usb = int(row["usb_count"])
        exp_usb, _, peer_usb = blended("usb_count")
        s["usb_sayisi"] = k_usb
        s["usb_poisson_p"] = poisson_sf(k_usb, max(exp_usb if not math.isnan(exp_usb) else 0.1, 0.1)) if k_usb > 0 else 1.0
        s["usb_ilk_kez"] = int(k_usb > 0 and profil_gun >= 30 and float(ctx.p_sum.get(sid, 0.0)) == 0.0)
        # 2.3 eşik altı kalma: günlük eşiğin altında kalan ama haftalık toplamda belirgin artış (7 günlük kümülatif pencere)
        prev6 = ctx.w6_sum.loc[sid] if sid in ctx.w6_sum.index else None
        usb7 = k_usb + (int(prev6["usb_count"]) if prev6 is not None else 0)
        s["usb_7g_toplam"] = usb7
        s["usb_7g_poisson_p"] = poisson_sf(usb7, 7 * max(exp_usb if not math.isnan(exp_usb) else 0.1, 0.1)) if usb7 > 0 else 1.0
        s["usb_anomali_p"] = min(s["usb_poisson_p"], s["usb_7g_poisson_p"])
        files7 = k_f + (int(prev6["files_accessed"]) if prev6 is not None else 0)
        s["dosya_7g_toplam"] = files7
        s["dosya_7g_poisson_p"] = (
            negbin_sf(
                files7,
                7 * max(exp_f if not math.isnan(exp_f) else 0.5, 0.5),
                7 * var_f if not math.isnan(var_f) else float("nan"),
            )
            if files7 > 0
            else 1.0
        )
        # 9.3 / 17.2 devamsızlık takvimi: kayıtlı izin dönüşü UEBA katmanında da bilinmelidir.
        # `izin_kayitli` Prediction katmanında üretiliyor ve UEBA ondan ÖNCE çalışıyor (pipeline); 12.5
        # bastırması için aynı hesap burada yapılır. Bastırılan olay sayılır ve raporlanır — sessizce yutulmaz.
        s["izin_donusu"] = 0
        _last = ctx.last_active.get(sid)
        if _last is not None and _last < day and len(self.leaves):
            _gap = int((day - _last).days) - 1
            if _gap >= 7:
                _lv = self.leaves[self.leaves["sid"] == sid]
                s["izin_donusu"] = int(any((r.start <= day - DAY) and (r.end >= _last + DAY) for r in _lv.itertuples()))
        # 2.3 "eşik altı kalma" — veri hacmi için 7 günlük kümülatif pencere (dosya/USB ile aynı kalıp).
        # 12.4 bulgusu: dokümanda söz verilmişti, yalnızca dosya ve USB için uygulanmıştı; hacimde yoktu.
        bytes7 = float(row["bytes_out"]) + (float(prev6["bytes_out"]) if prev6 is not None else 0.0)
        s["veri_hacmi_7g_toplam"] = bytes7
        # bağımsız günlerin toplamında ölçek ~√7 kat büyür; beklenen 7 × günlük beklenen
        # Ölçek: bağımsız günlerin toplamında ~√7 kat büyür. Göreli taban (%10) GÜNLÜK değil HAFTALIK
        # beklenen üzerinden uygulanır; aksi hâlde taban %10 → %3,8'e düşer ve ılımlı bir yükseliş z'yi patlatır.
        s["veri_hacmi_7g_z"] = (
            robust_z(
                bytes7,
                7.0 * exp_b,
                math.sqrt(7.0) * sc_b,
                max(math.sqrt(7.0) * FEATURE_FLOOR["bytes_out"], 0.1 * abs(7.0 * exp_b)),
            )
            if not math.isnan(exp_b)
            else float("nan")
        )
        # usb_anomali_p ile aynı idiom: günlük pencere ile kümülatif pencereden hangisi daha güçlüyse o
        _zc = [z for z in (s["veri_hacmi_z"], s["veri_hacmi_7g_z"]) if not (isinstance(z, float) and math.isnan(z))]
        s["veri_hacmi_anomali_z"] = max(_zc) if _zc else float("nan")
        # 12.4 mutlak taban: kritik varlığa erişim varsa şiddette akran indirimi uygulanmaz
        s["kritik_varlik_erisim_sayisi"] = int(row.get("sensitive_access_count", 0) or 0)
        if not math.isnan(exp_b):
            ex["veri_hacmi_7g_mb"] = f"{bytes7 / 1e6:,.0f} MB (7g beklenen ~{7 * exp_b / 1e6:,.0f} MB)"
        ex["usb_7g"] = f"{usb7} (beklenen ~{7 * (exp_usb if not math.isnan(exp_usb) else 0.1):.1f})"
        exp_fail, _, _ = blended("failed_logon_count")
        k_fail = int(row["failed_logon_count"])
        s["basarisiz_giris_sayisi"] = k_fail
        s["basarisiz_giris_poisson_p"] = poisson_sf(k_fail, max(exp_fail if not math.isnan(exp_fail) else 0.3, 0.3))
        # 10.6 küme farkı — uygulama / cihaz / ülke
        p_apps = ctx.p_sets["apps"].get(sid, frozenset())
        g_apps = ctx.peer_sets["apps"].get(peer, frozenset())
        apps_today = row["apps"] or frozenset()
        new_p = apps_today - p_apps
        new_both = new_p - g_apps
        new_sens = (new_p & SENSITIVE_APPS) if profil_gun >= 30 else frozenset()
        s["yeni_uygulama_kisisel"], s["yeni_uygulama_sayisi"] = len(new_p), len(new_both)
        s["yeni_hassas_uygulama"] = len(new_sens)
        s["jaccard_uygulama"] = jaccard(set(apps_today), set(p_apps))
        if new_both or new_sens:
            ex["yeni_uygulamalar"] = sorted(new_both | new_sens)
            evid["new_app"] = [row["app_events"][a] for a in sorted(new_both | new_sens) if a in (row["app_events"] or {})]
        p_dev = ctx.p_sets["devices"].get(sid, frozenset())
        p_ctry = ctx.p_sets["countries"].get(sid, frozenset())
        g_dev = ctx.peer_sets["devices"].get(peer, frozenset())
        devs_today = row["devices"] or frozenset()
        unseen = (devs_today - p_dev) if profil_gun >= 14 else frozenset()  # kişisel kümede yok
        new_dev = unseen - g_dev  # akran kümesinde de yok (10.6)
        # başka kullanıcıya ATANMIŞ, paylaşımlı olmayan cihaz: yanal hareket / hesap kötüye kullanımı işareti (senaryo 3-4)
        others = {d for d in unseen if d not in self.shared_devices and self.owner_of_device.get(d) not in (None, sid)}
        new_ctry = (row["countries"] or frozenset()) - p_ctry if profil_gun >= 14 else frozenset()
        s["yeni_cihaz_sayisi"], s["yeni_ulke_sayisi"], s["baskasinin_cihazi_sayisi"] = len(new_dev), len(new_ctry), len(others)
        s["cihaz_konum_yenilik"] = len(new_dev | others) + len(new_ctry)
        # şiddet, davranışın akran grubundaki nadirliğiyle ölçeklenir: akranlar sık sık başka makineye giriyorsa zayıf sinyal
        rate = float(ctx.peer_foreign_rate.get(peer, 0.0))
        s["cihaz_yenilik_akran_nadirlik"] = -math.log10(max(rate, 1e-4)) if (new_dev or others) else 0.0
        if new_dev or others:
            ex["cihaz_akran_orani"] = f"akran varlık-günlerinin %{100 * rate:.2f}'sinde yabancı cihaz kullanımı var"
        if new_dev or others:
            ex["yeni_cihazlar"] = sorted(new_dev | others)
            ex["baskasinin_cihazi"] = {d: self.owner_of_device[d] for d in sorted(others)}
            evid["new_device"] = [row["device_events"][d] for d in sorted(new_dev | others)]
        if new_ctry:
            ex["yeni_ulkeler"] = sorted(new_ctry)
            evid["new_country"] = [row["country_events"][c] for c in sorted(new_ctry)]
        s["seyahat_hizi_kmh"] = float(row["max_travel_speed"])
        s["imkansiz_seyahat"] = int(row["max_travel_speed"] > 900)
        # keşif
        s["kesif_sureci_sayisi"] = int(row["recon_process_count"])
        exp_r, _, peer_r = blended("distinct_resources")
        s["kaynak_cesitliligi"] = int(row["distinct_resources"])
        s["kesif_genisligi_akran_kati"] = (
            int(row["distinct_resources"]) / max(peer_r if not math.isnan(peer_r) else exp_r, 1.0)
            if not math.isnan(exp_r)
            else 0.0
        )
        ex["normal_kaynak_cesitliligi"] = round(exp_r, 1) if not math.isnan(exp_r) else None
        # #9 akran grubundan çok değişkenli yapısal sapma (kısa pencere medyanları vs akran medyan/MAD)
        s["akran_yapisal_mesafe"] = (
            self._structural_distance(ctx, sid, peer)
            if (sid in ctx.s_med.index and has_peer and int(ctx.s_n.get(sid, 0)) >= 5)
            else 0.0
        )
        s["akran_celiski"] = int(self.peers.behavioral_conflict.get(sid, 0))
        # 9.2 / 10.4 zehirleme şüphesi: kısa pencere uzun pencereden koptu mu?
        poison = False
        if sid in ctx.s_med.index and sid in ctx.p_med.index and int(ctx.s_n.get(sid, 0)) >= 3:
            for c in ("bytes_out", "files_accessed"):
                poison |= drift_suspicion(
                    float(ctx.s_med.loc[sid, c]),
                    float(ctx.p_med.loc[sid, c]),
                    float(ctx.p_mad.loc[sid, c]),
                    cfg.poisoning_drift_z,
                )
        s["zehirleme_suphesi"] = int(poison)
        if poison:
            ex["zehirleme"] = "7g medyanı 90g medyanından koptu; akran referansı ve uzun pencere esas alındı"
        # #10 log sessizliği (veri yokluğu da sinyaldir)
        s["log_sessizligi"] = int(sid in ctx.silent_devices)
        if sid in ctx.silent_devices:
            ex["sessiz_cihaz"] = ctx.silent_devices[sid]
            evid["silence"] = [f"cihaz:{ctx.silent_devices[sid]} (EDR akışı yok — veri yokluğu kanıtı)"]
        # aldatma katmanı (honeytoken): baseline/akran yok — etkileşim sayısı doğrudan sinyaldir (13.5 tek-sinyal istisnası)
        tokens = row.get("honeytokens") or frozenset()
        s["tuzak_etkilesim_sayisi"] = int(row.get("honeytoken_count", 0) or 0)
        s["tuzak_hesap_sayisi"] = sum(1 for t in tokens if t.startswith(KIND_ACCOUNT + ":"))
        s["tuzak_kaynak_sayisi"] = sum(1 for t in tokens if t.startswith(KIND_RESOURCE + ":"))
        s["tuzak_cihaz_sayisi"] = sum(1 for t in tokens if t.startswith(KIND_DEVICE + ":"))
        if tokens:
            ex["tuzak_varliklar"] = sorted(tokens)
        # İK sinyalleri
        s["ayrilik_bildirimi"] = int(not pd.isna(u["resignation_notice_date"]) and u["resignation_notice_date"] <= day)
        g = u["privilege_grant_date"]
        s["yetki_degisim_gun"] = int((day - g).days) if (not pd.isna(g) and 0 <= (day - g).days <= 30) else -1
        # Isolation Forest destek
        s["if_anomali_pct"] = float(ctx.if_pct.get(sid, 0.0))
        if sid in ctx.if_top:
            ex["if_katki"] = ctx.if_top[sid]
        return s, ex, evid

    def _structural_distance(self, ctx: DayContext, sid: str, peer: str) -> float:
        zs = []
        for c in NUM_FEATURES:
            pm, pmad = float(ctx.peer_med.loc[peer, c]), float(ctx.peer_mad.loc[peer, c])
            z = robust_z(float(ctx.s_med.loc[sid, c]), pm, pmad, max(FEATURE_FLOOR[c], 0.1 * abs(pm)))
            if not math.isnan(z):
                zs.append(min(abs(z), 10.0))
        return float(math.sqrt(np.mean(np.square(zs)))) if zs else 0.0
