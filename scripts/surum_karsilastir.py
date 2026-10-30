#!/usr/bin/env python3
"""Sürüm regresyonu: yeni yetenekler eklendikten sonra r4.2 çıktısı DEĞİŞTİ Mİ?

revizeler.txt / revizeler2.txt maddeleri eklenirken hepsi **varsayılanda kapalı** tutuldu (gölge mod, 14.5).
Sözleşme bu: kapalı bileşen mevcut davranışı değiştiremez. Bu betik sözleşmeyi ölçer.

Referans, `bellek_esdegerlik.py`'nin ürettiği `esdegerlik.json` dosyasındaki koşudur (aynı veri, aynı pencere,
aynı bütçe). Karşılaştırılan alanlar:

    olay              yüklenen olay sayısı
    kuyruk            gün gün, sıralı kullanıcı listesi
    kural_tetiklenme  kural başına tetiklenme sayısı
    vaka              toplam vaka
    kapsama           senaryo başına sonuç

Bunlardan biri bile değişmişse çıkış kodu 1'dir ve fark ayrıntılı basılır: kapalı olması gereken bir bileşen
sızmış demektir. Ek olarak, ESKİ koşuda bulunmayan yeni ölçütler (Recall@K) ayrıca raporlanır — bunlar
davranış değişikliği değil, aynı koşunun daha fazla ölçülmesidir.

Kullanım:
    python scripts/surum_karsilastir.py --cert-dir .../cert_data/r4.2 \
        --referans .../ztp_out_esdegerlik/esdegerlik.json --out .../ztp_out_surum
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from ztp.config import TenantConfig
from ztp.data.cert import load_cert_dataset
from ztp.detection.catalog import load_catalog
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.schema import DAY

LOG = logging.getLogger("surum")
KARSILASTIRILAN = ("olay", "kuyruk", "kural_tetiklenme", "vaka", "kapsama")


# "Hepsi açık" yapılandırması. Bunlar ÖLÇÜM için açılır; hangisinin faydalı olduğu ablasyonla belirlenir.
HEPSI_ACIK = dict(
    graf_enabled=True,
    graf_agirligi=0.5,
    adwin_enabled=True,
    bayes_kapi_esigi=0.3,
    belirsizlik_enabled=True,
    kanit_dogrulama="dengeli",
    cok_ajanli_rapor=True,
    # v5: r6.2 ölçümünün yapısal bulgusuna cevap — çarpan yerine toplamsal terim + kurala bağlı olmayan kanal
    graf_toplamsal_agirlik=0.5,
    anomali_enabled=True,
    anomali_agirligi=0.5,
    anomali_dogrulama_esigi=0.995,
    pred_sinif_agirligi=True,
)


def kosu(cert_dir: str, answers: str, out: Path, days: int, warmup: int, budget: int, tenant: str, ac: bool = False) -> dict:
    end = pd.Timestamp("2010-11-30")
    start = end - (days - 1) * DAY
    start_hist = end - (90 + warmup + days) * DAY
    t0 = time.perf_counter()
    data = load_cert_dataset(cert_dir, start_hist, end, answers_dir=answers)
    ek = HEPSI_ACIK if ac else {}
    cfg = TenantConfig(tenant_id=tenant, alarm_budget_per_day=budget, llm_backend="none", sinks=[], **ek)
    cfg.available_sources = tuple(sorted(set(data.events["source"].astype(str).unique()) | {"hr"}))
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), out)
    pipe.run(start, end, warmup)
    m = pipe.metrics
    hassasiyet = m.labeled_precision() or {}
    # Hangi bileşen GERÇEKTEN çalıştı: açmak ile etki etmek ayrı şeylerdir, ikisi ayrı raporlanır.
    graf_sinyalli = sum(1 for g in (pipe.tgraph.kullanicilar if pipe.tgraph else []) if g)
    etkinlik = dict(
        graf_kuruldu=pipe.tgraph is not None,
        graf_kullanici=graf_sinyalli,
        graf_kenar=pipe.tgraph.kenar_sayisi if pipe.tgraph else 0,
        adwin_kesim=len(pipe.profile.adwin_cut),
        adwin_izlenen=len(pipe.adwin),
        bayes_elenen_gun=len(pipe.bayes_elenen),
        bayes_elenen_vaka=sum(len(v) for v in pipe.bayes_elenen.values()),
        **(pipe.anomali.etkinlik() if pipe.anomali is not None else {}),
    )
    return dict(
        etkinlik=etkinlik,
        olay=len(data.events),
        kuyruk={str(d.date()): list(v) for d, v in m.queue_by_day.items()},
        kural_tetiklenme=dict(m.rule_hits),
        vaka=sum(len(v) for v in m.queue_by_day.values()),
        kapsama=[(c["senaryo"], c["sonuc"]) for c in m.coverage()],
        hassasiyet=hassasiyet,
        sure_sn=round(time.perf_counter() - t0),
    )


def _kuyruk_farki(eski: Dict[str, List[str]], yeni: Dict[str, List[str]]) -> List[dict]:
    farklar = []
    for gun in sorted(set(eski) | set(yeni)):
        a, b = eski.get(gun, []), yeni.get(gun, [])
        if a != b:
            farklar.append(dict(gun=gun, eski=a, yeni=b, eksilen=sorted(set(a) - set(b)), eklenen=sorted(set(b) - set(a))))
    return farklar


def karsilastir(eski: dict, yeni: dict) -> dict:
    farkli: Dict[str, Any] = {}
    for alan in KARSILASTIRILAN:
        if alan not in eski:
            continue
        a, b = eski[alan], yeni[alan]
        if alan == "kapsama":  # referans listeyi liste-of-liste, biz tuple üretiyoruz
            a, b = [tuple(x) for x in a], [tuple(x) for x in b]
        if a != b:
            farkli[alan] = _kuyruk_farki(a, b) if alan == "kuyruk" else dict(eski=a, yeni=b)
    return farkli


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cert-dir", required=True)
    ap.add_argument("--answers-dir")
    ap.add_argument("--referans", required=True, help="bellek_esdegerlik.py çıktısı (esdegerlik.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--warmup", type=int, default=21)
    ap.add_argument("--budget", type=int, default=10)
    ap.add_argument("--tenant", default="esd-optimize", help="referans koşuyla AYNI olmalı")
    ap.add_argument("--ac", action="store_true", help="tüm v4 bileşenlerini aç (ölçüm koşusu; fark BEKLENİR)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ref_dosya = json.loads(Path(args.referans).read_text(encoding="utf-8"))
    eski = ref_dosya["yeni"] if "yeni" in ref_dosya else ref_dosya  # esdegerlik.json ya da doğrudan koşu kaydı
    answers = args.answers_dir or str(Path(args.cert_dir).parent / "answers")

    yeni = kosu(args.cert_dir, answers, out, args.days, args.warmup, args.budget, args.tenant, args.ac)
    farkli = karsilastir(eski, yeni)

    yeni_olcutler = {k: v for k, v in (yeni.get("hassasiyet") or {}).items() if k.startswith("recall@") or k == "recall_paydasi"}
    sonuc = dict(
        mod="hepsi_acik" if args.ac else "varsayilan_kapali",
        beklenen="fark olabilir" if args.ac else "fark OLMAMALI",
        ayni=not farkli,
        etkinlik=yeni.get("etkinlik", {}),
        karsilastirilan=list(KARSILASTIRILAN),
        farkli_alanlar=sorted(farkli),
        fark_ayrintisi=farkli,
        ozet=dict(
            olay=dict(eski=eski.get("olay"), yeni=yeni["olay"]),
            vaka=dict(eski=eski.get("vaka"), yeni=yeni["vaka"]),
            kural_sayisi=dict(eski=len(eski.get("kural_tetiklenme", {})), yeni=len(yeni["kural_tetiklenme"])),
            sure_sn=dict(eski=eski.get("sure_sn"), yeni=yeni["sure_sn"]),
        ),
        yeni_olcutler=yeni_olcutler,
        precision_at_k={k: v for k, v in (yeni.get("hassasiyet") or {}).items() if k.startswith("precision@")},
    )
    (out / ("surum_karsilastirma_acik.json" if args.ac else "surum_karsilastirma.json")).write_text(
        json.dumps(dict(ozet=sonuc, yeni_kosu=yeni), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    LOG.info("SONUÇ: %s", json.dumps({k: v for k, v in sonuc.items() if k != "fark_ayrintisi"}, ensure_ascii=False))
    if farkli and not args.ac:
        LOG.error("DEĞİŞİKLİK VAR — kapalı olması gereken bir bileşen sızmış olabilir: %s", sorted(farkli))
    return 0 if (sonuc["ayni"] or args.ac) else 1


if __name__ == "__main__":
    sys.exit(main())
