"""Robust-z taban sabitlerini TÜRETME — tahmin yerine kural.

`robust_z(x, med, mad, floor) = 0.6745 · (x − med) / max(mad, floor)`. Taban, kullanıcının kendi
MAD'i dejenere olduğunda onun yerine geçen **asgari ölçektir**. Dolayısıyla yerine geçtiği şeyin
tipik büyüklüğünde olmalı: daha küçüğü sahte alarm, daha büyüğü sağırlık üretir.

Türetme kuralı (`docs/v10-on-kayit.md`, ölçümden önce yazıldı):

> taban = nüfus genelinde, kullanıcı başına günlük değerin MAD'inin **medyanı**

Kural, sonucu bilinen bir yerde sınanır: `FEATURE_FLOOR["bytes_out"] = 5e6` çalışan bir sabittir.
Kural onu ±3 kat içinde yeniden üretirse sağlamdır. Bu sınama, eşiği sonuca göre ayarlamanın önüne
geçen tek korumadır.

**Senaryo günleri hariç tutulur**: enjekte edilen sızıntı günleri MAD'i şişirir ve eşik saldırıya
göre ayarlanmış olur — döngüsel.

Kullanım:
    python scripts/taban_turet.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ztp.config import TenantConfig  # noqa: E402
from ztp.data.synthetic import SyntheticOrg  # noqa: E402
from ztp.features import FEATURE_FLOOR, extract_features  # noqa: E402
from ztp.metrics import MetricsCollector  # noqa: E402
from ztp.schema import DAY  # noqa: E402

MIN_GUN = 20  # bu kadar günü olmayan kullanıcı MAD'e girmez: dejenere spread gürültü üretir


def _senaryo_gunleri(gt: list, pseud=None) -> set:
    """Enjekte edilen senaryo pencereleri — (sid, gün) çiftleri. Taban hesabından çıkarılır."""
    out = set()
    for g in gt:
        w0, w1 = MetricsCollector._window(g, grace_days=0)
        gun = w0
        while gun <= w1:
            out.add((g["sid"], pd.Timestamp(gun).normalize()))
            gun = gun + DAY
    return out


def taban_turet(feat: pd.DataFrame, kolon: str, haric: set) -> dict:
    """Türetme kuralı: kullanıcı başına MAD'lerin medyanı."""
    df = feat[["sid", "day", kolon]].copy()
    df["day"] = pd.to_datetime(df["day"]).dt.normalize()
    temiz = df[~df.set_index(["sid", "day"]).index.isin(haric)]
    mads = []
    for sid, grup in temiz.groupby("sid"):
        v = grup[kolon].astype(float)
        if len(v) < MIN_GUN:
            continue
        mads.append(float((v - v.median()).abs().median()))
    mads = np.array([m for m in mads if np.isfinite(m)])
    if not len(mads):
        return dict(kolon=kolon, n_kullanici=0, taban=None)
    return dict(
        kolon=kolon,
        n_kullanici=int(len(mads)),
        atilan_gun=len(df) - len(temiz),
        mad_medyan=float(np.median(mads)),
        mad_p25=float(np.percentile(mads, 25)),
        mad_p75=float(np.percentile(mads, 75)),
        deger_medyan=float(temiz[kolon].median()),
        taban=float(np.median(mads)),
    )


def yuvarla(x: float) -> float:
    """En yakın 1/2/5 × 10^k değerine yuvarlar — sabit okunabilir kalsın."""
    if x <= 0:
        return 0.0
    k = math_floor_log10(x)
    for m in (1.0, 2.0, 5.0, 10.0):
        if x <= m * 10**k * 1.5:
            return m * 10**k
    return 10.0 ** (k + 1)


def math_floor_log10(x: float) -> int:
    return int(np.floor(np.log10(x)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=80)
    ap.add_argument("--eval-days", type=int, default=12)
    ap.add_argument("--tohum", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cfg = TenantConfig(tenant_id="taban", pseudonym_secret="s")
    end = pd.Timestamp("2026-09-16")
    data = SyntheticOrg(
        n_users=a.users, n_days=cfg.long_window_days + a.eval_days + 10, eval_days=a.eval_days, end_day=end, seed=a.tohum
    ).build()
    # Özellik çıkarımı kimlik eşleştirmesi ister (`canonical`, `is_service` kolonları).
    from ztp.identity import IdentityResolver
    from ztp.schema import to_utc_naive

    ev = data.events.copy()
    ev["time"] = to_utc_naive(ev["time"])
    ev["received_time"] = to_utc_naive(ev["received_time"])
    ev = IdentityResolver(data.directory, data.ip_leases).resolve(ev)
    feat = extract_features(ev, data.critical_assets)
    haric = _senaryo_gunleri(data.ground_truth)

    print(f"\n# Taban türetme — {a.users} kullanıcı, tohum {a.tohum}\n")
    print(f"Senaryo günleri hariç tutuldu: {len(haric)} (sid, gün) çifti\n")

    print("## 1. Kuralın sınanması — bilinen-iyi sabit\n")
    b = taban_turet(feat, "bytes_out", haric)
    bilinen = FEATURE_FLOOR["bytes_out"]
    turetilen = yuvarla(b["taban"])
    kat = turetilen / bilinen if bilinen else float("inf")
    gecti = (1 / 3) <= kat <= 3
    print(f"| | değer |")
    print(f"|---|---|")
    print(f"| `bytes_out` günlük medyan | {b['deger_medyan']:,.0f} |")
    print(f"| kullanıcı MAD'i medyanı | {b['mad_medyan']:,.0f} |")
    print(f"| MAD çeyrekler (p25–p75) | {b['mad_p25']:,.0f} – {b['mad_p75']:,.0f} |")
    print(f"| **türetilen taban** | **{turetilen:,.0f}** |")
    print(f"| bilinen-iyi (`FEATURE_FLOOR`) | {bilinen:,.0f} |")
    print(f"| oran | **{kat:.2f}×** |")
    print(f"\n  → kural {'GEÇTİ' if gecti else 'KALDI'} (±3 kat sınırı)")

    print("\n## 2. Kural geçtiyse: `EPOSTA_TABAN`\n")
    e = taban_turet(feat, "ext_email_bytes", haric)
    e_turetilen = yuvarla(e["taban"]) if e["taban"] else None
    if not gecti:
        print("  Kural sınamayı geçmedi → EPOSTA_TABAN DEĞİŞTİRİLMEZ (ön kayıt ölçütü 1).")
    elif not e_turetilen:
        print("  Dış e-posta MAD'i hesaplanamadı.")
    else:
        print(f"| `ext_email_bytes` günlük medyan | {e['deger_medyan']:,.0f} |")
        print(f"|---|---|")
        print(f"| kullanıcı MAD'i medyanı | {e['mad_medyan']:,.0f} |")
        print(f"| MAD çeyrekler (p25–p75) | {e['mad_p25']:,.0f} – {e['mad_p75']:,.0f} |")
        print(f"| **türetilen taban** | **{e_turetilen:,.0f}** |")
        print(f"| şu anki (v8) | 50,000 |")
        print(f"| oran | **{e_turetilen / 50_000:.1f}×** |")
        print(f"\n  tetikleme eşiği: x > med + {5.19 * e_turetilen / 1e6:.2f} MB "
              f"(şu an med + {5.19 * 50_000 / 1e6:.2f} MB)")

    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                dict(
                    bytes_out=dict(**b, turetilen=turetilen, bilinen=bilinen, oran=kat, kural_gecti=gecti),
                    ext_email_bytes=dict(**e, turetilen=e_turetilen, suanki=50_000),
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
