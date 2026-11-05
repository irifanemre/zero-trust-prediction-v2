"""Faz B ölçüm aracı — kanal kurallarının sentetik veride sınanabilirliği.

`UEBA-0022` (bulut), `UEBA-0023` (dış e-posta) ve `UEBA-0024` (kişisel webmail) üçü de gölge
modda doğdu ve **hiçbir veride doğrulanamadı**: r4.2'nin 34 senaryosunun 31'i USB'ye bağımlı,
sentetik üreteç ise e-posta hiç üretmiyor. Bu araç o boşluğu ölçer ve Faz B'nin önce/sonra
karşılaştırmasını sabit bir yapılandırmayla tekrarlanabilir kılar.

Yapılandırma BİLEREK sabit: tohum, kullanıcı sayısı ve pencere komut satırından değiştirilebilir
ama varsayılanları `tests/test_pipeline.py::test_pipeline_end_to_end` ile aynıdır — iki ölçüm aynı
veriden konuşsun.

Kullanım:
    python scripts/kanal_senaryo_olcumu.py                        # referans
    python scripts/kanal_senaryo_olcumu.py --out faz-b-oncesi.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ztp.config import TenantConfig  # noqa: E402
from ztp.data.synthetic import SyntheticOrg  # noqa: E402
from ztp.detection.catalog import load_catalog  # noqa: E402
from ztp.features import extract_features  # noqa: E402
from ztp.pipeline import ZeroTrustPredictionPipeline  # noqa: E402
from ztp.schema import CLOUD_APPS, SENSITIVE_APPS  # noqa: E402

KANAL_KURALLARI = ("UEBA-0022", "UEBA-0023", "UEBA-0024")
# Kanal sinyalleri: üretilip üretilmediği ölçülür. Sıfır toplam = kural yapısal olarak sınanamaz.
KANAL_SINYALLERI = ("cloud_app_count", "ext_email_bytes", "ext_email_count", "webmail_count", "sensitive_app_count")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=80)
    ap.add_argument("--eval-days", type=int, default=12)
    ap.add_argument("--tohum", type=int, default=7)
    ap.add_argument("--butce", type=int, default=6)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    end = pd.Timestamp("2026-09-16")
    cfg = TenantConfig(tenant_id="kanal", pseudonym_secret="s", alarm_budget_per_day=a.butce, threshold_jitter=0.0)
    data = SyntheticOrg(
        n_users=a.users,
        n_days=cfg.long_window_days + a.eval_days + 10,
        eval_days=a.eval_days,
        end_day=end,
        seed=a.tohum,
    ).build()

    ev = data.events
    sozluk = sorted({str(x) for x in ev["app"].dropna().unique()})
    kaynaklar = sorted(ev["source"].unique())

    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), Path(tempfile.mkdtemp()))
    pipe.run(end - pd.Timedelta(days=a.eval_days - 1), end, warmup_days=10)
    m = pipe.metrics
    cov = m.coverage()
    pozitif = [c for c in cov if "negatif" not in c["senaryo"].lower()]
    negatif = [c for c in cov if "negatif" in c["senaryo"].lower()]
    golge = collections.Counter(s["kural"] for s in pipe.engine.shadow_log)
    # Özellik tablosu boru hattında yerel; sinyal ölçümü için aynı girdiden yeniden çıkarılır.
    feat = extract_features(pipe.events, pipe.crit)

    print(f"\n# Kanal senaryo ölçümü — {a.users} kullanıcı, {a.eval_days} gün, tohum {a.tohum}\n")
    print(f"Kaynaklar : {', '.join(kaynaklar)}")
    print(f"App sözcükleri ({len(sozluk)}): {', '.join(sozluk)}")
    kesisim = sorted(set(sozluk) & SENSITIVE_APPS)
    print(f"Tespit katmanının tanıdığı app  : {kesisim or 'HİÇBİRİ — hassas kategori sinyali yalnız senaryodan gelir'}")
    print(f"Bulut app'i olan ({len(CLOUD_APPS)} tanımlı): {sorted(set(sozluk) & CLOUD_APPS) or 'yok'}")

    print("\n## Kanal sinyalleri üretiliyor mu\n")
    print("| Sinyal | Toplam | Sıfır olmayan kullanıcı-günü |")
    print("|---|---|---|")
    sinyal_ozet = {}
    for c in KANAL_SINYALLERI:
        if c in feat.columns:
            toplam, gun = float(feat[c].sum()), int((feat[c] > 0).sum())
        else:
            toplam, gun = 0.0, 0
        sinyal_ozet[c] = dict(toplam=toplam, gun=gun)
        isaret = "" if gun else "  ← ÜRETİLMİYOR"
        print(f"| `{c}` | {toplam:,.0f} | {gun}{isaret} |")

    print("\n## Kanal kuralları (gölge modda — kuyruğa vaka göndermezler)\n")
    for rid in KANAL_KURALLARI:
        n = golge.get(rid, 0)
        print(f"  {rid}: {n} tetiklenme" + ("" if n else "  ← HİÇ SINANMADI"))

    print("\n## Kapsama (mevcut senaryolar — Faz B bunları BOZMAMALI)\n")
    yakalanan = sum(1 for c in pozitif if c["sonuc"].startswith("GEÇTİ"))
    print(f"  {yakalanan}/{len(pozitif)} pozitif senaryo")
    for c in pozitif:
        print(f"    {'✔' if c['sonuc'].startswith('GEÇTİ') else '✘'} {c['senaryo']:<42} {c['sonuc'][:52]}")
    for c in negatif:
        print(f"    {'✔' if c['sonuc'].startswith('GEÇTİ') else '✘'} {c['senaryo']:<42} {c['sonuc'][:52]}")

    sonuc = dict(
        yapilandirma=dict(users=a.users, eval_days=a.eval_days, tohum=a.tohum, butce=a.butce),
        kaynaklar=kaynaklar,
        app_sozlugu=sozluk,
        taninan_app=kesisim,
        kanal_sinyalleri=sinyal_ozet,
        golge_tetiklenme={r: golge.get(r, 0) for r in KANAL_KURALLARI},
        golge_tum=dict(golge),
        kapsama=dict(
            pozitif=len(pozitif),
            yakalanan=yakalanan,
            senaryolar={c["senaryo"]: c["sonuc"] for c in cov},
        ),
    )
    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nyazıldı: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
