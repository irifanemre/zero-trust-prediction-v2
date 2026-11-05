"""Faz C-1 — mevcut tek olasılık, farklı ufuklarda farklı mı ayırt ediyor?

Brief dört ufuk (1/3/7/14 gün) için dört model başı istiyor. Bu betik **önce** şunu ölçüyor: tek
olasılık (`p7`) zaten dört ufku da aynı güçle sıralıyorsa dört baş yazmanın değeri yoktur.

Yöntem: TEK koşunun tahmin satırları, dört ufka karşı ayrı ayrı değerlendirilir. `outcomes()` ufku
parametre olarak alıyor, yani ufuklar arası fark **modelden değil yalnız hedef tanımından** gelir —
karşılaştırma adil.

Karar kuralı (`docs/faz-c-on-kayit.md`, ölçümden önce yazıldı): ufuklar arası AUC farkı ≥ 0,10 ise
C-2 (ufuk başına model) yazılır; değilse yazılmaz.

**Brier ufuklar arasında doğrudan karşılaştırılamaz**: uzun ufukta taban oranı yükselir ve Brier
kendiliğinden düşer. Bu yüzden AUC (sıralama gücü, taban oranından bağımsız) ve beceri skoru
(tabana göre normalize) karşılaştırılır.

Kullanım:
    python scripts/ufuk_olcumu.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ztp.config import TenantConfig  # noqa: E402
from ztp.data.synthetic import SyntheticOrg  # noqa: E402
from ztp.detection.catalog import load_catalog  # noqa: E402
from ztp.pipeline import ZeroTrustPredictionPipeline  # noqa: E402
from ztp.prediction_model import calibration_report  # noqa: E402

UFUKLAR = (1, 3, 7, 14)
KARAR_ESIGI = 0.10  # ön kayıtta yazılan: bu farkın altında C-2 yazılmaz


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=120)
    ap.add_argument("--eval-days", type=int, default=20)
    ap.add_argument("--tohum", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cfg = TenantConfig(tenant_id="ufuk", pseudonym_secret="s", alarm_budget_per_day=6, threshold_jitter=0.0)
    end = pd.Timestamp("2026-09-16")
    data = SyntheticOrg(
        n_users=a.users,
        n_days=cfg.long_window_days + a.eval_days + 10,
        eval_days=a.eval_days,
        end_day=end,
        seed=a.tohum,
    ).build()
    cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), Path(tempfile.mkdtemp()))
    pipe.run(end - pd.Timedelta(days=a.eval_days - 1), end, warmup_days=10)

    rows = pipe.pred.rows
    m = pipe.metrics
    print(f"\n# Ufuk ölçümü — {a.users} kullanıcı, {a.eval_days} gün, tohum {a.tohum}\n")
    print(f"Tahmin satırı: {len(rows)}\n")
    if not rows:
        print("Tahmin satırı yok — ölçüm yapılamaz.")
        return 1

    # Model ve sezgisel AYNI ise ikinci sütun anlamsız olur; önce kontrol edilir.
    model_var = any(r.get("p7") != r.get("p7_sezgisel") for r in rows)
    sutunlar = [("p7_sezgisel", "sezgisel")] + ([("p7", "model")] if model_var else [])

    sonuc = {}
    print("| Ufuk | n | pozitif | taban oranı | " + " | ".join(f"AUC ({ad})" for _, ad in sutunlar) + " |")
    print("|---|---|---|---|" + "---|" * len(sutunlar))
    for h in UFUKLAR:
        y = m.outcomes(rows, horizon_days=h)
        satir = dict(ufuk=h, n=len(y), pozitif=int(sum(y)), taban=round(sum(y) / len(y), 4) if y else None)
        hucre = []
        for kolon, ad in sutunlar:
            rep = calibration_report([r[kolon] for r in rows], y)
            satir[ad] = dict(
                auc=rep.get("auc"),
                brier=rep.get("brier"),
                beceri=rep.get("brier_beceri"),
                ece=rep.get("ece"),
                auprc=rep.get("auprc"),
                auprc_kat=rep.get("auprc_kat"),
            )
            hucre.append(f"{rep.get('auc'):.3f}" if rep.get("auc") is not None else "—")
        sonuc[h] = satir
        print(f"| {h}g | {satir['n']} | {satir['pozitif']} | {satir['taban']} | " + " | ".join(hucre) + " |")

    print("\n## Brier ve beceri skoru (Brier ufuklar arasında KARŞILAŞTIRILAMAZ)\n")
    print("| Ufuk | Brier | beceri skoru | ECE | AUPRC | × taban |")
    print("|---|---|---|---|---|---|")
    ana = sutunlar[-1][1]  # model varsa model, yoksa sezgisel
    for h in UFUKLAR:
        d = sonuc[h][ana]
        b = f"{d['brier']:.4f}" if d["brier"] is not None else "—"
        s_ = f"{d['beceri']:.3f}" if d["beceri"] is not None else "—"
        e = f"{d['ece']:.4f}" if d["ece"] is not None else "—"
        ap_ = f"{d['auprc']:.4f}" if d["auprc"] is not None else "—"
        kat = f"{d['auprc_kat']}×" if d["auprc_kat"] is not None else "—"
        print(f"| {h}g | {b} | {s_} | {e} | {ap_} | {kat} |")

    aucs = [sonuc[h][ana]["auc"] for h in UFUKLAR if sonuc[h][ana]["auc"] is not None]
    print(f"\n## Karar — ön kayıt kuralı: AUC farkı ≥ {KARAR_ESIGI} ise C-2 yazılır\n")
    if len(aucs) < 2:
        print("  AUC hesaplanamadı — karar verilemiyor.")
        karar = None
    else:
        fark = max(aucs) - min(aucs)
        karar = fark >= KARAR_ESIGI
        print(f"  en iyi AUC {max(aucs):.3f} · en kötü {min(aucs):.3f} · **fark {fark:.3f}**")
        print(f"  → C-2 (ufuk başına model) {'YAZILIR' if karar else 'YAZILMAZ'}")
        if not karar:
            print("  Yorum: tek olasılık dört ufku da aynı güçle sıralıyor; ufuk başına ayrı model")
            print("  ek bilgi taşımıyor. Ufuk ailesi yalnız raporlama etiketi olarak anlamlı.")

    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                dict(
                    yapilandirma=dict(users=a.users, eval_days=a.eval_days, tohum=a.tohum),
                    n_satir=len(rows),
                    model_var=model_var,
                    ufuklar=sonuc,
                    auc_farki=(max(aucs) - min(aucs)) if len(aucs) >= 2 else None,
                    karar_esigi=KARAR_ESIGI,
                    c2_yazilir=karar,
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nyazıldı: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
