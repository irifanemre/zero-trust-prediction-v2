#!/usr/bin/env python3
"""r6.2 kör koşusu, ön kayıt §3: örneklem oranı `f`'i YÜKLEYİCİ ÖLÇÜMÜYLE belirler. Tespit/skor/kuyruk ÜRETMEZ.

Plan şöyle diyor: "En büyük pencerenin tahmini tepe belleği 12 GB'ı aşarsa: tek oranlı katmanlı örneklem …
`f = min(1, 12 / tahmini tepe)`, 0,05 adımla aşağı yuvarlanır. `f` koşudan önce, yalnız yükleyici ölçümüyle
belirlenir." Bu betik o ölçümü yapar: en büyük pencereyi gerçekten yükler, tepe RSS'i ölçer, `f`'i hesaplar.

Tahmin değil ölçüm: r4.2'den devşirilen "olay başına bayt" sayısı yalnız çapraz kontrol için basılır. Karar
r6.2'nin kendi tepe RSS ölçümüne göre verilir. Yükleyici bellek bütçesini aşarsa süreç zaten burada düşer —
kör koşunun ortasında değil.

Kullanım:
    python scripts/r62_bellek_olcumu.py --cert-dir .../cert_data/r6.2 \
        --answers-dir .../cert_data/answers --out .../ztp_out_r62_hazirlik
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kor_kosu_hazirlik import BUDGET_GB, PeakMemory  # noqa: E402

from ztp.data.cert import load_cert_dataset  # noqa: E402

LOG = logging.getLogger("r62_bellek")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cert-dir", required=True)
    ap.add_argument("--answers-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    out = Path(args.out)
    sayim = json.loads((out / "r62_sayim.json").read_text(encoding="utf-8"))
    # En büyük pencere: olay sayısı en yüksek olan (tarihçesi dahil sayılmıştır)
    w = max(sayim["pencereler"], key=lambda x: x["olay"])
    LOG.info("En büyük pencere: %s → %s (tarihçe %s), %d olay", w["baslangic"], w["bitis"], w["tarihce_baslangic"], w["olay"])

    peak = PeakMemory()
    t0 = time.perf_counter()
    data = load_cert_dataset(
        args.cert_dir,
        pd.Timestamp(w["tarihce_baslangic"]),
        pd.Timestamp(w["bitis"]),
        answers_dir=args.answers_dir,
    )
    n = len(data.events)
    cerceve_gb = data.events.memory_usage(deep=True).sum() / 1e9
    tepe_gb = peak.gb()
    sure = round(time.perf_counter() - t0)

    # Tespit aşaması çerçevenin üstüne ek bellek ister. r4.2'de ölçüldü: tepe / yükleme-sonrası = 9,73 / 8,64 = 1,126.
    r42 = json.loads((out / "r42_model.json").read_text(encoding="utf-8"))
    tespit_carpani = round(r42["tepe_bellek_gb"] / r42["yukleme_sonrasi_bellek_gb"], 3)
    beklenen_tepe = round(tepe_gb * tespit_carpani, 2)
    f = 1.0 if beklenen_tepe <= BUDGET_GB else round(int(min(1.0, BUDGET_GB / beklenen_tepe) / 0.05) * 0.05, 2)

    res = dict(
        pencere=w,
        olay=n,
        cerceve_gb=round(cerceve_gb, 2),
        olculen_tepe_rss_gb=round(tepe_gb, 2),
        olay_basina_bayt=round(cerceve_gb * 1e9 / max(n, 1), 1),
        r42_olay_basina_bayt=r42["olay_basina_bayt"],
        tespit_carpani=tespit_carpani,
        beklenen_tepe_gb=beklenen_tepe,
        bellek_butcesi_gb=BUDGET_GB,
        orneklem_orani_f=f,
        orneklem_gerekli=f < 1.0,
        yukleme_sure_sn=sure,
    )
    del data
    gc.collect()
    (out / "r62_bellek_olcumu.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("ÖLÇÜM: %s", json.dumps(res, ensure_ascii=False))
    if f < 1.0:
        LOG.warning("Örneklem GEREKLİ: f=%.2f — plan §3 adım 2 uygulanacak (katmanlı, tohum 42)", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
