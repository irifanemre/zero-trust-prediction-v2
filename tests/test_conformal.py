"""Belirsizlik modellemesi (revizeler.txt §1.2): Venn-Abers olasılık aralığı ve etiket kümesi."""

import random

import pytest

from ztp.gnn.conformal_eval import MIN_KALIBRASYON, VA_MIN, VennAbersKalibrator, _gerekli_n, _kuantil, _pava


def _veri(n, seed=42, gurultu=0.0):
    """Skoru gerçek olasılığa yakın olan bir model taklidi; etiket Bernoulli(p)."""
    rng = random.Random(seed)
    skor, etiket = [], []
    for _ in range(n):
        p = rng.random()
        skor.append(min(1.0, max(0.0, p + rng.gauss(0, gurultu))))
        etiket.append(1 if rng.random() < p else 0)
    return skor, etiket


# ---------------------------------------------------------------- PAVA
def test_pava_izotonik_ciktiyor():
    assert _pava([1, 2, 3], [1, 1, 1]) == [1, 2, 3]  # zaten artan: dokunmaz
    assert _pava([3, 1], [1, 1]) == [2.0, 2.0]  # ihlal: havuzlanır
    out = _pava([0, 1, 0, 1], [1, 1, 1, 1])
    assert all(a <= b for a, b in zip(out, out[1:]))  # sonuç daima azalmayan


# ---------------------------------------------------------------- aralık
def test_az_veride_aralik_sahte_daraltilmaz():
    c = VennAbersKalibrator().fit(*_veri(VA_MIN - 1))
    assert not c.hazir
    ar = c.aralik(0.81)
    assert (ar.alt, ar.ust) == (0.0, 1.0)
    assert ar.yetersiz_veri and ar.guven == "yetersiz_veri"
    assert "gözlem süresi uzatılmalı" in ar.uyari
    assert "yetersiz veri" in ar.metin()


def test_yeterli_veride_dar_aralik_ve_nokta_icinde():
    c = VennAbersKalibrator().fit(*_veri(2000))
    ar = c.aralik(0.81)
    assert not ar.yetersiz_veri
    assert 0.0 <= ar.alt <= ar.nokta <= ar.ust <= 1.0  # nokta kestirimi daima aralıkta
    assert ar.genislik < 0.30  # bol veride daralır
    assert ar.metin().startswith("%")


def test_veri_arttikca_aralik_daralir():
    """Asıl iddia: genişlik, o bölgedeki kalibrasyon yoğunluğunun ölçüsüdür."""
    dar = VennAbersKalibrator().fit(*_veri(4000, seed=5)).aralik(0.5).genislik
    genis = VennAbersKalibrator().fit(*_veri(40, seed=5)).aralik(0.5).genislik
    assert genis > dar


def test_aralik_monoton_skorla_artar():
    c = VennAbersKalibrator().fit(*_veri(3000))
    noktalar = [c.aralik(s).nokta for s in (0.05, 0.25, 0.5, 0.75, 0.95)]
    assert all(a <= b + 1e-9 for a, b in zip(noktalar, noktalar[1:])), noktalar


def test_bozuk_model_kalibre_ediliyor():
    """Model aşırı güvenliyse (hep ~1 diyor ama yarısı yanlış) Venn-Abers bunu düzeltir."""
    n = 600
    skor = [0.97] * n
    etiket = [i % 2 for i in range(n)]  # gerçek oran %50
    ar = VennAbersKalibrator().fit(skor, etiket).aralik(0.97)
    assert 0.35 <= ar.nokta <= 0.65, ar.ozet()  # ham skor 0,97 iken kalibre nokta ~0,5
    assert ar.ham_skor == 0.97


def test_kapsama_olcumu_brier_dusuruyor():
    kal_s, kal_e = _veri(2000, seed=7)
    test_s, test_e = _veri(2000, seed=99)
    c = VennAbersKalibrator().fit(kal_s, kal_e)
    olcum = c.kapsama_olc(test_s, test_e)
    ham_brier = sum((p - y) ** 2 for p, y in zip(test_s, test_e)) / len(test_s)
    assert olcum["brier"] <= ham_brier + 0.02  # kalibrasyon Brier'i kötüleştirmemeli
    assert olcum["n"] == 2000


# ---------------------------------------------------------------- etiket kümesi
def test_tahmin_kumesi_az_veride_karasizdir_ve_bos_donmez():
    assert VennAbersKalibrator().fit(*_veri(5)).tahmin_kumesi(0.81) == (0, 1)
    c = VennAbersKalibrator(alpha=0.5).fit(*_veri(500))
    for p in (0.0, 0.3, 0.5, 0.7, 1.0):
        assert c.tahmin_kumesi(p), f"{p} için boş küme döndü"


def test_gerekli_n_ve_kuantil_sinirlari():
    assert _gerekli_n(0.05) == MIN_KALIBRASYON == 19
    assert _kuantil(sorted([0.1] * 18), 0.05) is None  # 18 nokta yetmez
    assert _kuantil(sorted([0.1] * 19), 0.05) == 0.1  # 19 yeter
    assert _kuantil([], 0.05) is None


def test_bozuk_girdi_reddedilir():
    with pytest.raises(ValueError):
        VennAbersKalibrator(alpha=0.0)
    with pytest.raises(ValueError):
        VennAbersKalibrator().fit([0.5], [0, 1])
    with pytest.raises(ValueError):
        VennAbersKalibrator().fit([1.5], [1])
    with pytest.raises(ValueError):
        VennAbersKalibrator().fit([0.5], [2])
    with pytest.raises(ValueError):
        VennAbersKalibrator().fit(*_veri(50)).aralik(1.2)
