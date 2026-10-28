#!/usr/bin/env python3
"""Bellek optimizasyonunun kabul ölçütü: r4.2'de tespit/kuyruk çıktısı DEĞİŞMEMELİ.

Ön kayıt §2, ayrıştırıcı uyarlamasının şartı: "Uyarlama r4.2'de koşulur. r4.2'nin kural tetikleme sayıları ve
kapsama sonuçları birebir aynı kalmalıdır." Bu betik aynı veriyi iki kez koşar — optimizasyon açık ve kapalı —
ve kuyruk, kural tetiklemeleri, kapsama ile vaka hacmini karşılaştırır. Fark varsa optimizasyon geri alınır.

Kullanım: python scripts/bellek_esdegerlik.py --cert-dir .../cert_data/r4.2 --out /tmp/esdegerlik
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from ztp.config import TenantConfig
from ztp.data import cert as cert_mod
from ztp.detection.catalog import load_catalog
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.schema import DAY

LOG = logging.getLogger("esdegerlik")


def kosu(cert_dir: str, answers: str, out: Path, etiket: str, compact: bool, days: int, warmup: int, budget: int) -> dict:
    orijinal = cert_mod._compact
    if not compact:
        cert_mod._compact = lambda ev: ev  # optimizasyon kapalı: eski davranış
    try:
        end = pd.Timestamp("2010-11-30")
        start = end - (days - 1) * DAY
        start_hist = end - (90 + warmup + days) * DAY
        t0 = time.perf_counter()
        data = cert_mod.load_cert_dataset(cert_dir, start_hist, end, answers_dir=answers)
        bellek = data.events.memory_usage(deep=True).sum()
        cfg = TenantConfig(tenant_id=f"esd-{etiket}", alarm_budget_per_day=budget, llm_backend="none", sinks=[])
        cfg.available_sources = tuple(sorted(set(data.events["source"].astype(str).unique()) | {"hr"}))
        pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), out)
        pipe.run(start, end, warmup)
        res = dict(
            etiket=etiket,
            olay=len(data.events),
            bellek_gb=round(bellek / 1e9, 3),
            bayt_olay=round(bellek / max(len(data.events), 1), 1),
            sure_sn=round(time.perf_counter() - t0),
            kuyruk={str(d.date()): list(v) for d, v in pipe.metrics.queue_by_day.items()},
            kural_tetiklenme=dict(pipe.metrics.rule_hits),
            vaka=sum(len(v) for v in pipe.metrics.queue_by_day.values()),
            kapsama=[(c["senaryo"], c["sonuc"]) for c in pipe.metrics.coverage()],
        )
        del pipe, data
        gc.collect()
        return res
    finally:
        cert_mod._compact = orijinal


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cert-dir", required=True)
    ap.add_argument("--answers-dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--warmup", type=int, default=21)
    ap.add_argument("--budget", type=int, default=10)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    answers = args.answers_dir or str(Path(args.cert_dir).parent / "answers")

    yeni = kosu(args.cert_dir, answers, out, "optimize", True, args.days, args.warmup, args.budget)
    eski = kosu(args.cert_dir, answers, out, "eski", False, args.days, args.warmup, args.budget)

    farklar = [k for k in ("kuyruk", "kural_tetiklenme", "vaka", "kapsama", "olay") if yeni[k] != eski[k]]
    sonuc = dict(
        esdeger=not farklar,
        farkli_alanlar=farklar,
        bellek=dict(
            eski_gb=eski["bellek_gb"],
            yeni_gb=yeni["bellek_gb"],
            kazanc_kat=round(eski["bellek_gb"] / max(yeni["bellek_gb"], 1e-9), 2),
            eski_bayt_olay=eski["bayt_olay"],
            yeni_bayt_olay=yeni["bayt_olay"],
        ),
        sure=dict(eski_sn=eski["sure_sn"], yeni_sn=yeni["sure_sn"]),
        vaka=dict(eski=eski["vaka"], yeni=yeni["vaka"]),
    )
    (out / "esdegerlik.json").write_text(
        json.dumps(dict(ozet=sonuc, eski=eski, yeni=yeni), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    LOG.info("SONUÇ: %s", json.dumps(sonuc, ensure_ascii=False))
    return 0 if sonuc["esdeger"] else 1


if __name__ == "__main__":
    sys.exit(main())
