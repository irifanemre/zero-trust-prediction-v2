"""Denetimsiz anomali kanalı — ECOD ve Isolation Forest.

Bu kanalın VAR OLMA nedeni r6.2 ölçümündeki yapısal bulgu: kaçan insider hiçbir kural tetiklemedi, graf ise
çarpan olduğu için tabanı sıfır olana ulaşamadı. Buradaki testler o tavanın gerçekten kaldırıldığını ve
kaldırılırken iki şeyin bozulmadığını doğrular: **sızıntı yok** (bugünün verisi uyuma girmez) ve
**determinizm** (aynı girdi aynı skor).
"""

import numpy as np
import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.detection.engine import Hit
from ztp.features import NUM_FEATURES
from ztp.feedback import LabelStore
from ztp.graph.knowledge import KnowledgeGraph
from ztp.scoring import RiskScorer
from ztp.unsupervised import MIN_UYUM_SATIR, AnomaliKanali, Ecod, Orman


def _normal(n: int = 400, tohum: int = 7) -> np.ndarray:
    rng = np.random.default_rng(tohum)
    return np.abs(rng.normal(10.0, 2.0, size=(n, len(NUM_FEATURES))))


def test_ecod_uc_noktayi_ustte_siralar():
    X = _normal()
    e = Ecod().uyumla(X)
    normal = X[:1].copy()
    uc = X[:1].copy()
    uc[0, :] = 1000.0  # her boyutta sağ kuyruk
    s_normal, s_uc = e.skorla(normal)[0], e.skorla(uc)[0]
    assert s_uc.skor > s_normal.skor
    assert s_uc.skor >= 0.99  # uyum dağılımının en üstünde
    assert s_uc.yon == "sag"


def test_ecod_sol_kuyrugu_da_yakalar():
    """Beklenenden AZ etkinlik de anomalidir: sessizleşen hesap (veri sızdırıp sonra susmak) bu yöne düşer."""
    X = _normal()
    e = Ecod().uyumla(X)
    sifir = np.zeros((1, len(NUM_FEATURES)))
    s = e.skorla(sifir)[0]
    assert s.skor >= 0.99
    assert s.yon in ("sol", "carpiklik")


def test_ecod_boyut_katkisi_dogru_boyutu_gosterir():
    """Açıklanabilirlik (14.6): hangi boyutun anomaliyi sürüklediği uydurulmaz, hesaplanır."""
    X = _normal()
    e = Ecod().uyumla(X)
    nokta = X[:1].copy()
    hedef = NUM_FEATURES.index("bytes_out")
    nokta[0, hedef] = 1e6
    s = e.skorla(nokta)[0]
    baskın = max(s.katkilar.items(), key=lambda kv: kv[1])[0]
    assert baskın == "bytes_out"


def test_ecod_deterministik_ve_monoton_donusume_duyarsiz():
    """Sıra tabanlı olduğu için log/ölçek dönüşümü skoru DEĞİŞTİRMEMELİ — modül dokümantasyonundaki iddia bu."""
    X = _normal()
    nokta = X[:5] * 3.0
    a = Ecod().uyumla(X).skorla(nokta)
    b = Ecod().uyumla(X).skorla(nokta)
    assert [x.skor for x in a] == [x.skor for x in b]  # determinizm
    c = Ecod().uyumla(np.log1p(X)).skorla(np.log1p(nokta))
    assert [round(x.skor, 6) for x in a] == [round(x.skor, 6) for x in c]


def test_ecod_sabit_boyut_patlatmaz():
    X = _normal()
    X[:, 0] = 5.0  # varyans 0
    e = Ecod().uyumla(X)
    s = e.skorla(X[:1])[0]
    assert 0.0 <= s.skor <= 1.0 and np.isfinite(s.ham)


def test_ecod_az_veriyle_uyumlanmaz():
    with pytest.raises(ValueError, match=str(MIN_UYUM_SATIR)):
        Ecod().uyumla(_normal(n=MIN_UYUM_SATIR - 1))


def test_orman_deterministik():
    X = _normal()
    nokta = X[:5]
    a = [s.skor for s in Orman().uyumla(X).skorla(nokta)]
    b = [s.skor for s in Orman().uyumla(X).skorla(nokta)]
    assert a == b


def test_orman_uc_noktayi_ustte_siralar():
    X = _normal()
    o = Orman().uyumla(X)
    uc = X[:1].copy()
    uc[0, :] = 1000.0
    assert o.skorla(uc)[0].skor > o.skorla(X[:1])[0].skor


def _feats(gunler: int = 40, kullanici: int = 10, tohum: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(tohum)
    satirlar = []
    bas = pd.Timestamp("2010-01-01")
    for g in range(gunler):
        for k in range(kullanici):
            r = {ad: float(abs(rng.normal(10.0, 2.0))) for ad in NUM_FEATURES}
            r.update(sid=f"U{k:03d}", day=bas + g * pd.Timedelta(days=1))
            satirlar.append(r)
    return pd.DataFrame(satirlar)


def test_kanal_bugunun_verisini_uyuma_ALMAZ():
    """Sızıntı testi — kanalın en kritik özelliği.

    Bugünün satırları uyum penceresine girerse, uç bir değer kendi dağılımını da kaydırır ve skor düşer
    (kendini normalleştirir). Pencere yarı açık olduğu için uç nokta uyumu etkilemez ve en üstte kalır.
    """
    feats = _feats()
    gun = pd.Timestamp("2010-02-05")
    bugun = feats[feats["day"] == gun].copy()
    bugun.loc[bugun.index, NUM_FEATURES] = 10_000.0  # BÜTÜN kullanıcılar uçta
    kanal = AnomaliKanali(pencere_gun=30, yenileme_gun=1)
    sonuc = kanal.gun(gun, feats[feats["day"] < gun], bugun)
    assert sonuc and all(s.skor >= 0.99 for s in sonuc.values())


def test_kanal_az_veride_skor_uretmez():
    feats = _feats(gunler=3, kullanici=5)  # 15 satır
    gun = pd.Timestamp("2010-01-03")
    kanal = AnomaliKanali()
    assert kanal.gun(gun, feats[feats["day"] < gun], feats[feats["day"] == gun]) == {}
    assert kanal.atlanan_gun == 1


def test_kanal_yenileme_araligina_uyar():
    feats = _feats(gunler=60)  # döngünün tamamı veri içinde kalmalı: veri biterse gün atlanır, uyum sayılmaz
    kanal = AnomaliKanali(pencere_gun=30, yenileme_gun=7)
    for g in range(14):
        gun = pd.Timestamp("2010-02-05") + g * pd.Timedelta(days=1)
        kanal.gun(gun, feats[feats["day"] < gun], feats[feats["day"] == gun])
    assert kanal.uyum_sayisi == 2  # 14 günde 7 günlük aralıkla iki uyum
    assert kanal.etkinlik()["anomali_tur"] == "ecod"


def test_kanal_eksik_kolonda_sessiz_dusmez():
    feats = _feats().drop(columns=["usb_count"])
    gun = pd.Timestamp("2010-02-05")
    with pytest.raises(ValueError, match="usb_count"):
        AnomaliKanali().gun(gun, feats[feats["day"] < gun], feats[feats["day"] == gun])


# ---- skorlama bağlantısı: yapısal tavanın gerçekten kalktığı burada görünür


def _hit(rule: str, day: pd.Timestamp, w: float = 10.0, sev: float = 1.0) -> Hit:
    return Hit(rule, rule, "UEBA", day, sev, w, [], [], {}, "yayinda", "", "RB", False, [])


def _scorer(tmp_path, **cfg_ek) -> RiskScorer:
    cfg = TenantConfig(llm_backend="none", sinks=[], **cfg_ek)
    return RiskScorer(cfg, KnowledgeGraph(), LabelStore(tmp_path / "l.json"))


def test_anomali_kurali_olmayan_kullaniciya_skor_URETIR(tmp_path):
    """A1 — bu testin tamamı r6.2 bulgusunun cevabıdır.

    Çarpan yolu: hiç tespiti olmayan kullanıcıda base = 0 → `1,5 × 0 = 0`, skor sıfır kalır.
    Toplamsal yol: aynı kullanıcı anomali skoruyla sıfırın üstüne çıkar.
    """
    gun = pd.Timestamp("2010-06-01")
    sinyal = dict(graf_riski=1.0, anomali_skoru=0.99)
    carpan = _scorer(tmp_path, graf_enabled=True, graf_agirligi=0.5).compute("U1", gun, sinyal)
    assert carpan.raw == 0.0  # yapısal tavan: çarpan tabanı sıfır olana ulaşamaz
    toplamsal = _scorer(tmp_path, graf_enabled=True, graf_toplamsal_agirlik=0.5).compute("U1", gun, sinyal)
    assert toplamsal.raw == pytest.approx(0.5 * 1.0 * 10.0)
    assert "GRAF-TOPLAMSAL" in toplamsal.contributions
    anomali = _scorer(tmp_path, anomali_enabled=True, anomali_agirligi=0.5).compute("U1", gun, sinyal)
    assert anomali.raw == pytest.approx(0.5 * 0.99 * 10.0)
    assert "ANOMALI-DENETIMSIZ" in anomali.contributions


def test_toplamsal_terimler_carpanla_olceklenmez(tmp_path):
    """Toplamsal terim çarpanların ARDINDAN eklenir: `ayrilik_bildirimi` çarpanı onu büyütmemeli."""
    gun = pd.Timestamp("2010-06-01")
    s = _scorer(tmp_path, anomali_enabled=True, anomali_agirligi=0.5)
    s.add_hits("U1", [_hit("UEBA-0001", gun)])
    sade = s.compute("U1", gun, dict(anomali_skoru=1.0))
    s2 = _scorer(tmp_path, anomali_enabled=True, anomali_agirligi=0.5)
    s2.add_hits("U1", [_hit("UEBA-0001", gun)])
    carpanli = s2.compute("U1", gun, dict(anomali_skoru=1.0, ayrilik_bildirimi=1))
    # base 10 → çarpanlı 18; toplamsal terim ikisinde de aynı 5
    assert sade.raw == pytest.approx(10.0 + 5.0)
    assert carpanli.raw == pytest.approx(10.0 * 1.8 + 5.0)


def test_varsayilan_yapilandirmada_hicbir_sey_eklenmez(tmp_path):
    """v5 sözleşmesi: bayraklar kapalıyken skor v4 ile birebir aynı."""
    gun = pd.Timestamp("2010-06-01")
    s = _scorer(tmp_path)
    s.add_hits("U1", [_hit("UEBA-0001", gun)])
    r = s.compute("U1", gun, dict(graf_riski=1.0, anomali_skoru=1.0))
    assert r.raw == pytest.approx(10.0)
    assert r.anomali == 1.0  # sinyal taşınır ama skora girmez
    assert not {"GRAF-TOPLAMSAL", "ANOMALI-DENETIMSIZ"} & set(r.contributions)


def test_anomali_dogrulama_kapisi_ayri_anahtar(tmp_path):
    """Toplamsal skor tek başına v2 doğrulama kapısını geçmez; geçmesi için ayrı anahtar gerekir."""
    gun = pd.Timestamp("2010-06-01")
    kapali = _scorer(tmp_path, anomali_enabled=True, anomali_agirligi=0.5)
    r = kapali.compute("U1", gun, dict(anomali_skoru=0.999))
    assert not kapali.corroborated(r)  # tek sinyal, kural yok, çarpan yok → izleme listesi
    acik = _scorer(tmp_path, anomali_enabled=True, anomali_agirligi=0.5, anomali_dogrulama_esigi=0.995)
    assert acik.corroborated(acik.compute("U1", gun, dict(anomali_skoru=0.999)))
    assert not acik.corroborated(acik.compute("U1", gun, dict(anomali_skoru=0.99)))


def test_agirlik_acikken_enabled_zorunlu():
    with pytest.raises(ValueError, match="anomali_enabled"):
        TenantConfig(anomali_agirligi=0.5)
    with pytest.raises(ValueError, match="graf_enabled"):
        TenantConfig(graf_toplamsal_agirlik=0.5)
