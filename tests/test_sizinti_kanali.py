"""Sızıntı kanalı sayacının ayrılması — sprint v6 katman D.

Düzeltilen hata: `sensitive_app_count` beş sızıntı kanalını iş arama ve saldırı araçlarıyla AYNI
sayaçta topluyordu. İş aramayı yoğun yapan bir kullanıcının gerçek bulut yüklemesi, kendi tarama
tabanına gömülüyordu — yani **niyet sinyali yöntem sinyalini maskeliyordu**.

CERT r6.2'de kaçan S5-MBG3183'te ölçüldü: havuzlanmış taban 11,99 olay/gün, bulut tabanı 0,098/gün.
Olay günündeki 4 bulut olayı havuz sayacında p = 0,347 (hiç anormal değil), ayrı sayaçta p = 0,0134.
"""

import numpy as np
import pandas as pd
import pytest

from ztp.features import extract_features
from ztp.schema import CLOUD_APPS, EVENT_COLUMNS, OCSF_HTTP, SENSITIVE_APPS
from ztp.stats import negbin_sf

D0 = pd.Timestamp("2010-06-01 09:00:00")


def _ev(sid: str, gun_ofseti: int, app: str, n: int = 1) -> pd.DataFrame:
    t = D0 + pd.Timedelta(days=gun_ofseti)
    satirlar = []
    for i in range(n):
        r = dict.fromkeys(EVENT_COLUMNS)
        r.update(
            event_id=f"e-{sid}-{gun_ofseti}-{app}-{i}",
            time=t + pd.Timedelta(minutes=i),
            received_time=t + pd.Timedelta(minutes=i),
            class_uid=OCSF_HTTP,
            source="proxy",
            actor_raw=sid,
            app=app,
            category=app,
            action="http",
            outcome="success",
            bytes_out=0,
        )
        r["canonical"], r["is_service"] = sid, False
        satirlar.append(r)
    return pd.DataFrame(satirlar)


# ---------------------------------------------------------------- kategori kümeleri


def test_bulut_kumesi_havuzun_alt_kumesi():
    assert CLOUD_APPS < SENSITIVE_APPS
    assert "job_search" in SENSITIVE_APPS and "job_search" not in CLOUD_APPS
    assert "hacking_tools" in SENSITIVE_APPS and "hacking_tools" not in CLOUD_APPS
    assert "cloud_storage" in CLOUD_APPS


# ---------------------------------------------------------------- sayaç ayrımı


def test_iki_sayac_ayri_sayiyor():
    ev = pd.concat([_ev("U1", 0, "job_search", 10), _ev("U1", 0, "cloud_storage", 3)], ignore_index=True)
    f = extract_features(ev, critical_assets=())
    assert int(f["sensitive_app_count"].iloc[0]) == 13  # havuz ikisini de sayar
    assert int(f["cloud_app_count"].iloc[0]) == 3  # yeni sayaç yalnız kanalı


def test_yalniz_is_arama_bulut_sayacini_arttirmaz():
    f = extract_features(_ev("U1", 0, "job_search", 20), critical_assets=())
    assert int(f["sensitive_app_count"].iloc[0]) == 20
    assert int(f["cloud_app_count"].iloc[0]) == 0


def test_olaysiz_gun_nan_birakmaz():
    """groupby.size() olaysız günde NaN üretir; int() dönüşümü patlardı (fillna zorunlu)."""
    f = extract_features(_ev("U1", 0, "social", 5), critical_assets=())
    assert int(f["cloud_app_count"].iloc[0]) == 0
    assert not f["cloud_app_count"].isna().any()


def test_butun_bulut_kategorileri_sayilir():
    ev = pd.concat([_ev("U1", 0, k, 2) for k in sorted(CLOUD_APPS)], ignore_index=True)
    f = extract_features(ev, critical_assets=())
    assert int(f["cloud_app_count"].iloc[0]) == 2 * len(CLOUD_APPS)


# ---------------------------------------------------------------- maskelemenin kendisi


def test_havuzlanmis_sayac_seyrek_kanali_maskeler():
    """Katman D'nin varlık sebebi. MBG3183'ün gerçek rakamlarıyla.

    Havuz tabanı 5,75/gün (çoğu iş araması), bulut tabanı 0,075/gün. Olay haftasında havuzda 45
    olay (beklenen 40) → sıradan; bulutta 4 olay (beklenen 0,52) → iki kat daha anlamlı.
    """
    havuz_p = negbin_sf(45, 7 * 5.751, 7 * 29.04)
    bulut_p = negbin_sf(4, 7 * 0.0747, 7 * 0.1123)
    assert havuz_p > 0.3  # havuzda hiç anormal görünmüyor
    assert bulut_p < 0.02  # ayrı sayaçta kuralın eşiğini geçiyor
    assert bulut_p < havuz_p / 20  # ayrım en az yirmi kat anlamlılık kazandırıyor


def test_seyrek_sayacta_sert_esik_yapisal_olarak_zor():
    """Sapma 3'ün gerekçesi: aynı p değeri, taban yoğunluğuna göre farklı şiddette anomali ister."""
    seyrek = lambda n: negbin_sf(n, 7 * 0.0747, 7 * 0.1123)
    yogun = lambda n: negbin_sf(n, 7 * 5.751, 7 * 29.04)
    # seyrek kanalda p<0,001 için ~8 olay (15 kat sıçrama) gerekir
    assert seyrek(4) > 0.001 and seyrek(8) < 0.001
    # yoğun sayaçta aynı eşik ~2,5 kat sıçramayla geçilir
    assert yogun(100) < 0.001 and 100 / (7 * 5.751) < 3


# ---------------------------------------------------------------- kural sözleşmesi


def test_ueba_0022_golge_modda_dogdu():
    from ztp.detection.catalog import load_catalog

    r = next(x for x in load_catalog() if x["id"] == "UEBA-0022")
    assert r["durum"] == "golge-modda"  # 13.6: yeni kural doğrudan yayına girmez
    assert r["agirlik"] == 6
    assert r["mantik"]["kosullar"] == ["bulut_7g_toplam >= 3", "bulut_7g_p < 0.02"]
    assert r["veri_kaynaklari"] == ["proxy"]


def test_ueba_0021_degismedi():
    """Katman D yeni bir sayaç EKLER; havuzlanmış kural olduğu gibi kalır."""
    from ztp.detection.catalog import load_catalog

    r = next(x for x in load_catalog() if x["id"] == "UEBA-0021")
    assert r["mantik"]["kosullar"] == ["hassas_7g_toplam >= 5", "hassas_7g_p < 0.001"]
    assert r["agirlik"] == 4


def test_kural_test_senaryolari_tutarli():
    """Kuralın kendi test senaryoları, yazılı eşiklerle uyumlu olmalı."""
    from ztp.detection.catalog import load_catalog
    from ztp.detection.expr import SafeExpr, _Signals

    r = next(x for x in load_catalog() if x["id"] == "UEBA-0022")
    for ts in r["test_senaryolari"]:
        sinyal = _Signals(ts["sinyaller"])
        # jitter 0: test senaryosu kesin eşikle sınanır (21.2 rastgeleleştirmesi üretimde devrede)
        sonuc = all(
            bool(eval(SafeExpr(k).compile(0.0, ""), {"__builtins__": {}}, sinyal)) for k in r["mantik"]["kosullar"]
        )
        assert sonuc is ts["beklenen"], f"{ts['ad']}: beklenen {ts['beklenen']}, çıkan {sonuc}"
