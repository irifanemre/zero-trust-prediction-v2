"""Varlık-gün özellik çıkarımı — 13.1: tespitler varlık-gün bağlamında toplanır."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import numpy as np
import pandas as pd

from ztp.deception import TOKEN_COLUMN
from ztp.schema import CLOUD_APPS, OCSF_AUTH, OCSF_NETWORK, RECON_CMD_HINTS, RECON_PROCESSES, SENSITIVE_APPS, haversine_km

NUM_FEATURES = [
    "event_count",
    "logon_count",
    "failed_logon_count",
    "bytes_out",
    "files_accessed",
    "distinct_resources",
    "sensitive_access_count",
    "recon_process_count",
    "proc_count",
    "usb_count",
    "offhours_ratio",
    "distinct_apps_n",
    "offhours_logon_count",
]
SEASONAL_FEATURES = {"logon_count", "files_accessed", "bytes_out", "event_count", "distinct_resources"}
FEATURE_FLOOR = {
    "bytes_out": 5e6,
    "files_accessed": 1.0,
    "failed_logon_count": 0.5,
    "logon_count": 0.5,
    "distinct_resources": 0.5,
    "event_count": 2.0,
    "sensitive_access_count": 0.5,
    "recon_process_count": 0.5,
    "proc_count": 1.0,
    "usb_count": 0.5,
    "offhours_ratio": 0.05,
    "distinct_apps_n": 0.5,
    "offhours_logon_count": 0.3,
}


def extract_features(ev_all: pd.DataFrame, critical_assets: Sequence[str]) -> pd.DataFrame:
    ev = ev_all[ev_all["canonical"].notna() & ~ev_all["is_service"]].copy()
    ev["day"] = ev["time"].dt.normalize()
    hour = ev["time"].dt.hour + ev["time"].dt.minute / 60.0
    ev["hour"] = hour
    ev["offhours"] = (hour < 7) | (hour >= 20) | (ev["day"].dt.dayofweek >= 5)
    ev["is_recon"] = ev["source"].eq("edr") & (
        ev["process"].isin(RECON_PROCESSES)
        | ev["cmdline"].fillna("").str.contains("|".join(map(lambda s: s.replace("/", r"\/"), RECON_CMD_HINTS)), regex=True)
    )
    keys = ["canonical", "day"]
    g = ev.groupby(keys, sort=True)
    f = pd.DataFrame({"event_count": g.size()})
    f["offhours_ratio"] = g["offhours"].mean()
    f["bytes_out"] = g["bytes_out"].sum()
    auth = ev[(ev["class_uid"] == OCSF_AUTH) & (ev["action"] == "logon")]
    ok = auth[auth["outcome"] == "success"]
    f["logon_count"] = ok.groupby(keys).size()
    f["first_logon_hour"] = ok.groupby(keys)["hour"].min()
    f["offhours_logon_count"] = ok[ok["offhours"]].groupby(keys).size()  # ilk giriş saati normal olsa da gece tekrar giriş
    f["failed_logon_count"] = auth[auth["outcome"] == "failure"].groupby(keys).size()
    files = ev[ev["source"] == "file_server"]
    f["files_accessed"] = files.groupby(keys).size()
    f["distinct_resources"] = files.groupby(keys)["resource"].nunique()
    f["sensitive_access_count"] = files[files["resource"].isin(set(critical_assets))].groupby(keys).size()
    f["file_offhours_ratio"] = files.groupby(keys)["offhours"].mean()
    f["proc_count"] = ev[ev["source"] == "edr"].groupby(keys).size()
    f["recon_process_count"] = ev[ev["is_recon"]].groupby(keys).size()
    f["usb_count"] = ev[(ev["source"] == "dlp") & (ev["action"] == "usb_copy")].groupby(keys).size()
    f["distinct_apps_n"] = ev[ev["app"].notna()].groupby(keys)["app"].nunique()
    # v2: hassas kategori (iş arama, bulut depolama, saldırı aracı) KULLANIM SAYISI — "ilk kez" sinyali, kategoriyi
    # zaten kullanan kişide artışı göremiyordu (CERT r5.2 S2). NUM_FEATURES dışında: IF ve akran kıyası değişmez.
    f["sensitive_app_count"] = ev[ev["app"].isin(SENSITIVE_APPS)].groupby(keys).size()
    # v6-D: SIZINTI KANALI ayrı sayılır. Gerekçe (`docs/sprint-v6-on-kayit.md`, katman D): havuzlanmış sayaçta
    # niyet sinyali (iş arama) yöntem sinyalini (bulut yükleme) maskeliyor. r6.2'de kaçan S5'te ölçüldü:
    # kullanıcının havuz tabanı 11,99/gün, bulut tabanı 0,098/gün; olay günü 4 bulut olayı havuzda görünmez kaldı.
    f["cloud_app_count"] = ev[ev["app"].isin(CLOUD_APPS)].groupby(keys).size()
    # v8: KANAL BAZINDA ayrı sayaçlar (`docs/sprint-v8-kanal-kurallari-on-kayit.md`). v6-D'deki maskelemenin
    # aynısı e-postada da var: e-posta baytları genel `bytes_out` havuzunda web trafiğiyle AYNI baz çizgisini
    # paylaşıyordu. Yoğun web kullanan birinin dış e-postayla veri çıkarması kendi web tabanına gömülür.
    dis_eposta = ev[ev["app"] == "email_external"]
    f["ext_email_bytes"] = dis_eposta.groupby(keys)["bytes_out"].sum()
    f["ext_email_count"] = dis_eposta.groupby(keys).size()
    if "attachments" in ev.columns:  # CSV'den okunuyordu ama hiç kullanılmıyordu: ek SAYISI hacimden ayrı bir davranış
        f["ext_email_attachments"] = pd.to_numeric(dis_eposta["attachments"], errors="coerce").groupby(
            [dis_eposta[k] for k in keys]
        ).sum()
    # Kişisel webmail: URL_CATEGORIES'te tanımlıydı ama ne SENSITIVE_APPS ne CLOUD_APPS'te — yani tanınıp
    # görmezden geliniyordu. Kurumsal e-posta ağ geçidini atlamanın en basit yolu budur.
    f["webmail_count"] = ev[ev["app"] == "webmail"].groupby(keys).size()
    # aldatma katmanı: tuzak etkileşimi sayımı baseline'a GİRMEZ (NUM_FEATURES dışında) — deterministik sinyal
    has_token = ev[TOKEN_COLUMN].notna() if TOKEN_COLUMN in ev.columns else pd.Series(False, index=ev.index)
    f["honeytoken_count"] = ev[has_token].groupby(keys).size()
    count_cols = [c for c in NUM_FEATURES if c in f.columns] + [
        "file_offhours_ratio",
        "honeytoken_count",
        "sensitive_app_count",
        "cloud_app_count",  # v6-D: sızıntı kanalı sayacı da doldurulur (groupby.size() olaysız günde NaN üretir)
        "ext_email_bytes",  # v8: kanal bazlı sayaçlar
        "ext_email_count",
        "ext_email_attachments",
        "webmail_count",
    ]
    count_cols = [c for c in count_cols if c in f.columns]
    f[count_cols] = f[count_cols].fillna(0)
    # kümeler + kanıt (olay kimlikleri) + imkânsız seyahat: numpy döngüsü (varlık-gün başına ~15 olay)
    idx = g.indices
    A = {
        c: ev[c].values
        for c in [
            "event_id",
            "app",
            "device",
            "country",
            "resource",
            "offhours",
            "hour",
            "source",
            "outcome",
            "bytes_out",
            "is_recon",
            "action",
            "class_uid",
        ]
    }
    T = ev["time"].values.astype("datetime64[m]").astype(np.int64)
    tokens_col = ev[TOKEN_COLUMN].values if TOKEN_COLUMN in ev.columns else None
    recs = {}
    for key, pos in idx.items():
        apps, devs, ctry, ress = {}, {}, {}, {}
        evid = defaultdict(list)
        travel = []
        off_hours = []
        top_bytes = []
        tokens = set()
        for p in pos:
            eid = A["event_id"][p]
            src = A["source"][p]
            if tokens_col is not None and isinstance(tokens_col[p], str):
                tokens.add(tokens_col[p])
                kind = "honeytoken_" + tokens_col[p].split(":", 1)[0]  # kanıt tuzak türüne göre ayrılır (hesap/kaynak/cihaz)
                if len(evid[kind]) < 6:
                    evid[kind].append(eid)
            if A["app"][p] is not None and isinstance(A["app"][p], str):
                apps.setdefault(A["app"][p], eid)
            if isinstance(A["device"][p], str):
                devs.setdefault(A["device"][p], eid)
            if isinstance(A["country"][p], str):
                ctry.setdefault(A["country"][p], eid)
                if A["class_uid"][p] in (OCSF_AUTH, OCSF_NETWORK) and A["outcome"][p] == "success":
                    travel.append((T[p], A["country"][p], eid))
            if isinstance(A["resource"][p], str):
                ress.setdefault(A["resource"][p], eid)
                if len(evid["file"]) < 6:
                    evid["file"].append(eid)
            if A["offhours"][p]:
                off_hours.append(float(A["hour"][p]))
                if len(evid["offhours"]) < 6:
                    evid["offhours"].append(eid)
            if src == "ad" and A["outcome"][p] == "failure" and len(evid["failed_logon"]) < 6:
                evid["failed_logon"].append(eid)
            if src == "ad" and A["outcome"][p] == "success" and len(evid["logon"]) < 4:
                evid["logon"].append(eid)
            if A["is_recon"][p] and len(evid["recon"]) < 6:
                evid["recon"].append(eid)
            if src == "dlp" and len(evid["usb"]) < 4:
                evid["usb"].append(eid)
            if A["bytes_out"][p] > 0:
                top_bytes.append((int(A["bytes_out"][p]), eid))
        top_bytes.sort(reverse=True)
        evid["bytes"] = [e for _, e in top_bytes[:5]]
        max_speed, travel_ev = 0.0, []
        if len(travel) > 1:
            travel.sort()
            for (t1, c1, e1), (t2, c2, e2) in zip(travel, travel[1:]):
                if c1 != c2:
                    hours = max((t2 - t1) / 60.0, 1 / 60.0)
                    speed = haversine_km(c1, c2) / hours
                    if speed > max_speed:
                        max_speed, travel_ev = speed, [e1, e2]
        evid["travel"] = travel_ev
        recs[key] = dict(
            apps=frozenset(apps),
            devices=frozenset(devs),
            countries=frozenset(ctry),
            resources=frozenset(ress),
            app_events=apps,
            device_events=devs,
            country_events=ctry,
            resource_events=ress,
            evidence=dict(evid),
            offhours_hours=off_hours,
            max_travel_speed=max_speed,
            honeytokens=frozenset(tokens),
        )
    extra = pd.DataFrame.from_dict(recs, orient="index")
    extra.index = pd.MultiIndex.from_tuples(extra.index, names=keys)
    f = f.join(extra, how="left")
    f = f.reset_index().rename(columns={"canonical": "sid"})
    f["dow"] = f["day"].dt.dayofweek
    return f


DEVICE_DAY_COLUMNS = ["device", "day", "edr_count", "ad_users"]


def extract_device_day(ev_all: pd.DataFrame) -> pd.DataFrame:
    """Cihaz-gün türev tablosu: EDR olay sayısı ve o gün cihazdan başarılı AD oturumu açan kullanıcılar (kullanıcı → sayı).
    Ajan sessizliği (#10), cihaz sahipliği/paylaşımlılık ve 'başkasının cihazı' sinyalleri yalnızca bu tabloya dayanır;
    ham olaylar saklanmadan artımlı çalışmayı mümkün kılar (Prensip 1 maliyet hunisi)."""
    ev = ev_all[ev_all["device"].notna()]
    day = ev["time"].dt.normalize()
    edr = ev[ev["source"] == "edr"].groupby([ev["device"], day]).size().rename("edr_count")
    ad = ev[(ev["source"] == "ad") & ev["canonical"].notna() & (ev["outcome"] == "success") & (ev["action"] == "logon")]
    users = (
        ad.groupby([ad["device"], ad["time"].dt.normalize(), ad["canonical"]])
        .size()
        .groupby(level=[0, 1])
        .agg(lambda s: {k[2]: int(v) for k, v in s.items()})
        .rename("ad_users")
    )
    out = pd.concat([edr, users], axis=1).reset_index()
    out.columns = DEVICE_DAY_COLUMNS
    out["edr_count"] = out["edr_count"].fillna(0).astype(int)
    out["ad_users"] = out["ad_users"].apply(lambda v: v if isinstance(v, dict) else {})
    return out
