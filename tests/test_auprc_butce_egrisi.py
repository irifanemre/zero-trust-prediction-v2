"""AUPRC ve bütçe–recall eğrisi — dengesiz veride tek sayının yanıltıcı olduğu yerler.

r6.2'de AUROC 0,775 çıkmıştı ama precision@1 0,003'tü. İkisi çelişmiyor: AUROC'un paydasında negatif sayısı
var ve 1:2800 dengesizlikte negatif sınıf her şeyi domine ediyor. AUPRC'nin tabanı pozitif oranıdır, yani şans
seviyesi baştan görünür. Bütçe eğrisi de aynı şeyi recall tarafında yapar: "recall@30 = 0,765" cümlesi bütçe
100'e çıkınca ne olduğunu söylemiyordu.
"""

import numpy as np
import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.metrics import MetricsCollector
from ztp.prediction_model import auprc_score, calibration_report

DAY0 = pd.Timestamp("2010-06-01")


# ------------------------------------------------------------------ AUPRC


def test_auprc_mukemmel_siralamada_1():
    y = np.array([1, 1, 0, 0, 0])
    p = np.array([0.9, 0.8, 0.3, 0.2, 0.1])
    assert auprc_score(p, y) == pytest.approx(1.0)


def test_auprc_en_kotu_siralamada_tabanin_altinda():
    """Pozitifler en sona sıralanırsa AUPRC taban oranının ALTINA düşer — AUROC'ta bu 0,0 olur, burada ~taban/2."""
    y = np.array([0, 0, 0, 0, 1, 1])
    p = np.array([0.9, 0.8, 0.7, 0.6, 0.2, 0.1])
    ap = auprc_score(p, y)
    assert ap is not None and ap < y.mean()


def test_auprc_rastgele_siralamada_taban_civarinda():
    rng = np.random.default_rng(11)
    y = (rng.random(20_000) < 0.01).astype(int)
    p = rng.random(20_000)  # etiketle ilgisiz
    ap = auprc_score(p, y)
    assert ap == pytest.approx(y.mean(), abs=0.005)


def test_auprc_bagli_skorlari_sismez():
    """Bütün skorlar eşitse sıralama yok: AP taban oranına eşit olmalı, rastgele koparsa yapay şişer."""
    y = np.array([1, 0, 0, 1, 0, 0, 0, 0, 0, 0])
    p = np.full(10, 0.5)
    assert auprc_score(p, y) == pytest.approx(y.mean())


def test_auprc_tek_sinifta_none():
    assert auprc_score(np.array([0.5, 0.6]), np.array([0, 0])) is None
    assert auprc_score(np.array([0.5, 0.6]), np.array([1, 1])) is None


def test_auprc_sklearn_ile_ayni():
    from sklearn.metrics import average_precision_score

    rng = np.random.default_rng(5)
    for _ in range(5):
        y = (rng.random(500) < 0.05).astype(int)
        p = np.clip(y * 0.3 + rng.random(500) * 0.7, 0, 1)
        if 0 < y.sum() < len(y):
            assert auprc_score(p, y) == pytest.approx(average_precision_score(y, p), abs=1e-9)


def test_kalibrasyon_raporu_auprc_ve_tabani_birlikte_verir():
    rng = np.random.default_rng(3)
    y = (rng.random(5000) < 0.02).astype(int)
    p = np.clip(y * 0.4 + rng.random(5000) * 0.3, 0, 1)
    rep = calibration_report(p, y)
    assert rep["auprc"] is not None and rep["auprc_taban"] == pytest.approx(y.mean(), abs=1e-4)
    # ×taban: şans seviyesinin kaç katı — tek başına AUPRC yorumlanamaz
    assert rep["auprc_kat"] == pytest.approx(rep["auprc"] / rep["auprc_taban"], rel=0.02)
    assert rep["auprc_kat"] > 1.0


# ------------------------------------------------------------------ bütçe–recall eğrisi


def _collector(kuyruklar: dict, insiderlar: dict, aktif: int = 100) -> MetricsCollector:
    """`kuyruklar`: {gün: sıralı sid listesi}; `insiderlar`: {sid: (başlangıç, olay)}."""
    gt = [
        dict(
            senaryo=f"S-{sid}",
            aktor=sid,
            sid=sid,
            teknikler=["T1078"],
            veri_kaynagi="ad",
            beklenen=["UEBA-0001"],
            baslangic_tarihi=str(bas.date()),
            olay_tarihi=str(olay.date()),
            pencere=[str(bas.date()), str(olay.date())],
        )
        for sid, (bas, olay) in insiderlar.items()
    ]
    m = MetricsCollector(TenantConfig(), gt, [])
    for gun, sidler in kuyruklar.items():
        m.queue_by_day[gun] = list(sidler)
        m.daily.append(dict(gun=str(gun.date()), aktif_kullanici=aktif, kuyruk=len(sidler)))
        for sid in sidler:
            m.alerts_by_sid[sid].append((gun, {"UEBA-0001"}))
    return m


def test_egri_butce_buyudukce_recall_azalmaz():
    gunler = [DAY0 + i * pd.Timedelta(days=1) for i in range(10)]
    # insider her gün 7. sırada: bütçe 5'te görünmez, 10'da görünür
    kuyruklar = {g: [f"N{i:02d}" for i in range(6)] + ["INS1"] + [f"M{i:02d}" for i in range(20)] for g in gunler}
    m = _collector(kuyruklar, {"INS1": (gunler[0], gunler[-1])})
    egri = m.butce_recall_egrisi(butceler=(1, 3, 5, 10, 30))
    satir = {r["butce"]: r for r in egri["egri"]}
    assert satir[5]["recall_kullanici"] == 0.0
    assert satir[10]["recall_kullanici"] == 1.0
    oranlar = [r["recall_gun"] for r in egri["egri"]]
    assert oranlar == sorted(oranlar)  # monoton artan


def test_egri_butce_oranini_ve_marjinal_maliyeti_verir():
    gunler = [DAY0 + i * pd.Timedelta(days=1) for i in range(4)]
    kuyruklar = {g: [f"N{i:02d}" for i in range(9)] + ["INS1"] for g in gunler}
    m = _collector(kuyruklar, {"INS1": (gunler[0], gunler[-1])}, aktif=1000)
    egri = m.butce_recall_egrisi(butceler=(1, 10))
    satir = {r["butce"]: r for r in egri["egri"]}
    assert satir[1]["butce_orani"] == pytest.approx(0.001)  # 1 / 1000 aktif kullanıcı
    assert satir[1]["incelenen_vaka"] == 4 and satir[10]["incelenen_vaka"] == 40
    # 1 insider daha görmek için 36 ek vaka incelendi
    assert satir[10]["vaka_basina_insider"] == pytest.approx(36.0)
    assert egri["payda"]["insider_kullanici"] == 1
    assert egri["payda"]["ort_aktif_kullanici"] == 1000.0


def test_egri_butce_kuyruk_uzunlugunu_asinca_sismez():
    """Bütçe 100 ama kuyruk 3 uzunluğunda: incelenen vaka 3×gün olmalı, 100×gün değil."""
    gunler = [DAY0 + i * pd.Timedelta(days=1) for i in range(5)]
    m = _collector({g: ["A", "B", "INS1"] for g in gunler}, {"INS1": (gunler[0], gunler[-1])})
    egri = m.butce_recall_egrisi(butceler=(3, 100))
    satir = {r["butce"]: r for r in egri["egri"]}
    assert satir[100]["incelenen_vaka"] == 15  # 3 × 5 gün
    assert satir[100]["recall_kullanici"] == satir[3]["recall_kullanici"] == 1.0
    assert satir[100]["vaka_basina_insider"] is None  # ek insider yok → marjinal maliyet tanımsız


def test_egri_pencere_disi_gunu_firsat_saymaz():
    """İnsider'ın tespit penceresi dışındaki günler paydaya girmez (yoksa recall yapay düşer)."""
    gunler = [DAY0 + i * pd.Timedelta(days=1) for i in range(20)]
    m = _collector({g: ["INS1"] for g in gunler}, {"INS1": (gunler[0], gunler[1])})
    egri = m.butce_recall_egrisi(butceler=(1,))
    # pencere [bas-7g, olay+7g] → 20 günün yalnız bir kısmı fırsat
    assert egri["payda"]["insider_gun"] < len(gunler)
    assert egri["egri"][0]["recall_gun"] == 1.0  # fırsat günlerinin tamamında ilk sırada


def test_egri_etiket_yoksa_none():
    m = MetricsCollector(TenantConfig(), [], [])
    assert m.butce_recall_egrisi() is None
