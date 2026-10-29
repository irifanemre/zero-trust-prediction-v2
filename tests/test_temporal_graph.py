"""Temporal heterogeneous graph (revizeler2.txt §1 ATHITD): zaman kısıtlı komşuluk, yenilik, akran seyrekliği."""

import pandas as pd
import pytest

from ztp.gnn.temporal_graph import Kenar, TemporalHeteroGraph, kenar_akisi

T0 = pd.Timestamp("2026-02-01")


def _t(gun, saat=9):
    return T0 + pd.Timedelta(days=gun, hours=saat)


def _olaylar(satirlar):
    return pd.DataFrame(satirlar)


@pytest.fixture
def graf():
    g = TemporalHeteroGraph()
    for gun, hedef in ((0, "PC-1"), (1, "PC-1"), (5, "PC-2")):
        g.ekle(Kenar(_t(gun), "U1", "cihaz", hedef, "kullandi"))
    for gun, hedef in ((0, "rapor.docx"), (6, "maas.xlsx")):
        g.ekle(Kenar(_t(gun), "U1", "kaynak", hedef, "eristi"))
    g.ekle(Kenar(_t(0), "U2", "kaynak", "rapor.docx", "eristi"))
    g.ekle(Kenar(_t(6), "U2", "cihaz", "PC-1", "kullandi"))
    return g.sonlandir()


def test_sonlandirilmadan_sorgu_reddedilir():
    g = TemporalHeteroGraph()
    g.ekle(Kenar(_t(0), "U1", "cihaz", "PC-1", "kullandi"))
    with pytest.raises(RuntimeError):
        g.kenarlar("U1")


def test_zaman_kisitli_komsuluk(graf):
    """Asıl fark bu: gözlem grafı 'U1 PC-2 kullanır' der; burada NE ZAMAN kullandığı sorulabilir."""
    assert graf.komsular("U1", _t(0), _t(1, 23)) == {("cihaz", "PC-1"), ("kaynak", "rapor.docx")}
    assert ("cihaz", "PC-2") in graf.komsular("U1", _t(4), _t(7))
    assert ("cihaz", "PC-2") not in graf.komsular("U1", _t(0), _t(3))


def test_hedef_turune_gore_suzme(graf):
    assert graf.komsular("U1", hedef_tur="kaynak") == {("kaynak", "rapor.docx"), ("kaynak", "maas.xlsx")}


def test_ilk_gorulme_novelty_temeli(graf):
    assert graf.ilk_gorulme("U1", "cihaz", "PC-1") == _t(0)  # ikinci kullanım değil, ilki
    assert graf.ilk_gorulme("U1", "cihaz", "PC-9") is None


def test_yeni_komsular_gecmisle_kiyaslanir(graf):
    """6. günde maas.xlsx yeni; PC-1 değil çünkü 0. günde de vardı."""
    yeni = graf.yeni_komsular("U1", _t(5), _t(7), gecmis_baslangic=_t(0))
    assert ("kaynak", "maas.xlsx") in yeni
    assert ("cihaz", "PC-1") not in yeni


def test_akran_seyrekligi_zamana_bagli(graf):
    """rapor.docx'e iki kullanıcı dokundu; PC-2'ye yalnız biri — seyreklik sinyali budur."""
    assert graf.hedefe_dokunan_kullanicilar("kaynak", "rapor.docx") == {"U1", "U2"}
    assert graf.hedefe_dokunan_kullanicilar("kaynak", "maas.xlsx") == {"U1"}
    assert graf.hedefe_dokunan_kullanicilar("cihaz", "PC-1", _t(0), _t(2)) == {"U1"}  # U2 6. günde geldi
    assert graf.hedefe_dokunan_kullanicilar("cihaz", "PC-1", _t(0), _t(7)) == {"U1", "U2"}


def test_tur_dagilimi_davranis_sekli(graf):
    assert graf.tur_dagilimi("U1") == {"cihaz": 3, "kaynak": 2}
    assert graf.tur_dagilimi("U1", _t(0), _t(1, 23)) == {"cihaz": 2, "kaynak": 1}


def test_kenar_akisi_zaman_sirasinda(graf):
    akis = kenar_akisi(graf)
    assert [k.zaman for k in akis] == sorted(k.zaman for k in akis)
    assert len(akis) == graf.kenar_sayisi == 7


# ---------------------------------------------------------------- olaylardan kurulum
def test_olaylardan_heterojen_kenar_uretir():
    ev = _olaylar(
        [
            dict(time=_t(0), canonical="U1", device="PC-1", resource="a.docx", category="haber", process=None, app="word"),
            dict(time=_t(1), canonical="U1", device="PC-1", resource=None, category=None, process="cmd.exe", app=None),
            dict(time=_t(2), canonical=None, device="PC-9", resource="x", category=None, process=None, app=None),
        ]
    )
    g = TemporalHeteroGraph.olaylardan(ev)
    o = g.ozet()
    assert o["kullanici"] == 1  # çözülmemiş aktör (canonical=None) grafa girmez
    assert o["tur_dagilimi"] == {"cihaz": 2, "kaynak": 1, "site": 1, "surec": 1, "uygulama": 1}


def test_usb_kopyasi_medya_kenari_uretir():
    ev = _olaylar([dict(time=_t(0), canonical="U1", device="USB-1", action="usb_copy", resource="gizli.xlsx")])
    g = TemporalHeteroGraph.olaylardan(ev)
    assert ("medya", "USB-1") in g.komsular("U1")
    assert ("kaynak", "gizli.xlsx") in g.komsular("U1")


def test_bos_olay_tablosu_coksmez():
    g = TemporalHeteroGraph.olaylardan(pd.DataFrame())
    assert g.kenar_sayisi == 0 and g.kullanicilar == []
    assert g.komsular("yok") == set()


def test_eksik_kolonlar_atlanir():
    ev = _olaylar([dict(time=_t(0), canonical="U1", device="PC-1")])  # resource/category/process yok
    g = TemporalHeteroGraph.olaylardan(ev)
    assert g.ozet()["tur_dagilimi"] == {"cihaz": 1}


def test_akran_sayisi_erken_cikis(graf):
    """Seyreklik sorusu 'eşikten az mı' biçiminde; tam sayım gerekmez. Erken çıkış eşikle sınırlı değer döndürür."""
    assert graf.akran_sayisi("kaynak", "rapor.docx") == 2  # sınırsız: tam sayı
    assert graf.akran_sayisi("kaynak", "rapor.docx", en_fazla=1) == 1  # eşiğe ulaşınca durur
    assert graf.akran_sayisi("kaynak", "maas.xlsx", en_fazla=3) == 1  # seyrek: eşiğin altında kalır
    assert graf.akran_sayisi("kaynak", "yok", en_fazla=3) == 0
    assert graf.akran_sayisi("cihaz", "PC-1", _t(0), _t(2), en_fazla=5) == 1  # zaman penceresine saygılı


def test_akran_sayisi_hedefe_dokunanlarla_tutarli(graf):
    for tur, hedef in (("kaynak", "rapor.docx"), ("cihaz", "PC-1"), ("kaynak", "maas.xlsx")):
        assert graf.akran_sayisi(tur, hedef) == len(graf.hedefe_dokunan_kullanicilar(tur, hedef))
