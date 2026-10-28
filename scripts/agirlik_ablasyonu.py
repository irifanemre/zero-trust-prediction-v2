#!/usr/bin/env python3
"""Öğrenen modelin skora katkısı: `prediction_weight` ablasyonu (14.5 giriş şartı, 14.6 "ezmez, eklenir").

Gerekçe (r5.2 kör koşusu): kaçırılan 5 değerlendirilebilir insider'ın 3'ünde beklenen kural TETİKLENDİ ama günlük 10
vakalık bütçeye giremedi — yani sorun tespit değil SIRALAMA. Öğrenen model kendi kurumunda iyi sıralıyor (r5.2 test
AUC 0,91) ama skora hiç katılmıyor (`prediction_weight: 0`). Bu betik, katmanın "hak edilmiş" olup olmadığını ölçer.

Protokol (sızıntısız):
  1. Temel koşu (ağırlık 0) → tahmin satırları, gerçekleşme etiketleri, parça metrikleri.
  2. Model YALNIZ eğitim parçasının kullanıcılarıyla eğitilir (C, lr_protocol'ün doğrulamada seçtiği değer).
  3. Her ağırlık için boru hattı baştan koşulur, model enjekte edilir.
  4. Karşılaştırma DOĞRULAMA parçasında yapılır: o kullanıcılar eğitime hiç girmedi (etiket kişiye özel olduğu için
     kullanıcı ayrımı sızıntıyı keser). TEST parçasına bu betikte bakılmaz — karar verilirse bir kez bakılacak.

Kurallara, eşiklere, skor formülüne dokunulmaz: yalnız `prediction_weight` değeri değişir (donmuş varsayılan 0).

Kullanım:
    python scripts/agirlik_ablasyonu.py --cert-dir ~/Desktop/zero_trust_prediction/cert_data/r4.2 \
        --out /tmp/ztp_out/agirlik --agirliklar 0.25 0.5 1.0
Çıktı: <out>/sonuclar.json, <out>/ozet.md
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ztp.config import TenantConfig
from ztp.data.cert import load_cert_dataset, resolve_cert_dir
from ztp.detection.catalog import load_catalog
from ztp.evaluation import load_or_create_split, lr_protocol, part_metrics
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.prediction_model import LogisticModel, rows_to_matrix
from ztp.schema import DAY

LOG = logging.getLogger("agirlik")
REPO = Path(__file__).resolve().parents[1]
DEFAULT_SPLIT = REPO / "configs" / "splits" / "cert-r4.2-kullanici-bolmesi.json"


def run_once(cfg: TenantConfig, data, catalog, out: Path, start, end, warmup: int, model: LogisticModel | None) -> dict:
    """Tek koşu; model verilirse tahmin katmanına enjekte edilir (skora 14.6 terimiyle girer)."""
    pipe = ZeroTrustPredictionPipeline(cfg, data, catalog, out)
    if model is not None:
        pipe.pred.model = model
    pipe.run(start, end, warmup)
    res = dict(
        parcalar=part_metrics(pipe.metrics, SPLIT),
        vaka=dict(
            toplam=sum(len(v) for v in pipe.metrics.queue_by_day.values()),
            gun=len(pipe.metrics.queue_by_day),
        ),
    )
    rows, outcomes = pipe.pred.rows, pipe.metrics.outcomes(pipe.pred.rows)
    del pipe
    gc.collect()
    return res, rows, outcomes


def train_on_training_part(rows, y, split: dict, c: float) -> LogisticModel:
    """Model yalnız eğitim parçasının kullanıcılarından öğrenir; doğrulama/test kullanıcıları hiç görülmez."""
    assign = split["atama"]
    part = np.array([assign.get(r["sid"], "") for r in rows])
    m = part == "egitim"
    X, yv = rows_to_matrix(rows), np.asarray(y, dtype=int)
    LOG.info("Model eğitimi: %d satır, %d pozitif, C=%s", int(m.sum()), int(yv[m].sum()), c)
    return LogisticModel.fit(X[m], yv[m], C=c)


def table(rows: list[dict]) -> str:
    """Doğrulama parçası: modelin hiç görmediği kullanıcılar (eğitim kullanıcı bazında ayrıldı)."""
    head = "| ağırlık | yakalama (geçti/n) | prec@1 | prec@3 | prec@10 | FP oranı (masum) | vaka |"
    sep = "|---|---|---|---|---|---|---|"
    out = [head, sep]
    for r in rows:
        d = r["dogrulama"]
        ev, cm = d["degerlendirilebilir"], d["confusion"]
        fp_rate = _f(_safe_ratio(cm["fp"], cm["fp"] + cm["tn"]))
        out.append(
            f"| {r['agirlik']} | {ev['gecti']}/{ev['senaryo']} | {_f(d.get('precision@1'))} | {_f(d.get('precision@3'))} "
            f"| {_f(d.get('precision@10'))} | {fp_rate} | {r['vaka']} |"
        )
    return "\n".join(out)


def _safe_ratio(a: int, b: int):
    return None if not b else a / b


def _f(v) -> str:
    return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def main() -> int:
    global SPLIT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cert-dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default=str(DEFAULT_SPLIT))
    ap.add_argument("--answers-dir")
    ap.add_argument("--end", default="2010-11-30")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--warmup", type=int, default=21)
    ap.add_argument("--budget", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--agirliklar", type=float, nargs="+", default=[0.25, 0.5, 1.0])
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base_dir = resolve_cert_dir(args.cert_dir)
    end = pd.Timestamp(args.end)
    start = end - (args.days - 1) * DAY
    t0 = time.perf_counter()

    cfg0 = TenantConfig(tenant_id="agirlik-temel", alarm_budget_per_day=args.budget, llm_backend="none", sinks=[])
    # tarihçe penceresi ve cevap anahtarı yolu cert_eval.py ile birebir aynı
    start_hist = end - (cfg0.long_window_days + args.warmup + args.days) * DAY
    answers = args.answers_dir or str(Path(base_dir).parent / "answers")
    data = load_cert_dataset(str(base_dir), start_hist, end, answers_dir=answers)
    cfg0.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
    SPLIT, created = load_or_create_split(
        Path(args.split),
        data.directory["sid"].astype(str).tolist(),
        data.ground_truth,
        seed=args.seed,
        source=f"{data.name}; end={end.date()} days={args.days} warmup={args.warmup}",
    )
    LOG.info("Bölme %s", "üretildi" if created else "dosyadan yüklendi")

    res: dict = dict(veri=data.name, ayarlar=vars(args) | dict(bolme=SPLIT["meta"]), satirlar=[])

    # ---- 1. temel koşu (ağırlık 0 = donmuş varsayılan)
    base, rows, outcomes = run_once(cfg0, data, catalog := load_catalog(), out, start, end, args.warmup, None)
    res["satirlar"].append(dict(agirlik=0.0, **base["parcalar"], vaka=base["vaka"]["toplam"]))
    LOG.info("Temel koşu bitti (%.0f sn)", time.perf_counter() - t0)

    # ---- 2. C seçimi (doğrulama log-loss'u) ve eğitim parçasında model
    lr = lr_protocol(rows, outcomes, SPLIT)
    c = lr.get("secilen_C") or lr.get("tamamlayici_tum_gunler", {}).get("secilen_C") or 0.001
    res["lr_protokolu"] = lr
    model = train_on_training_part(rows, outcomes, SPLIT, float(c))
    (out / "model.json").write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    del rows, outcomes
    gc.collect()

    # ---- 3. ağırlık varyantları
    for w in args.agirliklar:
        cfg = TenantConfig(
            tenant_id=f"agirlik-{w}",
            alarm_budget_per_day=args.budget,
            llm_backend="none",
            sinks=[],
            prediction_weight=w,
            available_sources=cfg0.available_sources,
        )
        r, _, _ = run_once(cfg, data, catalog, out, start, end, args.warmup, model)
        res["satirlar"].append(dict(agirlik=w, **r["parcalar"], vaka=r["vaka"]["toplam"]))
        (out / "sonuclar.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        LOG.info("Ağırlık %.2f bitti (%.0f sn)", w, time.perf_counter() - t0)

    (out / "sonuclar.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / "ozet.md").write_text(
        "# prediction_weight ablasyonu (r4.2, doğrulama parçası)\n\n"
        "Model yalnız eğitim parçasının kullanıcılarıyla eğitildi; aşağıdaki sayılar modelin hiç görmediği\n"
        "doğrulama kullanıcılarınındır. Test parçasına bakılmadı.\n\n" + table(res["satirlar"]) + "\n",
        encoding="utf-8",
    )
    LOG.info("Bitti (%.0f sn): %s", time.perf_counter() - t0, out / "ozet.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
