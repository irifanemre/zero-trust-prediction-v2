#!/usr/bin/env python3
"""CERT r6.2 kör koşusu — koşu ÖNCESİ hazırlık. Tespit/skor/kuyruk çıktısı ÜRETMEZ.

r5.2 hazırlığının (kor_kosu_hazirlik.py) r6.2 karşılığı; ortak yardımcılar oradan alınır. Yapılanlar:
  sayim   Yükleyicinin filtreleriyle gün gün olay sayımı, D0/D1, 90 günlük pencereler ve pencere başına
          tahmini tepe bellek (r4.2'de ölçülen olay başına bayt ile). Yalnız tarih/aktivite kolonları okunur.
  orneklem Plan §3 adım 2: ölçülen `f` ile tek oranlı katmanlı örneklem (S1–S5 + benign, tohum 42).
  bolme   70/15/15 kullanıcı bölmesi (tohum 42): yalnız LDAP kullanıcı listesi ve cevap anahtarındaki
          insider senaryo katmanıyla. Tespit çıktısına bakılmaz.

r6.2'nin r5.2'den farkı: 4000 kullanıcı, ~17 ay, senaryo başına TEK insider (S1–S5, toplam 5). Bu yüzden
yakalama oranı kaba bir metriktir (her insider %20); belgenin asıl ölçtüğü şey ölçek ve yanlış alarm oranıdır.

Kullanım:
    python scripts/kor_kosu_r62_hazirlik.py sayim --cert-dir .../cert_data/r6.2 --out .../ztp_out_r62_hazirlik
    python scripts/kor_kosu_r62_hazirlik.py bolme --cert-dir .../cert_data/r6.2
    python scripts/kor_kosu_r62_hazirlik.py orneklem --cert-dir .../cert_data/r6.2 --out .../ztp_out_r62_hazirlik
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kor_kosu_hazirlik import (  # noqa: E402
    BUDGET_GB,
    COUNT_FILTERS,
    HISTORY_DAYS,
    logon_bounds,
    windows_from_bounds,
)

from ztp.evaluation import make_user_split, save_split  # noqa: E402
from ztp.schema import DAY  # noqa: E402

LOG = logging.getLogger("kor_r62")
REPO = Path(__file__).resolve().parents[1]
R62_SPLIT = REPO / "configs" / "splits" / "cert-r6.2-kullanici-bolmesi.json"
R62_SAMPLE = REPO / "configs" / "splits" / "cert-r6.2-orneklem.json"  # plan §3 adım 2 (f, katmanlı, tohum 42)


def population(cert_dir: Path) -> tuple[list[str], dict]:
    """LDAP'ta herhangi bir ayda görülen kullanıcılar + cevap anahtarından insider senaryo katmanı."""
    users: set = set()
    for f in sorted((cert_dir / "LDAP").glob("*.csv")):
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        col = next((c for c in df.columns if c.strip().lower() == "user_id"), df.columns[1])
        users.update(df[col].astype(str).str.strip())
    answers = cert_dir.parent / "answers" / "insiders.csv"
    strata: dict = {}
    if answers.exists():
        ins = pd.read_csv(answers, dtype=str, keep_default_na=False)
        rel = ins[ins["dataset"].str.strip() == "6.2"]
        strata = {r["user"].strip(): f"S{r['scenario'].strip()}" for _, r in rel.iterrows()}
    return sorted(u for u in users if u), strata


def cmd_sayim(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cert_dir = Path(args.cert_dir)
    t0 = time.perf_counter()
    d0, d1 = logon_bounds(cert_dir)
    LOG.info("D0=%s D1=%s (%d gün)", d0.date(), d1.date(), (d1 - d0).days + 1)

    per_day: dict = {}
    rows_total: dict = {}
    for name, flt in COUNT_FILTERS.items():
        path = cert_dir / name
        if not path.exists():
            LOG.warning("yok: %s", name)
            continue
        cols = ["date"] + ([flt[0]] if flt else [])
        cnt: Counter = Counter()
        total = 0
        for ch in pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False, chunksize=2_000_000):
            total += len(ch)
            if flt:
                ch = ch[ch[flt[0]].str.strip().str.lower().eq(flt[1])]
            cnt.update(ch["date"].str[:10].value_counts().to_dict())
        per_day[name] = {str(pd.to_datetime(k, format="%m/%d/%Y").date()): int(v) for k, v in cnt.items()}
        rows_total[name] = total
        LOG.info("%s: %d satır → filtre sonrası %d (%.0f sn)", name, total, sum(cnt.values()), time.perf_counter() - t0)

    days = pd.Series({d: sum(per_day[n].get(d, 0) for n in per_day) for d in set().union(*per_day.values())}).sort_index()
    days.index = pd.to_datetime(days.index)
    keep, skipped = windows_from_bounds(d0, d1)

    r42_path = out / "r42_model.json"
    bpe = None
    if r42_path.exists():
        bpe = json.loads(r42_path.read_text(encoding="utf-8"))["olay_basina_bayt"]
    for w in keep:
        n = int(days[(days.index >= pd.Timestamp(w["tarihce_baslangic"])) & (days.index <= pd.Timestamp(w["bitis"]) + DAY)].sum())
        w["olay"] = n
        if bpe:
            w["tahmini_tepe_gb"] = round(n * bpe / 1e9, 2)
    peak = max((w.get("tahmini_tepe_gb", 0) for w in keep), default=0)
    f = 1.0 if (not peak or peak <= BUDGET_GB) else float(np.floor(min(1.0, BUDGET_GB / peak) / 0.05) * 0.05)

    res = dict(
        veri="cert-r6.2",
        D0=str(d0.date()),
        D1=str(d1.date()),
        gun=(d1 - d0).days + 1,
        degerlendirme_donemi=[str((d0 + HISTORY_DAYS * DAY).date()), str(d1.date())],
        pencereler=keep[::-1],
        atlanan_pencereler=skipped,
        satir_sayilari=rows_total,
        filtre_sonrasi={n: sum(v.values()) for n, v in per_day.items()},
        r42_olay_basina_bayt=bpe,
        en_buyuk_pencere_tahmini_gb=peak,
        orneklem_orani_f=f,
        bellek_butcesi_gb=BUDGET_GB,
        sure_sn=round(time.perf_counter() - t0),
    )
    (out / "r62_gunluk_sayim.json").write_text(json.dumps(dict(gun=per_day), ensure_ascii=False), encoding="utf-8")
    (out / "r62_sayim.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("Sayım bitti: %s", json.dumps({k: v for k, v in res.items() if k != "pencereler"}, ensure_ascii=False))
    return 0


def cmd_bolme(args: argparse.Namespace) -> int:
    users, strata = population(Path(args.cert_dir))
    gt = [dict(senaryo=f"CERT-r6.2-{s}-{u}", sid=u) for u, s in strata.items()]
    split = make_user_split(users, gt, seed=42, source="cert-r6.2; LDAP kullanıcıları (tüm aylar) + answers/insiders.csv")
    save_split(split, R62_SPLIT)
    LOG.info("Bölme: %s — %s", R62_SPLIT, json.dumps(split["meta"]["ozet"], ensure_ascii=False))
    return 0


def cmd_orneklem(args: argparse.Namespace) -> int:
    """Plan §3 adım 2: tek oranlı katmanlı örneklem. `f`, r62_bellek_olcumu.json'daki ÖLÇÜMDEN gelir."""
    olcum = json.loads((Path(args.out) / "r62_bellek_olcumu.json").read_text(encoding="utf-8"))
    f = olcum["orneklem_orani_f"]
    if f >= 1.0:
        LOG.info("f=%.2f — örneklem gerekmiyor, tüm kurum koşulur", f)
        return 0
    users, strata = population(Path(args.cert_dir))
    atama = json.loads(R62_SPLIT.read_text(encoding="utf-8"))["atama"]
    # Katman = (70/15/15 parçası × senaryo|benign). Parçanın katmana girmesi ZORUNLU: bölme de tohum 42 ile aynı
    # sıralı nüfusu karıştırdığından, yalnız senaryoya göre katmanlanan örneklem bölmeyle ÇAKIŞIR ve "rastgele %70"
    # tam olarak eğitim parçası çıkar (ölçüldü: eğitim 2654/2800, doğrulama 103/600, test 45/600). Parça katmana
    # girince her parçadan tam olarak f oranı seçilir ve çakışma yapısal olarak imkânsızlaşır.
    groups: dict = {}
    for u in users:
        groups.setdefault(f"{atama.get(u, 'atanmamis')}|{strata.get(u, 'benign')}", []).append(u)
    rng = np.random.RandomState(42)
    chosen, ozet = [], {}
    for key in sorted(groups):  # her katmandan aynı oran f (yarım yukarı yuvarlanır), katman içinde tohumlu seçim
        n = int(np.floor(f * len(groups[key]) + 0.5))
        chosen += sorted(rng.choice(groups[key], size=n, replace=False).tolist())
        ozet[key] = dict(nufus=len(groups[key]), secilen=n)
    n_ins = sum(v["secilen"] for k, v in ozet.items() if not k.endswith("|benign"))
    doc = dict(
        meta=dict(
            f=f,
            tohum=42,
            yontem=(
                "tek oranlı katmanlı örneklem (plan §3 adım 2, §3.1 tadili): katman = (70/15/15 parçası × S1–S5|benign); "
                "her katmandan floor(f·n + 0,5), katman içinde tohum 42. Parça katmana girer, çünkü bölme de aynı tohumla "
                "aynı sıralı nüfusu karıştırır; yalnız senaryoya göre katmanlamak örneklemi eğitim parçasına çakıştırıyordu."
            ),
            gerekce=dict(
                olculen_tepe_rss_gb=olcum["olculen_tepe_rss_gb"],
                beklenen_tepe_gb=olcum["beklenen_tepe_gb"],
                bellek_butcesi_gb=olcum["bellek_butcesi_gb"],
            ),
            katmanlar=ozet,
            kullanici=len(chosen),
            insider=n_ins,
            insider_orani=round(n_ins / len(chosen), 5),
            nufus_insider_orani=round(len(strata) / len(users), 5),
        ),
        kullanicilar=sorted(chosen),
    )
    R62_SAMPLE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    LOG.info("Örneklem: %s — %s", R62_SAMPLE, json.dumps(doc["meta"]["katmanlar"], ensure_ascii=False))
    if n_ins != len(strata):
        LOG.error("İnsider KAYBI: %d/%d — f çok düşük, plan §3 gözden geçirilmeli", n_ins, len(strata))
        return 1
    # Bölmenin parçaları örneklemle kesişince her parçada insider kalmalı (test parçası tek insider'lı)
    atama = json.loads(R62_SPLIT.read_text(encoding="utf-8"))["atama"]
    sec = set(chosen)
    eksik = []
    for parca in ("egitim", "dogrulama", "test"):
        tum = [u for u, p in atama.items() if p == parca]
        kalan = [u for u in tum if u in sec]
        kalan_ins = [u for u in kalan if u in strata]
        LOG.info("%s: %d → %d kullanıcı, insider %d", parca, len(tum), len(kalan), len(kalan_ins))
        if not kalan_ins:
            eksik.append(parca)
    if eksik:
        LOG.error("Örneklem bir parçanın insider'ını düşürdü: %s — plan §3 gözden geçirilmeli", ", ".join(eksik))
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("komut", choices=["sayim", "bolme", "orneklem"])
    ap.add_argument("--cert-dir", required=True)
    ap.add_argument("--out", default="./ztp_out/kor_r62_hazirlik")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return dict(sayim=cmd_sayim, bolme=cmd_bolme, orneklem=cmd_orneklem)[args.komut](args)


if __name__ == "__main__":
    sys.exit(main())
