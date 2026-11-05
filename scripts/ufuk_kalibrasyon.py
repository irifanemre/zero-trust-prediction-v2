"""Faz C-2a — ufuk başına kalibrasyon beceri skorunu pozitife çevirebilir mi?

C-1 ölçtü: `p7` iyi bir SIRALAYICI (AUC 0,90, AUPRC tabanın 13 katı), kötü bir OLASILIK (beceri
skoru dört ufukta ve dört tohumda da negatif). Sebebi tek elle konulmuş kesme noktası
(`sigmoid(-3.5 + Σcomp)`), tek ufka göre — oysa taban oranı ufka göre iki kat değişiyor.

Bu betik boru hattına hiçbir şey bağlamadan şunu ölçüyor: ufuk başına PAVA izotonik kalibrasyon
beceri skorunu negatiften pozitife çeviriyor mu?

**Sızıntı bariyeri** (`docs/faz-c2-on-kayit.md`, en kritik tasarım kısıtı): ufuk h için gün d'nin
sonucu ancak d+h'de bilinir. Dolayısıyla kalibrasyon kümesi ile değerlendirme kümesi arasında
**h günlük tampon** bırakılır ve tampon hiçbir kümeye girmez. Tampon olmazsa kalibrasyon,
değerlendirme penceresine taşan sonuçları görür ve beceri skoru yapay yükselir.

**Etiket kaynağı — ölçüm iyimser:** etiketler cevap anahtarından geliyor (sentetik veride analist
etiketi yok). Üretimde etiket analistten gelir, gecikmeli ve eksiktir. Yani buradaki sonuç bir
ÜST SINIRDIR: "mükemmel etiketle kalibrasyon bu kadar kazandırıyor".

Kullanım:
    python scripts/ufuk_kalibrasyon.py
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
from ztp.gnn.conformal_eval import VennAbersKalibrator  # noqa: E402
from ztp.pipeline import ZeroTrustPredictionPipeline  # noqa: E402
from ztp.prediction_model import calibration_report  # noqa: E402

UFUKLAR = (1, 3, 7, 14)
MIN_SATIR, MIN_POZITIF = 300, 10  # ön kayıt ölçütü 4: altında "ölçülemedi" denir, sayı uydurulmaz


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=120)
    ap.add_argument("--eval-days", type=int, default=60, help="ön kayıt: 14g ufuk + tampon için uzun pencere gerekir")
    ap.add_argument("--tohum", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cfg = TenantConfig(tenant_id="kal", pseudonym_secret="s", alarm_budget_per_day=6, threshold_jitter=0.0)
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
    gunler = sorted({r["gun"] for r in rows})
    print(f"\n# Ufuk kalibrasyonu — {a.users} kullanıcı, {len(gunler)} gün, tohum {a.tohum}\n")
    print(f"Tahmin satırı: {len(rows)}\n")
    if len(gunler) < 10:
        print("Yeterli gün yok.")
        return 1

    sonuc = {}
    print("| Ufuk | kalib. n | değ. n | değ. pozitif | beceri ÖNCE | beceri SONRA | ECE önce | ECE sonra | AUC önce | AUC sonra |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for h in UFUKLAR:
        y_tum = m.outcomes(rows, horizon_days=h)
        # Zamansal bölme: [kalibrasyon] [h günlük TAMPON] [değerlendirme]
        kesme = len(gunler) // 2
        kal_gunleri = set(gunler[:kesme])
        deg_gunleri = set(gunler[kesme + h :])  # tampon: kesme ile kesme+h arası hiçbir kümede yok
        kal = [(r["p7_sezgisel"], y) for r, y in zip(rows, y_tum) if r["gun"] in kal_gunleri]
        deg = [(r["p7_sezgisel"], y) for r, y in zip(rows, y_tum) if r["gun"] in deg_gunleri]
        n_poz = sum(y for _, y in deg)
        kayit = dict(ufuk=h, kalib_n=len(kal), deg_n=len(deg), deg_pozitif=int(n_poz), tampon_gun=h)
        if len(deg) < MIN_SATIR or n_poz < MIN_POZITIF:
            kayit["durum"] = "ÖLÇÜLEMEDİ"
            kayit["neden"] = f"değerlendirme kümesi yetersiz (satır {len(deg)}/{MIN_SATIR}, pozitif {n_poz}/{MIN_POZITIF})"
            sonuc[h] = kayit
            print(f"| {h}g | {len(kal)} | {len(deg)} | {n_poz} | — | **ÖLÇÜLEMEDİ** | — | — | — | — |")
            continue

        va = VennAbersKalibrator().fit([p for p, _ in kal], [y for _, y in kal])
        onceki = [p for p, _ in deg]
        sonraki = [va.aralik(p).nokta for p in onceki]
        ydeg = [y for _, y in deg]
        r_on, r_son = calibration_report(onceki, ydeg), calibration_report(sonraki, ydeg)
        kayit.update(
            durum="ölçüldü",
            once=dict(beceri=r_on["brier_beceri"], ece=r_on["ece"], brier=r_on["brier"], auc=r_on["auc"]),
            sonra=dict(beceri=r_son["brier_beceri"], ece=r_son["ece"], brier=r_son["brier"], auc=r_son["auc"]),
            kalib_hazir=va.hazir,
        )
        sonuc[h] = kayit
        print(
            f"| {h}g | {len(kal)} | {len(deg)} | {n_poz} | {r_on['brier_beceri']} | **{r_son['brier_beceri']}** | "
            f"{r_on['ece']} | {r_son['ece']} | {r_on['auc']} | {r_son['auc']} |"
        )

    print("\n## Ön kayıtlı ölçütler\n")
    olculen = [h for h in UFUKLAR if sonuc[h]["durum"] == "ölçüldü"]
    if not olculen:
        print("  Hiçbir ufuk ölçülemedi → ölçüt 4 kaldı, karar verilemiyor.")
    else:
        poz = all((sonuc[h]["sonra"]["beceri"] or -1) > 0 for h in olculen)
        ece = all((sonuc[h]["sonra"]["ece"] or 1) <= (sonuc[h]["once"]["ece"] or 0) / 2 for h in olculen)
        auc = all(abs((sonuc[h]["sonra"]["auc"] or 0) - (sonuc[h]["once"]["auc"] or 0)) <= 0.005 for h in olculen)
        tam = len(olculen) == len(UFUKLAR)
        for ad, ok, aciklama in (
            ("1. beceri skoru pozitife geçer", poz, "ölçülen ufukların hepsinde"),
            ("2. ECE en az yarıya düşer", ece, "ölçülen ufukların hepsinde"),
            ("3. AUC değişmez (±0,005)", auc, "doğruluk kontrolü — kalibrasyon monotondur"),
            ("4. değerlendirme kümesi yeterli", tam, f"ölçülen {len(olculen)}/{len(UFUKLAR)} ufuk"),
        ):
            print(f"  {'GEÇTİ' if ok else 'KALDI'}  {ad}  ({aciklama})")
        print(f"\n  → C-2b (boru hattına bağlama) {'YAZILIR' if (poz and auc) else 'YAZILMAZ'}")
        print("    (ön kayıt: ölçüt 1 ve 3 birlikte geçmeli)")

    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                dict(
                    yapilandirma=dict(users=a.users, eval_days=a.eval_days, tohum=a.tohum, gun=len(gunler)),
                    n_satir=len(rows),
                    etiket_kaynagi="cevap_anahtari (ÜST SINIR — üretimde analist etiketi gecikmeli ve eksik)",
                    ufuklar=sonuc,
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
