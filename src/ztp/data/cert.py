"""CERT Insider Threat Test Dataset (SEI/CMU) yükleyicisi — 19.2 birincil doğrulama kaynağı."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from ztp.data.dataset import Dataset
from ztp.schema import DAY, EVENT_COLUMNS, OCSF_AUTH, OCSF_EMAIL, OCSF_FILE, OCSF_HTTP

LOG = logging.getLogger(__name__)


# Veri yolu repoya gömülmez: CERT ~20 GB'tır ve repo dışında (ör. OneDrive dışı bir diskte) durur.
CERT_PATH_ENV = "ZTP_CERT_PATH"


def resolve_cert_dir(explicit: Optional[str] = None) -> Path:
    """CERT sürüm dizinini bulur: açık yol > `ZTP_CERT_PATH` ortam değişkeni.

    Yol ya sürüm dizinini (`.../r4.2`: içinde `logon.csv` ve `LDAP/`) ya da onu içeren kök dizini (`.../cert_r4.2`)
    gösterebilir; kökte `logon.csv` içeren tek bir `r*` alt dizini varsa o seçilir. Sürüm dizin ADINDAN okunur
    (`load_cert_dataset` cevap anahtarını `dataset == "4.2"` ile süzer) — bu yüzden dönen dizin her zaman `r*` adlıdır;
    adı `r` ile başlamayan bir dizin açık hata verir (sessizce sıfır insider üretmesin — Prensip 5)."""
    raw = explicit or os.environ.get(CERT_PATH_ENV, "")
    if not raw:
        raise FileNotFoundError(
            f"CERT yolu verilmedi: --cert-dir <sürüm dizini> kullanın ya da {CERT_PATH_ENV} ortam değişkenini ayarlayın (README)."
        )
    p = Path(raw).expanduser()
    if not p.is_dir():
        raise FileNotFoundError(f"CERT dizini bulunamadı: {p}")
    if (p / "logon.csv").exists():
        cand = p
    else:
        found = sorted(d for d in p.iterdir() if d.is_dir() and d.name.startswith("r") and (d / "logon.csv").exists())
        if not found:
            raise FileNotFoundError(f"{p} içinde CERT sürüm dizini (logon.csv içeren r* klasörü) bulunamadı")
        if len(found) > 1:
            names = ", ".join(d.name for d in found)
            raise FileNotFoundError(f"{p} içinde birden çok sürüm var ({names}); sürüm dizinini doğrudan verin")
        cand = found[0]
    if not cand.name.startswith("r"):
        raise FileNotFoundError(
            f"Sürüm dizini adı 'r<sürüm>' olmalı (ör. r4.2), bulunan: {cand.name} — sürüm cevap anahtarını süzmek için adından okunur"
        )
    return cand


URL_CATEGORIES = [
    (
        "cloud_storage",
        (
            "wikileaks",
            "dropbox",
            "box.com",
            "drive.google",
            "mega.",
            "mediafire",
            "4shared",
            "onedrive",
            "wetransfer",
            "sendspace",
            "rapidshare",
            "hightail",
            "filedropper",
            "pastebin",
        ),
    ),
    (
        "job_search",
        (
            "job",
            "career",
            "monster.com",
            "indeed",
            "glassdoor",
            "dice.com",
            "simplyhired",
            "linkedin",
            "craigslist",
            "recruit",
            "hiring",
            "resume",
        ),
    ),
    (
        "hacking_tools",
        (
            "keylog",
            "keystroke",
            "spyware",
            "hack",
            "crack",
            "exploit",
            "malware",
            "rootkit",
            "stealth",
            "sniff",
            "spector",
            "monitoring",
            "surveillance",
            "trojan",
            "backdoor",
        ),
    ),
    ("webmail", ("gmail", "yahoo", "hotmail", "aol.com", "mail.", "outlook.com")),
    ("social", ("facebook", "twitter", "youtube", "myspace", "reddit", "flickr")),
]
CERT_SCENARIO_MAP = {
    1: dict(
        aktor="Kızgın çalışan (mesai dışı + USB + wikileaks yükleme, ayrılış)",
        teknikler=["T1078", "T1052", "T1567"],
        beklenen=["UEBA-0001", "UEBA-0017", "UEBA-0002"],
    ),
    2: dict(
        aktor="Fırsatçı (iş arama siteleri + USB ile veri hırsızlığı, ayrılış)",
        teknikler=["T1052"],
        beklenen=["UEBA-0002", "UEBA-0017"],
    ),
    3: dict(
        aktor="Kızgın sistem yöneticisi (keylogger, amirinin makinesi, toplu e-posta)",
        teknikler=["T1078", "T1204", "T1021"],
        beklenen=["UEBA-0005", "UEBA-0002"],
    ),
    4: dict(
        aktor="Başka kullanıcının makinesinden dosya arama, eve e-posta (3 ay artan)",
        teknikler=["T1078", "T1021", "T1567"],
        beklenen=["UEBA-0005", "UEBA-0003", "PRED-0012"],
    ),
    5: dict(aktor="İşten çıkarma sonrası Dropbox'a yükleme", teknikler=["T1567"], beklenen=["UEBA-0002", "UEBA-0003"]),
}


def _url_category(url: str) -> Optional[str]:
    u = str(url).lower()
    for cat, keys in URL_CATEGORIES:
        if any(k in u for k in keys):
            return cat
    return None


def load_cert_dataset(
    cert_dir: str, start: pd.Timestamp, end: pd.Timestamp, max_users: Optional[int] = None, answers_dir: Optional[str] = None
) -> Dataset:
    """CERT Insider Threat Test Dataset (r1 … r6.2) → OCSF-lite (19.2 birincil doğrulama kaynağı, ADR-004).
    Farklılıklar sürüme göre ele alınır: r1'de kullanıcı 'DTAA/XXX0001', http.csv başlıksız, LDAP kolonları büyük harf;
    r4.2+'da email.csv/file.csv/psychometric.csv vardır. psychometric.csv BİLİNÇLİ olarak okunmaz (4.2 etik sınır /
    20.1 amaçla sınırlılık: kişilik/verimlilik verisi skorlamaya girmez)."""
    base = Path(cert_dir)
    release = base.name.lstrip("r")
    t0 = time.perf_counter()
    # ---- LDAP (aylık dizin anlık görüntüleri) → İK/AD dizini -------------------------------------------------
    ldap_files = sorted((base / "LDAP").glob("*.csv"))
    if not ldap_files:
        raise FileNotFoundError("CERT LDAP dizini bulunamadı; AD/IdP olmadan akran grubu kurulamaz (11.1: zorunlu kaynak).")
    frames = []
    for f in ldap_files:
        df = pd.read_csv(f)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df["month"] = f.stem
        frames.append(df)
    ldap = pd.concat(frames, ignore_index=True)
    first_month = ldap.groupby("user_id")["month"].min()
    last_month = ldap.groupby("user_id")["month"].max()
    latest = ldap.drop_duplicates("user_id", keep="last").set_index("user_id")
    months = sorted(ldap["month"].unique())
    role = latest.get("role", pd.Series("", index=latest.index)).astype(str)

    def level(r: str) -> int:
        r = r.lower()
        if any(k in r for k in ("director", "vp", "president", "council", "counsel")):
            return 4
        if any(k in r for k in ("manager", "manger", "it admin", "itadmin")):
            return 3
        if any(k in r for k in ("foreman", "lead", "supervisor", "senior")):
            return 2
        return 1

    dept = latest["department"] if "department" in latest else role
    loc = latest["business_unit"] if "business_unit" in latest else pd.Series("HQ", index=latest.index)
    hire = first_month.reindex(latest.index).map(lambda m: (start - 400 * DAY) if m == months[0] else pd.Timestamp(m + "-01"))
    depart = last_month.reindex(latest.index).map(
        lambda m: pd.NaT if m == months[-1] else (pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(1))
    )
    directory = pd.DataFrame(
        dict(
            sid=latest.index,
            display_name=latest["employee_name"].values,
            ad_sam=latest.index,
            upn=latest["email"].values,
            vpn_user=latest.index,
            primary_device=None,
            dept=dept.values,
            title_level=role.map(level).values,
            location=loc.values,
            hire_date=hire.values,
            is_service=False,
            is_privileged=role.str.contains("admin", case=False).values,
            resignation_notice_date=pd.NaT,
            resignation_date=depart.values,  # ayrılış LDAP'tan SONRADAN görülür; bildirim olarak KULLANILMAZ
            role_change_date=pd.NaT,
            privilege_grant_date=pd.NaT,
        )
    ).reset_index(drop=True)
    # ---- Cevap anahtarı (kapsama/erkenlik ve etiketli precision için) ----------------------------------------------
    gt = []
    insiders_path = Path(answers_dir) / "insiders.csv" if answers_dir else base / "answers" / "insiders.csv"
    if insiders_path.exists():
        ins = pd.read_csv(insiders_path)
        ins = ins[ins["dataset"].astype(str) == release]
        for r in ins.itertuples(index=False):
            s0, s1 = pd.to_datetime(r.start, format="mixed"), pd.to_datetime(r.end, format="mixed")
            if s1 < start - 7 * DAY or s0 > end + 7 * DAY:
                continue
            m = CERT_SCENARIO_MAP.get(int(r.scenario), dict(aktor="?", teknikler=[], beklenen=[]))
            gt.append(
                dict(
                    senaryo=f"CERT-r{release}-S{r.scenario}-{r.user}",
                    aktor=m["aktor"],
                    sid=r.user,
                    baslangic_tarihi=str(s0.date()),
                    olay_tarihi=str(s1.date()),
                    pencere=[str(s0.date()), str(s1.date())],
                    teknikler=m["teknikler"],
                    beklenen=m["beklenen"],
                    veri_kaynagi=["ad", "dlp", "proxy", "email", "file_server"],
                )
            )
    # ---- kullanıcı alt kümesi (varsa cevap anahtarındaki kullanıcılar korunur) -----------------------------------
    users = set(directory["sid"])
    if max_users and len(users) > max_users:
        keep = {g["sid"] for g in gt}
        rest = [u for u in sorted(users) if u not in keep]
        rng = np.random.default_rng(0)
        keep |= set(rng.choice(rest, size=max(0, max_users - len(keep)), replace=False))
        users = keep
        directory = directory[directory["sid"].isin(users)].reset_index(drop=True)

    # ---- log dosyaları (parça parça, pencere filtresi, vektörel dönüşüm) -------------------------------------------
    def read_window(name: str, cols: List[str]) -> pd.DataFrame:
        p = base / name
        if not p.exists():
            LOG.warning("CERT dosyası yok: %s — ilgili tespitler kısıtlı çalışır (11.1)", name)
            return pd.DataFrame(columns=cols)
        with open(p, encoding="utf-8", errors="ignore") as fh:
            has_header = fh.readline().lower().startswith("id,")
        parts = []
        for ch in pd.read_csv(
            p,
            header=0 if has_header else None,
            names=None if has_header else cols,
            usecols=cols,
            chunksize=1_000_000,
            dtype=str,
            keep_default_na=False,
            encoding_errors="ignore",
        ):
            ch["date"] = pd.to_datetime(ch["date"], format="%m/%d/%Y %H:%M:%S", errors="coerce")
            ch = ch[(ch["date"] >= start) & (ch["date"] <= end + DAY)]
            if ch.empty:
                continue
            ch["user"] = ch["user"].str.split("/").str[-1]
            ch = ch[ch["user"].isin(users)]
            parts.append(ch)
        out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
        LOG.info("CERT %s: %d satır (pencere içi)", name, len(out))
        return out

    def frame(df: pd.DataFrame, cls: int, source: str, **cols) -> pd.DataFrame:
        n = len(df)
        base_cols = dict(
            event_id=df["id"].values if "id" in df else [f"E-{source[:2]}{i:07x}" for i in range(n)],
            time=df["date"].values,
            received_time=df["date"].values,
            class_uid=cls,
            source=source,
            actor_raw=df["user"].values,
            device=df["pc"].values if "pc" in df else None,
            src_ip=None,
            country=None,
            resource=None,
            app=None,
            action="",
            outcome="success",
            bytes_out=0,
            process=None,
            parent_process=None,
            cmdline=None,
            category=None,
        )
        base_cols.update(cols)
        return pd.DataFrame(base_cols, columns=EVENT_COLUMNS)

    frames = []
    lg = read_window("logon.csv", ["id", "date", "user", "pc", "activity"])
    if len(lg):
        frames.append(frame(lg, OCSF_AUTH, "ad", action=lg["activity"].str.lower().values))
    dv = read_window("device.csv", ["id", "date", "user", "pc", "activity"])
    dv = dv[dv["activity"].str.lower().eq("connect")] if len(dv) else dv
    if len(dv):
        frames.append(frame(dv, OCSF_FILE, "dlp", action="usb_copy", category="removable_media"))
    http_cols = ["id", "date", "user", "pc", "url"]  # 'content' (sayfa metni) okunmaz: hacim vekili değil, veri minimizasyonu
    ht = read_window("http.csv", http_cols)
    if len(ht):
        cat = ht["url"].map(_url_category)
        frames.append(
            frame(
                ht,
                OCSF_HTTP,
                "proxy",
                app=cat.values,
                category=cat.fillna("web").values,
                action="http",
                bytes_out=(ht["content"].str.len().values if "content" in ht else 0),
            )
        )
        del ht
    em = read_window("email.csv", ["id", "date", "user", "pc", "to", "cc", "bcc", "size", "attachments"])
    if len(em):
        rcpt = (em["to"].fillna("") + ";" + em["cc"].fillna("") + ";" + em["bcc"].fillna("")).str.lower()
        # dış alıcı: dtaa.com dışında en az bir adres
        ext = rcpt.str.split(";").map(lambda xs: any("@" in x and not x.strip().endswith("@dtaa.com") for x in xs))
        frames.append(
            frame(
                em,
                OCSF_EMAIL,
                "email",
                action="send",
                app=np.where(ext, "email_external", "email_internal"),
                category=np.where(ext, "email_external", "email_internal"),
                bytes_out=pd.to_numeric(em["size"], errors="coerce").fillna(0).astype(int).values,
            )
        )
    fl = read_window("file.csv", ["id", "date", "user", "pc", "filename", "content"])
    if len(fl):
        ext_ = fl["filename"].str.extract(r"\.([A-Za-z0-9]+)$")[0].fillna("bin").str.lower()
        # r4.2 file.csv = taşınabilir medyaya dosya kopyası; dosya adı saklanmaz, uzantı kategori olur (20.1 veri minimizasyonu)
        frames.append(
            frame(
                fl,
                OCSF_FILE,
                "file_server",
                category=("ext:" + ext_).values,
                action="copy",
                bytes_out=fl["content"].str.len().values,
            )
        )  # boyut vekili; içerik saklanmaz
    events = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=EVENT_COLUMNS)
    events["time"] = pd.to_datetime(events["time"])
    events["received_time"] = pd.to_datetime(events["received_time"])
    events["bytes_out"] = pd.to_numeric(events["bytes_out"], errors="coerce").fillna(0).astype(np.int64)
    events = events.sort_values("time").reset_index(drop=True)
    pcs = events[events["source"] == "ad"].groupby("actor_raw")["device"].agg(lambda s: s.mode().iloc[0] if len(s) else None)
    directory["primary_device"] = directory["sid"].map(pcs)
    leases = pd.DataFrame(columns=["ip", "sid", "start", "end"])
    leaves = pd.DataFrame(columns=["sid", "start", "end", "tur"])
    LOG.info(
        "CERT r%s yüklendi: %d kullanıcı, %d olay, %d cevap anahtarı kaydı (%.0f sn)",
        release,
        len(directory),
        len(events),
        len(gt),
        time.perf_counter() - t0,
    )
    return Dataset(f"cert-r{release}", directory, leases, events, leaves, gt, [])
