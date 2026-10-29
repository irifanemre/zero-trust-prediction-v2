"""Graf risk sinyalleri (revizeler2.txt §1 ATHITD, §3 RiskScore-Guided GNN, §6 anticipation)."""

import pandas as pd
import pytest

from ztp.gnn.temporal_graph import Kenar, TemporalHeteroGraph
from ztp.gnn.tgn_model import (
    TemporalGraphBaseline,
    ablasyon_karsilastir,
    erken_uyari_suresi,
    risk_yayilimi,
    risk_yorungesi_egimi,
)

T0 = pd.Timestamp("2026-02-01")


def _g(gun, saat=9):
    return T0 + pd.Timedelta(days=gun, hours=saat)


def _graf(kenarlar):
    g = TemporalHeteroGraph()
    for gun, sid, tur, hedef in kenarlar:
        g.ekle(Kenar(_g(gun), sid, tur, hedef, "eristi"))
    return g.sonlandir()


# ---------------------------------------------------------------- yenilik
def test_gecmis_yetersizse_sinyal_uretilmez():
    """Sözleşme: az gözlemde uydurma sinyal yok, gozlem_yetersiz bayrağı ve sıfır risk."""
    g = _graf([(0, "U1", "kaynak", "a"), (10, "U1", "kaynak", "b")])
    s = TemporalGraphBaseline().hesapla(g, "U1", _g(10))
    assert s.gozlem_yetersiz and s.graf_riski == 0.0
    assert "yeterli geçmiş yok" in s.aciklama()


def test_yeni_iliski_yakalanir():
    gecmis = [(i, "U1", "kaynak", f"rutin{i}") for i in range(8)]
    g = _graf(gecmis + [(10, "U1", "kaynak", "maas.xlsx")])
    s = TemporalGraphBaseline().hesapla(g, "U1", _g(10))
    assert s.graf_yenilik == 1.0  # bugünkü tek hedef yeni
    assert ("kaynak", "maas.xlsx") in s.yeni_hedefler
    assert "yeni ilişki" in s.aciklama()


def test_tanidik_iliski_yenilik_uretmez():
    g = _graf([(i, "U1", "kaynak", "rutin") for i in range(12)])
    s = TemporalGraphBaseline().hesapla(g, "U1", _g(11))
    assert s.graf_yenilik == 0.0


# ---------------------------------------------------------------- seyreklik
def test_akranlarin_dokunmadigi_hedef_seyrek():
    """Aynı dosya: 10 kişi açıyorsa sıradan, kimse açmıyorsa sinyal. Sayım tabanlı özellikte bu fark yok."""
    kalabalik = [(i, f"U{i}", "kaynak", "ortak.docx") for i in range(10)]
    gecmis = [(i, "U1", "kaynak", f"r{i}") for i in range(8)]
    g = _graf(kalabalik + gecmis + [(10, "U1", "kaynak", "gizli.xlsx")])
    s = TemporalGraphBaseline().hesapla(g, "U1", _g(10))
    assert ("kaynak", "gizli.xlsx") in s.seyrek_hedefler
    assert s.graf_seyreklik == 1.0

    g2 = _graf(kalabalik + gecmis + [(10, "U1", "kaynak", "ortak.docx")])
    assert TemporalGraphBaseline().hesapla(g2, "U1", _g(10)).graf_seyreklik == 0.0


# ---------------------------------------------------------------- tür kayması
def test_davranisin_sekli_degisirse_yakalanir():
    """Hacim sabit, şekil değişiyor: geçmişte hep 'kaynak', bugün 'medya'. Sayımlarda görünmez."""
    g = TemporalHeteroGraph()
    for i in range(10):
        g.ekle(Kenar(_g(i), "U1", "kaynak", f"r{i}", "eristi"))
    g.ekle(Kenar(_g(11), "U1", "medya", "USB-1", "kopyaladi"))
    g.sonlandir()
    assert TemporalGraphBaseline().hesapla(g, "U1", _g(11)).graf_tur_kaymasi == 1.0


def test_sekil_aynisa_kayma_yok():
    g = _graf([(i, "U1", "kaynak", f"r{i}") for i in range(12)])
    assert TemporalGraphBaseline().hesapla(g, "U1", _g(11)).graf_tur_kaymasi == 0.0


# ---------------------------------------------------------------- risk yayılımı (§3)
def test_risk_paylasilan_varliktan_yayilir():
    g = _graf([(0, "RISKLI", "cihaz", "PC-1"), (0, "KOMSU", "cihaz", "PC-1"), (0, "UZAK", "cihaz", "PC-9")])
    y = risk_yayilimi(g, {"RISKLI": 1.0}, _g(-1), _g(1), adim=1)
    assert y.get("KOMSU", 0) > 0
    assert "UZAK" not in y


def test_kendi_riski_geri_donmez():
    """İki adımda A→hedef→B→hedef2→A yolu A'nın riskini A'ya geri vermemeli."""
    g = _graf([(0, "A", "cihaz", "PC-1"), (0, "B", "cihaz", "PC-1"), (0, "B", "kaynak", "f1"), (0, "A", "kaynak", "f1")])
    y = risk_yayilimi(g, {"A": 1.0}, _g(-1), _g(1), adim=2)
    assert y.get("A", 0.0) == 0.0, y
    assert y.get("B", 0.0) > 0


def test_herkesin_dokundugu_varlik_zayif_sinyal():
    """Paylaşım genişse mesaj zayıflar: ortak yazıcı, kişiye özel sunucu kadar bilgi taşımaz."""
    dar = _graf([(0, "R", "cihaz", "PC"), (0, "K", "cihaz", "PC")])
    genis = _graf([(0, "R", "cihaz", "PC")] + [(0, f"K{i}", "cihaz", "PC") for i in range(50)])
    d = risk_yayilimi(dar, {"R": 1.0}, _g(-1), _g(1), adim=1)
    gns = risk_yayilimi(genis, {"R": 1.0}, _g(-1), _g(1), adim=1)
    # dar paylaşımda tek komşu tüm mesajı alır; geniş paylaşımda mutlak pay çok daha küçüktür
    assert d["K"] == 1.0 and len(gns) == 50


def test_tohum_yoksa_yayilim_bos():
    g = _graf([(0, "A", "cihaz", "PC")])
    assert risk_yayilimi(g, {}, _g(-1), _g(1)) == {}
    with pytest.raises(ValueError):
        risk_yayilimi(g, {"A": 1.0}, _g(-1), _g(1), sonum=0.0)


# ---------------------------------------------------------------- ablasyon sözleşmesi (§10)
def test_agirlik_sifirken_skor_birebir_ayni():
    """Model A ↔ Model B sözleşmesi: graf kapalıyken çıktı tabanla BİREBİR aynı olmalı."""
    taban = {"U1": 12.5, "U2": 3.0}
    g = _graf([(i, "U1", "kaynak", f"r{i}") for i in range(10)] + [(10, "U1", "kaynak", "yeni")])
    sinyal = TemporalGraphBaseline().toplu(g, ["U1", "U2"], _g(10))
    assert ablasyon_karsilastir(taban, sinyal, 0.0) == taban
    artirilmis = ablasyon_karsilastir(taban, sinyal, 0.5)
    assert artirilmis["U1"] > taban["U1"]  # graf sinyali olan yükseldi
    assert artirilmis["U2"] == taban["U2"]  # sinyali olmayan değişmedi
    with pytest.raises(ValueError):
        ablasyon_karsilastir(taban, sinyal, 1.5)


# ---------------------------------------------------------------- anticipation (§6)
def test_erken_uyari_suresi():
    """Day 1: 0.20 … Day 5: 0.72 → Day 6 olay. Eşik 0,5 ise 2 gün önce uyarılmış olmalı."""
    seri = [(_g(i), r) for i, r in enumerate([0.20, 0.25, 0.34, 0.51, 0.72])]
    assert erken_uyari_suresi(seri, _g(5), esik=0.5) == 2


def test_tek_gunluk_sicrama_erken_uyari_sayilmaz():
    """Eşiği aşıp geri düşen bir gün analist için gürültüdür; sayaç sıfırlanır."""
    seri = [(_g(0), 0.9), (_g(1), 0.1), (_g(2), 0.1), (_g(3), 0.8), (_g(4), 0.85)]
    assert erken_uyari_suresi(seri, _g(5), esik=0.5) == 2  # 3. günden itibaren, 0. gün değil


def test_esik_hic_asilmazsa_erken_uyari_yok():
    seri = [(_g(i), 0.1) for i in range(5)]
    assert erken_uyari_suresi(seri, _g(5), esik=0.5) is None
    assert erken_uyari_suresi([], _g(5), esik=0.5) is None


def test_yorunge_egimi():
    artan = [(_g(i), 0.1 * i) for i in range(6)]
    assert risk_yorungesi_egimi(artan) == pytest.approx(0.1, abs=1e-6)
    assert risk_yorungesi_egimi([(_g(i), 0.5) for i in range(6)]) == 0.0
    assert risk_yorungesi_egimi([(_g(0), 0.5)]) == 0.0


def test_sinyal_adlari_ve_sozluk():
    g = _graf([(i, "U1", "kaynak", f"r{i}") for i in range(10)] + [(10, "U1", "kaynak", "yeni")])
    s = TemporalGraphBaseline().hesapla(g, "U1", _g(10))
    assert set(s.sozluk()) == set(TemporalGraphBaseline.sinyal_adlari())
    assert all(0.0 <= v <= 1.0 for v in s.sozluk().values())


def test_bozuk_parametre():
    with pytest.raises(ValueError):
        TemporalGraphBaseline(gecmis_gun=0)
    with pytest.raises(ValueError):
        TemporalGraphBaseline(seyrek_esik=0)
