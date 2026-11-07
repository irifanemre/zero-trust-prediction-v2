"""Kural dondurma: kör koşudan önce dondurulan kural/eşik/ağırlık kümesi sessizce değişmesin.

Bu test kalırsa bir kural ya da tespit kodu dondurmadan sonra değişmiştir. Bilinçli bir değişiklikse yeni bir dondurma
sürümü yazılır (`python -m ztp.freeze --write configs/freeze/kurallar-donduruldu-v3.json`) ve yeni etiket atılır;
eski manifest silinmez. Kör koşu sonucu görüldükten sonra yeni sürüm, o koşunun sonucunu geçersiz kılar.
"""

import json

import pytest

from ztp.freeze import REPO, build_manifest, diff_manifest, file_sha256

MANIFEST = REPO / "configs" / "freeze" / "kurallar-donduruldu-v12.json"
V11 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v11.json"
V10 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v10.json"
V9 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v9.json"
V8 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v8.json"
V7 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v7.json"
V6 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v6.json"
V5 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v5.json"
V4 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v4.json"
V3 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v3.json"
V2 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v2.json"


def test_rules_match_frozen_manifest():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert diff_manifest(expected, build_manifest()) == []


def test_manifest_covers_all_rules():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(m["degerler"]["kurallar"]) == 25  # v8/v9/v10 kural EKLEMEZ: v7'nin 25 kuralı aynı
    assert m["etiket"] == "kurallar-donduruldu-v12"


def test_v3_kurallari_v2_ile_ayni():
    """v3'te hiçbir kural/eşik/ağırlık değişmedi: eklenen yetenekler varsayılanda kapalı olduğu için tespit
    davranışı v2 ile birebir aynıdır. Değişen yalnız kodu taşıyan dosyaların karmaları."""
    v2, v3 = (json.loads(p.read_text(encoding="utf-8")) for p in (V2, V3))
    assert v2["degerler"]["kurallar"] == v3["degerler"]["kurallar"]
    degisen = {f for f in v3["dosyalar"] if v2["dosyalar"].get(f) != v3["dosyalar"][f]}
    assert degisen == {"src/ztp/config.py", "src/ztp/detection/engine.py", "src/ztp/profile.py", "src/ztp/scoring.py"}


def test_v4_kurallari_v3_ile_ayni():
    """v4 revizeler.txt/revizeler2.txt bileşenlerini bağlar (graf, ADWIN, Bayes kapısı, belirsizlik).

    Hiçbir KURAL, eşik ya da ağırlık değişmedi — değişen, bu bileşenlerin bağlandığı üç dosya ve tenant
    varsayılanlarına eklenen bayraklar. Bayraklar varsayılanda kapalı olduğundan v4'ün kapalı davranışı v3 ile
    birebir aynıdır; bunu `scripts/surum_karsilastir.py` r4.2'de ölçer.
    """
    v3, v4 = (json.loads(p.read_text(encoding="utf-8")) for p in (V3, V4))
    assert v3["degerler"]["kurallar"] == v4["degerler"]["kurallar"]
    degisen = {f for f in v4["dosyalar"] if v3["dosyalar"].get(f) != v4["dosyalar"][f]}
    assert degisen == {"src/ztp/config.py", "src/ztp/profile.py", "src/ztp/scoring.py"}


def test_v5_kurallari_v4_ile_ayni():
    """v5, r6.2 ölçümünün yapısal bulgusuna cevap verir (`docs/r62-v4-olcumu.md`).

    Değişen: graf riski için TOPLAMSAL yol, kurala bağlı olmayan denetimsiz anomali kanalı (`unsupervised.py`),
    lojistik modelde sınıf ağırlığı anahtarı. Hiçbir KURAL, eşik ya da ağırlık değişmedi; dondurulan dosya
    kümesine bir dosya EKLENDİ (anomali kanalı skora girdiği için donmak zorunda).
    """
    v4, v5 = (json.loads(p.read_text(encoding="utf-8")) for p in (V4, V5))
    assert v4["degerler"]["kurallar"] == v5["degerler"]["kurallar"]
    eklenen = set(v5["dosyalar"]) - set(v4["dosyalar"])
    assert eklenen == {"src/ztp/unsupervised.py"}
    degisen = {f for f in v4["dosyalar"] if v5["dosyalar"].get(f) != v4["dosyalar"][f]}
    assert degisen == {"src/ztp/config.py", "src/ztp/prediction_model.py", "src/ztp/scoring.py"}


def test_v4_bayraklari_varsayilanda_kapali():
    """Sözleşme: yeni bileşenlerin hiçbiri varsayılanda karar yoluna giremez."""
    from ztp.config import TenantConfig

    c = TenantConfig()
    assert c.graf_enabled is False and c.graf_agirligi == 0.0
    assert c.bayes_kapi_esigi == 0.0
    assert c.adwin_enabled is False
    assert c.belirsizlik_enabled is False
    assert c.kanit_dogrulama == "kapali"
    assert c.cok_ajanli_rapor is False


def test_v5_bayraklari_varsayilanda_kapali():
    """Aynı sözleşme v5 için: toplamsal graf, denetimsiz kanal ve sınıf ağırlığı varsayılanda karar yolunda DEĞİL.

    r6.2 ölçümünden sonra bu daha da önemli: ölçülen tek veride açmak yakalamayı değiştirmeden yanlış alarmı
    ikiye katladı. Varsayılanı değiştirmek için bu betiklerin ablasyon sonucu gerekir (14.5).
    """
    from ztp.config import TenantConfig

    c = TenantConfig()
    assert c.graf_toplamsal_agirlik == 0.0
    assert c.anomali_enabled is False and c.anomali_agirligi == 0.0
    assert c.anomali_dogrulama_esigi == 0.0
    assert c.pred_sinif_agirligi is False


def test_hash_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.yaml", tmp_path / "crlf.yaml"
    lf.write_bytes(b"id: X\nesik: 3.5\n")
    crlf.write_bytes(b"id: X\r\nesik: 3.5\r\n")
    assert file_sha256(lf) == file_sha256(crlf)


def test_diff_reports_changed_threshold():
    m = build_manifest()
    changed = json.loads(json.dumps(m))
    changed["degerler"]["kurallar"]["UEBA-0003"]["kosullar"] = ["veri_hacmi_anomali_z > 3.0"]
    assert diff_manifest(m, changed) == ["değer: kurallar"]


def test_v6_ilk_kural_eklemesi_ve_golge_modda():
    """v6, v2'den beri İLK kural eklemesidir: UEBA-0022 (sızıntı kanalı ani artış).

    Kural gölge modda doğdu (13.6) — yani dondurma kümesine girdi ama kuyruğa vaka gönderemez.
    Ayrıca sızıntı kanalı sayacı havuzdan ayrıldığı için `features.py` ve `profile.py` değişti.
    """
    v5, v6 = (json.loads(p.read_text(encoding="utf-8")) for p in (V5, V6))
    eklenen = set(v6["degerler"]["kurallar"]) - set(v5["degerler"]["kurallar"])
    assert eklenen == {"UEBA-0022"}
    assert v6["degerler"]["kurallar"]["UEBA-0022"]["durum"] == "golge-modda"
    # havuzlanmış kural DEĞİŞMEDİ: v6-D yeni bir sayaç ekler, eskisini bozmaz
    assert v5["degerler"]["kurallar"]["UEBA-0021"] == v6["degerler"]["kurallar"]["UEBA-0021"]
    degisen = {f for f in v5["dosyalar"] if v6["dosyalar"].get(f) != v5["dosyalar"][f]}
    assert degisen == {"src/ztp/config.py", "src/ztp/features.py", "src/ztp/profile.py", "src/ztp/scoring.py"}


def test_v6_bayraklari_varsayilanda_kapali():
    """Sprint v6'nın üç katmanı da ölçüldü ve eşiğini geçemedi; varsayılanda kapalı kalırlar."""
    from ztp.config import TenantConfig

    c = TenantConfig()
    assert c.geri_bildirim_dongusu is False  # katman A
    assert c.saldiri_yolu_enabled is False and c.saldiri_yolu_agirligi == 0.0  # katman B
    assert c.graf_ogrenen_enabled is False and c.graf_ogrenen_agirligi == 0.0  # katman C


def test_v7_kanal_kurallari_golge_modda():
    """v7, eksik KANALLARA kural ekler: dış e-posta ve kişisel webmail.

    İkisi de gölge modda doğdu. Ön kayıt (`docs/sprint-v8-kanal-kurallari-on-kayit.md`) bu kuralların
    değerinin CERT'te ölçülemeyeceğini önceden yazdı: r4.2'nin 34 senaryosunun 31'i USB'ye bağımlı.
    Kuralları yine de yazmanın sebebi, kanal açıldığında kör kalmamaktır.
    """
    v6, v7 = (json.loads(p.read_text(encoding="utf-8")) for p in (V6, V7))
    eklenen = set(v7["degerler"]["kurallar"]) - set(v6["degerler"]["kurallar"])
    assert eklenen == {"UEBA-0023", "UEBA-0024"}
    for rid in sorted(eklenen):
        assert v7["degerler"]["kurallar"][rid]["durum"] == "golge-modda"
        assert v7["degerler"]["kurallar"][rid]["agirlik"] == 6
    # mevcut kurallar DEĞİŞMEDİ: v8 yeni kanal ekler, eskisini bozmaz
    for rid in v6["degerler"]["kurallar"]:
        assert v6["degerler"]["kurallar"][rid] == v7["degerler"]["kurallar"][rid]


def test_v8_hicbir_kural_degismedi_yalniz_olcum_durustlesti():
    """v8 bir TESPİT sürümü değil, bir ÖLÇÜM sürümüdür (`docs/faz-a2-on-kayit.md`).

    Hiçbir kural, eşik ya da ağırlık değişmedi. Değişen: şemadan ölü kural artık "bu veride desen
    görülmedi" demek yerine `sinanamaz` sayılıyor ve beklenen tespitlerinin hepsi ölü olan senaryo
    kapsama PAYDASINDAN düşüyor. Dondurma kümesine iki dosya eklendi çünkü ikisi de bir kuralın
    ölü/canlı sayılmasına karar veriyor.
    """
    v7, v8 = (json.loads(p.read_text(encoding="utf-8")) for p in (V7, V8))
    assert v7["degerler"]["kurallar"] == v8["degerler"]["kurallar"]
    eklenen = set(v8["dosyalar"]) - set(v7["dosyalar"])
    assert eklenen == {"src/ztp/availability.py", "src/ztp/schema_profiler.py"}
    degisen = {f for f in v7["dosyalar"] if v8["dosyalar"].get(f) != v7["dosyalar"][f]}
    assert degisen == {"src/ztp/config.py", "src/ztp/detection/engine.py"}


def test_v8_bayragi_varsayilanda_kapali():
    """Sözleşme: şema farkındalığı kapalıyken ölçüm birebir v7'dir (ön kayıt ölçütü 1)."""
    from ztp.config import TenantConfig

    assert TenantConfig().sema_farkindaligi is False


def test_v7_eposta_webmail_sinyalleri_uretiliyor():
    """Kurallar sinyalsiz kalmasın: iki kanalın da özellik ve sinyal yolu bağlı olmalı."""
    import inspect

    from ztp import features, profile

    kaynak = inspect.getsource(features) + inspect.getsource(profile)
    for ad in ("ext_email_bytes", "webmail_count", "eposta_dis_z", "webmail_7g_p"):
        assert ad in kaynak, f"{ad} hiçbir yerde üretilmiyor"


def test_v9_kanal_duzeyi_ve_duzeltilmis_teshis():
    """v9 de bir ÖLÇÜM sürümüdür: kural/eşik/ağırlık değişmedi (`docs/faz-a3-sonuclar.md`).

    Değişen üç şey: (1) şema kararı kanal düzeyine indi, (2) kanallar arası TOPLANAN alanlar bu
    kararın dışında bırakıldı, (3) `http.csv:content` kritik olmaktan çıktı — kolon varken de
    okunmadığı ölçüldü, dolayısıyla yokluğu bir eksik değil.
    """
    v8, v9 = (json.loads(p.read_text(encoding="utf-8")) for p in (V8, V9))
    assert v8["degerler"]["kurallar"] == v9["degerler"]["kurallar"]
    assert set(v9["dosyalar"]) == set(v8["dosyalar"]), "v9 donmuş kümeye dosya EKLEMEZ"
    degisen = {f for f in v8["dosyalar"] if v9["dosyalar"].get(f) != v8["dosyalar"][f]}
    assert degisen == {"src/ztp/availability.py", "src/ztp/config.py", "src/ztp/schema_profiler.py"}


def test_v9_kanal_bayragi_varsayilanda_kapali_ve_A2_gerektirir():
    from ztp.config import TenantConfig

    assert TenantConfig().sema_kanal_duzeyi is False
    with pytest.raises(ValueError, match="sema_farkindaligi açık olmalı"):
        TenantConfig(sema_kanal_duzeyi=True)


def test_v10_kaynak_listesi_tamamlandi_esik_DEGISMEDI():
    """v10 yalnız varsayılan kaynak listesini tamamlar; hiçbir eşik değişmedi.

    Ön kayıt (`docs/v10-on-kayit.md`) iki iş planlamıştı: (A) varsayılana `email`, (B) `EPOSTA_TABAN`'ın
    türetme kuralıyla yeniden hesaplanması. **B YAPILMADI**: türetme kuralı, ön kayıtta yazılan
    kendi doğrulama sınamasını geçemedi — `bytes_out` için 50 MB üretti, bilinen-iyi sabit 5 MB,
    yani ±3 kat sınırının dışında. Ölçüt 1 "üretmezse EPOSTA_TABAN değişmez" diyordu.
    """
    from ztp.config import TenantConfig
    from ztp.profile import EPOSTA_TABAN

    v9, v10 = (json.loads(p.read_text(encoding="utf-8")) for p in (V9, V10))
    assert v9["degerler"]["kurallar"] == v10["degerler"]["kurallar"]
    degisen = {f for f in v9["dosyalar"] if v10["dosyalar"].get(f) != v9["dosyalar"][f]}
    assert degisen == {"src/ztp/config.py"}, f"v10 yalnız config.py'yi değiştirir, değişen: {degisen}"
    assert EPOSTA_TABAN == 50_000, "eşik ön kayıt gereği DEĞİŞMEDİ — türetme kuralı sınamayı geçemedi"
    assert "email" in TenantConfig().available_sources


def test_v10_varsayilan_hicbir_kurali_devre_disi_birakmaz():
    """Sözleşme: varsayılan yapılandırma kataloğun TAMAMINI değerlendirebilmeli.

    `UEBA-0023` v8'den v10'a kadar "kaynak yok" diye sessizce devre dışıydı ve bu, eşiğinin iki kez
    yanlış teşhis edilmesine yol açtı (`docs/faz-b-sonuclar.md`). Bir kural varsayılanda devre dışı
    kalacaksa bu bilinçli bir karar olmalı — sessiz bir eksik olmamalı.
    """
    from ztp.config import TenantConfig
    from ztp.detection.catalog import load_catalog
    from ztp.detection.engine import DetectionEngine

    e = DetectionEngine(TenantConfig(), load_catalog())
    assert e.disabled == {}, f"varsayılanda devre dışı kural: {e.disabled}"
    assert len(e.rules) == 25


def test_v11_butce_devretme_varsayilanda_kapali():
    """v11 kullanılmayan bütçenin devretmesini ekler; kural/eşik/ağırlık değişmedi.

    Faz D ölçtü ki düzgün dağıtım kapasitenin %18'ini kullanmıyor (`docs/faz-d-sonuclar.md`).
    Devretme o boş slotları yoğun günlere taşır ve ölçümde kapsamayı 7/8'den 8/8'e çıkardı
    (`docs/v11-sonuclar.md`) — ama varsayılan KAPALI: iki farklı veride ölçülmeden açılmaz.
    """
    from ztp.config import TenantConfig

    v10, v11 = (json.loads(p.read_text(encoding="utf-8")) for p in (V10, V11))
    assert v10["degerler"]["kurallar"] == v11["degerler"]["kurallar"]
    degisen = {f for f in v10["dosyalar"] if v11["dosyalar"].get(f) != v10["dosyalar"][f]}
    assert degisen == {"src/ztp/config.py", "src/ztp/scoring.py"}
    c = TenantConfig()
    assert c.butce_devretme is False and c.butce_devir_tavani == 0


def test_v11_devretme_kapasite_YARATMAZ(tmp_path):
    """Sözleşme: devretme bütçeyi kaydırır, artırmaz. Ön kayıt ölçütü 2 — doğruluk kontrolü.

    Tavan olmadan devir, uzun sessizlikten sonra tek günde kuyruğu patlatır; o yüzden günlük ek
    kapasite `butce_devir_tavani` ile sınırlı.
    """
    import pandas as pd

    from ztp.config import TenantConfig
    from ztp.feedback import LabelStore
    from ztp.graph.knowledge import KnowledgeGraph
    from ztp.scoring import RiskResult, RiskScorer

    # `kuyruk_dogrulama` kapatılır: bu test BÜTÇE TAVANINI sınıyor, kanıt çeşitliliğini değil —
    # açık kalsa kanıtsız sahte sonuçların hepsi elenir ve tavan hiç sınanmaz.
    cfg = TenantConfig(
        tenant_id="t", pseudonym_secret="s", alarm_budget_per_day=3, butce_devretme=True, kuyruk_dogrulama=False
    )
    sc = RiskScorer(cfg, KnowledgeGraph(), LabelStore(tmp_path / "l.json"))
    gun = pd.Timestamp("2026-03-01")
    # iki sessiz gün (hiç aday yok) → bakiye 6 birikir, tavan 3 ile sınırlanır
    for k in range(2):
        assert sc.select_queue(gun + k * pd.Timedelta(days=1), {}) == []
    assert sc.devir_bakiyesi == 6
    yogun = {
        f"S-{i}": RiskResult(
            sid=f"S-{i}", raw=10.0 - i, base=1.0, multipliers={}, percentile=0.9, hits=[], contributions={}
        )
        for i in range(20)
    }
    kuyruk = sc.select_queue(gun + pd.Timedelta(days=2), yogun)
    assert len(kuyruk) == 6, f"günlük tavan bütçe+tavan = 6 olmalı, alınan {len(kuyruk)}"


def test_v12_tek_seferlik_kanit_varsayilanda_kapali():
    """v12, kanıt kapısının MANTIKSAL bir çelişkisini düzeltir; kural/eşik/ağırlık değişmedi.

    Kapının 6. koşulu "3+ farklı günde tekrar" istiyor. `usb_ilk_kez` tanımı gereği kullanıcı
    başına BİR KEZ doğru olabilir (`profile.py`: geçmiş toplamı sıfır şartı). Tetiklenmesi
    tekrarlanamayan bir kuraldan tekrar istemek çelişkidir ve r4.2'de 5 insider'ı bloke ettiği
    ÖLÇÜLDÜ (`docs/graf-kapi-sonuclar.md`).

    Varsayılan kapalı: r6.2'de kapıya bağlı kaçan insider YOK, dolayısıyla ikinci veri setiyle
    doğrulanamıyor (`docs/r62-kapi-on-kayit.md`).
    """
    from ztp.config import TenantConfig
    from ztp.scoring import TEK_SEFERLIK_SINYAL

    v11, v12 = (json.loads(p.read_text(encoding="utf-8")) for p in (V11, MANIFEST))
    assert v11["degerler"]["kurallar"] == v12["degerler"]["kurallar"]
    degisen = {f for f in v11["dosyalar"] if v12["dosyalar"].get(f) != v11["dosyalar"][f]}
    assert degisen == {"src/ztp/config.py", "src/ztp/scoring.py"}
    assert TenantConfig().tek_seferlik_kanit is False
    assert TEK_SEFERLIK_SINYAL == frozenset({"usb_ilk_kez"})


def test_v12_tek_seferlik_kanit_kapiyi_SADECE_tek_seferlikte_acar(tmp_path):
    """Sözleşme: düzeltme DAR olmalı — yalnız tek-seferlik sinyal taşıyan tek tespiti geçirir.

    Ön kayıt ölçütü 3: bedel, kapıyı tamamen kapatmaktan belirgin az olmalı. Düzeltme her tek
    sinyalli vakayı geçirirse kapıyı gevşetmekten farkı kalmaz.
    """
    import pandas as pd

    from ztp.config import TenantConfig
    from ztp.detection.engine import Hit
    from ztp.feedback import LabelStore
    from ztp.graph.knowledge import KnowledgeGraph
    from ztp.scoring import RiskResult, RiskScorer

    gun = pd.Timestamp("2026-03-01")

    def _hit(sinyaller):
        return Hit("UEBA-0017", "USB", "UEBA", gun, 0.9, 7.0, [], [], sinyaller, "yayinda")

    def _sonuc(sinyaller):
        return RiskResult(
            sid="S-1", raw=5.0, base=5.0, multipliers={}, percentile=0.5,
            hits=[_hit(sinyaller)], contributions={},
        )

    for acik in (False, True):
        cfg = TenantConfig(tenant_id="t", pseudonym_secret="s", tek_seferlik_kanit=acik)
        sc = RiskScorer(cfg, KnowledgeGraph(), LabelStore(tmp_path / f"l{int(acik)}.json"))
        # tek-seferlik sinyal YOK → her iki hâlde de kapı kapalı
        assert sc.corroborated(_sonuc({"usb_sayisi": 4})) is False
        # tek-seferlik sinyal VAR → yalnız bayrak açıkken geçer
        assert sc.corroborated(_sonuc({"usb_ilk_kez": 1})) is acik
