#!/usr/bin/env python
"""Eşik ulaşılabilirlik denetimi — "bu kural hiç tetiklenebilir mi?"

Üç kez aynı hataya düşüldü ve üçünde de kural **yapısal olarak ulaşılamaz** oldu:

1. `UEBA-0003` r6.2'de: `http.csv`'de `content` kolonu yok → `bytes_out = 0` → hacim sinyali hiç
   üretilmiyor. Kural ağırlığı 8, en ağır iki UEBA kuralından biri, ve o koşuda hiç tetiklenemedi.
2. İlk `UEBA-0022` eşiği (`p < 0.001`): seyrek bir sayaçta o p değeri 8 olay (15 kat sıçrama)
   istiyordu; yoğun sayaçta aynı eşik ~2,5 kat sıçramayla geçiliyordu.
3. İlk `UEBA-0023` tabanı (5 MB): `bytes_out`'tan kopyalanmıştı. Dış e-posta kullanıcı-gün
   medyanı 0,10 MB, veri setindeki en büyük gün 0,99 MB — eşik verinin 18 katı uzağındaydı.

Ortak kalıp: **başka ölçekten alınan bir sabit, eşiği verinin erişemeyeceği yere koyuyor.** Bu,
testlerle yakalanmaz çünkü kod doğrudur; kural sessizce hiç tetiklenmez ve raporda "bu veride
desen görülmedi" diye görünür — bozuk olduğu anlaşılmaz.

Bu betik sentetik veri üzerinde her sinyalin GÖZLENEN aralığını çıkarır, kural eşikleriyle
karşılaştırır ve eşiği aralığın dışında kalan kuralları listeler.

    PYTHONPATH=src python scripts/esik_ulasilabilirlik.py
    PYTHONPATH=src python scripts/esik_ulasilabilirlik.py --kullanici 250 --gun 160

Çıkış kodu 1 ise en az bir `yayinda` kuralın eşiği ulaşılamazdır.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from ztp.config import TenantConfig
from ztp.data.synthetic import SyntheticOrg
from ztp.detection.catalog import load_catalog
from ztp.schema import DAY

# Karşılaştırma operatörleri: (ast düğümü, "sinyal eşiğin hangi yanında olmalı")
KARSILASTIRMA = {ast.Gt: ">", ast.GtE: ">=", ast.Lt: "<", ast.LtE: "<=", ast.Eq: "==", ast.NotEq: "!="}


def kosul_esikleri(kosul: str) -> List[Tuple[str, str, float]]:
    """`veri_hacmi_z > 3.5` → [("veri_hacmi_z", ">", 3.5)]. Karmaşık ifadelerde tüm karşılaştırmalar."""
    try:
        agac = ast.parse(kosul, mode="eval")
    except SyntaxError:
        return []
    out = []
    for d in ast.walk(agac):
        if not isinstance(d, ast.Compare) or len(d.ops) != 1 or len(d.comparators) != 1:
            continue
        op = KARSILASTIRMA.get(type(d.ops[0]))
        sol, sag = d.left, d.comparators[0]
        if op and isinstance(sol, ast.Name) and isinstance(sag, ast.Constant) and isinstance(sag.value, (int, float)):
            out.append((sol.id, op, float(sag.value)))
        elif op and isinstance(sag, ast.Name) and isinstance(sol, ast.Constant) and isinstance(sol.value, (int, float)):
            ters = {">": "<", "<": ">", ">=": "<=", "<=": ">="}.get(op, op)
            out.append((sag.id, ters, float(sol.value)))
    return out


def sinyal_araliklari(n_kullanici: int, n_gun: int, tohum: int) -> Dict[str, Tuple[float, float, int]]:
    """Sentetik veride her sinyalin (en küçük, en büyük, gözlem sayısı) değeri.

    TAM hattı koşar — yalnız profil katmanını değil. Tahmin, graf ve kanal sinyalleri ancak hat
    koşunca üretilir; eksik koşmak "sinyal hiç üretilmedi" diye yanlış bulgu verir.
    Aldatma katmanı da açılır, yoksa HONEY-* kuralları ulaşılamaz görünür.
    """
    from ztp.detection.catalog import load_catalog as _kat
    from ztp.pipeline import ZeroTrustPredictionPipeline

    cfg = TenantConfig(
        tenant_id="esik",
        llm_backend="none",
        sinks=[],
        threshold_jitter=0.0,
        alarm_budget_per_day=20,
        # Tüm opsiyonel bileşenler AÇIK: amacı en geniş sinyal kümesini görmek, performans ölçmek değil.
        graf_enabled=True,
        graf_agirligi=0.5,
        anomali_enabled=True,
        belirsizlik_enabled=True,
        saldiri_yolu_enabled=True,
        geri_bildirim_dongusu=True,
    )
    eval_gun = min(45, max(10, n_gun // 3))
    data = SyntheticOrg(n_users=n_kullanici, n_days=n_gun, eval_days=eval_gun, seed=tohum, honeytokens=True).build()
    cfg.honeytokens = data.honeytokens or {}
    cfg.available_sources = tuple(sorted(set(data.events["source"].astype(str).unique()) | {"hr"}))
    aralik: Dict[str, List[float]] = defaultdict(list)

    def gozlemci(_gun, sinyaller: Dict[str, dict]) -> None:
        for s_ in sinyaller.values():
            for ad, deger in s_.items():
                if isinstance(deger, (int, float)) and not isinstance(deger, bool):
                    aralik[ad].append(float(deger))

    with tempfile.TemporaryDirectory() as td:
        pipe = ZeroTrustPredictionPipeline(cfg, data, _kat(), Path(td))
        pipe.sinyal_gozlemci = gozlemci
        son = data.events["time"].max().normalize()
        pipe.run(son - (eval_gun - 1) * DAY, son, warmup_days=14)
    return {ad: (min(v), max(v), len(v)) for ad, v in aralik.items() if v}


def denetle(araliklar: Dict[str, Tuple[float, float, int]], katalog: List[dict]) -> List[dict]:
    """Her kuralın her eşiğini gözlenen aralıkla karşılaştırır."""
    bulgular = []
    for kural in katalog:
        for kosul in kural["mantik"]["kosullar"]:
            for sinyal, op, esik in kosul_esikleri(kosul):
                if sinyal not in araliklar:
                    bulgular.append(
                        dict(kural=kural["id"], durum=kural["durum"], kosul=kosul, sinyal=sinyal, sorun="sinyal hiç üretilmedi")
                    )
                    continue
                alt, ust, n = araliklar[sinyal]
                ulasir = {
                    ">": ust > esik,
                    ">=": ust >= esik,
                    "<": alt < esik,
                    "<=": alt <= esik,
                    "==": alt <= esik <= ust,
                    "!=": True,
                }[op]
                if not ulasir:
                    pay = (esik / ust) if op in (">", ">=") and ust > 0 else None
                    bulgular.append(
                        dict(
                            kural=kural["id"],
                            durum=kural["durum"],
                            kosul=kosul,
                            sinyal=sinyal,
                            gozlenen=f"[{alt:.6g}, {ust:.6g}] (n={n})",
                            esik=esik,
                            sorun="eşik gözlenen aralığın dışında",
                            kat=(round(pay, 1) if pay else None),
                        )
                    )
    return bulgular


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kullanici", type=int, default=200)
    ap.add_argument("--gun", type=int, default=150)
    ap.add_argument("--tohum", type=int, default=42)
    ap.add_argument("--json", action="store_true", help="bulguları JSON olarak yaz")
    ap.add_argument("--golge-dahil", action="store_true", help="gölge moddaki kuralları da hata say")
    args = ap.parse_args()

    araliklar = sinyal_araliklari(args.kullanici, args.gun, args.tohum)
    bulgular = denetle(araliklar, load_catalog())
    if args.json:
        print(json.dumps(dict(sinyal=len(araliklar), bulgular=bulgular), ensure_ascii=False, indent=1))
    else:
        print(f"Sentetik veride {len(araliklar)} sinyal gözlendi ({args.kullanici} kullanıcı, {args.gun} gün).\n")
        if not bulgular:
            print("Her kural eşiği gözlenen aralığın içinde — ulaşılamaz eşik yok.")
        for b in bulgular:
            isaret = "✘" if b["durum"] == "yayinda" else "·"
            print(f"  {isaret} {b['kural']:<12} [{b['durum']}] {b['kosul']}")
            print(f"      {b['sorun']}" + (f" — gözlenen {b['gozlenen']}" if "gozlenen" in b else ""))
            if b.get("kat"):
                print(f"      eşik, gözlenen en büyük değerin {b['kat']} katı")
        print(
            "\nNot: sentetik veri gerçek kurumu temsil etmez; burada ulaşılabilen bir eşik gerçek veride\n"
            "ulaşılamaz olabilir (r6.2'de `content` kolonunun olmaması gibi). Bu denetim ALT sınırdır."
        )
    hatali = [b for b in bulgular if args.golge_dahil or b["durum"] == "yayinda"]
    return 1 if hatali else 0


if __name__ == "__main__":
    sys.exit(main())
