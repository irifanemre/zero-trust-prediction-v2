"""Şema profilleyici — "bu veri setinde hangi sinyal GERÇEKTEN var?"

Bu modülün varlık sebebi ölçülmüş bir hata: CERT r6.2'nin `http.csv` dosyasında `content` kolonu
yoktur, dolayısıyla `bytes_out` her web olayında sıfırdır ve ağırlığı 8 olan `UEBA-0003` o koşuda
hiç tetiklenemedi. Aylarca fark edilmedi çünkü raporda "bu veride desen görülmedi" diye göründü.

Veri kalitesi katmanı bunu yakalayamaz: o çalışma zamanında hacim düşüşüne bakar, bir kolonun en
baştan hiç olmamasına değil.
"""

import numpy as np
import pandas as pd
import pytest

from ztp.schema_profiler import (
    HAM_BAGIMLILIK,
    MIN_DOLULUK,
    TUREV_BAGIMLILIK,
    AlanDurumu,
    OzellikHaritasi,
    ham_basliklar,
    olay_alanlari,
    profille,
    rapor,
)


# ---------------------------------------------------------------- alan durumu


def test_alan_durumlari():
    assert AlanDurumu("x", var=False).durum == "yok"
    assert AlanDurumu("x", var=True, doluluk=0.0, tekil=1).durum == "bos"
    assert AlanDurumu("x", var=True, doluluk=1.0, tekil=1).durum == "sabit"
    assert AlanDurumu("x", var=True, doluluk=0.5, tekil=9).durum == "kullanilabilir"
    assert AlanDurumu("x", var=True, doluluk=0.5, tekil=9).kullanilabilir


def test_sifir_sayisal_alan_bos_sayilir():
    """`bytes_out` hep 0 ise alan teknik olarak VAR ama bilgi taşımaz — r6.2'nin tam durumu."""
    ev = pd.DataFrame(dict(bytes_out=[0, 0, 0, 0], app=["a", "b", "c", "d"]))
    a = olay_alanlari(ev)
    assert a["bytes_out"].durum == "bos"
    assert a["app"].durum == "kullanilabilir"


def test_tek_degerli_alan_sabit_sayilir():
    ev = pd.DataFrame(dict(source=["proxy"] * 10, app=list("abcdefghij")))
    a = olay_alanlari(ev)
    assert a["source"].durum == "sabit"  # bilgi taşımaz: z-skoru hep 0 olur
    assert a["app"].durum == "kullanilabilir"


def test_olmayan_alan_yok_isaretlenir():
    a = olay_alanlari(pd.DataFrame(dict(x=[1, 2])), alanlar=["x", "yok_boyle_bir_alan"])
    assert a["x"].kullanilabilir and a["yok_boyle_bir_alan"].durum == "yok"


def test_bos_tablo_cokmez():
    assert olay_alanlari(pd.DataFrame()) == {}
    assert olay_alanlari(None) == {}


def test_ornekleme_deterministik():
    """Büyük tabloda baştan alınır, rastgele değil — koşu tekrarlanabilirliği (21.2)."""
    ev = pd.DataFrame(dict(x=list(range(1000))))
    a, b = olay_alanlari(ev, ornek=100), olay_alanlari(ev, ornek=100)
    assert a["x"].tekil == b["x"].tekil == 100


# ---------------------------------------------------------------- ham başlıklar


def test_baslik_okuma(tmp_path):
    (tmp_path / "logon.csv").write_text("id,date,user,pc,activity\n1,x,y,z,Logon\n", encoding="utf-8")
    assert ham_basliklar(tmp_path, ["logon.csv"])["logon.csv"] == ["id", "date", "user", "pc", "activity"]


def test_basliksiz_dosya_bos_doner(tmp_path):
    """CERT r1'in `http.csv`'si başlıksızdır; çökmemeli ve yanlış kolon adı uydurmamalı."""
    (tmp_path / "http.csv").write_text("{A1B2-C3D4},01/04/2010 08:14:09,ABC0123,PC-1,http://x\n", encoding="utf-8")
    assert ham_basliklar(tmp_path, ["http.csv"])["http.csv"] == []


def test_olmayan_dosya_bos_doner(tmp_path):
    assert ham_basliklar(tmp_path, ["yok.csv"])["yok.csv"] == []


# ---------------------------------------------------------------- asıl hata: r6.2


def test_r62_deseni_content_kolonu_eksik(tmp_path):
    """Ölçülmüş hatanın yeniden üretimi: `http.csv`'de `content` yoksa UYARI çıkmalı."""
    (tmp_path / "http.csv").write_text("id,date,user,pc,url\n", encoding="utf-8")
    h = profille("sahte-r6.2", ham_dizin=tmp_path, ham_dosyalar=["http.csv"])
    assert any("content" in u and "bytes_out" in u for u in h.uyarilar)
    assert h.notlar == []


def test_r42_deseni_content_var_uyari_yok(tmp_path):
    (tmp_path / "http.csv").write_text("id,date,user,pc,url,content\n", encoding="utf-8")
    h = profille("sahte-r4.2", ham_dizin=tmp_path, ham_dosyalar=["http.csv"])
    assert h.uyarilar == []


def test_ayristiricinin_ele_aldigi_fark_uyari_degil_NOT(tmp_path):
    """r4.2'de `to_removable_media` yokluğu NORMALDİR: dosya kaydı zaten kopya demektir.

    İlk sürümde bu uyarı olarak çıkıyordu — yanlış alarm. Kritik/not ayrımı o yüzden var.
    """
    (tmp_path / "file.csv").write_text("id,date,user,pc,filename,content\n", encoding="utf-8")
    h = profille("sahte-r4.2", ham_dizin=tmp_path, ham_dosyalar=["file.csv"])
    assert h.uyarilar == []
    assert any("to_removable_media" in n for n in h.notlar)


def test_basliksiz_dosya_yanlis_alarm_uretmez(tmp_path):
    """r1'de her dosya başlıksız; 'kolon yok' diye tüm bağımlılıkları ölü ilan etmemeli."""
    (tmp_path / "http.csv").write_text("{A1},01/04/2010 08:14:09,U,PC,http://x\n", encoding="utf-8")
    h = profille("sahte-r1", ham_dizin=tmp_path, ham_dosyalar=["http.csv"])
    assert h.uyarilar == [] and h.notlar == []


# ---------------------------------------------------------------- türev zinciri


def test_olu_turev_eksik_alani_gosterir():
    h = OzellikHaritasi("t")
    h.alanlar = {
        "bytes_out": AlanDurumu("bytes_out", var=True, doluluk=0.0, tekil=1),  # boş
        "app": AlanDurumu("app", var=True, doluluk=0.9, tekil=12),
    }
    olu = h.olu_turevler()
    assert "bytes_out" in olu and olu["bytes_out"] == ["bytes_out"]
    assert "ext_email_bytes" in olu  # app var ama bytes_out boş → zincir kopuk
    assert not h.turev_uretilebilir("bytes_out")
    assert h.turev_uretilebilir("ext_email_count")  # yalnız app'e dayanır


def test_bilinmeyen_turev_engellenmez():
    """Haritada olmayan bir türev hakkında karar verilmez — sessizce kapatmak daha kötüdür."""
    assert OzellikHaritasi("t").turev_uretilebilir("hic_bilinmeyen_ozellik")


def test_turev_bagimliliklari_tutarli():
    """Her bağımlılık bir olay alanı olmalı; yazım hatası sessizce 'üretilebilir' demesin."""
    olay_alanları = {"bytes_out", "source", "action", "resource", "process", "cmdline", "app", "time", "outcome"}
    for turev, bagimlilik in TUREV_BAGIMLILIK.items():
        for a in bagimlilik:
            assert a in olay_alanları, f"{turev} → bilinmeyen alan {a}"


def test_ham_bagimlilik_bicimi():
    for anahtar, deger in HAM_BAGIMLILIK.items():
        assert ":" in anahtar and anahtar.endswith(tuple("abcdefghijklmnopqrstuvwxyz_"))
        alan, aciklama, kritik = deger
        assert isinstance(kritik, bool) and aciklama


# ---------------------------------------------------------------- rapor


def test_rapor_eksik_yokken_bunu_soyler():
    h = OzellikHaritasi("temiz")
    h.alanlar = {a: AlanDurumu(a, var=True, doluluk=0.9, tekil=9) for a in ("bytes_out", "source", "action", "resource", "process", "cmdline", "app", "time", "outcome")}
    assert "Eksik sinyal yok" in rapor(h)


def test_rapor_uyariyi_tasir():
    h = OzellikHaritasi("bozuk")
    h.uyarilar = ["http.csv: `content` kolonu yok"]
    r = rapor(h)
    assert "content" in r and "Uyarılar" in r
