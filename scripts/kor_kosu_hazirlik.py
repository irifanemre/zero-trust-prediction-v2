#!/usr/bin/env python3
"""CERT r5.2 kör koşusu — koşu ÖNCESİ hazırlık (ön kayıt planı §3, §6: `git show kor-kosu-r5.2-hazir:docs/kor-kosu-plani.md`). r5.2'de tespit/skor/kuyruk üretmez.

Alt komutlar:
    r42-model   r4.2 temel koşusu (cert_eval.py ile aynı ayarlar) → birincil LR modeli (C = 0,001, tamamlayıcı protokolün
                eğitim parçası, tüm günler), doğrulama eşiği, tepe bellek, olay sayısı ve r4.2 kural tetikleme sayıları.
    r52-sayim   r5.2 log satırlarını yükleyicinin filtreleriyle gün gün sayar (yalnız tarih/aktivite kolonları okunur).
                Pencereler mekanik hesaplanır; r4.2 olay başına bellekle her pencerenin tepe belleği tahmin edilir.
    r52-bolme   r5.2 kullanıcı bölmesi (70/15/15, tohum 42): yalnız LDAP kullanıcı listesi ve cevap anahtarıyla.
    r52-orneklem  Plan §3.2: tahmini tepe 12 GB'ı aşarsa tek oranlı katmanlı örneklem (S1–S4 + benign, oran f, tohum 42).

Kullanım:
    python scripts/kor_kosu_hazirlik.py r42-model --cert-dir C:/data/cert_r4.2/r4.2 --out C:/data/ztp_out/kor_r52_hazirlik
    python scripts/kor_kosu_hazirlik.py r52-sayim --cert-dir C:/data/cert_r5.2/r5.2 --out C:/data/ztp_out/kor_r52_hazirlik
    python scripts/kor_kosu_hazirlik.py r52-bolme --cert-dir C:/data/cert_r5.2/r5.2
    python scripts/kor_kosu_hazirlik.py r52-orneklem --cert-dir C:/data/cert_r5.2/r5.2 --out C:/data/ztp_out/kor_r52_hazirlik
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from ztp.config import TenantConfig
from ztp.data.cert import load_cert_dataset
from ztp.detection.catalog import load_catalog
from ztp.evaluation import PARTS, f1_at, f1_best, load_or_create_split, make_user_split, save_split, scenario_table
from ztp.prediction_model import LogisticModel, calibration_report, rows_to_matrix
from ztp.schema import DAY

LOG = logging.getLogger("kor_kosu_hazirlik")
REPO = Path(__file__).resolve().parents[1]
R42_SPLIT = REPO / "configs" / "splits" / "cert-r4.2-kullanici-bolmesi.json"
R52_SPLIT = REPO / "configs" / "splits" / "cert-r5.2-kullanici-bolmesi.json"
R52_SAMPLE = REPO / "configs" / "splits" / "cert-r5.2-orneklem.json"
MODEL_PATH = REPO / "configs" / "models" / "kor-r52-birincil-lr.json"
PRIMARY_C = 0.001  # r4.2 tamamlayıcı protokolünde doğrulama log-loss'uyla seçilen değer (plan §4.6)
WINDOW_DAYS, WARMUP_DAYS = 90, 21
HISTORY_DAYS = 90 + WARMUP_DAYS  # uzun pencere + ısınma: pencere başlangıcından önce gereken tarihçe
BUDGET_GB = 12.0


class PeakMemory:
    """Süreç bellek tepesi: Windows'ta işletim sisteminin peak_wset'i, değilse 1 sn'lik örnekleme."""

    def __init__(self) -> None:
        self.proc = psutil.Process()
        self.peak = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._poll, daemon=True)
        self._t.start()

    def _poll(self) -> None:
        while not self._stop.wait(1.0):
            self.peak = max(self.peak, self.proc.memory_info().rss)

    def gb(self) -> float:
        mi = self.proc.memory_info()
        return round(max(self.peak, mi.rss, getattr(mi, "peak_wset", 0)) / 1e9, 2)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------------------------ r4.2
def cmd_r42_model(args: argparse.Namespace) -> int:
    from ztp.pipeline import ZeroTrustPredictionPipeline

    out = Path(args.out)
    mem = PeakMemory()
    t0 = time.perf_counter()
    cert_dir = Path(args.cert_dir)
    end = pd.Timestamp("2010-11-30")
    cfg = TenantConfig(tenant_id="cert-r42", alarm_budget_per_day=10)
    start_hist = end - (cfg.long_window_days + WARMUP_DAYS + WINDOW_DAYS) * DAY
    start = end - (WINDOW_DAYS - 1) * DAY
    data = load_cert_dataset(str(cert_dir), start_hist, end, answers_dir=str(cert_dir.parent / "answers"))
    load_gb = mem.gb()
    cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
    split, _ = load_or_create_split(R42_SPLIT, data.directory["sid"].astype(str).tolist(), data.ground_truth, seed=42)
    n_events = len(data.events)
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), out / "r42")
    pipe.run(start, end, WARMUP_DAYS)
    peak_gb = mem.gb()
    rows = pipe.pred.rows
    y = np.asarray(pipe.metrics.outcomes(rows), dtype=int)
    X = rows_to_matrix(rows)
    part = np.array([split["atama"].get(r["sid"], "") for r in rows])
    masks = {k: part == k for k in PARTS}  # tamamlayıcı protokol: kullanıcı ayrık, tüm günler
    model = LogisticModel.fit(X[masks["egitim"]], y[masks["egitim"]], C=PRIMARY_C)
    _, th = f1_best(model.predict_many(X[masks["dogrulama"]]), y[masks["dogrulama"]])
    pt = model.predict_many(X[masks["test"]])
    test = calibration_report(pt, y[masks["test"]])
    test.pop("guvenilirlik", None)
    test["f1_dogrulama_esiginde"] = round(f1_at(pt, y[masks["test"]], th), 3)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(
        model=model.to_dict(),
        C=PRIMARY_C,
        esik=round(th, 4),
        egitim=dict(
            veri="cert-r4.2; end=2010-11-30 days=90 warmup=21",
            bolme=str(R42_SPLIT.relative_to(REPO)).replace("\\", "/"),
            protokol="tamamlayıcı: eğitim parçasının kullanıcıları, tüm günler (embargo yok); eşik doğrulama parçasında en iyi F1",
            satir=int(masks["egitim"].sum()),
            pozitif=int(y[masks["egitim"]].sum()),
        ),
        r42_test_kontrol=test,
    )
    # depodaki LF ile aynı bayt → plana yazılan sha256 her platformda tutar
    MODEL_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    cov = scenario_table(pipe.metrics)
    res = dict(
        olay=n_events,
        kullanici=len(data.directory),
        yukleme_sonrasi_bellek_gb=load_gb,
        tepe_bellek_gb=peak_gb,
        olay_basina_bayt=round(peak_gb * 1e9 / n_events, 1),
        sure_sn=round(time.perf_counter() - t0),
        kural_tetikleme=dict(sorted(pipe.metrics.rule_hits.items())),
        kapsama=dict(Counter(r["sonuc"].split(" [")[0] for r in cov)),
        model_dosyasi=str(MODEL_PATH),
        model_sha256=sha256_file(MODEL_PATH),
        model_C=PRIMARY_C,
        model_esik=doc["esik"],
        r42_test_kontrol=test,
    )
    (out / "r42_model.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    LOG.info(
        "r4.2 bitti: %s", json.dumps({k: v for k, v in res.items() if k != "kural_tetikleme"}, ensure_ascii=False, default=str)
    )
    return 0


# ------------------------------------------------------------------------------------------------------------ r5.2
def windows_from_bounds(d0: pd.Timestamp, d1: pd.Timestamp) -> tuple[list[dict], list[dict]]:
    """Plan §3: D1'den geriye ardışık 90 günlük pencereler; başlangıcı D0 + 111'den önceye düşen pencere atlanır."""
    keep, skipped = [], []
    end = d1
    while True:
        start = end - (WINDOW_DAYS - 1) * DAY
        w = dict(baslangic=str(start.date()), bitis=str(end.date()), tarihce_baslangic=str((start - HISTORY_DAYS * DAY).date()))
        if start < d0 + HISTORY_DAYS * DAY:
            skipped.append(w)
            break
        keep.append(w)
        end = start - DAY
    return keep, skipped


def logon_bounds(cert_dir: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    """D0/D1: logon.csv'nin ilk ve son günü (tüm dosya taranır; sıralı olduğu varsayılmaz)."""
    lo = hi = None
    for ch in pd.read_csv(cert_dir / "logon.csv", usecols=["date"], dtype=str, chunksize=2_000_000):
        d = pd.to_datetime(ch["date"].str[:10], format="%m/%d/%Y")
        lo = d.min() if lo is None else min(lo, d.min())
        hi = d.max() if hi is None else max(hi, d.max())
    return lo.normalize(), hi.normalize()


# yükleyicinin (src/ztp/data/cert.py) satır filtreleri: dosya → (okunacak ek kolon, tutulan değer)
COUNT_FILTERS = {
    "logon.csv": None,
    "device.csv": ("activity", "connect"),
    "http.csv": None,
    "email.csv": ("activity", "send"),
    "file.csv": ("to_removable_media", "true"),
}


def cmd_r52_sayim(args: argparse.Namespace) -> int:
    out = Path(args.out)
    cert_dir = Path(args.cert_dir)
    t0 = time.perf_counter()
    d0, d1 = logon_bounds(cert_dir)
    per_day: dict = {}
    rows_total: dict = {}
    for name, flt in COUNT_FILTERS.items():
        cols = ["date"] + ([flt[0]] if flt else [])
        cnt: Counter = Counter()
        total = 0
        for ch in pd.read_csv(cert_dir / name, usecols=cols, dtype=str, keep_default_na=False, chunksize=2_000_000):
            total += len(ch)
            if flt:
                ch = ch[ch[flt[0]].str.strip().str.lower().eq(flt[1])]
            cnt.update(ch["date"].str[:10].value_counts().to_dict())
        per_day[name] = {str(pd.to_datetime(k, format="%m/%d/%Y").date()): v for k, v in cnt.items()}
        rows_total[name] = total
        LOG.info("%s: %d satır, filtre sonrası %d (%.0f sn)", name, total, sum(cnt.values()), time.perf_counter() - t0)
    days = pd.Series({d: sum(per_day[n].get(d, 0) for n in per_day) for d in set().union(*per_day.values())}).sort_index()
    days.index = pd.to_datetime(days.index)
    keep, skipped = windows_from_bounds(d0, d1)
    sayim = out / "r52_gunluk_sayim.json"  # r4.2 koşusu bitmemişse tahmin bu dosyadan yeniden hesaplanır
    sayim.write_text(json.dumps(dict(D0=str(d0.date()), D1=str(d1.date()), satir=rows_total, gun=per_day)), encoding="utf-8")
    r42_path = out / "r42_model.json"
    while not r42_path.exists():
        LOG.info("r4.2 tepe bellek ölçümü bekleniyor (%s)", r42_path)
        time.sleep(60)
    r42 = json.loads(r42_path.read_text(encoding="utf-8"))
    bpe = r42["olay_basina_bayt"]
    for w in keep:
        # yükleyici [tarihçe başlangıcı, bitiş + 1 gün] aralığını okur
        n = int(days[(days.index >= pd.Timestamp(w["tarihce_baslangic"])) & (days.index <= pd.Timestamp(w["bitis"]) + DAY)].sum())
        w["olay"] = n
        w["tahmini_tepe_gb"] = round(n * bpe / 1e9, 2)
    peak = max(w["tahmini_tepe_gb"] for w in keep)
    f = 1.0 if peak <= BUDGET_GB else float(np.floor(min(1.0, BUDGET_GB / peak) / 0.05) * 0.05)
    res = dict(
        D0=str(d0.date()),
        D1=str(d1.date()),
        degerlendirme_donemi=[str((d0 + HISTORY_DAYS * DAY).date()), str(d1.date())],
        pencereler=keep[::-1],
        atlanan_pencereler=skipped,
        satir_sayilari=rows_total,
        filtre_sonrasi=dict((n, sum(v.values())) for n, v in per_day.items()),
        r42_olay_basina_bayt=bpe,
        r42_tepe_bellek_gb=r42["tepe_bellek_gb"],
        en_buyuk_pencere_tahmini_gb=peak,
        orneklem_orani_f=f,
        sure_sn=round(time.perf_counter() - t0),
    )
    (out / "r52_sayim.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("r5.2 sayım: %s", json.dumps(res, ensure_ascii=False))
    return 0


def cmd_r52_bolme(args: argparse.Namespace) -> int:
    users, strata = r52_population(Path(args.cert_dir))
    gt = [dict(senaryo=f"CERT-r5.2-{s}-{u}", sid=u) for u, s in strata.items()]
    split = make_user_split(users, gt, seed=42, source="cert-r5.2; LDAP kullanıcıları (tüm aylar) + answers/insiders.csv")
    save_split(split, R52_SPLIT)
    LOG.info("Bölme: %s — %s", R52_SPLIT, json.dumps(split["meta"]["ozet"], ensure_ascii=False))
    return 0


def r52_population(cert_dir: Path) -> tuple[list[str], dict]:
    """LDAP'ta herhangi bir ayda görülen kullanıcılar ve r5.2 insider'larının senaryo katmanı (S1–S4)."""
    users = set()
    for f in sorted((cert_dir / "LDAP").glob("*.csv")):
        users |= set(pd.read_csv(f, usecols=["user_id"])["user_id"].astype(str))
    ins = pd.read_csv(cert_dir.parent / "answers" / "insiders.csv")
    ins = ins[ins["dataset"].astype(str) == "5.2"]
    return sorted(users), {r.user: f"S{r.scenario}" for r in ins.itertuples(index=False)}


def cmd_r52_orneklem(args: argparse.Namespace) -> int:
    f = json.loads((Path(args.out) / "r52_sayim.json").read_text(encoding="utf-8"))["orneklem_orani_f"]
    users, strata = r52_population(Path(args.cert_dir))
    groups: dict = {}
    for u in users:
        groups.setdefault(strata.get(u, "benign"), []).append(u)
    rng = np.random.RandomState(42)
    chosen, ozet = [], {}
    for key in sorted(groups):  # her katmandan aynı oran f (yarım yukarı yuvarlanır), katman içinde tohumlu seçim
        n = int(np.floor(f * len(groups[key]) + 0.5))
        chosen += sorted(rng.choice(groups[key], size=n, replace=False).tolist())
        ozet[key] = dict(nufus=len(groups[key]), secilen=n)
    n_ins = sum(v["secilen"] for k, v in ozet.items() if k != "benign")
    doc = dict(
        meta=dict(
            f=f,
            tohum=42,
            yontem="tek oranlı katmanlı örneklem (plan §3.2): katmanlar S1–S4 ve benign; her katmandan floor(f·n + 0,5)",
            katmanlar=ozet,
            kullanici=len(chosen),
            insider=n_ins,
            insider_orani=round(n_ins / len(chosen), 4),
            nufus_insider_orani=round(len(strata) / len(users), 4),
        ),
        kullanicilar=sorted(chosen),
    )
    R52_SAMPLE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    LOG.info("Örneklem: %s — %s", R52_SAMPLE, json.dumps(doc["meta"], ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("komut", choices=["r42-model", "r52-sayim", "r52-bolme", "r52-orneklem"])
    ap.add_argument("--cert-dir", required=True)
    ap.add_argument("--out", default="./ztp_out/kor_r52_hazirlik")
    args = ap.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(Path(args.out) / f"{args.komut}.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    cmds = dict(r42_model=cmd_r42_model, r52_sayim=cmd_r52_sayim, r52_bolme=cmd_r52_bolme, r52_orneklem=cmd_r52_orneklem)
    return cmds[args.komut.replace("-", "_")](args)


if __name__ == "__main__":
    sys.exit(main())
