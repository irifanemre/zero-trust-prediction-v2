"""Kurulum hazırlık raporu — "bu ortamda 25 kuralın kaçı gerçekten çalışır?"

Bu araç müşteri ortamına koşturulacak bir teslimat. Varlık sebebi ölçülmüş bir hata: CERT'te
`UEBA-0006` ve `UEBA-0008` (toplam ağırlık 11) yapısal olarak ölüydü ve 11 ablasyon varyantının
hepsinde "bu veride desen görülmedi" diye raporlandı. Aynısı gerçek kurulumda olursa daha pahalı:
ürün "25 kural" diye anlatılır, 23'ü çalışır.
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from ztp.schema import EVENT_COLUMNS

KOK = Path(__file__).resolve().parents[1]
BETIK = KOK / "scripts" / "kurulum_hazirlik.py"


def _kos(csv: Path, *ek: str) -> str:
    r = subprocess.run(
        [sys.executable, str(BETIK), "--olaylar", str(csv), "--ad", "test", *ek],
        capture_output=True,
        text=True,
        cwd=KOK,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def _yaz(tmp_path: Path, df: pd.DataFrame) -> Path:
    p = tmp_path / "olaylar.csv"
    df.to_csv(p, index=False)
    return p


def _temel(n: int = 400) -> pd.DataFrame:
    """Her alanı dolu, sağlıklı bir olay tablosu."""
    zaman = pd.date_range("2026-01-01", periods=n, freq="h")
    kaynaklar = ["ad", "proxy", "email", "file_server", "dlp", "edr"]
    df = pd.DataFrame(
        {
            "event_id": [f"E-{i:06d}" for i in range(n)],
            "time": zaman,
            "received_time": zaman,
            "class_uid": 1001,
            "source": [kaynaklar[i % len(kaynaklar)] for i in range(n)],
            "actor_raw": [f"U{i % 20}" for i in range(n)],
            "device": [f"HOST-{i % 11}" for i in range(n)],
            "src_ip": [f"10.0.0.{i % 250}" for i in range(n)],
            "country": "TR",
            "resource": [f"\\\\SRV\\pay{i % 17}" for i in range(n)],
            "app": [["erp", "personal_cloud", "email_external", "webmail", "crm", "git"][i % 6] for i in range(n)],
            "action": [["logon", "http", "send", "copy", "usb_copy", "exec"][i % 6] for i in range(n)],
            "outcome": ["success", "failure"][0 : 1] * n if False else [("failure" if i % 23 == 0 else "success") for i in range(n)],
            "bytes_out": [1000 * (i % 97) + 50 for i in range(n)],
            "process": [f"p{i % 13}.exe" for i in range(n)],
            "parent_process": "explorer.exe",
            "cmdline": [f"p{i % 13}.exe --flag{i % 5}" for i in range(n)],
            "category": [f"c{i % 7}" for i in range(n)],
        }
    )
    return df[[c for c in EVENT_COLUMNS]]


def test_saglikli_veride_olu_kural_bildirmez(tmp_path):
    """Her alan doluyken hiçbir kural 'sınanamaz' çıkmamalı — yoksa araç yanlış alarm üretiyordur."""
    out = _kos(_yaz(tmp_path, _temel()))
    assert "Her kural bu veride sınanabilir" in out
    assert "SINANAMAZ" not in out


def test_eksik_alan_olu_kurali_ve_AGIRLIGINI_bildirir(tmp_path):
    """CERT'in gerçek durumu birebir yeniden üretilir → iki kural ölü, toplam ağırlık 11.

    `outcome` sabit (CERT `logon.csv` başarısız giriş tutmaz), `process`/`cmdline` boş (süreç
    telemetrisi yok) ve `resource` boş (`cert.py` dosya adı saklamaz, 20.1 veri minimizasyonu).

    Üçüncüsü şart: yalnız `process`/`cmdline` boşaltılırsa `UEBA-0008` **kısmen** ölür
    (`kesif_genisligi_akran_kati` → `distinct_resources` → `resource` hâlâ canlı) ve kural
    çalışmaya devam eder — bu doğru davranıştır (`docs/faz-a2-sonuclar.md`: "kısmen ölü kural
    çalışmaya devam eder"). CERT'te üç alan da boş olduğu için orada tamamen ölüyor.

    Rapor yalnız "ölü" demekle kalmamalı, **kaç ağırlık kaybedildiğini** de söylemeli — karar
    verenin bilmesi gereken sayı o.
    """
    df = _temel()
    df["outcome"] = "success"  # sabit: başarısız giriş kaydı yok
    df["process"] = ""
    df["cmdline"] = ""
    df["resource"] = ""  # CERT dosya adı saklamaz
    out = _kos(_yaz(tmp_path, df))
    assert "SINANAMAZ" in out
    assert "UEBA-0006" in out and "UEBA-0008" in out
    assert "toplam ağırlık 11" in out  # 5 + 6, CERT'te kaybedilen ağırlık


def test_hr_kanali_YANLIS_ALARM_uretmez(tmp_path):
    """`hr` olay akışında değil İK/AD dizininde gelir; olay tablosunda aranması yanlış alarmdır.

    İlk sürüm onu "YOK" diye raporluyordu ve dört kuralı şüpheli gösteriyordu.
    """
    out = _kos(_yaz(tmp_path, _temel()))
    satir = next(s for s in out.splitlines() if s.startswith("| `hr`"))
    assert "YOK" not in satir and "dizinden gelir" in satir


def test_eposta_hacim_dagilimi_esik_karari_icin_cikar(tmp_path):
    """`UEBA-0023`'ün eşiği türetilemedi ve operasyonel karara dönüştü (`docs/v10-sonuclar.md`).

    Karar sayıyla verilebilsin diye rapor dış e-posta hacim dağılımını çıkarmalı.
    """
    out = _kos(_yaz(tmp_path, _temel()))
    assert "UEBA-0023` eşiği için hacim dağılımı" in out
    for olcut in ("medyan", "p90", "p99", "mad_medyan"):
        assert olcut in out


def test_eksik_kolonlari_bildirir_ve_COKMEZ(tmp_path):
    """Müşteri verisi eksik kolonla gelebilir; araç çökmemeli, eksiği raporlamalı."""
    df = _temel().drop(columns=["cmdline", "parent_process", "country"])
    out = _kos(_yaz(tmp_path, df))
    assert "Şemada olmayan kolonlar" in out
    assert "cmdline" in out and "country" in out
