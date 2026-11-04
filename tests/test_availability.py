"""Şema farkındalığı — "desen görülmedi" ile "bakılamadı" ayrımı.

Faz A-1 (şema profilleyici) eksiği RAPOR ediyordu ama hiçbir kararı değiştirmiyordu. Bu katman
raporu karara bağlar: koşullarındaki tüm veri bağımlı sinyaller üretilemeyen kural değerlendirilmez
ve `sinanamaz` sayılır; beklenen tespitlerinin hepsi böyle olan senaryo `ÖLÇÜLEMEDİ` işaretlenir.

Ölçülmüş gerekçe: r6.2'de `UEBA-0003` (ağırlık 8) `bytes_out = 0` yüzünden ölüydü ve kapsama raporu
onu "bu veride desen görülmedi" diye gösterdi. 3/4 yakalama rakamı, aslında 3/3 ölçülebilir + 1
ölçülemeyen senaryoydu. Yanlış bir rakama güvenmek, düşük bir rakamı bilmekten pahalıdır.
"""

from typing import Tuple

import pandas as pd
import pytest

from ztp.availability import (
    SINYAL_TUREV,
    KuralDurumu,
    MevcudiyetHaritasi,
    kosul_sinyalleri,
    kural_mevcudiyeti,
    senaryo_olculebilirligi,
)
from ztp.config import TenantConfig
from ztp.detection.catalog import load_catalog
from ztp.detection.engine import DetectionEngine
from ztp.schema_profiler import TUREV_BAGIMLILIK, AlanDurumu, OzellikHaritasi

TUM_ALANLAR = ("bytes_out", "source", "action", "resource", "process", "cmdline", "app", "time", "outcome")


def _harita(**ezilen: str) -> OzellikHaritasi:
    """Her alanı kullanılabilir bir harita; `ezilen` ile tek tek bozulur ("bos" / "sabit" / "yok")."""
    h = OzellikHaritasi("test")
    for a in TUM_ALANLAR:
        d = ezilen.get(a)
        if d == "yok":
            h.alanlar[a] = AlanDurumu(a, var=False)
        elif d == "bos":
            h.alanlar[a] = AlanDurumu(a, var=True, doluluk=0.0, tekil=1)
        elif d == "sabit":
            h.alanlar[a] = AlanDurumu(a, var=True, doluluk=1.0, tekil=1)
        else:
            h.alanlar[a] = AlanDurumu(a, var=True, doluluk=0.9, tekil=9)
    return h


# ---------------------------------------------------------------- koşul ayrıştırma


def test_kosuldaki_sinyaller():
    assert kosul_sinyalleri("veri_hacmi_z > 3.5") == {"veri_hacmi_z"}
    assert kosul_sinyalleri("a > 1 and b < 2 or c == 3") == {"a", "b", "c"}
    assert kosul_sinyalleri("") == set()


def test_bozuk_kosul_cokmez_ve_bos_doner():
    """Ayrıştırılamayan koşul sessizce kural öldürmesin: boş küme → veri bağımlı sinyal yok → canlı."""
    assert kosul_sinyalleri("bu ( bozuk") == set()


# ---------------------------------------------------------------- asıl hata: r6.2


def test_r62_deseni_bytes_out_bos_UEBA0003_olur():
    """Ölçülmüş hatanın yeniden üretimi: `bytes_out` boşsa hacim kuralı SINANAMAZ."""
    katalog = [dict(id="UEBA-0003", mantik=dict(kosullar=["veri_hacmi_z > 3.5"]))]
    m = kural_mevcudiyeti(katalog, _harita(bytes_out="bos"))
    assert not m.degerlendirilebilir("UEBA-0003")
    assert m.olu == {"UEBA-0003"}
    assert "veri_hacmi_z" in m.neden("UEBA-0003") and "bytes_out" in m.neden("UEBA-0003")


def test_r42_deseni_bytes_out_dolu_UEBA0003_canli():
    katalog = [dict(id="UEBA-0003", mantik=dict(kosullar=["veri_hacmi_z > 3.5"]))]
    m = kural_mevcudiyeti(katalog, _harita())
    assert m.degerlendirilebilir("UEBA-0003") and m.olu == frozenset()


# ---------------------------------------------------------------- aşırı kapatmama


def test_kismen_olu_kural_CALISMAYA_DEVAM_EDER():
    """`or`'lu kuralda bir kol ölse bile diğeri tetikleyebilir — fazla agresif kapatmak tespit susturur.

    `UEBA-0017`'nin gerçek deseni: iki Poisson kolu ulaşılamaz olsa bile `usb_ilk_kez` tetikliyor.
    """
    katalog = [dict(id="K", mantik=dict(kosullar=["veri_hacmi_z > 3 or usb_sayisi > 2"]))]
    m = kural_mevcudiyeti(katalog, _harita(bytes_out="bos"))
    assert m.degerlendirilebilir("K"), "tek sinyal ölünce kural kapatılmamalı"
    assert m.kurallar["K"].eksik_sinyaller == ("veri_hacmi_z",)  # yine de kayda geçer


def test_veri_bagimsiz_kural_hic_etkilenmez():
    """Risk serisinden türeyen kural (PRED-*) ham şemaya dayanmaz: her alan boş olsa bile canlı."""
    katalog = [dict(id="PRED-0011", mantik=dict(kosullar=["risk_ewma_kisa > 0.6 and risk_egim_7g > 0"]))]
    m = kural_mevcudiyeti(katalog, _harita(**{a: "bos" for a in TUM_ALANLAR}))
    assert m.degerlendirilebilir("PRED-0011")


def test_bilinmeyen_kural_engellenmez():
    assert MevcudiyetHaritasi("t").degerlendirilebilir("HIC-YOK-0099")


def test_kosulsuz_kural_canli():
    m = kural_mevcudiyeti([dict(id="K", mantik=dict(kosullar=[]))], _harita(**{a: "bos" for a in TUM_ALANLAR}))
    assert m.degerlendirilebilir("K")


# ---------------------------------------------------------------- senaryo ölçülebilirliği


def test_senaryo_olculebilirlik_durumlari():
    m = MevcudiyetHaritasi("t")
    m.kurallar = {
        "A": KuralDurumu("A", False, ("x",), ("bytes_out",)),
        "B": KuralDurumu("B", True),
    }
    assert senaryo_olculebilirligi(["A"], m) == "olculemez"
    assert senaryo_olculebilirligi(["A", "B"], m) == "kismi"
    assert senaryo_olculebilirligi(["B"], m) == "olculebilir"
    assert senaryo_olculebilirligi([], m) == "olculebilir"  # beklenen tespit yoksa karar verilmez


# ---------------------------------------------------------------- harita tutarlılığı


def test_turev_zinciri_uretim_koduyla_tutarli():
    """Zincirin KENDİSİ denetlenir: türev özelliğin dayandığı alan, onu üreten satırda geçmeli.

    Bu test ölçülmüş bir hatadan doğdu. `files_accessed` ilk sürümde `resource`'a bağlanmıştı ama
    `features.py` dosya OLAYLARINI sayar (`source == "file_server"`); CERT dosya adı saklamadığı
    için (20.1) r4.2'de `UEBA-0007`'nin dosya sinyalleri yanlışlıkla "şemadan ölü" görünüyordu.
    Yani bu fazın yakalamak için yazıldığı hatanın aynısı, fazın kendi haritasında vardı.
    """
    import pathlib
    import re

    kok = pathlib.Path(__file__).resolve().parents[1] / "src/ztp"
    kaynak = "".join((kok / ad).read_text(encoding="utf-8") for ad in ("features.py", "prediction.py"))
    for turev, bagimlilik in TUREV_BAGIMLILIK.items():
        satirlar = [s for s in kaynak.splitlines() if re.search(rf'["\[]{re.escape(turev)}["\]]', s)]
        if not satirlar:
            continue  # ara alan (ör. `devices`, `logon_hour`) tek satırda üretilmez — aşağıdaki test kapsar
        birlesik = " ".join(satirlar)
        for alan in bagimlilik:
            if alan in ("source", "time"):
                continue  # her olayda var; üretim satırında adı geçmeden dolaylı kullanılır
            assert alan in birlesik or alan in kaynak, f"{turev} → `{alan}` üretim kodunda görünmüyor"


def test_her_sinyal_bilinen_bir_turev_gosterir():
    """Yazım hatası sessizce "üretilebilir" demesin: `turev_uretilebilir` bilinmeyene True döner."""
    for sinyal, turev in SINYAL_TUREV.items():
        assert turev in TUREV_BAGIMLILIK, f"{sinyal} → bilinmeyen türev {turev}"


def test_haritadaki_sinyaller_gercekten_uretiliyor():
    """Harita gerçek sinyal adları içermeli; uydurma ad hiçbir kuralı etkilemez ve sessizce bayatlar.

    Veri bağımlı sinyalleri iki modül üretir: günlük profil ve 7/14 günlük tahmin penceresi. Graf,
    denetimsiz kanal ve dizin sinyalleri bilerek haritada DEĞİLDİR (modül başlığındaki tablo).
    """
    import pathlib

    kok = pathlib.Path(__file__).resolve().parents[1] / "src/ztp"
    kaynak = "".join((kok / ad).read_text(encoding="utf-8") for ad in ("profile.py", "prediction.py"))
    eksik = [s for s in SINYAL_TUREV if s not in kaynak]
    assert not eksik, f"profile.py/prediction.py bu sinyalleri üretmiyor: {eksik}"


def test_yayindaki_katalog_tam_semada_hic_olu_kural_vermez():
    """Sözleşme: her alan doluyken hiçbir kural şemadan ölü sayılmamalı — yoksa mekanizma yanlış pozitif üretir."""
    m = kural_mevcudiyeti(load_catalog(), _harita())
    assert m.olu == frozenset(), f"tam şemada ölü ilan edilen kural: {sorted(m.olu)}"


# ---------------------------------------------------------------- motor entegrasyonu


def _cfg(**kw) -> TenantConfig:
    return TenantConfig(tenant_id="t", pseudonym_secret="s", **kw)


def test_bayrak_KAPALI_motor_birebir_eski_davranis():
    """Ön kayıt ölçütü 1: bayrak kapalıyken harita hiç okunmaz."""
    katalog = load_catalog()
    m = kural_mevcudiyeti(katalog, _harita(bytes_out="bos", app="bos"))
    assert m.olu, "test anlamsız olurdu: harita ölü kural içermeli"
    kapali = DetectionEngine(_cfg(), katalog, mevcudiyet=m)
    referans = DetectionEngine(_cfg(), katalog)
    assert kapali.sema_olu == {} and kapali.mevcudiyet is None
    assert [r["id"] for r in kapali.rules] == [r["id"] for r in referans.rules]


def test_bayrak_ACIK_olu_kural_degerlendirilmez_ama_SAYILIR():
    katalog = load_catalog()
    m = kural_mevcudiyeti(katalog, _harita(bytes_out="bos"))
    e = DetectionEngine(_cfg(sema_farkindaligi=True), katalog, mevcudiyet=m)
    assert m.olu, "harita ölü kural içermeli"
    assert e.sema_olu, "en az bir kural şemadan ölü sayılmalı"
    for rid in m.olu:
        assert rid not in [r["id"] for r in e.rules], f"{rid} hâlâ değerlendiriliyor"
        # Öncelik: "kaynak yok" müşteri kurulumudur ve ÖNCE bakılır; o kurala şema damgası vurulmaz.
        assert (rid in e.sema_olu) ^ (rid in e.disabled), f"{rid} iki sebeple birden sayılıyor"
    for rid, neden in e.sema_olu.items():
        assert "şema" in neden and rid not in e.disabled


def test_bayrak_ACIK_ama_harita_YOK_degisiklik_olmaz():
    """Bayrak açık + harita verilmemiş (ör. şemasız bir koşu): kural kapatılmaz."""
    katalog = load_catalog()
    e = DetectionEngine(_cfg(sema_farkindaligi=True), katalog, mevcudiyet=None)
    assert e.sema_olu == {}
    assert [r["id"] for r in e.rules] == [r["id"] for r in DetectionEngine(_cfg(), katalog).rules]


def test_motor_tam_semada_hicbir_kurali_dusurmez():
    katalog = load_catalog()
    e = DetectionEngine(_cfg(sema_farkindaligi=True), katalog, mevcudiyet=kural_mevcudiyeti(katalog, _harita()))
    assert e.sema_olu == {}
    assert [r["id"] for r in e.rules] == [r["id"] for r in DetectionEngine(_cfg(), katalog).rules]


# ---------------------------------------------------------------- ölçüm entegrasyonu


def _metrics(cfg, gt, katalog, m):
    from ztp.metrics import MetricsCollector

    mc = MetricsCollector(cfg, gt, katalog, mevcudiyet=m)
    mc.eval_range = (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"))
    return mc


_GT = [
    dict(
        senaryo="S5-hacim",
        sid="U1",
        aktor="U1",
        teknikler=["T1048"],
        veri_kaynagi="proxy",
        beklenen=["UEBA-0003"],
        baslangic_tarihi="2026-03-01",
        olay_tarihi="2026-03-10",
        bitis_tarihi="2026-03-20",
    )
]


def test_kapsama_olu_beklenen_tespitte_OLCULEMEDI_der():
    katalog = load_catalog()
    m = kural_mevcudiyeti(katalog, _harita(bytes_out="bos"))
    assert not m.degerlendirilebilir("UEBA-0003"), "ön koşul: UEBA-0003 ölü olmalı"
    cov = _metrics(_cfg(sema_farkindaligi=True), _GT, katalog, m).coverage()
    assert cov[0]["sonuc"].startswith("ÖLÇÜLEMEDİ") and cov[0]["olculebilirlik"] == "olculemez"
    assert "UEBA-0003" in cov[0]["sonuc"]


def test_kapsama_bayrak_kapaliyken_KALDI_der():
    """Kapalı hâl eski davranış: aynı senaryo "tetiklenmedi" diye kaçırılmış sayılır."""
    katalog = load_catalog()
    m = kural_mevcudiyeti(katalog, _harita(bytes_out="bos"))
    cov = _metrics(_cfg(), _GT, katalog, m).coverage()
    assert cov[0]["sonuc"].startswith("KALDI") and cov[0]["olculebilirlik"] == "olculebilir"


def test_kapsama_paydasi_olculemeyen_senaryoyu_dusurur():
    katalog = load_catalog()
    m = kural_mevcudiyeti(katalog, _harita(bytes_out="bos"))
    mc = _metrics(_cfg(sema_farkindaligi=True), _GT, katalog, m)
    e = DetectionEngine(_cfg(sema_farkindaligi=True), katalog, mevcudiyet=m)
    s = mc.summary(_bos_etiket(), [], [], e, pd.Timestamp("2026-12-31"))
    assert s["kapsama"]["senaryo"] == 1 and s["kapsama"]["olculebilir"] == 0
    assert s["kapsama"]["olculemez"] == ["S5-hacim"]
    assert s["kapsama"]["olculebilir_oran"] is None  # ölçülebilir senaryo yok → oran uydurulmaz
    assert s["kapsama"]["oran"] == 0.0  # eski alan korunur: geriye dönük karşılaştırma bozulmaz


def test_kural_matrisi_sinanamaz_durumunu_ayri_tutar():
    katalog = load_catalog()
    m = kural_mevcudiyeti(katalog, _harita(bytes_out="bos"))
    mc = _metrics(_cfg(sema_farkindaligi=True), _GT, katalog, m)
    e = DetectionEngine(_cfg(sema_farkindaligi=True), katalog, mevcudiyet=m)
    matris = mc.rule_matrix(e, pd.Timestamp("2026-12-31"))
    satir = next(r for r in matris if r["kural"] == "UEBA-0003")
    assert satir["dogrulama"] == "sinanamaz" and satir["not_"].startswith("şema")
    assert "desen görülmedi" not in satir["not_"]
    ozet = mc._matrix_summary(matris)
    assert ozet["sinanamaz_sema"] == len(e.sema_olu) and "UEBA-0003" in ozet["sema_olu_kural"]
    assert ozet["sinanamaz_sema"] + ozet["sinanmadi"] + ozet["dogrulandi"] + ozet["kismen"] == ozet["kural"]


# ---------------------------------------------------------------- A-3: kanal düzeyi


def _kanalli(**olu: Tuple[str, ...]) -> OzellikHaritasi:
    """Her alan her kanalda dolu; `olu` ile tek tek kanal boşaltılır: `_kanalli(app=("email",))`."""
    h = _harita()
    kaynaklar = ("ad", "proxy", "email", "file_server", "dlp", "edr")
    for a in TUM_ALANLAR:
        for k in kaynaklar:
            bos = k in olu.get(a, ())
            h.kanallar[(a, k)] = (
                AlanDurumu(a, var=True, doluluk=0.0, tekil=1) if bos else AlanDurumu(a, var=True, doluluk=0.9, tekil=9)
            )
    return h


def test_kural_kanallari_source_alias_cevirisi():
    """Katalogdaki iş dilindeki kaynak adı, olay tablosundaki teknik ada çevrilmeli."""
    from ztp.availability import kural_kanallari

    assert kural_kanallari(dict(veri_kaynaklari=["proxy"])) == ("proxy",)
    assert kural_kanallari(dict(veri_kaynaklari=["ad_oturum"])) == ("ad",)
    assert kural_kanallari(dict(veri_kaynaklari=["dosya_sunucu", "proxy"])) == ("file_server", "proxy")
    assert kural_kanallari(dict(veri_kaynaklari=["_internal"])) == ()  # şemaya bağlı değil
    assert kural_kanallari({}) == ()


def test_A3_kanal_duzeyi_kanala_ozel_sinyalde_calisir():
    """Kanala özel sinyal: `usb_count` yalnız `dlp`'den gelir (`features.py:75` filtreli).

    `dlp` kanalında `action` boşsa USB kuralı ölüdür — alan düzeyi bunu göremez, çünkü `action`
    diğer kanallarda doludur.
    """
    katalog = [dict(id="UEBA-0017", veri_kaynaklari=["dlp"], mantik=dict(kosullar=["usb_sayisi >= 3"]))]
    h = _kanalli(action=("dlp",))
    assert h.kullanilabilir("action"), "ön koşul: alan TOPLAMDA dolu görünmeli"
    assert not h.kullanilabilir("action", "dlp")
    assert kural_mevcudiyeti(katalog, h, kanal_duzeyi=False).degerlendirilebilir("UEBA-0017")  # A-2: göremez
    m = kural_mevcudiyeti(katalog, h, kanal_duzeyi=True)
    assert not m.degerlendirilebilir("UEBA-0017")  # A-3: görür
    assert "action@dlp" in m.neden("UEBA-0017")


def test_A3_KANALLAR_ARASI_toplanan_alan_kanal_kararindan_MUAF():
    """`bytes_out` günün tüm kanallarındaki toplamdır (`features.py:61`, kaynak filtresi YOK).

    Web kanalı boşsa sinyal ZAYIFLAR, sıfırlanmaz: `UEBA-0003` r4.2'de skor payının 0,68'ini
    üretiyor, çünkü e-posta ve dosya kanalları bayt taşıyor. A-3'ün ilk sürümü bu kuralı
    `bytes_out@proxy` boş diye ölü ilan etti — ön kayıt ölçütü 4 o yüzden kaldı.

    `veri_kaynaklari` üretimde hangi telemetrinin GEREKTİĞİNİ beyan eder; sinyalin hangi kanalı
    topladığını beyan etmez.
    """
    from ztp.schema_profiler import KANALLAR_ARASI

    assert "bytes_out" in KANALLAR_ARASI
    katalog = [dict(id="UEBA-0003", veri_kaynaklari=["proxy"], mantik=dict(kosullar=["veri_hacmi_z > 3.5"]))]
    h = _kanalli(bytes_out=("proxy",))
    assert not h.kanallar[("bytes_out", "proxy")].kullanilabilir  # kanal profili yine ÖLÇÜLÜR
    assert h.kullanilabilir("bytes_out", "proxy"), "ama karar ALAN düzeyine düşer"
    assert kural_mevcudiyeti(katalog, h, kanal_duzeyi=True).degerlendirilebilir("UEBA-0003")
    # alan TAMAMEN boşsa kural yine ölür: muafiyet "hiç bakma" demek değil
    hepsi = _kanalli(bytes_out=("ad", "proxy", "email", "file_server", "dlp", "edr"))
    hepsi.alanlar["bytes_out"] = AlanDurumu("bytes_out", var=True, doluluk=0.0, tekil=1)
    assert not kural_mevcudiyeti(katalog, hepsi, kanal_duzeyi=True).degerlendirilebilir("UEBA-0003")


def test_A3_olcut4_saglam_kanalda_hicbir_kural_kapanmaz():
    """Ölçüt 3'ün freni: kanallar sağlamken hiçbir kural kapatılmamalı (r4.2'nin durumu)."""
    m = kural_mevcudiyeti(load_catalog(), _kanalli(), kanal_duzeyi=True)
    assert m.olu == frozenset(), f"sağlam şemada ölü ilan edilen kural: {sorted(m.olu)}"


def test_A3_cok_kanalli_kural_TEK_kanal_olunce_yasar():
    """Beyan edilen kanalların HEPSİ ölmeden kural ölmez — `UEBA-0021` deseni (proxy + email).

    `app` iki kanalda da üretilir (`cert.py`: http'de URL kategorisi, email'de iç/dış alıcı), yani
    kanala özeldir ve kanal kararına girer — `bytes_out`'un aksine.
    """
    katalog = [dict(id="K", veri_kaynaklari=["proxy", "email"], mantik=dict(kosullar=["yeni_uygulama_sayisi >= 1"]))]
    m = kural_mevcudiyeti(katalog, _kanalli(app=("proxy",)), kanal_duzeyi=True)
    assert m.degerlendirilebilir("K"), "bir kanal boş diye kural susturulmamalı"
    hepsi = kural_mevcudiyeti(katalog, _kanalli(app=("proxy", "email")), kanal_duzeyi=True)
    assert not hepsi.degerlendirilebilir("K")
    assert "app@proxy" in hepsi.neden("K") and "app@email" in hepsi.neden("K")


def test_A3_kanalsiz_kural_alan_duzeyine_duser():
    """`veri_kaynaklari` boş ya da yalnız `_internal` ise kanal kararı yoktur — eski yol."""
    katalog = [dict(id="PRED-X", veri_kaynaklari=["_internal"], mantik=dict(kosullar=["yeni_uygulama_sayisi >= 1"]))]
    assert not kural_mevcudiyeti(katalog, _kanalli(app=("proxy",)), kanal_duzeyi=True).olu
    h = _harita(app="bos")  # alan tamamen boş → alan düzeyi karar yine çalışır
    assert not kural_mevcudiyeti(katalog, h, kanal_duzeyi=True).degerlendirilebilir("PRED-X")


def test_A3_kanal_profili_YOKSA_alan_duzeyine_duser():
    """Bayrak açık ama kanal profili toplanmamış: karar verilmez, eski yola düşülür."""
    katalog = [dict(id="UEBA-0017", veri_kaynaklari=["dlp"], mantik=dict(kosullar=["usb_sayisi >= 3"]))]
    m = kural_mevcudiyeti(katalog, _harita(), kanal_duzeyi=True)  # kanallar boş
    assert m.degerlendirilebilir("UEBA-0017") and m.kurallar["UEBA-0017"].kanallar == ()


def test_A3_kaynak_alanlari_kanal_bazinda_profil_cikarir():
    from ztp.schema_profiler import kaynak_alanlari

    ev = pd.DataFrame(
        dict(
            source=["proxy"] * 4 + ["email"] * 4,
            bytes_out=[0, 0, 0, 0, 120, 340, 90, 7700],
            app=list("abcdefgh"),
        )
    )
    k = kaynak_alanlari(ev)
    assert k[("bytes_out", "proxy")].durum == "bos"  # r6.2: web olaylarında hep 0
    assert k[("bytes_out", "email")].kullanilabilir
    assert kaynak_alanlari(pd.DataFrame(dict(x=[1]))) == {}  # `source` kolonu yok → karar verilmez


def test_A3_kanal_icinde_YAPISAL_sabitlik_olu_sayilmaz():
    """Gruplama değişkeni kendi grubunda tek değerlidir — bu bir veri eksiği DEĞİLDİR.

    İlk sürüm tekilliği kanal başına ölçtü ve r4.2'de `UEBA-0005` ile `UEBA-0017`'yi ölü ilan etti.
    `UEBA-0017`, 34 senaryonun 31'inin dayandığı USB kuralıdır: mekanizma sistemin en değerli
    kuralını susturmuş olurdu.
    """
    from ztp.schema_profiler import kaynak_alanlari

    ev = pd.DataFrame(
        dict(
            source=["dlp"] * 3 + ["proxy"] * 3,
            action=["usb_copy"] * 3 + ["http"] * 3,  # kanal başına tek değer — YAPISAL
            bytes_out=[5, 6, 7, 0, 0, 0],
        )
    )
    k = kaynak_alanlari(ev)
    assert k[("source", "dlp")].kullanilabilir, "gruplama değişkeni kendi grubunda 'sabit' sayılmamalı"
    assert k[("action", "dlp")].kullanilabilir and k[("action", "proxy")].kullanilabilir
    assert k[("bytes_out", "dlp")].kullanilabilir  # gerçek doluluk kanala özel kalır
    assert k[("bytes_out", "proxy")].durum == "bos"


def test_A3_profille_kanal_uyarisi_alan_duzeyinin_goremedigini_soyler():
    from ztp.schema_profiler import profille

    ev = pd.DataFrame(
        dict(
            source=["proxy"] * 3 + ["email"] * 3,
            bytes_out=[7, 8, 9, 120, 340, 7700],
            app=["x", "y", "z", "", "", ""],  # yalnız `proxy`'de dolu → `app@email` ölü
            action=["http"] * 3 + ["send"] * 3,
            resource=list("uvwxyz"),
            process=list("ABCDEF"),
            cmdline=list("GHIJKL"),
            time=pd.date_range("2026-01-01", periods=6, freq="h"),
            outcome=["success", "failure"] * 3,
        )
    )
    alan = profille("t", events=ev, kanal_duzeyi=False)
    assert not any("kanallarda ölü" in u for u in alan.uyarilar), "alan düzeyi bunu göremez"
    kanal = profille("t", events=ev, kanal_duzeyi=True)
    assert any("app" in u and "email" in u and "kanallarda ölü" in u for u in kanal.uyarilar)
    assert kanal.olu_kanallar()["app"] == ["email"]
    assert "bytes_out" not in kanal.olu_kanallar()  # kanallar arası toplanan alan uyarı üretmez


def test_A3_bayrak_sema_farkindaligi_olmadan_acilamaz():
    with pytest.raises(ValueError, match="sema_farkindaligi açık olmalı"):
        TenantConfig(tenant_id="t", pseudonym_secret="s", sema_kanal_duzeyi=True)
    assert TenantConfig().sema_kanal_duzeyi is False


def test_A3_gercek_katalogda_her_kuralin_kanali_cozulebiliyor():
    """Sözleşme: yayındaki her kuralın kaynağı ya `_internal` ya da olay tablosunda görülen kanal.

    Çözülemeyen bir kaynak adı sessizce "kanal yok" olur ve kural alan düzeyine düşer — yani A-3 o
    kural için hiç çalışmaz. Katalog ile şema arasındaki sapma burada görünür.
    """
    from ztp.availability import kural_kanallari

    bilinen = {"ad", "proxy", "email", "file_server", "dlp", "edr", "hr", "vpn", "ids"}
    for kural in load_catalog():
        for k in kural_kanallari(kural):
            assert k in bilinen, f"{kural['id']}: `{k}` bilinen kanal değil (SOURCE_ALIAS eksik olabilir)"


@pytest.mark.slow
def test_mekanizma_RAPORU_degistirir_SKORU_degistirmez(tmp_path):
    """Ön kayıt ölçütü 1 + 2 tek ölçümde: şema farkındalığı skora, sıralamaya, kuyruğa DOKUNMAZ.

    Kurulum, r4.2'nin gerçek durumunu sentetik veride yeniden üretir: `outcome` sabitlenir ve
    `process`/`cmdline` boşaltılır → `UEBA-0006` (başarısız giriş) ve `UEBA-0008` (keşif) yapısal
    olarak ölür. İki koşu aynı sakat veriyle yapılır; tek fark bayrak.

    Ölçüt: günlük risk skorları ve kuyruk BİREBİR aynı; değişen yalnız kural sağlığı raporundaki
    durum (`sinanmadi → sinanamaz`). Mekanizma yanlış pozitif üretirse bu test kırılır.
    """
    from ztp.data.synthetic import SyntheticOrg
    from ztp.pipeline import ZeroTrustPredictionPipeline

    end = pd.Timestamp("2026-09-16")
    data = SyntheticOrg(n_users=40, n_days=TenantConfig().long_window_days + 18, eval_days=8, end_day=end, seed=11).build()
    data.events["outcome"] = "success"  # başarısız giriş kaydı yok (CERT'in gerçek durumu)
    data.events["process"] = None  # süreç telemetrisi yok
    data.events["cmdline"] = None

    kosular = {}
    for bayrak in (False, True):
        cfg = TenantConfig(
            tenant_id=f"sema-{int(bayrak)}",
            pseudonym_secret="s",
            alarm_budget_per_day=6,
            threshold_jitter=0.0,
            sema_farkindaligi=bayrak,
        )
        pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), tmp_path / str(int(bayrak)))
        pipe.run(end - pd.Timedelta(days=7), end, warmup_days=6)
        kosular[bayrak] = pipe

    kapali, acik = kosular[False], kosular[True]
    assert acik.engine.sema_olu, "kurulum anlamsız olurdu: en az bir kural şemadan ölü olmalı"
    assert kapali.engine.sema_olu == {}

    # 1) SKOR ve KUYRUK birebir aynı
    assert {k: dict(v) for k, v in kapali.final_risk.items()} == {k: dict(v) for k, v in acik.final_risk.items()}
    assert kapali.metrics.queue_by_day == acik.metrics.queue_by_day
    assert dict(kapali.metrics.rule_hits) == dict(acik.metrics.rule_hits)

    # 2) RAPOR değişti: aynı kural, farklı gerekçe
    def _durum(pipe, rid):
        satir = next(r for r in pipe.metrics.rule_matrix(pipe.engine, end) if r["kural"] == rid)
        return satir["dogrulama"], satir["not_"]

    for rid in acik.engine.sema_olu:
        assert _durum(kapali, rid) == ("sinanmadi", "bu veride desen görülmedi")
        d, neden = _durum(acik, rid)
        assert d == "sinanamaz" and neden.startswith("şema")


def _bos_etiket():
    import tempfile
    from pathlib import Path

    from ztp.feedback import LabelStore

    return LabelStore(Path(tempfile.mkdtemp()) / "labels.json")
