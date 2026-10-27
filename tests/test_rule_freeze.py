"""Kural dondurma: kör koşudan önce dondurulan kural/eşik/ağırlık kümesi sessizce değişmesin.

Bu test kalırsa bir kural ya da tespit kodu dondurmadan sonra değişmiştir. Bilinçli bir değişiklikse yeni bir dondurma
sürümü yazılır (`python -m ztp.freeze --write configs/freeze/kurallar-donduruldu-v2.json`) ve yeni etiket atılır;
eski manifest silinmez. Kör koşu sonucu görüldükten sonra yeni sürüm, o koşunun sonucunu geçersiz kılar.
"""

import json

from ztp.freeze import REPO, build_manifest, diff_manifest, file_sha256

MANIFEST = REPO / "configs" / "freeze" / "kurallar-donduruldu-v2.json"


def test_rules_match_frozen_manifest():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert diff_manifest(expected, build_manifest()) == []


def test_manifest_covers_all_rules():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(m["degerler"]["kurallar"]) == 22  # v2: UEBA-0021 eklendi
    assert m["etiket"] == "kurallar-donduruldu-v2"


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
