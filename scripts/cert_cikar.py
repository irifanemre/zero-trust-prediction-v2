#!/usr/bin/env python3
"""CERT tarball'ını diske sığacak biçimde çıkarır: yükleyicinin OKUMADIĞI kolonlar yazılmaz.

Neden: r6.2 açılınca ~74 GB (http.csv tek başına ~68 GB), çoğu `content` (sayfa metni). `data/cert.py`
http ve email'de `content` okumaz (20.1 veri minimizasyonu), dolayısıyla diske yazılmasına da gerek yoktur.
Satır filtresi YOKTUR: yalnız kolon düşürülür, böylece koşu resmi veriyle birebir aynı satırları görür.

Korunan kolonlar (yükleyici ne okuyorsa o):
  logon.csv   id,date,user,pc,activity
  device.csv  id,date,user,pc,activity
  http.csv    id,date,user,pc,url                     (content atılır)
  email.csv   id,date,user,pc,to,cc,bcc,size,attachments[,activity,from]   (content atılır)
  file.csv    tamamı                                  (content boyut vekilidir, atılamaz)
  LDAP/*.csv  tamamı
  psychometric.csv yazılmaz (yükleyici okumaz; 4.2 etik sınır)

Kullanım:
    python scripts/cert_cikar.py --tarball cert_data/r6.2.tar.bz2 --release r6.2 --dest cert_data
"""

from __future__ import annotations

import argparse
import bz2
import csv
import sys
import tarfile
import time
from pathlib import Path
from typing import Dict, List, Optional

csv.field_size_limit(10_000_000)  # r6+ içerik alanları uzun


def iter_lines(fh, chunk: int = 1 << 20):
    """Akış kipindeki tar üyesinden fiziksel satırlar. TextIOWrapper kullanılmaz: ileri okuması
    üye sınırını aşıp bz2 akışını bitiriyor. csv.reader tırnak içindeki satır sonlarını kendi birleştirir."""
    buf = b""
    while True:
        block = fh.read(chunk)
        if not block:
            break
        buf += block
        *lines, buf = buf.split(b"\n")
        for ln in lines:
            yield ln.decode("utf-8", "ignore")
    if buf:
        yield buf.decode("utf-8", "ignore")


# dosya → yazılacak kolonlar (None: tüm kolonlar); başlıkta olmayan kolon sessizce atlanır
KEEP: Dict[str, Optional[List[str]]] = {
    "logon.csv": ["id", "date", "user", "pc", "activity"],
    "device.csv": ["id", "date", "user", "pc", "activity"],
    "http.csv": ["id", "date", "user", "pc", "url"],
    "email.csv": ["id", "date", "user", "pc", "to", "cc", "bcc", "from", "size", "attachments", "activity"],
    "file.csv": None,
    "decoy_file.csv": None,
}
SKIP = {"psychometric.csv"}


def prune_stream(src, out_path: Path, keep: Optional[List[str]]) -> int:
    """CSV'yi satır satır okuyup seçilen kolonları yazar; satır sayısını döndürür (başlık hariç)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    reader = csv.reader(src)
    try:
        header = next(reader)
    except StopIteration:
        out_path.write_text("", encoding="utf-8")
        return 0
    # Eski sürümlerde (r1…r3) dosyalar başlıksızdır: kolon adı yoksa budama yapılmaz, dosya aynen yazılır.
    has_header = bool(header) and header[0].strip().lower() == "id"
    idx = list(range(len(header)))
    if keep is not None and has_header:
        lower = [h.strip().lower() for h in header]
        idx = [lower.index(c) for c in keep if c in lower]
        header = [header[i] for i in idx]
    n = 0
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if has_header:
            w.writerow(header)
        else:
            w.writerow(header)  # başlıksız dosyanın ilk satırı veridir; aynen korunur
            n += 1
        for row in reader:
            if not row or len(row) <= idx[-1]:  # bozuk/kısa satır atlanır
                continue
            w.writerow([row[i] for i in idx])
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tarball", required=True)
    ap.add_argument("--release", required=True, help="r4.2, r5.2, r6.2 …")
    ap.add_argument("--dest", default="./cert_data")
    args = ap.parse_args()

    dest = Path(args.dest) / args.release
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    totals: Dict[str, int] = {}

    # bz2.open: CERT tarball'ları ÇOK AKIŞLI (pbzip2); tarfile'ın kendi "r|bz2" çözücüsü ikinci akışta durur.
    with bz2.open(args.tarball, "rb") as raw, tarfile.open(fileobj=raw, mode="r|") as tar:  # tek geçiş, diske açılmaz
        for member in tar:
            if not member.isfile():
                continue
            name = Path(member.name).name
            rel = Path(member.name)
            parts = rel.parts
            if name in SKIP:
                print(f"  atlandı (yükleyici okumaz): {member.name}")
                continue
            fh = tar.extractfile(member)
            if fh is None:
                continue
            sub = Path(*parts[1:]) if len(parts) > 1 and parts[0].startswith(args.release) else rel
            out_path = dest / sub
            keep = KEEP.get(name, None if "LDAP" in parts or name.endswith(".txt") else None)
            if name.endswith(".csv"):
                n = prune_stream(iter_lines(fh), out_path, keep)
                totals[name] = totals.get(name, 0) + n
                mb = out_path.stat().st_size / 1e6
                print(f"  {sub}: {n:,} satır → {mb:,.0f} MB  ({time.time() - t0:,.0f} sn)", flush=True)
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(fh.read())
                print(f"  {sub}: kopyalandı", flush=True)

    print(f"\nTamam ({time.time() - t0:,.0f} sn). Satır sayıları:")
    for k in sorted(totals):
        print(f"  {k:<16} {totals[k]:>14,}")
    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    print(f"Toplam: {size / 1e9:,.1f} GB → {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
