"""Faz E — ADWIN insider'ın kendi tırmanışını "sürüklenme" sanıp tabanı sıfırlıyor mu?

ADWIN r4.2'de ölçülmüş ve ZARAR verdiği bulunmuştu (recall@10 0,618 → 0,588). Sebebi hiç
araştırılmadı. Brief iki yeni dedektör (Page-Hinkley, BOCPD) istiyor; sebebi bilinmeyen bir
başarısızlığı iki kez daha denemek yerine önce sebep aranıyor.

Hipotez (`docs/faz-e-on-kayit.md`, koddan okunarak kuruldu):

    pipeline.py:538 → a.ekle(results[sid].raw)      # RİSK SKORU besleniyor
                   → self.profile.adwin_cut[sid]    # taban o güne sıfırlanıyor

Yani sürüklenme dedektörü tespit ÇIKTISIYLA besleniyor ve tepkisi onu normalleştirmek. Doğruysa
insider'ın tırmanışı "yeni normal" ilan edilir ve tespit kendi eliyle silinir — ve Page-Hinkley /
BOCPD aynı sinyali izleyecekleri için aynı hatayı yapar.

Kullanım:
    python scripts/suruklenme_tanisi.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ztp.config import TenantConfig  # noqa: E402
from ztp.data.synthetic import SyntheticOrg  # noqa: E402
from ztp.detection.catalog import load_catalog  # noqa: E402
from ztp.metrics import MetricsCollector  # noqa: E402
from ztp.pipeline import ZeroTrustPredictionPipeline  # noqa: E402

MIN_KESME = 10  # ön kayıt: bundan az kesmede oran gürültülü, "ölçülemedi" denir


def _kos(cfg: TenantConfig, data, bas, end) -> ZeroTrustPredictionPipeline:
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), Path(tempfile.mkdtemp()))
    pipe.run(bas, end, warmup_days=10)
    return pipe


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=120)
    ap.add_argument("--eval-days", type=int, default=24)
    ap.add_argument("--tohum", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    end = pd.Timestamp("2026-09-16")
    bas = end - pd.Timedelta(days=a.eval_days - 1)
    temel = TenantConfig(tenant_id="dr", pseudonym_secret="s", alarm_budget_per_day=6, threshold_jitter=0.0)
    data = SyntheticOrg(
        n_users=a.users, n_days=temel.long_window_days + a.eval_days + 10, eval_days=a.eval_days, end_day=end, seed=a.tohum
    ).build()
    kaynaklar = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))

    print(f"\n# Sürüklenme teşhisi — {a.users} kullanıcı, {a.eval_days} gün, tohum {a.tohum}\n")

    kosular = {}
    for ad, acik in (("ADWIN kapalı", False), ("ADWIN açık", True)):
        cfg = TenantConfig(
            tenant_id=f"dr-{int(acik)}",
            pseudonym_secret="s",
            alarm_budget_per_day=6,
            threshold_jitter=0.0,
            adwin_enabled=acik,
        )
        cfg.available_sources = kaynaklar
        kosular[ad] = _kos(cfg, data, bas, end)

    # ---- ölçüt 3: zarar yeniden üretilebiliyor mu (önce bu okunmalı)
    print("## Doğruluk kontrolü — ADWIN'in zararı bu veride görünüyor mu\n")
    print("| Koşu | yakalanan | kuyruk paydası | toplam vaka |")
    print("|---|---|---|---|")
    ozet = {}
    for ad, pipe in kosular.items():
        cov = pipe.metrics.coverage()
        poz = [c for c in cov if "negatif" not in c["senaryo"].lower()]
        golge = [c for c in poz if c["sonuc"].startswith("GÖLGEDE")]
        yak = sum(1 for c in poz if c["sonuc"].startswith("GEÇTİ"))
        vaka = sum(len(q) for q in pipe.metrics.queue_by_day.values())
        ozet[ad] = dict(yakalanan=yak, payda=len(poz) - len(golge), vaka=vaka)
        print(f"| {ad} | **{yak}** | {len(poz) - len(golge)} | {vaka} |")
    zarar = ozet["ADWIN açık"]["yakalanan"] - ozet["ADWIN kapalı"]["yakalanan"]
    print(f"\n  ADWIN'in yakalamaya etkisi: **{zarar:+d} senaryo**")
    olcut3 = zarar <= 0
    print(f"  ölçüt 3 ({'zarar ya da etkisizlik görünüyor' if olcut3 else 'ADWIN FAYDA sağladı — 1-2 yorumlanmaz'}): "
          f"{'GEÇTİ' if olcut3 else 'KALDI'}")

    # ---- ölçüt 1/2: kesmeler insider pencerelerine mi düşüyor
    pipe = kosular["ADWIN açık"]
    kesmeler = dict(pipe.profile.adwin_cut)
    gunler = sorted(pipe.metrics.queue_by_day)
    insider_pencere = {}
    for g in pipe.metrics.gt:
        if g.get("negatif"):
            continue
        w0, w1 = MetricsCollector._window(g)
        insider_pencere[g["sid"]] = (w0, w1)

    tum_sid = set(pipe.final_risk)
    insider_sid = set(insider_pencere) & tum_sid
    temiz_sid = tum_sid - set(insider_pencere)

    ins_kesme = {s: d for s, d in kesmeler.items() if s in insider_sid}
    # insider'da kesme PENCERE İÇİNDE mi — hipotezin asıl testi
    pencere_ici = {s: d for s, d in ins_kesme.items() if insider_pencere[s][0] <= d <= insider_pencere[s][1]}
    temiz_kesme = {s: d for s, d in kesmeler.items() if s in temiz_sid}

    print("\n## Hipotez testi — kesmeler insider pencerelerine mi düşüyor\n")
    print(f"| | kullanıcı | kesme alan | oran |")
    print(f"|---|---|---|---|")
    ins_oran = len(ins_kesme) / len(insider_sid) if insider_sid else 0.0
    tem_oran = len(temiz_kesme) / len(temiz_sid) if temiz_sid else 0.0
    print(f"| insider | {len(insider_sid)} | {len(ins_kesme)} | **{ins_oran:.3f}** |")
    print(f"| temiz | {len(temiz_sid)} | {len(temiz_kesme)} | **{tem_oran:.3f}** |")
    print(f"\n  insider'larda kesme, pencere İÇİNDE olan: {len(pencere_ici)} / {len(ins_kesme)}")
    print(f"  toplam kesme: {len(kesmeler)}")

    yeterli = len(kesmeler) >= MIN_KESME
    kat = (ins_oran / tem_oran) if tem_oran > 0 else (float("inf") if ins_oran > 0 else 0.0)
    print("\n## Ön kayıtlı ölçütler\n")
    if not yeterli:
        print(f"  ÖLÇÜLEMEDİ — toplam kesme {len(kesmeler)} < {MIN_KESME}; oran gürültülü, sayı uydurulmaz.")
        dogrulandi = None
    else:
        dogrulandi = kat >= 2.0
        print(f"  oran katı: **{kat:.2f}×** (eşik 2,0)")
        print(f"  → hipotez {'DOĞRULANDI' if dogrulandi else 'ÇÜRÜDÜ'}")
        print(f"  → Page-Hinkley / BOCPD {'YAZILMAZ' if dogrulandi else 'yazılması GEREKÇELİ'}")

    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(dict(
            yapilandirma=dict(users=a.users, eval_days=a.eval_days, tohum=a.tohum),
            kapsama=ozet, adwin_zarari=zarar, olcut3=olcut3,
            kesme=dict(toplam=len(kesmeler), insider=len(ins_kesme), pencere_ici=len(pencere_ici),
                       temiz=len(temiz_kesme), insider_n=len(insider_sid), temiz_n=len(temiz_sid)),
            insider_oran=ins_oran, temiz_oran=tem_oran, kat=(None if kat == float("inf") else kat),
            yeterli_kesme=yeterli, hipotez_dogrulandi=dogrulandi,
        ), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nyazıldı: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
