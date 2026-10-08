"""Sentetik kurum ve enjekte edilen senaryolar — tehdit modeli 2.1 → tespit kataloğu 12.2. Not (19.2): kendi ürettiğimiz mock veri döngüsel doğrulama riski taşır; birincil kaynak CERT'tir."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from ztp.data.dataset import Dataset
from ztp.schema import CLOUD_APPS, EVENT_COLUMNS, OCSF_AUTH, OCSF_FILE, OCSF_HTTP, OCSF_NETWORK, OCSF_PROCESS

# sabit varsayılan bitiş günü: sentetik regresyon koşu tarihine (bugüne) bağlı olmasın — aynı tohum her gün aynı sonucu verir
SYNTHETIC_DEFAULT_END = pd.Timestamp("2026-09-16")
WEEKDAY_FACTOR = {0: 1.15, 1: 1.0, 2: 1.0, 3: 1.0, 4: 0.9, 5: 0.35, 6: 0.35}  # 10.5 haftalık mevsimsellik
DEPT_WEIGHTS = {"Finans": 0.14, "Muhasebe": 0.10, "IT": 0.16, "Satis": 0.20, "IK": 0.08, "ArGe": 0.20, "Operasyon": 0.12}
APPS_BY_DEPT = {
    "Finans": ["erp", "excel_online", "webmail", "intranet", "bank_portal"],
    "Muhasebe": ["erp", "webmail", "intranet", "efatura", "excel_online"],
    "IT": ["ticketing", "git", "webmail", "intranet", "cloud_console", "ssh_gw"],
    "Satis": ["crm", "webmail", "intranet", "linkedin", "slides"],
    "IK": ["hris", "webmail", "intranet", "job_portal"],
    "ArGe": ["git", "jira", "webmail", "intranet", "docs_wiki", "pkg_registry"],
    "Operasyon": ["wms", "webmail", "intranet", "ticketing"],
}
SHARES_BY_DEPT = {
    "Finans": [r"\\FIN-SRV-01\raporlar", r"\\FIN-SRV-01\butce", r"\\FILE-01\ortak"],
    "Muhasebe": [r"\\FIN-SRV-01\raporlar", r"\\FIN-SRV-01\muhasebe", r"\\FILE-01\ortak"],
    "IT": [r"\\DC-01\sysvol", r"\\IT-SRV-01\araclar", r"\\FILE-01\ortak"],
    "Satis": [r"\\SLS-SRV-01\teklifler", r"\\SLS-SRV-01\musteri", r"\\FILE-01\ortak"],
    "IK": [r"\\HR-SRV-01\bordro", r"\\HR-SRV-01\ozluk", r"\\FILE-01\ortak"],
    "ArGe": [r"\\ARGE-SRV-01\kaynak_kod", r"\\ARGE-SRV-01\tasarim", r"\\FILE-01\ortak"],
    "Operasyon": [r"\\OPS-SRV-01\sevkiyat", r"\\FILE-01\ortak"],
}
ALL_SHARES = sorted({s for v in SHARES_BY_DEPT.values() for s in v})
CRITICAL_ASSETS_DEFAULT = [r"\\FIN-SRV-01\butce", r"\\HR-SRV-01\bordro", r"\\DC-01\sysvol", r"\\ARGE-SRV-01\kaynak_kod"]
# aldatma katmanı tuzakları (honeytokens=True ile): meşru kullanımı olmayan hesap / paylaşım / sunucu
HONEYTOKENS_DEFAULT = dict(hesaplar=["svc-backup-legacy"], kaynaklar=[r"\\FIN-SRV-01\bonus_2026*"], cihazlar=["HONEY-SRV-01"])
BENIGN_PROCS = ["outlook.exe", "excel.exe", "chrome.exe", "teams.exe", "explorer.exe", "winword.exe", "code.exe"]
RECON_CMDS = [
    ("whoami.exe", "whoami /all"),
    ("net.exe", 'net group "Domain Admins" /domain'),
    ("nltest.exe", "nltest /dclist:kurum"),
    ("net.exe", "net view /domain"),
    ("powershell.exe", "Get-ADUser -Filter *"),
    ("nslookup.exe", "nslookup -type=srv _ldap._tcp"),
]
FIRST_NAMES = [
    "ahmet",
    "mehmet",
    "ayse",
    "fatma",
    "ali",
    "zeynep",
    "emre",
    "elif",
    "murat",
    "seda",
    "burak",
    "derya",
    "can",
    "ece",
    "kerem",
    "selin",
    "ozan",
    "melis",
    "tolga",
    "gizem",
    "baris",
    "irem",
    "cem",
    "naz",
]
LAST_NAMES = [
    "yilmaz",
    "kaya",
    "demir",
    "sahin",
    "celik",
    "yildiz",
    "aydin",
    "ozturk",
    "arslan",
    "dogan",
    "kilic",
    "aslan",
    "cetin",
    "kara",
    "koc",
    "kurt",
    "ozdemir",
    "polat",
    "erdogan",
    "tas",
    "acar",
    "bulut",
]


class SyntheticOrg:
    """Kör test / regresyon için sentetik kurum. Senaryolar tehdit modelindeki aktör tiplerine (2.1) karşılık gelir.
    Not (19.2): kendi ürettiğimiz mock veri döngüsel doğrulama riski taşır; birincil kaynak CERT'tir."""

    def __init__(
        self,
        n_users: int = 150,
        n_days: int = 141,
        eval_days: int = 30,
        end_day: Optional[pd.Timestamp] = None,
        seed: int = 42,
        honeytokens: bool = False,
    ):
        self.rng = np.random.default_rng(seed)
        self.n_users, self.n_days, self.eval_days = n_users, n_days, eval_days
        self.honeytokens = honeytokens  # S10 tuzak senaryosu ve tuzak listesi (varsayılan kapalı: regresyon sayıları değişmesin)
        self.end_day = (end_day if end_day is not None else SYNTHETIC_DEFAULT_END).normalize()
        self.day0 = self.end_day - pd.Timedelta(days=n_days - 1)
        self.E0 = n_days - eval_days  # değerlendirme penceresinin ilk gün indeksi
        self.users: List[dict] = []
        self.overrides: Dict[Tuple[int, int], dict] = defaultdict(dict)
        self.ground_truth: List[dict] = []
        self.leaves: List[dict] = []
        self._eid = 0

    # ---- dizin ---------------------------------------------------------------
    def _day(self, idx: int) -> pd.Timestamp:
        return self.day0 + pd.Timedelta(days=int(idx))

    def _make_directory(self) -> None:
        rng = self.rng
        depts = list(DEPT_WEIGHTS)
        probs = np.array(list(DEPT_WEIGHTS.values()))
        used = set()
        for i in range(self.n_users):
            while True:
                fn, ln = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
                if (fn, ln) not in used:
                    used.add((fn, ln))
                    break
            dept = str(rng.choice(depts, p=probs / probs.sum()))
            lvl = int(rng.choice([1, 2, 3, 4], p=[0.45, 0.3, 0.18, 0.07]))
            night = dept == "IT" and rng.random() < 0.1
            apps = APPS_BY_DEPT[dept]
            aw = rng.dirichlet(np.ones(len(apps)) * 2)
            shares = SHARES_BY_DEPT[dept]
            self.users.append(
                dict(
                    idx=i,
                    sid=f"S-1-5-21-{1000000 + i * 7919}-{2000000 + i * 104729}-{1000 + i}",
                    display_name=f"{fn.title()} {ln.title()}",
                    ad_sam=f"KURUM\\{fn}.{ln}",
                    upn=f"{fn}.{ln}@kurum.com",
                    vpn_user=f"{fn[0]}{ln}",
                    primary_device=f"HOST-{1000 + i}",
                    secondary_device=f"HOST-{5000 + i}",
                    dept=dept,
                    title_level=lvl,
                    location=str(rng.choice(["IST", "ANK", "IZM"], p=[0.6, 0.25, 0.15])),
                    hire_idx=-int(rng.integers(120, 2200)),
                    is_service=False,
                    is_privileged=bool((dept == "IT" and lvl >= 3) or rng.random() < 0.04),
                    resignation_notice_idx=None,
                    resignation_idx=None,
                    role_change_idx=None,
                    privilege_grant_idx=None,
                    mu_hour=(22.0 if night else float(rng.normal(8.6, 0.7))),
                    kappa=6.0,
                    lam_logon=1.8,
                    lam_http=6.0,
                    lam_file={"Finans": 5, "Muhasebe": 5, "ArGe": 4}.get(dept, 3.0),
                    lam_proc=3.0,
                    median_bytes=float(np.exp(rng.normal(np.log(120e6), 0.6))),
                    remote_prob=0.3,
                    apps=apps,
                    app_w=aw,
                    shares=shares,
                    night=night,
                )
            )
        # 8.2 / 11.2: servis hesapları ayrı sınıf — insan baseline'ına dahil edilmez
        for j, name in enumerate(["svc_backup", "svc_monitor", "svc_sync", "svc_scan"]):
            i = len(self.users)
            self.users.append(
                dict(
                    idx=i,
                    sid=f"S-1-5-21-9{j:06d}-{j}-{1000 + i}",
                    display_name=name,
                    ad_sam=f"KURUM\\{name}",
                    upn=f"{name}@kurum.com",
                    vpn_user=name,
                    primary_device=f"SRV-{10 + j}",
                    secondary_device=f"SRV-{10 + j}",
                    dept="IT",
                    title_level=0,
                    location="IST",
                    hire_idx=-3000,
                    is_service=True,
                    is_privileged=True,
                    resignation_notice_idx=None,
                    resignation_idx=None,
                    role_change_idx=None,
                    privilege_grant_idx=None,
                    mu_hour=2.5,
                    kappa=20.0,
                    lam_logon=1,
                    lam_http=0,
                    lam_file=40,
                    lam_proc=8,
                    median_bytes=8e9,
                    remote_prob=0,
                    apps=["intranet"],
                    app_w=np.array([1.0]),
                    shares=[r"\\FILE-01\ortak", r"\\FIN-SRV-01\raporlar", r"\\HR-SRV-01\ozluk"],
                    night=True,
                )
            )

    def _make_leases(self) -> pd.DataFrame:
        """IP → kullanıcı eşlemesi zaman aralıklıdır (8.2). Aylık kiralama + bir 'yeniden atanmış IP' örneği."""
        rows = []
        for u in self.users:
            i = u["idx"]
            for period in range(0, self.n_days, 30):
                ip = f"10.14.{(i // 200) + 20 + (period // 30) % 3}.{(i % 200) + 10}"
                rows.append(dict(ip=ip, sid=u["sid"], start=self._day(period), end=self._day(min(period + 30, self.n_days))))
        # yeniden atanmış IP: 0 numaralı kullanıcının ilk dönem IP'si sonra 1 numaralı kullanıcıya gider
        _u0, u1 = self.users[0], self.users[1]
        rows.append(dict(ip="10.14.20.10", sid=u1["sid"], start=self._day(60), end=self._day(self.n_days)))
        df = pd.DataFrame(rows)
        # u1'in kendi 60+ dönem kaydıyla çakışmasın: u1 için o dönemi taşınan IP'ye çevir
        mask = (df.sid == u1["sid"]) & (df.start >= self._day(60)) & (df.ip != "10.14.20.10")
        df = df[~mask].reset_index(drop=True)
        return df

    # ---- senaryolar (tehdit modeli 2.1 + tespit kataloğu 12.2) -------------------
    def _pick(self, dept: str, exclude: Set[int], cond=None) -> dict:
        cands = [
            u
            for u in self.users
            if u["dept"] == dept and not u["is_service"] and u["idx"] not in exclude and (cond is None or cond(u))
        ]
        if not cands:  # küçük kurumda departman boş kalabilir → herhangi bir insan hesabı
            cands = [u for u in self.users if not u["is_service"] and u["idx"] not in exclude and (cond is None or cond(u))]
        return cands[int(self.rng.integers(len(cands)))]

    def _apply_scenarios(self) -> None:
        E0, used = self.E0, set()
        ov = self.overrides

        # S1 — Kızgın/ayrılan çalışan: ayrılık öncesi kademeli sızıntı (tespit 3, 2, 7, 12, 14)
        s1 = self._pick("Satis", used)
        used.add(s1["idx"])
        s1["resignation_notice_idx"], s1["resignation_idx"] = E0 + 8, E0 + 20
        for d in range(E0 + 6, E0 + 21):
            k = d - (E0 + 6)
            ov[(s1["idx"], d)].update(bytes_mult=1.4 + k * 0.5)
            if d >= E0 + 9:
                ov[(s1["idx"], d)].update(extra_apps=["personal_cloud"])
            if d in (E0 + 12, E0 + 15, E0 + 19):
                ov[(s1["idx"], d)].update(offhours_files=45)
            if d == E0 + 14:
                ov[(s1["idx"], d)].update(usb=2)
        self.ground_truth.append(
            dict(
                senaryo="S1_ayrilik_oncesi_sizinti",
                aktor="Kızgın çalışan",
                sid=s1["sid"],
                baslangic=E0 + 6,
                olay_gunu=E0 + 19,
                teknikler=["T1567", "T1039", "T1052"],
                beklenen=["UEBA-0003", "UEBA-0002", "UEBA-0007", "PRED-0012", "PRED-0014"],
                veri_kaynagi=["proxy", "file_server", "dlp", "hr"],
            )
        )

        # S2 — Ele geçirilmiş hesap: yeni ülke + yeni cihaz + imkânsız seyahat + başarısız giriş yığını + keşif (4, 5, 6, IF)
        s2 = self._pick("ArGe", used)
        used.add(s2["idx"])
        for d in (E0 + 10, E0 + 11):
            ov[(s2["idx"], d)].update(
                attacker=dict(country="RU", hour=10.0, device="HOST-9911"),
                failed=(22 if d == E0 + 10 else 4),
                recon=6,
                extra_shares=[
                    r"\\HR-SRV-01\ozluk",
                    r"\\FIN-SRV-01\raporlar",
                    r"\\DC-01\sysvol",
                    r"\\IT-SRV-01\araclar",
                    r"\\SLS-SRV-01\musteri",
                ],
            )
        self.ground_truth.append(
            dict(
                senaryo="S2_ele_gecirilmis_hesap",
                aktor="Ele geçirilmiş hesap",
                sid=s2["sid"],
                baslangic=E0 + 10,
                olay_gunu=E0 + 10,
                teknikler=["T1078", "T1110", "T1087", "T1018"],
                beklenen=["UEBA-0004", "UEBA-0005", "UEBA-0006"],
                veri_kaynagi=["ad", "vpn", "edr", "file_server"],
            )
        )

        # S3 — Kötü niyetli yeni işe alım: hesap yaşı < 30 gün × keşif yoğunluğu (8)
        s3 = self._pick("Finans", used)
        used.add(s3["idx"])
        s3["hire_idx"] = E0 - 10
        for d in range(E0 + 2, E0 + 13):
            ov[(s3["idx"], d)].update(extra_shares=list(self.rng.choice(ALL_SHARES, 9, replace=False)), recon=2)
        self.ground_truth.append(
            dict(
                senaryo="S3_kotu_niyetli_yeni_ise_alim",
                aktor="Kötü niyetli yeni işe alım",
                sid=s3["sid"],
                baslangic=E0 + 2,
                olay_gunu=E0 + 6,
                teknikler=["T1087", "T1018"],
                beklenen=["UEBA-0008"],
                veri_kaynagi=["ad", "hr", "file_server", "edr"],
            )
        )

        # S4 — Yetki artışı sonrası davranış kayması (11): yeni yetki, iş tanımıyla ilgisiz alanlarda kullanılıyor
        s4 = self._pick("IT", used, cond=lambda u: not u["night"])
        used.add(s4["idx"])
        s4["privilege_grant_idx"] = E0 + 4
        s4["is_privileged"] = True
        for d in range(E0 + 5, self.n_days):
            ov[(s4["idx"], d)].update(
                extra_shares=[
                    r"\\FIN-SRV-01\butce",
                    r"\\HR-SRV-01\bordro",
                    r"\\SLS-SRV-01\musteri",
                    r"\\ARGE-SRV-01\kaynak_kod",
                    r"\\FIN-SRV-01\muhasebe",
                    r"\\HR-SRV-01\ozluk",
                ]
            )
        self.ground_truth.append(
            dict(
                senaryo="S4_yetki_artisi_kaymasi",
                aktor="Sabırlı içeriden tehdit",
                sid=s4["sid"],
                baslangic=E0 + 5,
                olay_gunu=E0 + 9,
                teknikler=["T1078.003"],
                beklenen=["PRED-0011"],
                veri_kaynagi=["ad", "hr", "file_server"],
            )
        )

        # S5 — Log kesintisi / ajan sessizliği (10): cihazdan EDR akmıyor ama kullanıcı aktif
        s5 = self._pick("Operasyon", used)
        used.add(s5["idx"])
        for d in range(E0 + 8, E0 + 15):
            ov[(s5["idx"], d)].update(edr_silent=True)
        self.ground_truth.append(
            dict(
                senaryo="S5_log_sessizligi",
                aktor="Ele geçirilmiş hesap / ajan kapatma",
                sid=s5["sid"],
                baslangic=E0 + 8,
                olay_gunu=E0 + 8,
                teknikler=["T1562"],
                beklenen=["DQ-0010"],
                veri_kaynagi=["edr", "ad"],
            )
        )

        # S6 — Baseline zehirleme (2.3): hacim haftalarca yavaşça kaydırılır → kısa/uzun pencere farkı + akran referansı
        s6 = self._pick("Muhasebe", used)
        used.add(s6["idx"])
        for d in range(E0 - 60, self.n_days):
            ov[(s6["idx"], d)].update(bytes_mult=1.045 ** (d - (E0 - 60)))
        self.ground_truth.append(
            dict(
                senaryo="S6_baseline_zehirleme",
                aktor="Sabırlı içeriden tehdit",
                sid=s6["sid"],
                baslangic=E0 - 60,
                olay_gunu=E0 + 22,
                teknikler=["T1567"],
                beklenen=["UEBA-0003"],
                veri_kaynagi=["proxy"],
                not_="zehirleme_suphesi bayrağı beklenir",
            )
        )

        # S7 — Yanal hareket: kurban cihazı başka hesapla kullanılıyor, kritik varlığa erişiliyor (15, 5)
        s7v = self._pick("Finans", used)
        used.add(s7v["idx"])
        s7a = self._pick("Satis", used)
        used.add(s7a["idx"])
        for d in range(E0 + 12, E0 + 15):
            ov[(s7a["idx"], d)].update(device=s7v["primary_device"], extra_shares=[r"\\FIN-SRV-01\butce"], recon=2)
        self.ground_truth.append(
            dict(
                senaryo="S7_yanal_hareket",
                aktor="Ele geçirilmiş hesap",
                sid=s7a["sid"],
                kurban_sid=s7v["sid"],
                baslangic=E0 + 12,
                olay_gunu=E0 + 13,
                teknikler=["T1021", "T1078"],
                beklenen=["UEBA-0005", "REL-0015"],
                veri_kaynagi=["ad", "file_server", "edr"],
            )
        )

        # S8 — Uzun sessizlik sonrası yoğun aktivite (13): izin kaydı YOK
        s8 = self._pick("ArGe", used)
        used.add(s8["idx"])
        for d in range(E0 - 22, E0 + 3):
            ov[(s8["idx"], d)].update(inactive=True)
        ov[(s8["idx"], E0 + 3)].update(bytes_mult=5.0, files_mult=4.0, force_active=True)
        self.ground_truth.append(
            dict(
                senaryo="S8_uzun_sessizlik_sonrasi_aktivite",
                aktor="Ele geçirilmiş hesap",
                sid=s8["sid"],
                baslangic=E0 + 3,
                olay_gunu=E0 + 3,
                teknikler=["T1078"],
                beklenen=["PRED-0013"],
                veri_kaynagi=["ad", "proxy", "file_server"],
            )
        )

        # S9 — NEGATİF KONTROL: kayıtlı izin dönüşü (9.3) — devamsızlık takvimi bilindiği için uyarı BEKLENMEZ
        s9 = self._pick("IK", used)
        used.add(s9["idx"])
        # izin dönüşü iş gününe denk gelir: hafta sonu dönüş mesai dışı girişi (UEBA-0001) haklı olarak tetikler ve negatif
        # kontrolün sonucu koşu tarihine bağlı kalırdı
        r9 = E0 + 2
        while self._day(r9).dayofweek >= 5:
            r9 += 1
        for d in range(E0 - 20, r9):
            ov[(s9["idx"], d)].update(inactive=True)
        ov[(s9["idx"], r9)].update(bytes_mult=3.0, files_mult=3.0, force_active=True)
        self.leaves.append(dict(sid=s9["sid"], start=self._day(E0 - 20), end=self._day(r9 - 1), tur="yillik_izin"))
        self.ground_truth.append(
            dict(
                senaryo="S9_kayitli_izin_donusu_NEGATIF",
                aktor="Dikkatsiz/normal çalışan",
                sid=s9["sid"],
                baslangic=r9,
                olay_gunu=r9,
                teknikler=[],
                beklenen=[],
                negatif=True,
                veri_kaynagi=["hr"],
            )
        )

        # S10 — Aldatma katmanı: iç keşif yapan kullanıcı tuzak paylaşımı açar, tuzak hesapla ve tuzak sunucuya oturum dener
        if self.honeytokens:
            s10 = self._pick("Operasyon", used)
            used.add(s10["idx"])
            ov[(s10["idx"], E0 + 10)].update(extra_shares=[r"\\FIN-SRV-01\bonus_2026.xlsx"], honeytoken_account=True)
            ov[(s10["idx"], E0 + 12)].update(honeytoken_device=True)
            self.ground_truth.append(
                dict(
                    senaryo="S10_tuzak_etkilesimi",
                    aktor="İç keşif / yanal hareket",
                    sid=s10["sid"],
                    baslangic=E0 + 10,
                    olay_gunu=E0 + 12,
                    teknikler=["T1039", "T1078", "T1021"],
                    beklenen=["HONEY-0019", "HONEY-0018", "HONEY-0020"],
                    veri_kaynagi=["file_server", "ad"],
                )
            )

    # ---- olay üretimi ---------------------------------------------------------
    def _add(self, rows: list, t: pd.Timestamp, cls: int, source: str, actor_raw: str, **kw) -> str:
        self._eid += 1
        eid = f"E-{self._eid:07x}"
        lag_min = {"dlp": float(self.rng.exponential(180)), "edr": float(self.rng.exponential(3))}.get(
            source, float(self.rng.exponential(5))
        )
        rows.append(
            (
                eid,
                t,
                t + pd.Timedelta(minutes=lag_min),
                cls,
                source,
                actor_raw,
                kw.get("device"),
                kw.get("src_ip"),
                kw.get("country"),
                kw.get("resource"),
                kw.get("app"),
                kw.get("action", ""),
                kw.get("outcome", "success"),
                int(kw.get("bytes_out", 0)),
                kw.get("process"),
                kw.get("parent_process"),
                kw.get("cmdline"),
                kw.get("category"),
            )
        )
        return eid

    def _lease_ip(self, leases: pd.DataFrame, sid: str, day: pd.Timestamp) -> Optional[str]:
        m = leases[(leases.sid == sid) & (leases.start <= day) & (leases.end > day)]
        return None if m.empty else str(m.iloc[0].ip)

    def _hour(self, mu: float, kappa: float) -> float:
        th = float(self.rng.vonmises(mu * 2 * math.pi / 24.0, kappa)) % (2 * math.pi)
        return th / (2 * math.pi) * 24.0

    def _ts(self, day: pd.Timestamp, hour: float) -> pd.Timestamp:
        return day + pd.Timedelta(minutes=int(min(max(hour, 0.0), 23.98) * 60))

    def _gen_user_day(self, rows: list, u: dict, d: int, leases: pd.DataFrame, lease_cache: dict) -> None:
        rng = self.rng
        day = self._day(d)
        ov = self.overrides.get((u["idx"], d), {})
        if ov.get("inactive"):
            return
        if d < u["hire_idx"]:
            return
        dow = day.dayofweek
        if u["is_service"]:
            self._gen_service(rows, u, day, d, leases, lease_cache)
            return
        p_active = 0.97 if dow < 5 else 0.08
        if not ov.get("force_active") and not ov and rng.random() > p_active:
            return
        # senaryonun zorladığı gün (S8/S9 dönüşü) haftalık mevsimsellikle zayıflatılmaz: enjeksiyon şiddeti normal iş gününe
        # göre tanımlıdır; aksi hâlde sonuç olay gününün hafta sonuna denk gelip gelmediğine (yani koşu tarihine) bağlı kalır
        season = 1.0 if ov.get("force_active") else WEEKDAY_FACTOR[dow]
        season *= 1.5 if u["dept"] in ("Finans", "Muhasebe") and day.day >= 27 else 1.0
        key = (u["sid"], d // 30)
        if key not in lease_cache:
            lease_cache[key] = self._lease_ip(leases, u["sid"], day)
        ip = lease_cache[key]
        device = ov.get("device", u["primary_device"] if rng.random() > 0.05 else u["secondary_device"])
        h0 = self._hour(ov.get("logon_hour", u["mu_hour"]), u["kappa"])
        remote = rng.random() < u["remote_prob"]
        country = "TR"
        if remote:
            country = "TR" if rng.random() > 0.01 else str(rng.choice(["DE", "NL", "GB"]))
            self._add(
                rows,
                self._ts(day, h0 - 0.1),
                OCSF_NETWORK,
                "vpn",
                u["vpn_user"],
                src_ip=ip,
                country=country,
                action="connect",
                bytes_out=int(rng.lognormal(np.log(2e6), 1)),
            )
        # AD oturumları
        n_logon = max(1, int(rng.poisson(u["lam_logon"])))
        hours = [h0] + sorted(rng.uniform(0.5, 9.0, n_logon - 1) + h0)
        for h in hours:
            self._add(
                rows,
                self._ts(day, h),
                OCSF_AUTH,
                "ad",
                u["ad_sam"],
                device=device,
                src_ip=ip,
                country=country,
                action="logon",
                outcome="success",
            )
        for _ in range(int(ov.get("failed", rng.poisson(0.15)))):
            self._add(
                rows,
                self._ts(day, h0 - 0.25 + rng.uniform(0, 0.15)),
                OCSF_AUTH,
                "ad",
                u["ad_sam"],
                device=device,
                src_ip=ip,
                country=country,
                action="logon",
                outcome="failure",
            )
        if ov.get("honeytoken_account"):  # tuzak hesapla oturum denemesi: kullanıcının KENDİ cihazından (atıf cihaz sahibine)
            self._add(
                rows,
                self._ts(day, h0 + 3.0),
                OCSF_AUTH,
                "ad",
                HONEYTOKENS_DEFAULT["hesaplar"][0],
                device=u["primary_device"],
                src_ip=ip,
                country=country,
                action="logon",
                outcome="failure",
            )
        if ov.get("honeytoken_device"):  # tuzak sunucuya oturum (yanal hareket)
            self._add(
                rows,
                self._ts(day, h0 + 4.0),
                OCSF_AUTH,
                "ad",
                u["ad_sam"],
                device=HONEYTOKENS_DEFAULT["cihazlar"][0],
                src_ip=ip,
                country=country,
                action="logon",
                outcome="success",
            )
        # Ele geçirilmiş hesap: saldırgan VPN ile başka ülkeden, yeni cihazla — gerçek kullanıcı ofiste (imkânsız seyahat)
        atk = ov.get("attacker")
        if atk:
            aip = f"10.99.{rng.integers(1, 254)}.{rng.integers(1, 254)}"
            self._add(
                rows,
                self._ts(day, atk["hour"]),
                OCSF_NETWORK,
                "vpn",
                u["vpn_user"],
                src_ip=aip,
                country=atk["country"],
                action="connect",
                bytes_out=int(rng.lognormal(np.log(5e6), 1)),
            )
            self._add(
                rows,
                self._ts(day, atk["hour"] + 0.05),
                OCSF_AUTH,
                "ad",
                u["ad_sam"],
                device=atk["device"],
                src_ip=aip,
                country=atk["country"],
                action="logon",
                outcome="success",
            )
            device_for_recon = atk["device"]
        else:
            device_for_recon = device
        # Proxy / HTTP (aktör = IP; kimlik eşleştirme katmanı çözer)
        n_http = int(rng.poisson(u["lam_http"] * season))
        apps = list(u["apps"])
        weights = list(u["app_w"])
        total_bytes = float(rng.lognormal(np.log(u["median_bytes"]), 0.5)) * season * ov.get("bytes_mult", 1.0)
        if n_http > 0:
            split = rng.dirichlet(np.ones(n_http))
            for k in range(n_http):
                app = str(rng.choice(apps, p=np.array(weights) / sum(weights)))
                self._add(
                    rows,
                    self._ts(day, h0 + rng.uniform(0.2, 9.5)),
                    OCSF_HTTP,
                    "proxy",
                    ip or "10.99.0.1",
                    src_ip=ip or "10.99.0.1",
                    app=app,
                    category=("cloud_storage" if app in CLOUD_APPS else "business"),
                    action="http",
                    bytes_out=int(total_bytes * split[k]),
                )
        for app in ov.get("extra_apps", []):
            for _ in range(3):
                self._add(
                    rows,
                    self._ts(day, h0 + rng.uniform(0.2, 9.5)),
                    OCSF_HTTP,
                    "proxy",
                    ip or "10.99.0.1",
                    src_ip=ip,
                    app=app,
                    category="cloud_storage",
                    action="http",
                    bytes_out=int(total_bytes * 0.15),
                )
        # Dosya sunucu
        n_file = int(rng.poisson(u["lam_file"] * season * ov.get("files_mult", 1.0)))
        for _ in range(n_file):
            share = str(rng.choice(u["shares"]))
            self._add(
                rows,
                self._ts(day, h0 + rng.uniform(0.1, 9.5)),
                OCSF_FILE,
                "file_server",
                u["ad_sam"],
                device=device,
                resource=share,
                action=str(rng.choice(["read", "read", "write"])),
                bytes_out=int(rng.lognormal(np.log(2e6), 1)),
            )
        for share in ov.get("extra_shares", []):
            for _ in range(int(rng.integers(1, 3))):
                self._add(
                    rows,
                    self._ts(day, h0 + rng.uniform(0.1, 9.5)),
                    OCSF_FILE,
                    "file_server",
                    u["ad_sam"],
                    device=device_for_recon,
                    resource=share,
                    action="read",
                    bytes_out=int(rng.lognormal(np.log(3e6), 1)),
                )
        for _ in range(int(ov.get("offhours_files", 0))):
            share = str(rng.choice(u["shares"]))
            self._add(
                rows,
                self._ts(day, 22.0 + rng.uniform(0, 1.9)),
                OCSF_FILE,
                "file_server",
                u["ad_sam"],
                device=device,
                resource=share,
                action="copy",
                bytes_out=int(rng.lognormal(np.log(8e6), 1)),
            )
        # EDR süreçleri (ajan çalışıyorsa cihaz kullanımdayken en az bir telemetri kaydı vardır; sessizlik senaryosunda hiç akmaz)
        if not ov.get("edr_silent"):
            for _ in range(max(1, int(rng.poisson(u["lam_proc"])))):
                self._add(
                    rows,
                    self._ts(day, h0 + rng.uniform(0.1, 9.0)),
                    OCSF_PROCESS,
                    "edr",
                    u["sid"],
                    device=device,
                    process=str(rng.choice(BENIGN_PROCS)),
                    parent_process="explorer.exe",
                    cmdline="",
                )
            for k in range(int(ov.get("recon", 0))):
                proc, cmd = RECON_CMDS[k % len(RECON_CMDS)]
                self._add(
                    rows,
                    self._ts(day, (atk["hour"] + 0.3 + k * 0.05) if atk else h0 + rng.uniform(0.5, 6)),
                    OCSF_PROCESS,
                    "edr",
                    u["sid"],
                    device=device_for_recon,
                    process=proc,
                    parent_process="cmd.exe",
                    cmdline=cmd,
                )
        # DLP (geç gelen kaynak)
        n_usb = int(ov.get("usb", 1 if rng.random() < 0.02 else 0))
        for _ in range(n_usb):
            self._add(
                rows,
                self._ts(day, h0 + rng.uniform(1, 8)),
                OCSF_FILE,
                "dlp",
                u["upn"],
                device=device,
                action="usb_copy",
                category="removable_media",
                bytes_out=int(rng.lognormal(np.log(50e6), 1)),
            )

    def _gen_service(self, rows: list, u: dict, day: pd.Timestamp, d: int, leases: pd.DataFrame, lease_cache: dict) -> None:
        rng = self.rng
        ip = f"10.14.1.{10 + u['idx'] % 200}"
        self._add(
            rows,
            self._ts(day, 2.0),
            OCSF_AUTH,
            "ad",
            u["ad_sam"],
            device=u["primary_device"],
            src_ip=ip,
            country="TR",
            action="logon",
            outcome="success",
        )
        for _ in range(int(rng.poisson(u["lam_file"]))):
            self._add(
                rows,
                self._ts(day, 2.0 + rng.uniform(0, 2)),
                OCSF_FILE,
                "file_server",
                u["ad_sam"],
                device=u["primary_device"],
                resource=str(rng.choice(u["shares"])),
                action="read",
                bytes_out=int(rng.lognormal(np.log(1e8), 0.8)),
            )
        for _ in range(int(rng.poisson(u["lam_proc"]))):
            self._add(
                rows,
                self._ts(day, 2.0 + rng.uniform(0, 2)),
                OCSF_PROCESS,
                "edr",
                u["sid"],
                device=u["primary_device"],
                process="robocopy.exe",
                parent_process="services.exe",
                cmdline="robocopy /MIR",
            )

    def build(self) -> Dataset:
        self._make_directory()
        self._apply_scenarios()
        leases = self._make_leases()
        rows: list = []
        lease_cache: dict = {}
        for u in self.users:
            for d in range(self.n_days):
                self._gen_user_day(rows, u, d, leases, lease_cache)
        # çözümlenemeyen kimlik örnekleri: misafir ağından proxy trafiği (kiralama kaydı yok)
        for _ in range(60):
            d = int(self.rng.integers(0, self.n_days))
            self._add(
                rows,
                self._ts(self._day(d), float(self.rng.uniform(8, 18))),
                OCSF_HTTP,
                "proxy",
                "10.250.0.7",
                src_ip="10.250.0.7",
                app="webmail",
                category="business",
                action="http",
                bytes_out=int(self.rng.lognormal(np.log(1e6), 1)),
            )
        events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
        events["time"] = pd.to_datetime(events["time"])
        events["received_time"] = pd.to_datetime(events["received_time"])
        events = events.sort_values("time").reset_index(drop=True)
        dir_rows = []
        for u in self.users:
            dir_rows.append(
                dict(
                    sid=u["sid"],
                    display_name=u["display_name"],
                    ad_sam=u["ad_sam"],
                    upn=u["upn"],
                    vpn_user=u["vpn_user"],
                    primary_device=u["primary_device"],
                    dept=u["dept"],
                    title_level=u["title_level"],
                    location=u["location"],
                    hire_date=self._day(u["hire_idx"]),
                    is_service=u["is_service"],
                    is_privileged=u["is_privileged"],
                    resignation_notice_date=(
                        self._day(u["resignation_notice_idx"]) if u["resignation_notice_idx"] is not None else pd.NaT
                    ),
                    resignation_date=(self._day(u["resignation_idx"]) if u["resignation_idx"] is not None else pd.NaT),
                    role_change_date=(self._day(u["role_change_idx"]) if u["role_change_idx"] is not None else pd.NaT),
                    privilege_grant_date=(
                        self._day(u["privilege_grant_idx"]) if u["privilege_grant_idx"] is not None else pd.NaT
                    ),
                )
            )
        directory = pd.DataFrame(dir_rows)
        for gt in self.ground_truth:
            gt["baslangic_tarihi"] = str(self._day(gt["baslangic"]).date())
            gt["olay_tarihi"] = str(self._day(gt["olay_gunu"]).date())
        leaves = pd.DataFrame(self.leaves, columns=["sid", "start", "end", "tur"])
        return Dataset(
            "sentetik",
            directory,
            leases,
            events,
            leaves,
            self.ground_truth,
            list(CRITICAL_ASSETS_DEFAULT),
            honeytokens=dict(HONEYTOKENS_DEFAULT) if self.honeytokens else {},
        )
