"""Kanıt doğrulayıcı (revizeler.txt §7.2): referansı olmayan iddialar rapordan silinir."""

import pytest

from ztp.llm_guards.claim_verifier import cumlelere_bol, dogrula, izinli_referanslar, referans_haritasi

VAKA = {
    "kullanici": "U-0042",
    "tespitler": [
        {"kural": "UEBA-0005", "ad": "USB kopya", "kanit": ["E-a1b2c3d", "E-9f8e7d6"]},
        {"kural": "UEBA-0001", "ad": "Mesai dışı giriş", "kanit": ["E-0011223"]},
    ],
    "kanit_serileri": {"rejim": ["E-ddee112"]},
    "hacim": "2400 MB dışa aktarıldı",
}


def test_izinli_referanslar_kanittan_cikariliyor():
    olaylar, kurallar = izinli_referanslar(VAKA)
    assert olaylar == {"E-A1B2C3D", "E-9F8E7D6", "E-0011223", "E-DDEE112"}
    assert kurallar == {"UEBA-0005", "UEBA-0001"}


def test_gecerli_referansli_cumle_tutulur():
    s = dogrula("Kullanıcı USB'ye kopya yaptı [E-a1b2c3d]. UEBA-0005 tetiklendi.", VAKA)
    assert s.temiz and not s.silinenler
    assert len(s.tutulanlar) == 2


def test_uydurma_olay_kimligi_silinir():
    """Modelin kanıt uydurmasının en güçlü işareti: vakada olmayan bir olay kimliği."""
    s = dogrula("USB kopya yapıldı [E-a1b2c3d]. Ayrıca E-ffffff0 olayında sızdırma görüldü.", VAKA)
    assert len(s.silinenler) == 1
    assert "olmayan olay kimliği" in s.silinenler[0].gerekce
    assert "E-ffffff0" not in s.metin and "E-a1b2c3d" in s.metin


def test_uydurma_kural_kimligi_silinir():
    s = dogrula("UEBA-0005 tetiklendi. REL-0016 kuralı da bu kullanıcıda tetiklendi.", VAKA)
    assert len(s.silinenler) == 1 and "olmayan kural kimliği" in s.silinenler[0].gerekce


def test_topraksiz_sayi_referansa_ragmen_silinir():
    """Referans doğru olsa bile uydurma hacim/adet kabul edilmez."""
    s = dogrula("Kullanıcı 2400 MB aktardı [E-a1b2c3d]. Kullanıcı 9999 MB aktardı [E-a1b2c3d].", VAKA)
    assert len(s.silinenler) == 1 and "kanıtta geçmeyen sayı" in s.silinenler[0].gerekce
    assert "2400" in s.metin and "9999" not in s.metin


def test_dengeli_mod_yonlendirme_cumlesini_tutar():
    s = dogrula("Vaka incelemeye alınmalıdır. Kullanıcı USB kullandı [E-a1b2c3d].", VAKA, katilik="dengeli")
    assert s.temiz
    assert "Vaka incelemeye alınmalıdır." in s.metin


def test_siki_mod_referanssiz_her_cumleyi_siler():
    s = dogrula("Vaka incelemeye alınmalıdır. Kullanıcı USB kullandı [E-a1b2c3d].", VAKA, katilik="siki")
    assert len(s.silinenler) == 1 and "sıkı mod" in s.silinenler[0].gerekce
    assert s.metin == "Kullanıcı USB kullandı [E-a1b2c3d]."


def test_dengeli_modda_referanssiz_iddia_silinir():
    """Sayı/kimlik taşıyan ama referansı olmayan cümle, dengeli modda da gider."""
    s = dogrula("Kullanıcı U-0042 şüphelidir.", VAKA, katilik="dengeli")
    assert len(s.silinenler) == 1 and "referansı yok" in s.silinenler[0].gerekce


def test_seri_isaretleri_referans_sayilir():
    s = dogrula("Davranış profili değişti [seri rejim].", VAKA)
    assert s.temiz and s.tutulanlar[0].referanslar == ["[seri rejim]"]


def test_silme_sessiz_degil():
    s = dogrula("USB kopya [E-a1b2c3d]. Uydurma E-ffffff0 var.", VAKA)
    o = s.ozet()
    assert o["silinen"] == 1 and o["tutulan"] == 1 and o["silinen_oran"] == 0.5
    assert o["gerekceler"][0]["gerekce"].startswith("vakada olmayan olay")


def test_cumle_bolme_madde_imlerini_ayirir():
    assert len(cumlelere_bol("Birinci cümle.\n- Madde bir\n- Madde iki")) == 3
    assert cumlelere_bol("") == []


def test_referans_haritasi_denetim_icin():
    h = referans_haritasi("USB kopya [E-a1b2c3d]. UEBA-0005 tetiklendi.", VAKA)
    assert any("E-a1b2c3d" in v for v in h.values())
    assert any("UEBA-0005" in v for v in h.values())


def test_bos_metin_ve_bozuk_katilik():
    assert dogrula("", VAKA).metin == ""
    with pytest.raises(ValueError):
        dogrula("x", VAKA, katilik="cok_siki")
