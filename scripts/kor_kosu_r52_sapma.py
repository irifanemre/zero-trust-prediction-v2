#!/usr/bin/env python3
"""CERT r5.2 kör koşusu — koşu SONRASI sapma kaydı: ikincil LR bölmesinin örneklemle çakışması.

Hata: `cert-r5.2-kullanici-bolmesi.json` (2000 kullanıcı) ve `cert-r5.2-orneklem.json` aynı tohumla (42) ve aynı
RandomState akışıyla üretildi. Katman içi permütasyonlar örtüştüğü için örneklemin 1102 kullanıcısının 1071'i eğitim
parçasına düştü; ikincil protokolde doğrulama/test 2'şer kullanıcıyla kaldı. Kurallar, eşikler, birincil model ve
tespit çıktıları bölmeyi kullanmaz — etkilenmez.

Düzeltme: bölme, aynı yöntemle (make_user_split, 70/15/15, tohum 42) yalnız örneklemin kullanıcıları üzerinde yeniden
üretilir ve ikincil protokol kaydedilmiş tahmin satırlarıyla (pencere_*.npz) yeniden hesaplanır. Boru hattı yeniden
koşulmaz. Ön kayıtlı sonuç (`sonuclar.json`) değiştirilmez; düzeltilmiş sonuç `sapma_ikincil_lr.json`'a yazılır.

Kullanım:
    python scripts/kor_kosu_r52_sapma.py --out C:/data/ztp_out/kor_r52
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from ztp.evaluation import lr_protocol, make_user_split, save_split
from ztp.prediction_model import PREDICTION_FEATURES

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "configs" / "splits" / "cert-r5.2-orneklem.json"
OLD_SPLIT = REPO / "configs" / "splits" / "cert-r5.2-kullanici-bolmesi.json"
NEW_SPLIT = REPO / "configs" / "splits" / "cert-r5.2-orneklem-bolmesi.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="./ztp_out/kor_r52")
    args = ap.parse_args()
    out = Path(args.out)
    users = json.loads(SAMPLE.read_text(encoding="utf-8"))["kullanicilar"]
    old = json.loads(OLD_SPLIT.read_text(encoding="utf-8"))["atama"]
    overlap = {p: sum(1 for u in users if old.get(u) == p) for p in ("egitim", "dogrulama", "test")}
    res = json.loads((out / "sonuclar.json").read_text(encoding="utf-8"))
    strata = {r["sid"]: r["katman"] for r in res["sonuc"]["senaryolar"]}  # örneklemdeki 56 insider ve senaryo türü
    gt = [dict(senaryo=f"CERT-r5.2-{k}-{u}", sid=u) for u, k in sorted(strata.items())]
    split = make_user_split(users, gt, seed=42, source="cert-r5.2 örneklemi (1102 kullanıcı); koşu sonrası sapma düzeltmesi")
    save_split(split, NEW_SPLIT)
    parts = [np.load(p, allow_pickle=False) for p in sorted(out.glob("pencere_*.npz"))]
    X = np.concatenate([p["X"] for p in parts])
    y = np.concatenate([p["y"] for p in parts])
    rows = [
        dict(gun=g, sid=s, ozellikler=dict(zip(PREDICTION_FEATURES, map(float, x))), p7_sezgisel=float(h))
        for g, s, x, h in zip(
            np.concatenate([p["gun"] for p in parts]),
            np.concatenate([p["sid"] for p in parts]),
            X,
            np.concatenate([p["heur"] for p in parts]),
        )
    ]
    doc = dict(
        hata=dict(eski_bolmede_orneklem_dagilimi=overlap, aciklama=__doc__.split("\n\n")[1].replace("\n", " ")),
        yeni_bolme=dict(dosya=NEW_SPLIT.name, ozet=split["meta"]["ozet"]),
        ikincil=lr_protocol(rows, y.tolist(), split),
    )
    (out / "sapma_ikincil_lr.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(dict(overlap=overlap, ozet=split["meta"]["ozet"]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
