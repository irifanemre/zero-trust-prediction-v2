"""Analist geri bildirim döngüsü — sprint v6 katman A.

En kritik iki özellik sızıntıya karşı: etiket GECİKMELİ gelir ve yalnız KUYRUĞA GİREN vaka etiketlenir.
İkisi de burada bağlanır; biri bozulursa sistem kendi geleceğini okumaya başlar ve bütün ölçümler
anlamsızlaşır.
"""

import pandas as pd
import pytest

from ztp.analyst_loop import (
    AnalistSimulatoru,
    KalibrasyonZamanlayicisi,
    _kararli_birim,
    bayes_besle,
    belirsizlik_sirasi,
)
from ztp.config import TenantConfig
from ztp.feedback import LabelStore
from ztp.gnn.bayesian_gate import BayesKapisi

D0 = pd.Timestamp("2010-06-10")


def _gt(sid: str = "INS1", bas: str = "2010-06-10", olay: str = "2010-06-20") -> dict:
    return dict(
        senaryo=f"S-{sid}",
        aktor=sid,
        sid=sid,
        teknikler=["T1078"],
        veri_kaynagi="ad",
        beklenen=["UEBA-0001"],
        baslangic_tarihi=bas,
        olay_tarihi=olay,
        pencere=[bas, olay],
    )


def _vaka(sid: str, gun: pd.Timestamp, kurallar=("UEBA-0001",), yuzdelik=0.9) -> dict:
    return dict(
        case_id=f"C-{gun.strftime('%Y%m%d')}-{sid}",
        gun=str(gun.date()),
        kullanici=f"p-{sid}",
        _sid=sid,
        yuzdelik=yuzdelik,
        tespitler=[dict(kural=k) for k in kurallar],
    )


# ---------------------------------------------------------------- sızıntı


def test_etiket_ayni_gun_gorunmez(tmp_path):
    """Döngünün en kritik kuralı: D günü kuyruğa giren vaka D günü etiketlenemez."""
    sim = AnalistSimulatoru([_gt()], gecikme_gun=2)
    store = LabelStore(tmp_path / "l.json")
    sim.kuyruga_al(D0, [_vaka("INS1", D0)])
    assert sim.gun(D0, store) == []  # aynı gün
    assert sim.gun(D0 + pd.Timedelta(days=1), store) == []  # bir gün sonra, hâlâ erken
    yazilan = sim.gun(D0 + pd.Timedelta(days=2), store)  # gecikme doldu
    assert len(yazilan) == 1 and yazilan[0]["karar"] == "gercek_pozitif"


def test_sifir_gecikme_ayni_gun_etiketler(tmp_path):
    sim = AnalistSimulatoru([_gt()], gecikme_gun=0)
    store = LabelStore(tmp_path / "l.json")
    sim.kuyruga_al(D0, [_vaka("INS1", D0)])
    assert len(sim.gun(D0, store)) == 1


def test_yalniz_kuyruga_girenler_etiketlenir(tmp_path):
    """Cevap anahtarında insider var ama kuyruğa girmediyse etiket üretilmez — analist görmediğini kapatmaz."""
    sim = AnalistSimulatoru([_gt(), _gt("INS2")], gecikme_gun=0)
    store = LabelStore(tmp_path / "l.json")
    sim.kuyruga_al(D0, [_vaka("INS1", D0)])  # INS2 kuyrukta yok
    sim.gun(D0, store)
    assert {lab["sid"] for lab in store.labels} == {"INS1"}


def test_pencere_disi_gun_yanlis_pozitif(tmp_path):
    """İnsider bile olsa tespit penceresi dışındaki gün yanlış pozitiftir."""
    sim = AnalistSimulatoru([_gt(bas="2010-06-10", olay="2010-06-12")], gecikme_gun=0)
    store = LabelStore(tmp_path / "l.json")
    uzak = pd.Timestamp("2010-08-01")  # pencere [bas-7g, olay+7g] dışında
    sim.kuyruga_al(uzak, [_vaka("INS1", uzak)])
    sim.gun(uzak, store)
    assert store.labels[0]["karar"] == "yanlis_pozitif"
    assert store.labels[0]["sebep"] in ("mesru_is_gerekcesi",)  # sebep zorunlu (17.3)


def test_masum_kullanici_yanlis_pozitif(tmp_path):
    sim = AnalistSimulatoru([_gt()], gecikme_gun=0)
    store = LabelStore(tmp_path / "l.json")
    sim.kuyruga_al(D0, [_vaka("NORMAL1", D0)])
    sim.gun(D0, store)
    assert store.labels[0]["karar"] == "yanlis_pozitif"


# ---------------------------------------------------------------- determinizm


def test_kararli_birim_siradan_bagimsiz():
    """Aynı vaka, hangi sırayla işlenirse işlensin aynı sayıyı alır — RNG durumu yok (21.2)."""
    a = [_kararli_birim(f"C-{i}") for i in range(20)]
    b = [_kararli_birim(f"C-{i}") for i in reversed(range(20))][::-1]
    assert a == b
    assert all(0.0 <= v < 1.0 for v in a)


def test_hata_orani_deterministik_ve_etkili(tmp_path):
    kararlar = []
    for _ in range(2):
        sim = AnalistSimulatoru([_gt()], gecikme_gun=0, hata_orani=0.5)
        store = LabelStore(tmp_path / f"l{_}.json")
        for i in range(40):
            g = D0 + pd.Timedelta(days=i)
            sim.kuyruga_al(g, [_vaka("INS1", g)])
            sim.gun(g, store)
        kararlar.append([lab["karar"] for lab in store.labels])
    assert kararlar[0] == kararlar[1]  # iki koşu birebir aynı
    assert len(set(kararlar[0])) == 2  # hem doğru hem ters etiket üretildi


def test_hata_orani_sifirken_hic_ters_etiket_yok(tmp_path):
    sim = AnalistSimulatoru([_gt()], gecikme_gun=0, hata_orani=0.0)
    store = LabelStore(tmp_path / "l.json")
    for i in range(10):
        g = D0 + pd.Timedelta(days=i)
        sim.kuyruga_al(g, [_vaka("INS1", g)])
        sim.gun(g, store)
    assert sim.hatali == 0
    assert all(lab["karar"] == "gercek_pozitif" for lab in store.labels)


def test_gecersiz_parametreler():
    with pytest.raises(ValueError):
        AnalistSimulatoru([], gecikme_gun=-1)
    with pytest.raises(ValueError):
        AnalistSimulatoru([], hata_orani=1.0)


# ---------------------------------------------------------------- Bayes kapısına bağlantı


def test_bayes_kapisi_etiketle_ogrenir(tmp_path):
    """30 Ekim ablasyonunda kapı 0 vaka elemişti: `ogren` hiçbir yerden çağrılmıyordu. Bu test o bağlantı."""
    kapi = BayesKapisi(esik=0.3, min_gozlem=5)
    oncesi = kapi.degerlendir("U1", ["UEBA-0005"])
    assert oncesi.gecti and oncesi.gozlem == 0  # gözlem yokken susturulmaz
    etiketler = [dict(karar="yanlis_pozitif", kurallar=["UEBA-0005"]) for _ in range(10)]
    assert bayes_besle(kapi, etiketler) == 10
    sonrasi = kapi.degerlendir("U1", ["UEBA-0005"])
    assert not sonrasi.gecti  # 10 yanlış pozitif → sonsal düştü, örüntü susturuldu


def test_bayes_belirsiz_karari_saymaz():
    kapi = BayesKapisi(esik=0.3, min_gozlem=1)
    assert bayes_besle(kapi, [dict(karar="belirsiz", kurallar=["R1"])]) == 0
    assert kapi.degerlendir("U1", ["R1"]).gozlem == 0


def test_bayes_gercek_pozitifle_susturmaz():
    kapi = BayesKapisi(esik=0.3, min_gozlem=5)
    bayes_besle(kapi, [dict(karar="gercek_pozitif", kurallar=["R1"]) for _ in range(10)])
    assert kapi.degerlendir("U1", ["R1"]).gecti


# ---------------------------------------------------------------- aktif öğrenme sırası


def test_belirsizlik_sirasi_en_genisi_one_alir():
    v = [
        dict(case_id="dar", belirsizlik=dict(genislik=0.05)),
        dict(case_id="genis", belirsizlik=dict(genislik=0.60)),
        dict(case_id="orta", belirsizlik=dict(genislik=0.30)),
    ]
    assert [x["case_id"] for x in belirsizlik_sirasi(v)] == ["genis", "orta", "dar"]


def test_belirsizlik_sirasi_aralksiz_vakayi_sona_atar_ama_atmaz():
    v = [dict(case_id="yok"), dict(case_id="var", belirsizlik=dict(genislik=0.1))]
    sirali = belirsizlik_sirasi(v)
    assert [x["case_id"] for x in sirali] == ["var", "yok"]
    assert len(sirali) == 2  # atılmaz: atmak kalibrasyonun hiç kurulamamasına yol açar


def test_belirsizlik_sirasi_ust_sinir():
    v = [dict(case_id=str(i), belirsizlik=dict(genislik=i / 10)) for i in range(10)]
    assert len(belirsizlik_sirasi(v, en_fazla=3)) == 3


# ---------------------------------------------------------------- kalibrasyon zamanlayıcısı


def test_zamanlayici_kapaliyken_hic_tetiklenmez():
    z = KalibrasyonZamanlayicisi(periyot_gun=0)
    assert not z.acik
    assert not z.gerekli_mi(D0, 10_000)


def test_zamanlayici_iki_sarti_birlikte_arar():
    z = KalibrasyonZamanlayicisi(periyot_gun=7, min_yeni_etiket=25)
    assert not z.gerekli_mi(D0, 10)  # etiket yetersiz
    assert z.gerekli_mi(D0, 30)  # ilk eğitim: gün şartı aranmaz
    z.kaydet(D0, 30, dict(egitildi=True, holdout_model=dict(auprc=0.4)))
    assert not z.gerekli_mi(D0 + pd.Timedelta(days=3), 80)  # gün dolmadı
    assert not z.gerekli_mi(D0 + pd.Timedelta(days=9), 40)  # yeni etiket yetersiz (40-30=10 < 25)
    assert z.gerekli_mi(D0 + pd.Timedelta(days=9), 80)  # ikisi de tamam


def test_zamanlayici_auprc_gecmisi_tutar():
    z = KalibrasyonZamanlayicisi(periyot_gun=7)
    z.kaydet(D0, 50, dict(egitildi=True, holdout_model=dict(auprc=0.30, auprc_kat=3.0)))
    z.kaydet(D0 + pd.Timedelta(days=7), 90, dict(egitildi=True, holdout_model=dict(auprc=0.45)))
    e = z.etkinlik()
    assert e["kalibrasyon_basarili"] == 2
    assert e["kalibrasyon_ilk_auprc"] == 0.30 and e["kalibrasyon_son_auprc"] == 0.45


def test_zamanlayici_basarisiz_egitimi_de_kaydeder():
    z = KalibrasyonZamanlayicisi(periyot_gun=7)
    z.kaydet(D0, 10, dict(egitildi=False, neden="yetersiz satır"))
    assert z.etkinlik()["kalibrasyon_denemesi"] == 1 and z.etkinlik()["kalibrasyon_basarili"] == 0


# ---------------------------------------------------------------- yapılandırma sözleşmesi


def test_v6a_bayraklari_varsayilanda_kapali():
    c = TenantConfig()
    assert c.geri_bildirim_dongusu is False
    assert c.pred_yeniden_egitim_gun == 0
    assert c.analist_hata_orani == 0.0


def test_etiketsiz_yeniden_egitim_reddedilir():
    with pytest.raises(ValueError, match="geri_bildirim_dongusu"):
        TenantConfig(pred_yeniden_egitim_gun=14)


def test_etiket_kaydi_yuzdeligi_saklar(tmp_path):
    """Venn-Abers kalibrasyon kümesi etiketten kurulur; skor etiketle birlikte saklanmalı."""
    store = LabelStore(tmp_path / "l.json")
    rec = store.add(_vaka("U1", D0, yuzdelik=0.77), "yanlis_pozitif", "a", reason="mesru_is_gerekcesi")
    assert rec["yuzdelik"] == 0.77
