"""Faz A-2 ölçütü 3: gerçek bir CERT sürümünde ŞEMA KARARI ne diyor?

Ön kayıt (`docs/faz-a2-on-kayit.md`) üç ölçüt yazdı. Üçüncüsü şu:

> Bayrak açıkken r6.2'de `UEBA-0003` `sinanamaz — şema` raporlanır ve S5 `ÖLÇÜLEMEDİ`/kısmi işaretlenir.

Bu betik o ölçütü ÖLÇER ama tam koşu yapmaz: şema kararı veri setinin ŞEMASINDAN çıkar, koşunun
sonucundan değil. Harita motor kurulurken, tek bir gün işlenmeden önce hesaplanır — dolayısıyla
kısa bir pencere, 360 günlük koşuyla aynı kararı verir. Yakalama/precision rakamları bu betikten
ÇIKMAZ; onlar için gerçek koşu gerekir.

Kullanım:
    python scripts/sema_karar_dogrula.py --cert-dir ~/Desktop/zero_trust_prediction/cert_data/r6.2
    python scripts/sema_karar_dogrula.py --cert-dir .../r4.2 --gun 30   # karşılaştırma (uyarı beklenmez)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ztp.availability import SINYAL_TUREV, kural_mevcudiyeti, senaryo_olculebilirligi  # noqa: E402
from ztp.config import TenantConfig  # noqa: E402
from ztp.data.cert import load_cert_dataset  # noqa: E402
from ztp.detection.catalog import load_catalog  # noqa: E402
from ztp.detection.engine import DetectionEngine  # noqa: E402
from ztp.schema_profiler import profille, rapor  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("sema-karar")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cert-dir", required=True)
    ap.add_argument("--answers-dir", default=None)
    ap.add_argument("--gun", type=int, default=30, help="pencere uzunluğu; şema kararını DEĞİŞTİRMEZ")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    base = Path(a.cert_dir).expanduser()
    surum = base.name
    a.answers_dir = a.answers_dir or str(base.parent / "answers")

    # Pencere: logon.csv'nin son günü geriye doğru. Şema kararı pencereden bağımsızdır; kısa tutulur.
    from kor_kosu_hazirlik import logon_bounds

    d0, d1 = logon_bounds(base)
    start, end = d1 - pd.Timedelta(days=a.gun), d1
    LOG.info("%s yükleniyor (%s … %s) — 17 GB http.csv taranıyor, sabırlı ol", surum, start.date(), end.date())
    t0 = time.perf_counter()
    data = load_cert_dataset(str(base), start, end, answers_dir=a.answers_dir)
    LOG.info("yüklendi: %d olay, %d kullanıcı, %.0f sn", len(data.events), len(data.directory), time.perf_counter() - t0)

    harita = profille(surum, ham_dizin=base, events=data.events)
    katalog = load_catalog()
    m = kural_mevcudiyeti(katalog, harita)

    cfg = TenantConfig(tenant_id=f"sema-{surum}", pseudonym_secret="x", sema_farkindaligi=True)
    cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
    motor = DetectionEngine(cfg, katalog, mevcudiyet=m)

    print()
    print(rapor(harita))
    print(f"\n## Şema kararı — {surum}\n")
    print(f"Katalog {len(katalog)} kural · şemadan ölü {len(m.olu)} · motorda sınanamaz {len(motor.sema_olu)}")
    print("(fark: 'kaynak yok' ile elenen kurallar şema damgası almaz — kurulum sebebi, veri sebebi değil)\n")
    for rid in sorted(motor.sema_olu):
        print(f"  {rid}: {motor.sema_olu[rid]}")
    if not motor.sema_olu:
        print("  (yok — her veri bağımlı sinyal bu veri setinde üretilebiliyor)")

    print(f"\n## Senaryo ölçülebilirliği — {surum}\n")
    pozitif = [g for g in data.ground_truth if not g.get("negatif")]
    sayac = {"olculebilir": 0, "kismi": 0, "olculemez": 0}
    satirlar = []
    for g in pozitif:
        beklenen = sorted(g.get("beklenen", []))
        durum = senaryo_olculebilirligi(beklenen, m)
        sayac[durum] += 1
        olu = [b for b in beklenen if not m.degerlendirilebilir(b)]
        satirlar.append(dict(senaryo=g["senaryo"], aktor=g["aktor"], beklenen=beklenen, durum=durum, olu=olu))
        if durum != "olculebilir":
            print(f"  {g['senaryo']:<28} {g['aktor']:<10} {durum:<12} ölü: {', '.join(olu) or '-'}")
    print(f"\n  ölçülebilir {sayac['olculebilir']} · kısmi {sayac['kismi']} · ÖLÇÜLEMEZ {sayac['olculemez']}")
    print(f"  → kapsama paydası {len(pozitif)} değil {len(pozitif) - sayac['olculemez']} olmalı")

    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                dict(
                    surum=surum,
                    pencere=[str(start.date()), str(end.date())],
                    olay=len(data.events),
                    sema=harita.ozet(),
                    mevcudiyet=m.ozet(),
                    motor_sinanamaz=motor.sema_olu,
                    senaryolar=satirlar,
                    sayac=sayac,
                    haritalanan_sinyal=len(SINYAL_TUREV),
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
