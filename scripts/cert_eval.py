#!/usr/bin/env python3
"""CERT r4.2 yansız değerlendirme (19.2): kullanıcı bazlı 70/15/15 bölme, parça bazlı metrikler, 26/27 uzlaştırması,
eşik hassasiyeti ve lojistik modelin yalnız eğitim parçasında eğitilmesi.

Veri yolu ZTP_CERT_PATH ortam değişkeninden (ya da --cert-dir) okunur; repoya yol gömülmez. Bölme dosyası repoda
(configs/splits/) durur: dosya varsa o kullanılır ve verinin nüfusuyla uyuştuğu doğrulanır — başka makinede aynı bölme.

Kullanım:
    python scripts/cert_eval.py --out C:/data/ztp_out/cert_eval             # temel koşu + 4 eşik varyantı (~45 dk)
    python scripts/cert_eval.py --out C:/data/ztp_out/cert_eval --no-variants
Çıktı: <out>/sonuclar.json ve <out>/ozet.md (her aşamadan sonra güncellenir).
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
from ztp.data.cert import load_cert_dataset, resolve_cert_dir
from ztp.detection.catalog import load_catalog
from ztp.evaluation import (
    PARTS,
    count_reconciliation,
    load_or_create_split,
    lr_protocol,
    part_metrics,
    run_threshold_variants,
    scenario_table,
    variant_row,
)
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.schema import DAY

LOG = logging.getLogger("cert_eval")
REPO = Path(__file__).resolve().parents[1]
DEFAULT_SPLIT = REPO / "configs" / "splits" / "cert-r4.2-kullanici-bolmesi.json"
# (UEBA-0003 z eşiği, akran nötr noktası) — temel (3.5, 5.0) ana koşudan gelir
VARIANTS = {"z3.0": (3.0, 5.0), "z4.0": (4.0, 5.0), "notr4": (3.5, 4.0), "notr6": (3.5, 6.0)}


def _fmt(v) -> str:
    if v is None:
        return "—"
    return f"{v:.3f}".replace(".", ",") if isinstance(v, float) else str(v)


def write_summary(res: dict, out: Path) -> None:
    (out / "sonuclar.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = [f"# CERT {res.get('veri', '')} yansız değerlendirme — özet", ""]
    if "bolme" in res:
        oz = res["bolme"]["ozet"]
        md += ["## Bölme", "", "| Parça | Kullanıcı | Insider | Katmanlar |", "|---|---|---|---|"]
        md += [f"| {p} | {oz[p]['kullanici']} | {oz[p]['insider']} | {oz[p]['katmanlar']} |" for p in PARTS]
        md.append("")
    if "parcalar" in res:
        md += [
            "## Parça bazlı metrikler (güncel kod, tüm kurumda tek koşu)",
            "",
            "| Parça | Değerlendirilebilir yakalama | Kısmi (geçti/n) | p@1 | p@3 | p@5 | p@10 | TP | FN | FP | TN |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for p in (*PARTS, "tumu"):
            m = res["parcalar"][p]
            ev, pa, cm = m["degerlendirilebilir"], m["kismi_pencereli"], m["confusion"]
            md.append(
                f"| {p} | {ev['gecti']}/{ev['senaryo']} ({_fmt(ev['yakalama'])}) | {pa['gecti']}/{pa['senaryo']} | "
                f"{_fmt(m['precision@1'])} | {_fmt(m['precision@3'])} | {_fmt(m['precision@5'])} | "
                f"{_fmt(m['precision@10'])} | {cm['tp']} | {cm['fn']} | {cm['fp']} | {cm['tn']} |"
            )
        md.append("")
    if "uzlastirma_26_27" in res:
        u = res["uzlastirma_26_27"]
        md += [
            "## 26 / 27 uzlaştırması",
            "",
            f"- coverage GEÇTİ: {u['coverage_gecti']} (değerlendirilebilir {u['coverage_gecti_degerlendirilebilir']}, "
            f"kısmi {u['coverage_gecti_kismi']})",
            f"- kullanıcı bazında pencerede kuyrukta: {u['kullanici_bazinda_pencerede_kuyrukta']}",
        ]
        md += [f"- yalnız kuyrukta: `{r['sid']}` {r['senaryo']} → {r['sonuc']}" for r in u["yalnizca_kuyrukta"]]
        md.append("")
    if "esik_hassasiyeti" in res:
        md += [
            "## Eşik hassasiyeti",
            "",
            "| Varyant | z | Akran nötr | Tümü yakalama | Tümü p@1 | Doğrulama yakalama | Doğrulama p@1 | Test yakalama | Test p@1 |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in res["esik_hassasiyeti"]:
            md.append(
                f"| {r['varyant']} | {r['z_esigi']} | {r['akran_notr']} | {_fmt(r['tumu_yakalama'])} | {_fmt(r['tumu_p@1'])} | "
                f"{_fmt(r['dogrulama_yakalama'])} | {_fmt(r['dogrulama_p@1'])} | {_fmt(r['test_yakalama'])} | "
                f"{_fmt(r['test_p@1'])} |"
            )
        md.append("")
    if "lojistik" in res:
        lr = res["lojistik"]
        md += [
            "## Lojistik regresyon",
            "",
            f"Bölme: {lr['bolme']}",
            "",
            "| C | Doğr. log-loss | Doğr. F1 | Doğr. AUC |",
            "|---|---|---|---|",
        ]
        md += [
            f"| {g['C']} | {g.get('dogrulama_logloss', g.get('hata'))} | {g.get('dogrulama_f1')} | {g.get('dogrulama_auc')} |"
            for g in lr["c_izgarasi"]
        ]
        md += ["", f"Seçilen C: {lr.get('secilen_C')}  {lr.get('secim_gecersiz', '')}", ""]
        for k in ("test", "test_sezgisel", "eski_protokol_bu_kosu"):
            md.append(f"- {k}: {lr.get(k)}")
        comp = lr.get("tamamlayici_tum_gunler") or {}
        if comp:
            md += ["", "### Tamamlayıcı: kullanıcı ayrık, tüm günler (embargo yok)", "", f"Bölme: {comp.get('bolme')}", ""]
            md += [
                f"- C={g['C']}: log-loss {g.get('dogrulama_logloss', g.get('hata'))}, F1 {g.get('dogrulama_f1')}, "
                f"AUC {g.get('dogrulama_auc')}"
                for g in comp.get("c_izgarasi", [])
            ]
            md.append(f"- seçilen C: {comp.get('secilen_C')}  {comp.get('secim_gecersiz', '')}")
            for k in ("test", "test_sezgisel"):
                md.append(f"- {k}: {comp.get(k)}")
        md.append("")
    (out / "ozet.md").write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cert-dir", help="CERT sürüm dizini (verilmezse ZTP_CERT_PATH)")
    ap.add_argument("--answers-dir")
    ap.add_argument("--end", default="2010-11-30")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--warmup", type=int, default=21)
    ap.add_argument("--budget", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tenant", default="cert-r42")
    ap.add_argument("--split", default=str(DEFAULT_SPLIT))
    ap.add_argument("--out", default="./ztp_out/cert_eval")
    ap.add_argument("--no-variants", action="store_true", help="eşik varyantlarını atla (yalnız temel koşu + LR)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(out / "cert_eval.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    t0 = time.perf_counter()
    cert_dir = resolve_cert_dir(args.cert_dir)
    end = pd.Timestamp(args.end).normalize()
    cfg = TenantConfig(tenant_id=args.tenant, alarm_budget_per_day=args.budget)
    start_hist = end - (cfg.long_window_days + args.warmup + args.days) * DAY
    start = end - (args.days - 1) * DAY
    answers = args.answers_dir or str(cert_dir.parent / "answers")
    LOG.info("CERT yükleniyor: %s (%s … %s)", cert_dir, start_hist.date(), end.date())
    data = load_cert_dataset(str(cert_dir), start_hist, end, answers_dir=answers)
    cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
    LOG.info(
        "Yüklendi: %d olay, %d kullanıcı, %d senaryo (%.0f sn)",
        len(data.events),
        len(data.directory),
        len(data.ground_truth),
        time.perf_counter() - t0,
    )
    split, created = load_or_create_split(
        Path(args.split),
        data.directory["sid"].astype(str).tolist(),
        data.ground_truth,
        seed=args.seed,
        source=f"{data.name}; end={end.date()} days={args.days} warmup={args.warmup}",
    )
    LOG.info("Bölme %s: %s", "üretildi" if created else "dosyadan yüklendi", args.split)
    res: dict = dict(
        veri=data.name,
        ayarlar=dict(
            end=str(end.date()),
            days=args.days,
            warmup=args.warmup,
            budget=args.budget,
            seed=args.seed,
            kaynaklar=list(cfg.available_sources),
        ),
        bolme=split["meta"],
    )
    write_summary(res, out)

    # ---- 4. temel koşu: tüm kurumda bir kez, metrikler parça parça
    catalog = load_catalog()
    pipe = ZeroTrustPredictionPipeline(cfg, data, catalog, out)
    pipe.run(start, end, args.warmup)
    res["parcalar"] = part_metrics(pipe.metrics, split)
    res["uzlastirma_26_27"] = count_reconciliation(pipe.metrics)
    res["senaryolar"] = [dict(r, parca=split["atama"].get(r["sid"])) for r in scenario_table(pipe.metrics)]
    res["vaka_hacmi"] = dict(toplam=sum(len(v) for v in pipe.metrics.queue_by_day.values()), gun=len(pipe.metrics.queue_by_day))
    base = variant_row("temel", res["parcalar"])
    base.update(z_esigi=3.5, akran_notr=5.0)
    write_summary(res, out)
    LOG.info("Temel koşu bitti (%.0f sn)", time.perf_counter() - t0)

    # ---- 6. lojistik regresyon: yalnız eğitim parçası, embargo, C doğrulamada, test sonda bir kez
    rows = pipe.pred.rows
    res["lojistik"] = lr_protocol(rows, pipe.metrics.outcomes(rows), split)
    write_summary(res, out)
    del pipe, rows
    gc.collect()

    # ---- 5. eşik hassasiyeti
    res["esik_hassasiyeti"] = [base]
    if not args.no_variants:
        res["esik_hassasiyeti"] += run_threshold_variants(cfg, data, catalog, out, start, end, args.warmup, split, VARIANTS)
    write_summary(res, out)
    LOG.info("Bitti (%.0f sn). Özet: %s", time.perf_counter() - t0, out / "ozet.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
