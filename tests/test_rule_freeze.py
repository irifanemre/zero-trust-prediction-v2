"""Kural dondurma: kör koşudan önce dondurulan kural/eşik/ağırlık kümesi sessizce değişmesin.

Bu test kalırsa bir kural ya da tespit kodu dondurmadan sonra değişmiştir. Bilinçli bir değişiklikse yeni bir dondurma
sürümü yazılır (`python -m ztp.freeze --write configs/freeze/kurallar-donduruldu-v3.json`) ve yeni etiket atılır;
eski manifest silinmez. Kör koşu sonucu görüldükten sonra yeni sürüm, o koşunun sonucunu geçersiz kılar.
"""

import json

from ztp.freeze import REPO, build_manifest, diff_manifest, file_sha256

MANIFEST = REPO / "configs" / "freeze" / "kurallar-donduruldu-v6.json"
V5 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v5.json"
V4 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v4.json"
V3 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v3.json"
V2 = REPO / "configs" / "freeze" / "kurallar-donduruldu-v2.json"


def test_rules_match_frozen_manifest():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert diff_manifest(expected, build_manifest()) == []


def test_manifest_covers_all_rules():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(m["degerler"]["kurallar"]) == 23  # v6: UEBA-0022 eklendi (v2'den beri ilk kural değişikliği)
    assert m["etiket"] == "kurallar-donduruldu-v6"


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
    v5, v6 = (json.loads(p.read_text(encoding="utf-8")) for p in (V5, MANIFEST))
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
