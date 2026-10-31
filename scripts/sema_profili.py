#!/usr/bin/env python
"""Şema profili raporu — "bu veri setinde hangi sinyal gerçekten var?"

Yalnız OKUR; hiçbir kararı değiştirmez. Ham başlıklar dosya başına tek satır okunur, dolayısıyla
17 GB'lık bir `http.csv`'de bile anlıktır. `--olaylar` verilirse veri seti ayrıştırılıp olay
alanlarının doluluk/tekillik profili de çıkarılır (yavaş).

    PYTHONPATH=src python scripts/sema_profili.py --cert-dir .../r6.2
    PYTHONPATH=src python scripts/sema_profili.py --cert-dir .../r6.2 --olaylar --gun 30
    PYTHONPATH=src python scripts/sema_profili.py --karsilastir .../r4.2 .../r5.2 .../r6.2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from ztp.schema_profiler import profille, rapor

DOSYALAR = ("logon.csv", "device.csv", "http.csv", "email.csv", "file.csv", "decoy_file.csv", "psychometric.csv")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cert-dir")
    ap.add_argument("--karsilastir", nargs="+", metavar="DIZIN", help="birden çok veri setini yan yana özetle")
    ap.add_argument("--olaylar", action="store_true", help="veriyi ayrıştır ve olay alanlarını da profille (yavaş)")
    ap.add_argument("--gun", type=int, default=30, help="--olaylar ile: kaç günlük pencere okunacak")
    ap.add_argument("--out", help="raporu bu dosyaya yaz")
    args = ap.parse_args()

    if args.karsilastir:
        print(f"{'veri seti':<12}{'uyarı':>7}{'not':>6}  kural öldüren eksikler")
        for d in args.karsilastir:
            h = profille(Path(d).name, ham_dizin=Path(d), ham_dosyalar=DOSYALAR)
            ilk = h.uyarilar[0] if h.uyarilar else "—"
            print(f"{h.veri_seti:<12}{len(h.uyarilar):>7}{len(h.notlar):>6}  {ilk}")
            for u in h.uyarilar[1:]:
                print(f"{'':<25}  {u}")
        return 0

    if not args.cert_dir:
        ap.error("--cert-dir ya da --karsilastir gerekli")
    d = Path(args.cert_dir)
    events = None
    if args.olaylar:
        from ztp.data.cert import load_cert_dataset

        son = pd.Timestamp("2010-11-30")
        events = load_cert_dataset(str(d), son - (args.gun - 1) * pd.Timedelta(days=1), son).events
    h = profille(d.name, ham_dizin=d, events=events, ham_dosyalar=DOSYALAR)
    metin = rapor(h)
    if args.out:
        Path(args.out).write_text(metin, encoding="utf-8")
        print(f"yazıldı: {args.out}")
    else:
        print(metin)
    return 1 if h.uyarilar else 0


if __name__ == "__main__":
    sys.exit(main())
