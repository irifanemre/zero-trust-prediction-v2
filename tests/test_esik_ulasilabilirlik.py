"""Eşik ulaşılabilirlik denetimi — "bu kural hiç tetiklenebilir mi?"

Üç kez aynı hataya düşüldü ve üçünde de kural yapısal olarak ulaşılamaz oldu:

1. `UEBA-0003` r6.2'de: `http.csv`'de `content` kolonu yok → `bytes_out = 0`. Ağırlığı 8 olan
   kural o koşuda hiç tetiklenemedi; aylarca "neden tetiklenmiyor" diye eşik tartışıldı.
2. İlk `UEBA-0022` eşiği (`p < 0.001`): seyrek sayaçta 8 olay / 15 kat sıçrama istiyordu.
3. İlk `UEBA-0023` tabanı (5 MB): `bytes_out`'tan kopyalanmıştı, dış e-posta ölçeği için 50 kat fazla.

Ortak kalıp: **başka ölçekten alınan bir sabit, eşiği verinin erişemeyeceği yere koyuyor.** Normal
testler bunu yakalamaz çünkü kod doğrudur — kural sessizce hiç tetiklenmez ve raporda "bu veride
desen görülmedi" diye görünür.

Bu test sentetik veride her sinyalin gözlenen aralığını çıkarır ve kural eşikleriyle karşılaştırır.
Bilinen bulgular aşağıda listelidir; **yeni** bir ulaşılamaz eşik eklenirse test kırılır.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from esik_ulasilabilirlik import denetle, kosul_esikleri, sinyal_araliklari  # noqa: E402

from ztp.detection.catalog import load_catalog  # noqa: E402

# Ölçülmüş ve BELGELENMİŞ ulaşılamaz eşikler. Her biri bilinçli olarak burada:
# yeni bir tane eklenirse test kırılır ve gerekçesi yazılmadan geçemez.
BILINEN = {
    # UEBA-0017'nin iki Poisson koşulu da sentetik veride ulaşılamaz (gözlenen en küçük p sırasıyla
    # 0,0047 ve 0,034; eşik 0,001). Kural pratikte YALNIZ `usb_ilk_kez == 1` ile tetikleniyor —
    # yani "hayatında ilk kez USB" yakalanıyor, "kademeli artış" yakalanmıyor. Bu, r4.2'de kaçan
    # 7 S2 senaryosunun muhtemel sebebidir (`docs/v7-ayar-taramasi.md` ve literatür haritası).
    ("UEBA-0017", "usb_poisson_p"),
    ("UEBA-0017", "usb_7g_poisson_p"),
    # Sentetik üreteç dış e-posta ÜRETMİYOR: `eposta_dis_z` hep 0. Kuralın hatası değil, üretecin
    # eksiği (`docs/sprint-v8-kanal-kurallari-on-kayit.md`). E-posta senaryoları eklenince kalkar.
    ("UEBA-0023", "eposta_dis_z"),
    # REL-0016'nın "ortak kaynağa erişen riskli kullanıcı kümesi" deseni sentetik veride oluşmuyor.
    ("REL-0016", "ortak_kaynak_riskli_kume"),
}


def test_kosul_ayristirma():
    """Eşik çıkarımı doğru çalışmalı: denetim buna dayanıyor."""
    assert kosul_esikleri("veri_hacmi_z > 3.5") == [("veri_hacmi_z", ">", 3.5)]
    assert kosul_esikleri("3.5 < veri_hacmi_z") == [("veri_hacmi_z", ">", 3.5)]
    assert kosul_esikleri("p < 0.001") == [("p", "<", 0.001)]
    cok = kosul_esikleri("a >= 3 or b < 0.02")
    assert ("a", ">=", 3.0) in cok and ("b", "<", 0.02) in cok
    assert kosul_esikleri("bir_sey_yok") == []  # karşılaştırma içermeyen ifade


def test_denetim_ulasilamaz_esigi_bulur():
    """Denetimin kendisi çalışıyor mu — uydurma bir aralıkla sınanır."""
    katalog = [dict(id="TEST-1", durum="yayinda", mantik=dict(kosullar=["x > 100"]))]
    assert denetle({"x": (0.0, 5.0, 10)}, katalog)[0]["sorun"] == "eşik gözlenen aralığın dışında"
    assert denetle({"x": (0.0, 500.0, 10)}, katalog) == []
    assert denetle({}, katalog)[0]["sorun"] == "sinyal hiç üretilmedi"


@pytest.mark.slow
def test_yayindaki_kurallarda_yeni_ulasilamaz_esik_yok():
    """Sözleşme: yayındaki bir kuralın eşiği, sinyalin gözlenen aralığında olmalı.

    Bilinen istisnalar `BILINEN` listesindedir ve her biri belgelenmiştir. Yeni bir tane çıkarsa
    bu test kırılır — kural yazarken "eşik bu veride ulaşılabilir mi" sorusu atlanamaz.
    """
    araliklar = sinyal_araliklari(n_kullanici=100, n_gun=130, tohum=42)
    assert len(araliklar) > 80, "sinyal toplama çalışmıyor olabilir"
    bulgular = [b for b in denetle(araliklar, load_catalog()) if b["durum"] == "yayinda"]
    yeni = [b for b in bulgular if (b["kural"], b["sinyal"]) not in BILINEN]
    assert not yeni, "yeni ulaşılamaz eşik:\n" + "\n".join(
        f"  {b['kural']} — {b['kosul']} (sinyal {b['sinyal']}, gözlenen {b.get('gozlenen', 'yok')})" for b in yeni
    )


@pytest.mark.slow
def test_bilinen_bulgular_hala_gecerli():
    """`BILINEN` listesi bayatlamasın: düzeltilen bir madde listeden çıkarılmalı.

    Aksi hâlde liste zamanla "her şeyi affeden" bir kara deliğe dönüşür ve denetim anlamını yitirir.
    """
    araliklar = sinyal_araliklari(n_kullanici=100, n_gun=130, tohum=42)
    bulgular = {(b["kural"], b["sinyal"]) for b in denetle(araliklar, load_catalog())}
    cozulmus = BILINEN - bulgular
    assert not cozulmus, f"artık ulaşılabilir, BILINEN listesinden çıkarılmalı: {sorted(cozulmus)}"
