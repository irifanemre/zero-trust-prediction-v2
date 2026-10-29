"""Bayesian risk kapısı (revizeler.txt §1.3): sakin günlerde kuyruk eksik kapanabilmeli.

r6.2 kör koşusu sorunu ölçtü: 2801 kullanıcıda günde 23,7 vaka, bütçe neredeyse her gün doldu.
Bütçe sabit bir SAYI, kapı sabit bir KURAL; nüfus büyüyünce kuyruk zayıf kanıtla doluyor.
"""

import pytest

from ztp.gnn.bayesian_gate import BayesKapisi


def _ogret(kapi, kurallar, dogru, kez):
    for _ in range(kez):
        kapi.ogren(kurallar, dogru)
    return kapi


def test_varsayilan_kapali_davranis_degismez():
    """Sözleşme: esik=0 iken hiçbir vaka elenmez."""
    k = _ogret(BayesKapisi(), ["UEBA-0005"], False, 500)
    gecen, elenen = k.suz(["U1", "U2"], {"U1": ["UEBA-0005"], "U2": ["UEBA-0005"]})
    assert gecen == ["U1", "U2"] and elenen == []


def test_gecmiste_hep_yanlis_cikan_oruntu_elenir():
    k = _ogret(BayesKapisi(esik=0.3), ["UEBA-0005"], False, 100)
    karar = k.degerlendir("U1", ["UEBA-0005"])
    assert not karar.gecti
    assert karar.olasilik < 0.05 and "eşik" in karar.gerekce


def test_gecmiste_dogru_cikan_oruntu_gecer():
    k = _ogret(BayesKapisi(esik=0.3), ["UEBA-0005", "HONEY-0019"], True, 40)
    assert k.degerlendir("U1", ["HONEY-0019", "UEBA-0005"]).gecti  # sıra önemsiz


def test_yeni_kural_susturulmaz():
    """Hiç etiketi olmayan örüntü önsel ortalamayla geçer — sistem bilmediğini susturmaz."""
    k = BayesKapisi(esik=0.3, min_gozlem=10)
    karar = k.degerlendir("U1", ["YENI-9999"])
    assert karar.gecti and "yetersiz gözlem" in karar.gerekce
    assert karar.olasilik == 0.5  # düzgün önsel


def test_az_gozlemli_oruntu_elenmez():
    k = _ogret(BayesKapisi(esik=0.4, min_gozlem=10), ["UEBA-0001"], False, 9)
    assert k.degerlendir("U1", ["UEBA-0001"]).gecti  # 9 < 10
    k.ogren(["UEBA-0001"], False)  # 10. gözlem
    assert not k.degerlendir("U1", ["UEBA-0001"]).gecti


def test_kritik_vaka_kapidan_muaf():
    """13.5 istisnası: honeytoken teması gibi deterministik sinyaller olasılığa bakmaz."""
    k = _ogret(BayesKapisi(esik=0.9), ["HONEY-0019"], False, 200)
    assert not k.degerlendir("U1", ["HONEY-0019"]).gecti
    muaf = k.degerlendir("U1", ["HONEY-0019"], kritik=True)
    assert muaf.gecti and "kritik" in muaf.gerekce


def test_sakin_gunde_kuyruk_eksik_kapanir():
    """Asıl amaç: bütçede yer olsa bile zayıf vakalar alınmaz."""
    k = _ogret(BayesKapisi(esik=0.3), ["ZAYIF"], False, 100)
    _ogret(k, ["GUCLU"], True, 50)
    kuyruk = [f"U{i}" for i in range(30)]
    harita = {sid: (["GUCLU"] if i < 4 else ["ZAYIF"]) for i, sid in enumerate(kuyruk)}
    gecen, elenen = k.suz(kuyruk, harita)
    assert len(gecen) == 4  # 30'luk bütçe 4 vakayla kapandı
    assert len(elenen) == 26
    assert all("eşik" in e.gerekce for e in elenen)


def test_yogun_gunde_hicbir_sey_degismez():
    k = _ogret(BayesKapisi(esik=0.3), ["GUCLU"], True, 50)
    kuyruk = [f"U{i}" for i in range(30)]
    gecen, elenen = k.suz(kuyruk, {sid: ["GUCLU"] for sid in kuyruk})
    assert gecen == kuyruk and elenen == []


def test_sira_korunur_kapi_yeniden_siralamaz():
    k = _ogret(BayesKapisi(esik=0.3), ["ZAYIF"], False, 100)
    _ogret(k, ["GUCLU"], True, 50)
    kuyruk = ["A", "B", "C", "D"]
    harita = {"A": ["ZAYIF"], "B": ["GUCLU"], "C": ["ZAYIF"], "D": ["GUCLU"]}
    gecen, _ = k.suz(kuyruk, harita)
    assert gecen == ["B", "D"]  # sıra bozulmadı, yalnız eleme yapıldı


def test_etiketlerden_toplu_ogrenme():
    k = BayesKapisi(esik=0.3, min_gozlem=2)
    k.etiketlerden(
        [
            {"kurallar": ["UEBA-0005"], "dogru": False},
            {"kurallar": ["UEBA-0005"], "dogru": False},
            {"kurallar": ["HONEY-0019"], "true_positive": True},
            {"kurallar": ["X"]},  # etiketsiz kayıt atlanır
        ]
    )
    assert not k.degerlendir("U1", ["UEBA-0005"]).gecti
    assert k.ozet()["oruntu_sayisi"] == 2


def test_ozet_en_zayif_oruntuyu_one_cikarir():
    k = _ogret(BayesKapisi(esik=0.3), ["ZAYIF"], False, 50)
    _ogret(k, ["GUCLU"], True, 50)
    o = k.ozet()
    assert o["oruntuler"][0]["oruntu"] == ["ZAYIF"]  # en düşük sonsal başta
    assert o["oruntuler"][0]["sonsal"] < o["oruntuler"][-1]["sonsal"]


def test_bos_oruntu_ve_bozuk_parametre():
    k = BayesKapisi(esik=0.3)
    k.ogren([], True)
    assert k.ozet()["oruntu_sayisi"] == 0
    for kwargs in ({"esik": 1.0}, {"esik": -0.1}, {"alfa": 0}, {"beta": -1}, {"min_gozlem": -1}):
        with pytest.raises(ValueError):
            BayesKapisi(**kwargs)
