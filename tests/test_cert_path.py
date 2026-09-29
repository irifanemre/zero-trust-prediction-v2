"""ZTP_CERT_PATH çözümleyici: veri yolu repoya gömülmez; sürüm dizin adından okunduğu için dönen dizin her zaman r* adlıdır."""

import pytest

from ztp.cli import main
from ztp.data.cert import CERT_PATH_ENV, resolve_cert_dir


def _release(root, name="r4.2"):
    d = root / name
    (d / "LDAP").mkdir(parents=True)
    (d / "logon.csv").write_text("id,date,user,pc,activity\n", encoding="utf-8")
    return d


def test_explicit_release_dir_is_used_and_beats_env(tmp_path, monkeypatch):
    rel = _release(tmp_path / "a")
    other = _release(tmp_path / "b")
    monkeypatch.setenv(CERT_PATH_ENV, str(other))
    assert resolve_cert_dir(str(rel)) == rel


def test_env_may_point_to_root_with_single_release(tmp_path, monkeypatch):
    rel = _release(tmp_path)
    (tmp_path / "answers").mkdir()  # kardeş dizin, sürüm sayılmaz
    monkeypatch.setenv(CERT_PATH_ENV, str(tmp_path))
    assert resolve_cert_dir() == rel


def test_missing_path_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.delenv(CERT_PATH_ENV, raising=False)
    with pytest.raises(FileNotFoundError, match=CERT_PATH_ENV):
        resolve_cert_dir()
    with pytest.raises(FileNotFoundError, match="bulunamadı"):
        resolve_cert_dir(str(tmp_path / "yok"))


def test_ambiguous_or_misnamed_release_fails(tmp_path):
    _release(tmp_path, "r4.1")
    _release(tmp_path, "r4.2")
    with pytest.raises(FileNotFoundError, match="birden çok"):
        resolve_cert_dir(str(tmp_path))
    odd = tmp_path / "veri"
    odd.mkdir()
    (odd / "logon.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="r<sürüm>"):  # ad r ile başlamıyor → cevap anahtarı süzülemez
        resolve_cert_dir(str(odd))


def test_cli_cert_dir_without_value_reads_env(tmp_path, monkeypatch):
    """`--cert-dir` değersiz verilince yol ZTP_CERT_PATH'ten okunur (ayrıştırma `--end`'i değer sanmamalı)."""
    monkeypatch.setenv(CERT_PATH_ENV, str(tmp_path / "yok"))
    assert main(["--test-rules"]) == 0  # değişken ayarlıyken kaynak gerektirmeyen yollar etkilenmez
    with pytest.raises(FileNotFoundError, match="bulunamadı"):
        main(["--cert-dir", "--end", "2010-11-30", "--out", str(tmp_path / "o")])
