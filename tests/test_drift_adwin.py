"""ADWIN kavram kayması (revizeler.txt §1.4): pencere veriye göre kısalır, sabit 90 gün yapay anomali üretmesin."""

import random

import pytest

from ztp.drift import Adwin, gecerli_gecmis


def _besle(a, degerler):
    return [a.ekle(v) for v in degerler]


def test_duragan_veride_kayma_yok():
    """Asıl yanlış alarm sınaması: davranış değişmediyse pencere KISALMAZ."""
    rng = random.Random(42)
    a = Adwin(delta=0.002)
    _besle(a, [rng.gauss(5.0, 1.0) for _ in range(800)])
    assert a.kayma_sayisi == 0
    assert a.adet == 800  # tüm geçmiş korunuyor
    assert 4.8 < a.ortalama < 5.2


def test_ani_kayma_saptanir_ve_pencere_kisalir():
    """Departman geçişi taklidi: ortalama 5'ten 25'e sıçrıyor."""
    rng = random.Random(7)
    a = Adwin(delta=0.002)
    _besle(a, [rng.gauss(5.0, 1.0) for _ in range(400)])
    _besle(a, [rng.gauss(25.0, 1.0) for _ in range(400)])
    assert a.kayma_sayisi > 0
    assert a.adet <= 400, a.adet  # 800 gözlem beslendi, pencerede yalnız yeni rejim kaldı
    assert a.ortalama > 20  # baz çizgisi yeni rejime taşındı
    assert a.son_kayma.eski_ortalama < a.son_kayma.yeni_ortalama  # kayma YÖNÜ doğru okunuyor
    assert a.son_kayma.fark > 10


def test_kayma_olayi_denetlenebilir():
    rng = random.Random(3)
    a = Adwin()
    _besle(a, [rng.gauss(0.0, 0.5) for _ in range(300)])
    _besle(a, [rng.gauss(10.0, 0.5) for _ in range(300)])
    o = a.son_kayma.ozet()
    assert o["atilan_gozlem"] > 0 and o["kalan_gozlem"] > 0
    assert o["fark"] > o["esik"]  # kesme kuralının kendisi: fark eşiği aşmalı


def test_izin_donusu_sonrasi_baz_cizgisi_yeni_rejimi_anlatir():
    """Yıllık izin: 60 gün sıfır etkinlik, sonra normale dönüş. Baz çizgisi sıfırlarda takılı kalmamalı."""
    a = Adwin(delta=0.002)
    _besle(a, [8.0 + (i % 3) * 0.1 for i in range(200)])  # normal çalışma
    _besle(a, [0.0] * 60)  # izin
    _besle(a, [8.0 + (i % 3) * 0.1 for i in range(200)])  # dönüş
    assert a.ortalama > 6.0, a.ortalama  # izin dönemi baz çizgisini aşağı çekip kalmadı
    assert a.kayma_sayisi >= 2  # hem izne giriş hem dönüş saptandı


def test_delta_kucukse_daha_az_alarm():
    rng = random.Random(11)
    veri = [rng.gauss(5.0, 3.0) for _ in range(400)] + [rng.gauss(7.0, 3.0) for _ in range(400)]
    gevsek = Adwin(delta=0.3)
    siki = Adwin(delta=1e-6)
    _besle(gevsek, veri)
    _besle(siki, veri)
    assert siki.kayma_sayisi <= gevsek.kayma_sayisi


def test_bellek_logaritmik_kaliyor():
    """Üstel histogram: 10.000 gözlem ham tutulmaz."""
    a = Adwin()
    _besle(a, [1.0] * 10_000)
    kova = sum(len(s) for s in a._kovalar)
    assert kova < 100, kova
    assert a.adet == 10_000


def test_kisa_pencerede_bolme_denenmez():
    a = Adwin(min_pencere=50)
    _besle(a, [0.0] * 20 + [100.0] * 20)  # 40 gözlem: eşiğin altında
    assert a.kayma_sayisi == 0


def test_gecerli_gecmis_kayma_yokken_eski_davranis():
    """Sözleşme: kayma görülmediyse davranış BİREBİR eskisi gibi — son `varsayilan` kayıt."""
    a = Adwin()
    gecmis = [(i, i * 1.0) for i in range(200)]
    _besle(a, [5.0] * 200)
    assert gecerli_gecmis(a, gecmis, 90) == gecmis[-90:]


def test_gecerli_gecmis_kaymadan_sonra_kisaliyor():
    a = Adwin()
    _besle(a, [0.0] * 300)
    _besle(a, [50.0] * 300)
    gecmis = [(i, i * 1.0) for i in range(600)]
    kisa = gecerli_gecmis(a, gecmis, 90)
    assert len(kisa) == min(600, a.adet)
    assert a.kayma_sayisi > 0


def test_bos_gecmis_ve_sifirla():
    a = Adwin()
    assert gecerli_gecmis(a, [], 90) == []
    _besle(a, [1.0] * 100)
    a.sifirla()
    assert a.adet == 0 and a.ortalama == 0.0 and a.varyans == 0.0


def test_bozuk_parametre_reddedilir():
    with pytest.raises(ValueError):
        Adwin(delta=0.0)
    with pytest.raises(ValueError):
        Adwin(delta=1.0)
    with pytest.raises(ValueError):
        Adwin(min_pencere=1)
