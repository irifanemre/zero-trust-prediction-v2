"""Saldırı yolu tahmini — sprint v6 katman B.

İki şey burada bağlanır: **sızıntı bariyeri** (önce tahmin, sonra öğrenme) ve **taban oranı** (model,
"her zaman en sık taktiği söyle" boş modelini geçmek zorunda). İkincisi olmadan yüksek bir isabet
rakamı anlamsızdır — 9 taktiklik bir sözlükte hiçbir şey öğrenmeden de yüksek top-3 alınır.
"""

import pandas as pd
import pytest

from ztp.attack_path import (
    BASLA,
    MIN_GECIS,
    NgramModeli,
    SaldiriYoluTahmincisi,
    degerlendir,
    ilerleme,
    model_kur,
    taban_orani,
    taktik_dizisi,
)
from ztp.config import TenantConfig
from ztp.detection.engine import Hit
from ztp.graph.knowledge import KnowledgeGraph

D0 = pd.Timestamp("2010-06-01")
KG = KnowledgeGraph()


def _hit(teknikler, gun=D0) -> Hit:
    return Hit("R", "R", "UEBA", gun, 0.8, 5.0, list(teknikler), [], {}, "yayinda", "", "", False, [])


# ---------------------------------------------------------------- taktik dizisi


def test_dizi_zaman_sirali():
    hits = [_hit(["T1052"], D0 + pd.Timedelta(days=2)), _hit(["T1087"], D0)]  # Exfiltration, Discovery
    assert [t for _, t in taktik_dizisi(hits, KG)] == ["Discovery", "Exfiltration"]


def test_ardisik_tekrar_tekillesir():
    """Aynı gün beş Discovery 'beş adım' değil bir adımdır; tekrar bilgisi zaten şiddette var."""
    hits = [_hit(["T1087"]), _hit(["T1018"]), _hit(["T1052"])]  # Discovery, Discovery, Exfiltration
    assert [t for _, t in taktik_dizisi(hits, KG)] == ["Discovery", "Exfiltration"]


def test_bilinmeyen_teknik_atilir():
    hits = [_hit(["T9999", "T1087"])]
    assert [t for _, t in taktik_dizisi(hits, KG)] == ["Discovery"]
    assert "Bilinmiyor" in [t for _, t in taktik_dizisi(hits, KG, bilinmeyeni_at=False)]


def test_bos_girdi():
    assert taktik_dizisi([], KG) == []


# ---------------------------------------------------------------- n-gram


def _ogret(m, diziler):
    for d in diziler:
        m.ogren(d)
    return m


def test_ngram_sik_gorulen_gecisi_ogrenir():
    m = _ogret(NgramModeli(en_uzun_baglam=2), [["Discovery", "Collection", "Exfiltration"]] * 40)
    t = m.tahmin(["Discovery", "Collection"])
    assert t.adaylar[0][0] == "Exfiltration"
    assert t.adaylar[0][1] > 0.8


def test_ngram_baglami_kisaltarak_geri_cekilir():
    """Görülmemiş uzun bağlam → kısalır. Sonunda marjinale düşer, asla boş dönmez."""
    m = _ogret(NgramModeli(en_uzun_baglam=2, min_baglam_gozlem=5), [["Discovery", "Exfiltration"]] * 20)
    gorulmemis = m.tahmin(["Impact", "Persistence"])  # bu bağlam hiç görülmedi
    assert gorulmemis.adaylar  # marjinalden cevap verir
    assert gorulmemis.baglam_uzunlugu == 0


def test_ngram_en_uzun_yeterli_baglami_secer():
    m = NgramModeli(en_uzun_baglam=2, min_baglam_gozlem=5)
    _ogret(m, [["Discovery", "Collection", "Exfiltration"]] * 10)
    assert m.tahmin(["Discovery", "Collection"]).baglam_uzunlugu == 2


def test_ngram_gorulmemis_taktige_sifir_olasilik_vermez():
    """Laplace: 'bu asla olmaz' demek, elimizdeki veriyle söylenemez."""
    m = _ogret(NgramModeli(), [["Discovery", "Exfiltration"]] * 30 + [["Discovery", "Impact"]])
    olasiliklar = dict(m.tahmin(["Discovery"], ust=10).adaylar)
    assert all(p > 0 for p in olasiliklar.values())


def test_ngram_deterministik_ve_esitlikte_alfabetik():
    a = _ogret(NgramModeli(), [["Discovery", "Collection"], ["Discovery", "Exfiltration"]])
    b = _ogret(NgramModeli(), [["Discovery", "Exfiltration"], ["Discovery", "Collection"]])
    assert a.tahmin(["Discovery"]).adaylar == b.tahmin(["Discovery"]).adaylar


def test_ngram_az_gozlemde_tahmin_yeterli_degil():
    m = _ogret(NgramModeli(), [["Discovery", "Exfiltration"]] * 2)
    t = m.tahmin(["Discovery"])
    assert t.gozlem < MIN_GECIS and not t.yeterli and t.metin() == ""


def test_metin_gozlem_sayisini_her_zaman_yazar():
    """3 geçişten öğrenilmiş tahminle 300'den öğrenilmiş aynı cümleyle sunulamaz."""
    m = _ogret(NgramModeli(), [["Discovery", "Exfiltration"]] * 40)
    metin = m.tahmin(["Discovery"]).metin()
    assert "geçişten öğrenildi" in metin and "ngram" in metin


def test_gecersiz_parametreler():
    for kw in (dict(en_uzun_baglam=0), dict(min_baglam_gozlem=0), dict(alfa=0.0)):
        with pytest.raises(ValueError):
            NgramModeli(**kw)
    with pytest.raises(ValueError):
        model_kur("baska")


# ---------------------------------------------------------------- taban oranı ve değerlendirme


def test_taban_orani_en_sik_taktiklerin_payi():
    diziler = [["A"]] * 70 + [["B"]] * 20 + [["C"]] * 10
    assert taban_orani(diziler, 1) == pytest.approx(0.70)
    assert taban_orani(diziler, 3) == pytest.approx(1.0)


def test_degerlendirme_tabani_da_raporlar():
    """Ölçüm tek başına isabet vermez: tabanı ve kaç katı olduğunu da verir (sapma 1)."""
    diziler = [["Discovery", "Collection", "Exfiltration"]] * 20 + [["Initial Access", "Discovery"]] * 30
    m = _ogret(NgramModeli(en_uzun_baglam=2), diziler)
    r = degerlendir(m, diziler)
    assert r["taban_top1"] is not None and r["top1_kat"] is not None
    assert r["top1"] > r["taban_top1"]  # model tabanı geçmeli


def test_degerlendirme_bos_veride_cokmez():
    assert degerlendir(NgramModeli(), [])["n"] == 0


# ---------------------------------------------------------------- sızıntı bariyeri


def test_tahmin_once_ogrenme_sonra():
    """En kritik test: bugünün geçişi, bugünün tahmininden SONRA öğrenilir."""
    t = SaldiriYoluTahmincisi(NgramModeli(en_uzun_baglam=1))
    # 40 gün boyunca herkes Discovery→Exfiltration izliyor
    for g in range(40):
        gun = D0 + pd.Timedelta(days=g)
        t.ogren_gun(gun, {f"U{i}": ["Discovery", "Exfiltration"] for i in range(3)})
    once = t.tahmin_et("YENI", ["Discovery"])
    assert once.adaylar[0][0] == "Exfiltration"
    # YENI'nin kendi geçişi henüz öğretilmedi: model onu görmemiş olmalı
    assert "YENI" not in t._gecmis


def test_ogrenme_ardisik_tekrari_atlar():
    t = SaldiriYoluTahmincisi(NgramModeli())
    t.ogren_gun(D0, {"U1": ["Discovery", "Discovery", "Exfiltration"]})
    assert t._gecmis["U1"] == ["Discovery", "Exfiltration"]


def test_gecmis_gunler_arasinda_birikir():
    t = SaldiriYoluTahmincisi(NgramModeli())
    t.ogren_gun(D0, {"U1": ["Discovery"]})
    t.ogren_gun(D0 + pd.Timedelta(days=1), {"U1": ["Collection"]})
    assert t._gecmis["U1"] == ["Discovery", "Collection"]
    assert t.tahmin_et("U1").gecmis[-2:] == ("Discovery", "Collection")


def test_tahminci_deterministik_sozluk_sirasindan_bagimsiz():
    """Kullanıcılar hangi sırayla gelirse gelsin model aynı olmalı (21.2)."""
    a, b = SaldiriYoluTahmincisi(NgramModeli()), SaldiriYoluTahmincisi(NgramModeli())
    gun = {"U1": ["Discovery"], "U2": ["Collection"], "U3": ["Exfiltration"]}
    a.ogren_gun(D0, gun)
    b.ogren_gun(D0, dict(reversed(list(gun.items()))))
    assert a.tahmin_et("X").adaylar == b.tahmin_et("X").adaylar


def test_etkinlik_alanlari():
    t = SaldiriYoluTahmincisi(NgramModeli())
    t.ogren_gun(D0, {"U1": ["Discovery", "Exfiltration"]})
    t.tahmin_et("U1")
    e = t.etkinlik()
    assert e["yol_gecis"] == 2 and e["yol_kullanici"] == 1 and e["yol_tahmin"] == 1


# ---------------------------------------------------------------- kill-chain ilerlemesi


def test_ilerleme_en_ileri_taktige_gore():
    assert ilerleme(["Initial Access"]) == 0.0
    assert ilerleme(["Discovery", "Exfiltration"]) == pytest.approx(0.9)
    assert ilerleme(["Impact"]) == 1.0
    assert ilerleme([]) is None
    assert ilerleme(["Bilinmiyor"]) is None


# ---------------------------------------------------------------- yapılandırma sözleşmesi


def test_v6b_varsayilanda_kapali_ve_skora_girmiyor():
    c = TenantConfig()
    assert c.saldiri_yolu_enabled is False
    assert c.saldiri_yolu_agirligi == 0.0  # ilk sürümde skora girmez — yalnız anlatıya


def test_transformer_torch_yoksa_acik_hata(monkeypatch):
    """Sessizce n-gram'a düşmek yasak: hangi modelin koştuğu koşu kaydından okunabilmeli."""
    import builtins

    gercek = builtins.__import__

    def sahte(ad, *a, **kw):
        if ad.startswith("torch"):
            raise ImportError("torch yok")
        return gercek(ad, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", sahte)
    import sys

    monkeypatch.delitem(sys.modules, "ztp.attack_path_torch", raising=False)
    with pytest.raises(ImportError, match="torch"):
        model_kur("transformer")
