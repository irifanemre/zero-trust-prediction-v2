"""Kural dondurma manifesti — kör koşudan önce tespit davranışını belirleyen dosya ve değerlerin kaydı.

Dondurulan küme: 21 kural YAML'ı + tespit/skorlama/profil kodu (dosya hash'i) ve okunur değer özeti. CERT ayrıştırıcısı
(`data/cert.py`) dosya olarak dondurulmaz — yeni sürüm biçimine uyarlanabilsin diye — ama URL kategorileri değer olarak
dondurulur (uygulama sınıflandırması tespiti doğrudan etkiler). Hash'ler satır sonundan bağımsızdır (CRLF → LF), aynı
içerik her makinede aynı hash'i verir.

Kullanım:
    python -m ztp.freeze --write configs/freeze/kurallar-donduruldu-v1.json   # yeni dondurma sürümü yazar
    python -m ztp.freeze --check configs/freeze/kurallar-donduruldu-v1.json   # mevcut kodu manifestle karşılaştırır
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Dict, List

import yaml

PKG = Path(__file__).resolve().parent
REPO = PKG.parent.parent
MANIFEST_VERSION = 1
FROZEN_CODE = (
    "config.py",
    "detection/catalog.py",
    "detection/engine.py",
    "detection/expr.py",
    "features.py",
    "graph/analysis.py",
    "prediction.py",
    "prediction_model.py",
    "profile.py",
    "quality.py",
    "scoring.py",
    "stats.py",
)
# kural davranışını değiştirmeyen alanlar (LLM, yollar, gizli anahtar, entegrasyon) değer özetine girmez
NON_BEHAVIOUR_FIELDS = {
    "tenant_id", "llm_backend", "ollama_model", "ollama_url", "anthropic_model", "rag_enabled", "llm_on_injection",
    "llm_max_field_len", "pseudonym_secret", "state_file", "sinks", "suppressions", "honeytokens", "critical_assets",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def frozen_files() -> List[Path]:
    rules = sorted((PKG / "detection" / "rules").glob("*.yaml"))
    return rules + [PKG / p for p in FROZEN_CODE]


def rule_summary(path: Path) -> dict:
    r = yaml.safe_load(path.read_text(encoding="utf-8"))
    sd = r.get("siddet") or {}
    return dict(
        durum=r["durum"],
        kosullar=r["mantik"]["kosullar"],
        siddet={k: sd[k] for k in ("sinyal", "esik", "olcek", "donusum", "akran_olcekleyici") if k in sd},
        agirlik=r["agirlik"],
        bastirma=r.get("bastirma") or [],
    )


def build_manifest() -> dict:
    from ztp.config import TenantConfig
    from ztp.data.cert import URL_CATEGORIES
    from ztp.detection.engine import PEER_FACTOR_MAX, PEER_FACTOR_MIN, PEER_NEUTRAL_RATIO
    from ztp.features import FEATURE_FLOOR

    cfg = TenantConfig()
    tenant = {f.name: getattr(cfg, f.name) for f in fields(cfg) if f.name not in NON_BEHAVIOUR_FIELDS}
    rules = sorted((PKG / "detection" / "rules").glob("*.yaml"))
    return dict(
        surum=MANIFEST_VERSION,
        dosyalar={p.relative_to(REPO).as_posix(): file_sha256(p) for p in frozen_files()},
        degerler=dict(
            kurallar={p.stem: rule_summary(p) for p in rules},
            tenant_varsayilanlari=json.loads(json.dumps(tenant)),
            motor=dict(PEER_NEUTRAL_RATIO=PEER_NEUTRAL_RATIO, PEER_FACTOR_MIN=PEER_FACTOR_MIN, PEER_FACTOR_MAX=PEER_FACTOR_MAX),
            ozellik_tabanlari=dict(FEATURE_FLOOR),
            cert_url_kategorileri={cat: list(keys) for cat, keys in URL_CATEGORIES},
        ),
    )


def diff_manifest(expected: dict, actual: dict) -> List[str]:
    """Manifestten sapan dosya ve değerler (boş liste = donmuş durumla aynı)."""
    out = []
    ef, af = expected["dosyalar"], actual["dosyalar"]
    for p in sorted(set(ef) | set(af)):
        if ef.get(p) != af.get(p):
            out.append(f"dosya: {p} ({'eksik' if p not in af else 'yeni' if p not in ef else 'içerik değişti'})")
    ev, av = expected["degerler"], actual["degerler"]
    for k in sorted(set(ev) | set(av)):
        if ev.get(k) != av.get(k):
            out.append(f"değer: {k}")
    return out


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", metavar="YOL")
    g.add_argument("--check", metavar="YOL")
    ap.add_argument("--etiket", default="", help="manifeste yazılacak git etiketi")
    args = ap.parse_args(argv)
    if args.write:
        m: Dict = dict(etiket=args.etiket, **build_manifest())
        Path(args.write).parent.mkdir(parents=True, exist_ok=True)
        Path(args.write).write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"yazıldı: {args.write} ({len(m['dosyalar'])} dosya)")
        return 0
    problems = diff_manifest(json.loads(Path(args.check).read_text(encoding="utf-8")), build_manifest())
    for p in problems:
        print(p)
    print("donmuş durumla aynı" if not problems else f"{len(problems)} sapma")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
