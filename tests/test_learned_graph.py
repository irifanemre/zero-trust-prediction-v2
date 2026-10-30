"""Öğrenen graf gömme — sprint v6 katman C.

Üç şey bağlanır: **sızıntı bariyeri** (bugünün kenarları skorlamadan sonra geçmişe girer), **bilinmeyene
skor üretmeme** (uydurulmuş skor, skorun olmamasından kötüdür) ve **determinizm** (aynı kenarlar aynı
ağırlıkları verir — dondurma protokolünün gereği).

`[ml]` eklentisi kurulu değilse modül atlanır: çekirdek torch'suz çalışmaya devam eder.
"""

import pandas as pd
import pytest

torch = pytest.importorskip("torch", reason="v6-C torch gerektirir ([ml] eklentisi)")

from ztp.config import TenantConfig  # noqa: E402
from ztp.gnn.learned import MIN_KENAR, MIN_KULLANICI, GrafGommeModeli, TemporalGrafOgrenen  # noqa: E402

D0 = pd.Timestamp("2010-06-01")


def _bolumlu_kenarlar(kullanici: int = 60, kaynak: int = 12, bolum: int = 3):
    """Her kullanıcı yalnız kendi bölümünün kaynaklarına dokunuyor — öğrenilecek net bir yapı."""
    return [(f"U{u:02d}", f"D{u % bolum}-K{k:02d}") for u in range(kullanici) for k in range(kaynak)]


# ---------------------------------------------------------------- öğrenme


def test_kendi_bolumu_yabanci_bolumden_daha_az_sasirtici():
    """Katmanın var olma sebebi: başka ekiplerin kaynaklarına yaklaşmak yakalanmalı."""
    m = GrafGommeModeli(boyut=16, devir=150)
    assert m.egit(_bolumlu_kenarlar())
    kendi = m.skorla("U00", ["D0-K03"])
    yabanci = m.skorla("U00", ["D1-K03"])
    assert yabanci > kendi
    assert yabanci - kendi > 0.1  # fark gürültü değil


def test_en_sasirtici_erisim_belirler_skoru():
    """Ortalama değil en uç: tek bir beklenmedik erişim ortalamada kaybolmamalı."""
    m = GrafGommeModeli(boyut=16, devir=150).egit(_bolumlu_kenarlar()) or GrafGommeModeli(boyut=16, devir=150)
    m = GrafGommeModeli(boyut=16, devir=150)
    m.egit(_bolumlu_kenarlar())
    tanidik = [f"D0-K{k:02d}" for k in range(5)]
    assert m.skorla("U00", tanidik + ["D2-K07"]) > m.skorla("U00", tanidik)


def test_az_veriyle_egitilmez():
    m = GrafGommeModeli()
    assert not m.egit([("U1", "K1")] * 10)  # kenar yetersiz
    assert not m.hazir
    az_kullanici = [(f"U{u}", f"K{k}") for u in range(MIN_KULLANICI - 5) for k in range(60)]
    assert len(az_kullanici) >= MIN_KENAR  # kenar yeterli ama kullanıcı değil
    assert not GrafGommeModeli().egit(az_kullanici)


def test_bilinmeyene_skor_uretilmez():
    """Uydurulmuş skor, kuyruğa sahte sinyalle girilmesine yol açar."""
    m = GrafGommeModeli(boyut=16, devir=40)
    m.egit(_bolumlu_kenarlar())
    assert m.skorla("HIC_GORULMEDI", ["D0-K01"]) is None
    assert m.skorla("U00", ["BILINMEYEN_HEDEF"]) is None
    assert m.skorla("U00", []) is None


def test_egitilmemis_model_skor_uretmez():
    assert GrafGommeModeli().skorla("U00", ["K1"]) is None


def test_deterministik_agirlik():
    """Aynı kenarlar aynı ağırlıkları vermeli — ağırlık sha256'sı koşu kaydına yazılıyor (21.2)."""
    k = _bolumlu_kenarlar()
    a, b = GrafGommeModeli(boyut=16, devir=30), GrafGommeModeli(boyut=16, devir=30)
    a.egit(k)
    b.egit(list(reversed(k)))  # kenar sırası değişti, küme aynı
    assert a.agirlik_ozeti() == b.agirlik_ozeti()
    assert a.skorla("U00", ["D1-K03"]) == b.skorla("U00", ["D1-K03"])


def test_varsayilan_cihaz_cpu():
    """MPS'te `index_add_` kayan nokta toplamasını sırasız yapar ve ağırlık özeti değişir — ölçüldü.
    Dondurma protokolü yeniden üretilebilirlik istediği için varsayılan CPU'dur; MPS açıkça seçilir."""
    assert GrafGommeModeli().cihaz == "cpu"


@pytest.mark.skipif(not torch.backends.mps.is_available(), reason="MPS yok")
def test_mps_acikca_secilebilir_ve_rapora_girer():
    m = GrafGommeModeli(boyut=16, devir=5, cihaz="mps")
    m.egit(_bolumlu_kenarlar())
    assert m.etkinlik()["graf_ogrenen_cihaz"] == "mps"  # gizli hızlandırma olmaz, kayda geçer


def test_gecersiz_parametreler():
    with pytest.raises(ValueError):
        GrafGommeModeli(boyut=2)
    with pytest.raises(ValueError):
        GrafGommeModeli(negatif=0)


def test_etkinlik_agirlik_ozetini_tasir():
    m = GrafGommeModeli(boyut=16, devir=20)
    m.egit(_bolumlu_kenarlar())
    e = m.etkinlik()
    assert e["graf_ogrenen_egitim"] == 1
    assert e["graf_ogrenen_agirlik_sha256"] and len(e["graf_ogrenen_agirlik_sha256"]) == 64


# ---------------------------------------------------------------- sızıntı bariyeri


def test_bugunun_kenarlari_skorlamadan_sonra_gecmise_girer():
    """En kritik test: model bugünü skorlarken bugünü görmemiş olmalı."""
    t = TemporalGrafOgrenen(GrafGommeModeli(boyut=16, devir=30), egitim_periyodu_gun=1, gecmis_gun=30)
    kenarlar = _bolumlu_kenarlar()
    gunluk = {}
    for u, h in kenarlar:
        gunluk.setdefault(u, []).append(h)
    for g in range(3):  # geçmiş birikir, model eğitilir
        t.gun(D0 + pd.Timedelta(days=g), gunluk)
    # YENI kullanıcı ilk kez bugün görünüyor: model onu tanımadığı için skor üretilmemeli
    skorlar = t.gun(D0 + pd.Timedelta(days=3), {**gunluk, "YENI": ["D0-K01"]})
    assert "YENI" not in skorlar
    # ertesi gün artık geçmişte: yine de model o günden sonra eğitilene dek tanınmaz
    assert any(u == "YENI" for _, u, _ in t._kenarlar)


def test_egitim_periyoduna_uyar():
    t = TemporalGrafOgrenen(GrafGommeModeli(boyut=16, devir=10), egitim_periyodu_gun=5, gecmis_gun=30)
    gunluk = {}
    for u, h in _bolumlu_kenarlar():
        gunluk.setdefault(u, []).append(h)
    for g in range(11):
        t.gun(D0 + pd.Timedelta(days=g), gunluk)
    # 0. günde geçmiş BOŞ olduğu için eğitilemez — sızıntı bariyerinin doğrudan sonucu.
    # Eğitim 1. ve 6. günlerde olur; 11. gün döngünün dışında kalır.
    assert t.model.egitim == 2


def test_kirpma_bellegi_sinirlar():
    """r6.2'de 51M kenar görüldü; pencere dışı kenarlar bellekte durmamalı."""
    t = TemporalGrafOgrenen(GrafGommeModeli(boyut=16, devir=5), egitim_periyodu_gun=30, gecmis_gun=5)
    gunluk = {}
    for u, h in _bolumlu_kenarlar():
        gunluk.setdefault(u, []).append(h)
    for g in range(40):
        t.gun(D0 + pd.Timedelta(days=g), gunluk)
    assert len(t._kenarlar) < 40 * len(_bolumlu_kenarlar())


def test_etkinlik_skorlanan_ve_atlanani_ayirir():
    t = TemporalGrafOgrenen(GrafGommeModeli(boyut=16, devir=20), egitim_periyodu_gun=1, gecmis_gun=30)
    gunluk = {}
    for u, h in _bolumlu_kenarlar():
        gunluk.setdefault(u, []).append(h)
    t.gun(D0, gunluk)
    t.gun(D0 + pd.Timedelta(days=1), {**gunluk, "YENI": ["D0-K01"]})
    e = t.etkinlik()
    assert e["graf_ogrenen_skorlanan"] > 0 and e["graf_ogrenen_atlanan"] > 0


# ---------------------------------------------------------------- skorlama bağlantısı


def test_skora_toplamsal_girer_ve_varsayilanda_kapali(tmp_path):
    from ztp.feedback import LabelStore
    from ztp.graph.knowledge import KnowledgeGraph
    from ztp.scoring import RiskScorer

    gun = pd.Timestamp("2010-06-01")
    sinyal = dict(graf_ogrenen_sasirticilik=0.8)
    kapali = RiskScorer(TenantConfig(), KnowledgeGraph(), LabelStore(tmp_path / "a.json"))
    assert kapali.compute("U1", gun, sinyal).raw == 0.0
    acik = RiskScorer(
        TenantConfig(graf_ogrenen_enabled=True, graf_ogrenen_agirligi=0.5),
        KnowledgeGraph(),
        LabelStore(tmp_path / "b.json"),
    )
    r = acik.compute("U1", gun, sinyal)
    assert r.raw == pytest.approx(0.5 * 0.8 * 10.0)  # kural tetiklenmeden skor üretildi
    assert "GRAF-OGRENEN" in r.contributions


def test_v6c_varsayilanda_kapali():
    c = TenantConfig()
    assert c.graf_ogrenen_enabled is False and c.graf_ogrenen_agirligi == 0.0
