"""Faz D — aynı toplam analist kapasitesi, farklı günlük dağıtım: kazandırıyor mu?

Dinamik kapasite, kapasite YARATMAZ; var olanı yeniden dağıtır. Dolayısıyla doğru soru "bütçeyi
artırsak ne olur" değil (onu `butce_recall_egrisi()` zaten ölçüyor), şu:

> Toplam kapasite SABİTken, düzgün dağıtım yerine duruma göre dağıtmak yakalamayı artırır mı?

Yöntem: yüksek bütçeyle (tavan) TEK koşu yapılır, kayıtlı risk sıralı kuyruklar üzerinde farklı
dağıtım planları çevrimdışı oynatılır. Her planın toplam kapasitesi aynı (±%2, doğruluk kontrolü).

Planlar arasında bilerek **hileli** bir tane var: o gün gerçekten insider varsa tavana çıkıyor.
Uygulanabilir değil; varlık sebebi dağıtımın teorik üst sınırını vermek. Hileli plan kazanamıyorsa
dağıtımda kazanç yoktur ve bu, planların yetersizliğini değil sorunun yapısını gösterir.

Kullanım:
    python scripts/kapasite_dagitimi.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ztp.config import TenantConfig  # noqa: E402
from ztp.data.synthetic import SyntheticOrg  # noqa: E402
from ztp.detection.catalog import load_catalog  # noqa: E402
from ztp.metrics import MetricsCollector  # noqa: E402
from ztp.pipeline import ZeroTrustPredictionPipeline  # noqa: E402

TAVAN = 30  # koşu bütçesi: kayıtlı kuyruk bundan uzun olamaz, dolayısıyla planların günlük tavanı


def _olcek(agirlik: Dict[pd.Timestamp, float], hedef_toplam: int, tavan: int) -> Dict[pd.Timestamp, int]:
    """Ağırlıkları, toplamı `hedef_toplam` olan ve hiçbiri `tavan`ı aşmayan tam sayı bütçelere çevirir.

    Tavana dayanan günlerin artığı diğer günlere yeniden dağıtılır; aksi hâlde toplam kapasite
    plandan plana değişir ve karşılaştırma geçersiz olur (ön kayıt ölçütü 3).
    """
    gunler = sorted(agirlik)
    kalan, w = float(hedef_toplam), {g: max(agirlik[g], 0.0) for g in gunler}
    sonuc = {g: 0 for g in gunler}
    for _ in range(50):
        acik = [g for g in gunler if sonuc[g] < tavan and w[g] > 0]
        toplam_w = sum(w[g] for g in acik)
        if not acik or toplam_w <= 0 or kalan < 1:
            break
        for g in acik:
            pay = int(round(kalan * w[g] / toplam_w))
            sonuc[g] = min(tavan, sonuc[g] + pay)
        kalan = hedef_toplam - sum(sonuc.values())
        if abs(kalan) < 1:
            break
    # kalan artık/eksik tek tek dağıtılır (yuvarlama hatası)
    while sum(sonuc.values()) < hedef_toplam:
        uygun = [g for g in gunler if sonuc[g] < tavan]
        if not uygun:
            break
        sonuc[max(uygun, key=lambda g: w[g])] += 1
    while sum(sonuc.values()) > hedef_toplam:
        uygun = [g for g in gunler if sonuc[g] > 0]
        if not uygun:
            break
        sonuc[min(uygun, key=lambda g: w[g])] -= 1
    return sonuc


def _yakalama(kuyruklar: Dict[pd.Timestamp, List[str]], plan: Dict[pd.Timestamp, int], firsat: dict) -> dict:
    """Plan uygulandığında kaç insider-günü ve kaç FARKLI insider görülür."""
    gorulen_gun, gorulen_sid = 0, set()
    for gun, kuyruk in kuyruklar.items():
        k = plan.get(gun, 0)
        for sid in kuyruk[:k]:
            if gun in firsat.get(sid, ()):
                gorulen_gun += 1
                gorulen_sid.add(sid)
    return dict(insider_gun=gorulen_gun, insider=len(gorulen_sid), vaka=sum(plan.values()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=120)
    ap.add_argument("--eval-days", type=int, default=24)
    ap.add_argument("--tohum", type=int, default=7)
    ap.add_argument("--hedef-butce", type=int, default=6, help="günlük ORTALAMA kapasite")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cfg = TenantConfig(tenant_id="kap", pseudonym_secret="s", alarm_budget_per_day=TAVAN, threshold_jitter=0.0)
    end = pd.Timestamp("2026-09-16")
    data = SyntheticOrg(
        n_users=a.users, n_days=cfg.long_window_days + a.eval_days + 10, eval_days=a.eval_days, end_day=end, seed=a.tohum
    ).build()
    cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), Path(tempfile.mkdtemp()))
    pipe.run(end - pd.Timedelta(days=a.eval_days - 1), end, warmup_days=10)

    m = pipe.metrics
    kuyruklar = {g: list(q) for g, q in sorted(m.queue_by_day.items())}
    gunler = sorted(kuyruklar)
    # insider fırsat günleri (senaryo pencereleri)
    firsat: Dict[str, set] = {}
    for g in m.gt:
        if g.get("negatif"):
            continue
        w0, w1 = MetricsCollector._window(g)
        firsat.setdefault(g["sid"], set()).update(d for d in gunler if w0 <= d <= w1)
    firsat = {k: v for k, v in firsat.items() if v}
    hedef = a.hedef_butce * len(gunler)

    print(f"\n# Kapasite dağıtımı — {a.users} kullanıcı, {len(gunler)} gün, tohum {a.tohum}\n")
    print(f"Toplam kapasite: {hedef} vaka ({a.hedef_butce}/gün ortalama), günlük tavan {TAVAN}")
    print(f"Ölçülebilir insider: {len(firsat)}, toplam fırsat günü: {sum(len(v) for v in firsat.values())}")
    print(f"Kayıtlı kuyruk uzunluğu: medyan {int(np.median([len(q) for q in kuyruklar.values()]))}, "
          f"maks {max(len(q) for q in kuyruklar.values())}\n")

    insider_gunu = {g: sum(1 for s, d in firsat.items() if g in d) for g in gunler}
    tepe = {g: (max((pipe.final_risk.get(s, {}).get(g, 0.0) for s in kuyruklar[g]), default=0.0) if kuyruklar[g] else 0.0)
            for g in gunler}
    planlar = {
        "düzgün (taban)": {g: 1.0 for g in gunler},
        "hafta içi ağırlıklı": {g: (1.4 if g.dayofweek < 5 else 0.3) for g in gunler},
        "kuyruk oranlı": {g: float(len(kuyruklar[g])) for g in gunler},
        "tepe skor oranlı": {g: float(tepe[g]) for g in gunler},
        "HİLELİ (yarını bilen)": {g: (10.0 if insider_gunu[g] else 1.0) for g in gunler},
    }

    print("| Plan | insider-günü | farklı insider | toplam vaka | taban farkı |")
    print("|---|---|---|---|---|")
    sonuc, taban = {}, None
    for ad, w in planlar.items():
        plan = _olcek(w, hedef, TAVAN)
        r = _yakalama(kuyruklar, plan, firsat)
        if taban is None:
            taban = r["insider_gun"]
        fark = r["insider_gun"] - taban
        sonuc[ad] = dict(**r, fark=fark, gunluk=sorted(set(plan.values())))
        isaret = "" if ad.startswith("düzgün") else f"{fark:+d}"
        print(f"| {ad} | **{r['insider_gun']}** | {r['insider']} | {r['vaka']} | {isaret} |")

    print("\n## Ön kayıtlı ölçütler\n")
    uygulanabilir = {k: v for k, v in sonuc.items() if not k.startswith(("düzgün", "HİLELİ"))}
    en_iyi = max(uygulanabilir.values(), key=lambda v: v["fark"]) if uygulanabilir else None
    hileli = sonuc["HİLELİ (yarını bilen)"]
    vakalar = [v["vaka"] for v in sonuc.values()]
    kapasite_esit = (max(vakalar) - min(vakalar)) <= 0.02 * hedef
    o1 = bool(en_iyi and en_iyi["fark"] >= 1)
    o2 = hileli["fark"] >= 2
    for ad, ok, acik in (
        ("1. uygulanabilir plan tabanı ≥1 insider-günü geçer", o1, f"en iyi {en_iyi['fark']:+d}" if en_iyi else "—"),
        ("2. hileli plan tabanı ≥2 geçer (üst sınır)", o2, f"{hileli['fark']:+d}"),
        ("3. toplam kapasite eşit (±%2)", kapasite_esit, f"{min(vakalar)}–{max(vakalar)} vaka"),
    ):
        print(f"  {'GEÇTİ' if ok else 'KALDI'}  {ad}  ({acik})")
    print(f"\n  → dinamik kapasite {'UYGULANIR' if o1 else 'UYGULANMAZ'}")
    if not o2:
        print("    Hileli plan da kazanamadı: dağıtımda kazanç YOK. Ölçüt 1'in kalması")
        print("    planların yetersizliğini değil SORUNUN YAPISINI gösteriyor (ön kayıt ölçüt 2).")

    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(dict(
            yapilandirma=dict(users=a.users, gun=len(gunler), tohum=a.tohum, hedef_butce=a.hedef_butce, tavan=TAVAN),
            toplam_kapasite=hedef, olculebilir_insider=len(firsat), planlar=sonuc,
            olcutler=dict(o1=o1, o2=o2, kapasite_esit=kapasite_esit),
        ), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nyazıldı: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
