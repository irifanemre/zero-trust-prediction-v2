#!/usr/bin/env python
"""Bileşen bazında ablasyon sürücüsü — "hangi bileşen neyi yaptı?" sorusunun cevabı (19.5, literatür §7.1).

Neden ayrı bir betik: `ztp.cli --ablation` bütün varyantları tek seferde koşar. r4.2'de bir varyant 14–60 dakika
sürdüğü için 20 varyant bir gecede bitmez ve ortada kesilirse her şey kaybolur. Bu betik:

- `--varyant` ile **seçili** varyantları koşar (virgülle),
- her varyantın sonucunu bitince **hemen** diske yazar,
- yeniden çalıştırıldığında mevcut sonuçları atlar (kesilirse kaldığı yerden devam eder),
- sonunda tabloyu ve markdown özetini üretir.

Ölçülen soru: r4.2 ve r6.2'de v4 bileşenlerinin HEPSİ birlikte açılmıştı. r4.2'de kapsama 21 → 26 çıktı,
r6.2'de 3 → 3 kaldı ve yanlış alarm ikiye katlandı. Hangi bileşenin hangi etkiyi ürettiği **bilinmiyor**.
Bu betik onu ayrıştırır.

Kullanım:
    PYTHONPATH=src python scripts/ablasyon_kosusu.py \
        --cert-dir .../r4.2 --answers-dir .../answers --out ztp_out_ablasyon \
        --days 90 --warmup 21 --budget 30 \
        --varyant tam,v4_graf_carpan,v4_adwin,v4_bayes,v5_graf_toplamsal,v5_anomali_ecod
    PYTHONPATH=src python scripts/ablasyon_kosusu.py ... --liste    # varyantları listeler
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from ztp.ablation import VARIANTS, format_ablation
from ztp.config import TenantConfig
from ztp.data.cert import load_cert_dataset
from ztp.data.dataset import Dataset
from ztp.detection.catalog import load_catalog
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.schema import DAY

LOG = logging.getLogger("ablasyon")


def _kopya(d: Dataset) -> Dataset:
    return Dataset(
        d.name,
        d.directory.copy(),
        d.ip_leases.copy(),
        d.events.copy(),
        d.leaves.copy(),
        copy.deepcopy(d.ground_truth),
        list(d.critical_assets),
        honeytokens=dict(d.honeytokens),
    )


def tek_varyant(
    ad: str,
    spec: dict,
    cfg: TenantConfig,
    data: Dataset,
    catalog: List[dict],
    out: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    warmup: int,
) -> dict:
    t0 = time.perf_counter()
    vcfg = replace(cfg, tenant_id=f"{cfg.tenant_id}__{ad}", llm_backend="none", sinks=[], **spec.get("cfg", {}))
    vcat = spec["catalog"](catalog) if "catalog" in spec else copy.deepcopy(catalog)
    pipe = ZeroTrustPredictionPipeline(vcfg, _kopya(data), vcat, out)
    pipe.run(start, end, warmup)
    summ = pipe.metrics.summary(
        pipe.labels, pipe.engine.shadow_log, pipe.engine.suppressed_log, pipe.engine, end, prediction_rows=pipe.pred.rows
    )
    lp = summ.get("etiketli_veri_precision") or {}
    cal = (summ.get("tahmin_kalibrasyonu") or {}).get("sezgisel") or {}
    egri = summ.get("butce_recall_egrisi") or {}
    erken = [v for v in summ["erkenlik_gun"].values() if v is not None]
    return dict(
        varyant=ad,
        aciklama=spec["aciklama"],
        cfg_degisikligi=spec.get("cfg", {}),
        kapsama=f"{summ['kapsama']['tespit']}/{summ['kapsama']['senaryo']}",
        kapsama_tespit=summ["kapsama"]["tespit"],
        kapsama_senaryo=summ["kapsama"]["senaryo"],
        kapsama_oran=summ["kapsama"]["oran"],
        vaka=summ["vaka_hacmi"]["toplam"],
        kuyruga_giren_kullanici=(lp.get("kullanici_bazinda") or {}).get("kuyruga_giren_kullanici"),
        precision_at_n=lp.get("precision_at_n"),
        precision_at_1=lp.get("precision@1"),
        precision_at_3=lp.get("precision@3"),
        precision_at_10=lp.get("precision@10"),
        recall_1_kullanici=lp.get("recall@1_kullanici"),
        recall_5_kullanici=lp.get("recall@5_kullanici"),
        recall_10_kullanici=lp.get("recall@10_kullanici"),
        recall_30_kullanici=lp.get("recall@30_kullanici"),
        erkenlik_medyan=(sorted(erken)[len(erken) // 2] if erken else None),
        tahmin_auc=cal.get("auc"),
        tahmin_auprc=cal.get("auprc"),
        tahmin_auprc_kat=cal.get("auprc_kat"),
        tahmin_brier=cal.get("brier"),
        tahmin_ece=cal.get("ece"),
        butce_egrisi=egri.get("egri"),
        kapsama_detay=[(c["senaryo"], c["sonuc"]) for c in summ["kapsama"]["detay"]],
        etkinlik=dict(
            graf_kenar=(pipe.tgraph.kenar_sayisi if pipe.tgraph else 0),
            adwin_kesim=len(pipe.profile.adwin_cut),
            bayes_elenen_vaka=sum(len(v) for v in pipe.bayes_elenen.values()),
            **(pipe.anomali.etkinlik() if pipe.anomali is not None else {}),
        ),
        sure_sn=round(time.perf_counter() - t0),
    )


def farklari_ekle(rows: List[dict]) -> List[dict]:
    ref = next((r for r in rows if r["varyant"] == "tam"), None)
    if not ref:
        return rows
    for r in rows:
        r["kapsama_farki"] = (
            None if r["kapsama_oran"] is None or ref["kapsama_oran"] is None else round(r["kapsama_oran"] - ref["kapsama_oran"], 3)
        )
        r["precision_farki"] = (
            None
            if r["precision_at_n"] is None or ref["precision_at_n"] is None
            else round(r["precision_at_n"] - ref["precision_at_n"], 3)
        )
        r["vaka_farki"] = r["vaka"] - ref["vaka"]
        r["insider_farki"] = r["kapsama_tespit"] - ref["kapsama_tespit"]
    return rows


def markdown(rows: List[dict], kayit: dict) -> str:
    satir = [
        f"# Bileşen ablasyonu — {kayit['veri']}",
        "",
        f"Koşu: {kayit['bitis']} · HEAD `{kayit['head']}` · dondurma `{kayit['dondurma']}` → **{kayit['dondurma_durum']}**",
        f"{kayit['gun']} gün, ısınma {kayit['warmup']}, bütçe {kayit['butce']}, {kayit['olay']:,} olay.",
        "",
        "Her satır **aynı veri** üzerinde tek bileşen değişkenle koşuldu. `tam` referanstır.",
        "",
        "| Varyant | Yakalanan | Δ | Vaka | Δvaka | prec@N | rec@10k | rec@30k | Erkenlik | AUPRC | ×taban | Süre |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def f(v, isaretli=False):
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:+.3f}" if isaretli else f"{v:.3f}"
        return f"{v:+d}" if isaretli and isinstance(v, int) else f"{v:,}"

    for r in rows:
        satir.append(
            f"| `{r['varyant']}` | {r['kapsama']} | {f(r.get('insider_farki'), True)} | {r['vaka']:,} | "
            f"{f(r.get('vaka_farki'), True)} | {f(r['precision_at_n'])} | {f(r['recall_10_kullanici'])} | "
            f"{f(r['recall_30_kullanici'])} | {f(r['erkenlik_medyan'])} | {f(r['tahmin_auprc'])} | "
            f"{f(r['tahmin_auprc_kat'])} | {r['sure_sn'] // 60} dk |"
        )
    satir += [
        "",
        "## Varyantlar",
        "",
        *[f"- `{r['varyant']}` — {r['aciklama']}" + (f"  \n  `{r['cfg_degisikligi']}`" if r["cfg_degisikligi"] else "") for r in rows],
        "",
        "## Bileşen etkinliği",
        "",
        "| Varyant | Graf kenar | ADWIN kesim | Bayes elenen | Anomali uyum | Anomali skorlanan |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        e = r["etkinlik"]
        satir.append(
            f"| `{r['varyant']}` | {e.get('graf_kenar', 0):,} | {e.get('adwin_kesim', 0)} | "
            f"{e.get('bayes_elenen_vaka', 0)} | {e.get('anomali_uyum', '—')} | {e.get('anomali_skorlanan', '—')} |"
        )
    satir += [
        "",
        "**Okuma:** Δ pozitifse bileşen yakalamayı artırıyor. Δvaka bedelini verir — yakalama artmadan vaka",
        "artıyorsa bileşen yalnız yanlış alarm üretmiştir. AUPRC tek başına okunmaz, `×taban` şans seviyesinin",
        "kaç katı olduğunu söyler.",
    ]
    return "\n".join(satir) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cert-dir")
    ap.add_argument("--answers-dir")
    ap.add_argument("--out", help="çıktı dizini (--liste dışında zorunlu)")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--warmup", type=int, default=21)
    ap.add_argument("--budget", type=int, default=30)
    ap.add_argument("--bitis", default="2010-11-30", help="değerlendirme penceresinin son günü")
    ap.add_argument("--varyant", default="", help="virgülle ayrılmış varyant adları (boş → hepsi)")
    ap.add_argument("--liste", action="store_true", help="varyantları listele ve çık")
    ap.add_argument("--dondurma", help="koşudan önce doğrulanacak dondurma manifesti")
    ap.add_argument("--yeniden", action="store_true", help="mevcut sonuçları atlamak yerine yeniden koş")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.liste:
        for ad, spec in VARIANTS.items():
            print(f"{ad:<24} {spec['aciklama']}")
        return 0
    if not args.cert_dir or not args.out:
        ap.error("--cert-dir ve --out gerekli (--liste dışında)")

    secili = [a.strip() for a in args.varyant.split(",") if a.strip()] or list(VARIANTS)
    bilinmeyen = [a for a in secili if a not in VARIANTS]
    if bilinmeyen:
        ap.error(f"bilinmeyen varyant: {bilinmeyen} (--liste ile görün)")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    varyant_dizin = out / "varyantlar"
    varyant_dizin.mkdir(exist_ok=True)

    dondurma_durum = "kontrol edilmedi"
    if args.dondurma:
        from ztp.freeze import build_manifest, diff_manifest

        beklenen = json.loads(Path(args.dondurma).read_text(encoding="utf-8"))
        fark = diff_manifest(beklenen, build_manifest())
        dondurma_durum = "donmuş durumla aynı" if not fark else f"SAPMA: {fark}"
        LOG.info("Dondurma: %s", dondurma_durum)
        if fark:
            LOG.error("Dondurma sapması var — ablasyon sonucu karşılaştırılamaz. Çıkılıyor.")
            return 2

    end = pd.Timestamp(args.bitis)
    start = end - (args.days - 1) * DAY
    start_hist = end - (90 + args.warmup + args.days) * DAY
    LOG.info("Veri yükleniyor: %s (%s → %s)", args.cert_dir, start_hist.date(), end.date())
    data = load_cert_dataset(args.cert_dir, start_hist, end, answers_dir=args.answers_dir)
    catalog = load_catalog()
    cfg = TenantConfig(tenant_id="ablasyon", alarm_budget_per_day=args.budget, llm_backend="none", sinks=[])
    cfg.available_sources = tuple(sorted(set(data.events["source"].astype(str).unique()) | {"hr"}))
    LOG.info("%d olay, %d kullanıcı, kaynaklar: %s", len(data.events), len(data.directory), cfg.available_sources)

    rows: List[dict] = []
    for i, ad in enumerate(secili, 1):
        yol = varyant_dizin / f"{ad}.json"
        if yol.exists() and not args.yeniden:
            LOG.info("[%d/%d] %s — mevcut sonuç kullanılıyor", i, len(secili), ad)
            rows.append(json.loads(yol.read_text(encoding="utf-8")))
            continue
        LOG.info("[%d/%d] %s — %s", i, len(secili), ad, VARIANTS[ad]["aciklama"])
        r = tek_varyant(ad, VARIANTS[ad], cfg, data, catalog, out, start, end, args.warmup)
        yol.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        LOG.info("[%d/%d] %s bitti (%d sn): kapsama %s, vaka %d", i, len(secili), ad, r["sure_sn"], r["kapsama"], r["vaka"])
        rows.append(r)

    rows = farklari_ekle(rows)
    from ztp.freeze import build_manifest

    kayit = dict(
        veri=Path(args.cert_dir).name,
        bitis=str(pd.Timestamp.now().date()),
        gun=args.days,
        warmup=args.warmup,
        butce=args.budget,
        olay=len(data.events),
        head=_head(),
        dondurma=(Path(args.dondurma).name if args.dondurma else "—"),
        dondurma_durum=dondurma_durum,
        manifest_surum=build_manifest()["surum"],
    )
    (out / "ablasyon.json").write_text(json.dumps(dict(kayit=kayit, satirlar=rows), ensure_ascii=False, indent=1), encoding="utf-8")
    md = markdown(rows, kayit)
    (out / "ablasyon.md").write_text(md, encoding="utf-8")
    print()
    print(format_ablation(rows))
    print(f"\nyazıldı: {out / 'ablasyon.json'}  ve  {out / 'ablasyon.md'}")
    return 0


def _head() -> str:
    import subprocess

    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "—"


if __name__ == "__main__":
    sys.exit(main())
