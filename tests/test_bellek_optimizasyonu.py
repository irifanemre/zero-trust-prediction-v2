"""Bellek optimizasyonunun (kategorik dtype) davranışı DEĞİŞTİRMEDİĞİNİ koruyan bekçi sınamaları.

Tuzak: pandas'ta kategorik anahtarla `groupby(observed=False)` o gün hiç görülmemiş kategoriler için de satır
üretir (count=0, zaman=NaT). Nesne dtype'ında böyle bir satır yoktur. Bu, graf kenarlarını ve veri kalitesi
metriklerini sessizce değiştirir. İki kural birlikte yeterlidir:
  1. Kategoriye çevrilen bir kolon, DONDURULMUŞ bir dosyada groupby anahtarı olamaz (düzeltilemez).
  2. Dondurulmamış tüketiciler o anahtarları `observed=True` ile gruplar.
"""

import ast
import json
from pathlib import Path

import pandas as pd

from ztp.data.cert import COMPACT_CATEGORICAL

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "ztp"


def _groupby_key_literals(tree: ast.AST) -> set:
    """Kaynaktaki her `groupby(...)` çağrısının dizgi sabiti anahtarları + observed bayrağı."""
    out = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "groupby"):
            continue
        observed = next((k.value.value for k in node.keywords if k.arg == "observed"), None)
        keys = []
        for arg in node.args[:1]:
            items = arg.elts if isinstance(arg, (ast.List, ast.Tuple)) else [arg]
            keys += [i.value for i in items if isinstance(i, ast.Constant) and isinstance(i.value, str)]
        for k in keys:
            out.add((k, observed))
    return out


def _frozen_py_files() -> list:
    manifest = json.loads((REPO / "configs" / "freeze" / "kurallar-donduruldu-v3.json").read_text(encoding="utf-8"))
    dosyalar = manifest.get("dosyalar") or manifest.get("files") or {}
    return [REPO / p for p in dosyalar if str(p).endswith(".py")]


def test_kategorik_kolon_dondurulmus_dosyada_groupby_anahtari_degil():
    """Dondurulmuş dosya düzeltilemez; o yüzden anahtarı olduğu kolon kategoriye ÇEVRİLMEZ (ör. `source`)."""
    ihlal = []
    for f in _frozen_py_files():
        if not f.exists():
            continue
        for anahtar, observed in _groupby_key_literals(ast.parse(f.read_text(encoding="utf-8"))):
            if anahtar in COMPACT_CATEGORICAL and observed is not True:
                ihlal.append(f"{f.relative_to(REPO)}: groupby({anahtar!r}) — kolon COMPACT_CATEGORICAL'dan çıkarılmalı")
    assert not ihlal, "Dondurulmuş dosyada kategorik groupby anahtarı:\n" + "\n".join(ihlal)


def test_dondurulmamis_tuketiciler_observed_true_kullaniyor():
    ihlal = []
    frozen = {f.resolve() for f in _frozen_py_files()}
    for f in sorted(SRC.rglob("*.py")):
        if f.resolve() in frozen:
            continue
        for anahtar, observed in _groupby_key_literals(ast.parse(f.read_text(encoding="utf-8"))):
            if anahtar in COMPACT_CATEGORICAL and observed is not True:
                ihlal.append(f"{f.relative_to(REPO)}: groupby({anahtar!r}) — observed=True gerekir")
    assert not ihlal, "Kategorik anahtarda observed bayrağı eksik:\n" + "\n".join(ihlal)


def test_source_kategoriye_cevrilmiyor():
    """Bekçi: `source`, dondurulmuş quality.py'nin groupby anahtarıdır — eklenirse veri kalitesi metrikleri bozulur."""
    assert "source" not in COMPACT_CATEGORICAL


def test_observed_false_hayalet_satir_uretir():
    """Tuzağın kendisi belgelenir: aynı veri, kategorik dtype ile 3 yerine 52 satır ve 49 hayalet kenar verir."""
    df = pd.DataFrame(
        {
            "canonical": ["u1", "u1", "u2"],
            "resource": ["A", "B", "A"],
            "event_id": ["e1", "e2", "e3"],
            "time": pd.to_datetime(["2010-01-01"] * 3),
        }
    )
    kategoriler = ["A", "B"] + [chr(c) for c in range(ord("C"), ord("Z") + 1)]
    kat = df.assign(resource=pd.Categorical(df["resource"], categories=kategoriler))
    agg = lambda d, obs: d.groupby(["canonical", "resource"], observed=obs).agg(n=("event_id", "size"))  # noqa: E731
    assert len(agg(df, True)) == 3
    assert len(agg(kat, False)) == 52  # hayalet satırlar
    assert len(agg(kat, True)) == 3  # nesne dtype'ıyla birebir
