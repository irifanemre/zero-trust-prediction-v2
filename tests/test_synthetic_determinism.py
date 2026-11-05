"""Sentetik regresyon koşu tarihine bağlı değil: varsayılan bitiş günü sabit ve S8 sonucu olay gününün haftanın hangi gününe
denk geldiğinden bağımsız (önceden S8 dönüşü hafta sonuna düşünce haftalık mevsimsellik enjeksiyonu zayıflatıyor, senaryo
yalnızca bazı tarihlerde KALIYORDU)."""

import json

import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.data.synthetic import SYNTHETIC_DEFAULT_END, SyntheticOrg
from ztp.detection.catalog import load_catalog
from ztp.pipeline import ZeroTrustPredictionPipeline

EVAL_DAYS, WARMUP = 6, 10


def test_default_end_day_is_fixed_not_today():
    org = SyntheticOrg(n_users=30, n_days=40, eval_days=5)
    assert org.end_day == SYNTHETIC_DEFAULT_END
    a = SyntheticOrg(n_users=30, n_days=40, eval_days=5, seed=3).build()
    b = SyntheticOrg(n_users=30, n_days=40, eval_days=5, seed=3).build()
    pd.testing.assert_frame_equal(a.events, b.events)


def _s8_day(end: pd.Timestamp) -> pd.Timestamp:
    n_days = 90 + WARMUP + EVAL_DAYS
    org = SyntheticOrg(n_users=40, n_days=n_days, eval_days=EVAL_DAYS, end_day=end, seed=7)
    return org.day0 + pd.Timedelta(days=org.E0 + 3)


# 7 ardışık bitiş günü → S8 olay günü haftanın 7 gününün her birine bir kez düşer
ENDS = [pd.Timestamp("2026-09-14") + pd.Timedelta(days=i) for i in range(7)]


def test_s8_days_cover_every_weekday():
    assert sorted(_s8_day(e).dayofweek for e in ENDS) == list(range(7))


@pytest.mark.slow
@pytest.mark.parametrize("end", ENDS, ids=lambda e: _s8_day(e).day_name())
def test_s8_result_independent_of_run_date(tmp_path, end):
    cfg = TenantConfig(tenant_id="t", alarm_budget_per_day=6, threshold_jitter=0.0)
    data = SyntheticOrg(n_users=40, n_days=90 + WARMUP + EVAL_DAYS, eval_days=EVAL_DAYS, end_day=end, seed=7).build()
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), tmp_path)
    pipe.run(end - pd.Timedelta(days=EVAL_DAYS - 1), end, warmup_days=WARMUP)
    cov = json.loads((tmp_path / "t" / "coverage_report.json").read_text(encoding="utf-8"))
    s8 = next(c for c in cov if c["senaryo"].startswith("S8"))
    s9 = next(c for c in cov if c["senaryo"].startswith("S9"))
    assert s8["sonuc"] == "GEÇTİ", s8
    assert "PRED-0013" in s8["gercek_sonuc"]
    assert s9["sonuc"].startswith("GEÇTİ"), s9  # negatif kontrol de güne bağlı olarak yanlış pozitife dönmemeli


def test_senaryo_kapsamasi_uzun_pencerede_UYARIR():
    """Test aracının bilinen sınırı sessizce tuzağa düşülemez olmalı.

    Ölçülmüş kusur (`docs/faz-c2-sonuclar.md`): senaryo olay günleri pencere uzunluğundan BAĞIMSIZ,
    `E0+2 … E0+22` aralığında sabit bir bant. Pencere uzadıkça bant başa sıkışıyor:

    | pencere | 1 günlük ufukta değerlendirme pozitifi |
    |---|---|
    | 24 gün | 54 |
    | 40 gün | 11 |
    | 60 gün | **0** |

    Faz C-2a'da 14 günlük ufuk tam bu yüzden ölçülemedi ve ön kayıttaki çözüm ("pencereyi büyüt")
    sorunu BÜYÜTTÜ. Kusur düzeltilmedi — senaryo zamanlamasını değiştirmek üretecin tanımlarını
    yeniden düzenlemek demek ve her sentetik kapsama rakamı ona dayanıyor. Bunun yerine sınır
    ölçülebilir ve uyarılabilir hâle getirildi.

    Bu test, uyarının çalıştığını ve kısa pencerede yanlış alarm vermediğini bağlar.
    """
    import pandas as pd

    from ztp.config import TenantConfig
    from ztp.data.synthetic import SyntheticOrg

    uzun = TenantConfig().long_window_days
    end = pd.Timestamp("2026-09-16")

    kisa = SyntheticOrg(n_users=20, n_days=uzun + 34, eval_days=24, end_day=end, seed=7)
    kisa.build()
    k = kisa.senaryo_kapsamasi()
    assert k["uyari"] is None, "kısa pencerede yanlış alarm olmamalı"
    assert k["kapsama_orani"] > 0.9

    uzun_pencere = SyntheticOrg(n_users=20, n_days=uzun + 70, eval_days=60, end_day=end, seed=7)
    uzun_pencere.build()
    u = uzun_pencere.senaryo_kapsamasi()
    assert u["uyari"] is not None and "YANILTICI" in u["uyari"]
    assert u["kapsama_orani"] < 0.5, "60 günlük pencerede senaryolar ilk yarıda bile değil"
    # bant uzunluğu pencereden BAĞIMSIZ: kusurun tanımı bu
    assert (u["son_olay"] - u["ilk_olay"]) == (k["son_olay"] - k["ilk_olay"])
