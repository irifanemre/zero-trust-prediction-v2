"""Recall@K — SOC kapasitesi ölçütü (revizeler2.txt §5: "Önemli metrik: Recall@K").

precision@k taban oranıyla birlikte düşer; r6.2'de 0,014 çıktı ve bu model kötülüğü değil, insider yoğunluğunun
binde 0,36 olmasıydı. Recall@K aynı soruyu analistin tarafından sorar ve taban oranından bağımsızdır:
"günde K vaka bakabiliyorsam insider'ların kaçını görürüm?"
"""

import pandas as pd

from ztp.config import TenantConfig
from ztp.metrics import MetricsCollector

D = [pd.Timestamp("2026-02-10") + pd.Timedelta(days=i) for i in range(3)]
UZAK = [pd.Timestamp("2026-02-10") + pd.Timedelta(days=i) for i in (0, 30, 31)]


def _gt(sid, d0, d1):
    return dict(senaryo=f"S-{sid}", sid=sid, pencere=[str(d0.date()), str(d1.date())], olay_tarihi=str(d1.date()))


def _mc(queue_by_day, gt):
    mc = MetricsCollector(TenantConfig(), gt, [])
    mc.queue_by_day = dict(queue_by_day)
    for d, sirali in queue_by_day.items():
        for sid in sirali:
            mc.alerts_by_sid[sid].append((d, {"R1"}))
    return mc


def test_recall_at_k_taban_oranindan_bagimsiz():
    """Aynı insider, aynı sırada: kuyruğa 3 ya da 300 masum eklemek recall@K'yı DEĞİŞTİRMEZ; precision çöker."""
    gt = [_gt("INS", D[0], D[2])]
    az = _mc({d: ["INS"] + [f"b{i}" for i in range(3)] for d in D}, gt).labeled_precision()
    cok = _mc({d: ["INS"] + [f"b{i}" for i in range(300)] for d in D}, gt).labeled_precision()
    assert az["recall@1"] == cok["recall@1"] == 1.0
    assert az["recall@10"] == cok["recall@10"] == 1.0  # kalabalıktan etkilenmez
    assert cok["precision@10"] < az["precision@10"]  # oysa precision kalabalıkla düşer


def test_recall_at_k_kapasiteyle_artar():
    gt = [_gt("INS", D[0], D[2])]
    p = _mc({d: [f"b{i}" for i in range(6)] + ["INS"] for d in D}, gt).labeled_precision()  # insider 7. sırada
    assert p["recall@1"] == p["recall@3"] == p["recall@5"] == 0.0
    assert p["recall@10"] == 1.0  # ancak 10'luk analist kapasitesinde görülüyor
    assert p["recall@10_kullanici"] == 1.0


def test_recall_kullanici_bazli_bir_kez_gormek_yeterli():
    """Pencere boyunca BİR kez ilk K'ya girmek yakalanmış saymak için yeter — SOC gerçeği budur."""
    p = _mc({D[0]: ["b0", "INS"], D[1]: ["b0", "b1"], D[2]: ["b0", "b1"]}, [_gt("INS", D[0], D[2])]).labeled_precision()
    assert p["recall@3"] == round(1 / 3, 3)  # insider-gün tabanlı: 3 fırsattan 1'i
    assert p["recall@3_kullanici"] == 1.0  # kullanıcı bazlı: bir kez görüldü, yeter
    assert p["recall_paydasi"] == dict(insider_gun=3, insider_kullanici=1)


def test_pencere_disi_gun_firsat_sayilmaz():
    """Tespit penceresi (±7 gün tolerans) dışındaki günler paydaya girmez."""
    p = _mc({d: ["INS"] for d in UZAK}, [_gt("INS", UZAK[0], UZAK[0])]).labeled_precision()
    assert p["recall_paydasi"]["insider_gun"] == 1  # 30 ve 31. günler toleransın dışında
    assert p["recall@1"] == 1.0


def test_cevap_anahtari_yoksa_recall_uretilmez():
    assert MetricsCollector(TenantConfig(), [], []).labeled_precision() is None
