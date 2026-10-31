"""Şema profilleyici — "bu veri setinde hangi sinyal GERÇEKTEN var?"

Neden var, ölçülmüş bir hatadan: CERT r6.2'nin `http.csv` dosyasında `content` kolonu **yoktur**.
Ayrıştırıcı `bytes_out`'u içerik uzunluğundan türettiği için o koşuda her web olayının `bytes_out`
değeri **sıfır** oldu. Sonuç: ağırlığı 8 olan `UEBA-0003` (anormal veri çıkış hacmi) r6.2 kör
koşusunda **hiç tetiklenemedi** — ve bu aylarca fark edilmedi. Raporda masum bir
"bu veride desen görülmedi" satırı olarak göründü.

Veri kalitesi katmanı (`quality.py`) bu hatayı yakalayamaz: o, **çalışma zamanında** hacim düşüşüne
ve çözümlenemeyen orana bakar. Bir kolonun en baştan hiç var olmaması farklı bir arıza sınıfıdır.

Profilleyici iki düzeyde çalışır ve **hiçbir kararı değiştirmez, yalnız okur**:

1. **Şema düzeyi** — ham dosyaların başlıkları. Ucuzdur (dosya başına bir satır) ve
   "kolon hiç yok" durumunu yakalar.
2. **Sinyal düzeyi** — ayrıştırılmış olay tablosunda her alanın doluluk oranı ve tekil değer
   sayısı. "Kolon var ama hep sıfır" ve "kolon var ama tek değer taşıyor" durumlarını yakalar.

İkisi birlikte `OzellikHaritasi` üretir: hangi türev özelliğin üretilebileceğinin kaydı.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)

# Bir alanın "kullanılabilir" sayılması için gereken en az doluluk oranı. Altında kalan alan
# teknik olarak vardır ama ona dayanan bir eşik pratikte ulaşılamaz (ölçülmüş hata sınıfı).
MIN_DOLULUK = 0.001
# Tek değer taşıyan alan bilgi taşımaz: `bytes_out` hep 0 ise z-skoru hep 0'dır.
MIN_TEKIL = 2

# Türev özellik → dayandığı HAM alan(lar). Kırılan zincir burada görünür hâle gelir:
# `UEBA-0003` → `veri_hacmi_z` → `bytes_out` özelliği → olay tablosunun `bytes_out` kolonu
# → CERT'te `http.csv`'nin `content` kolonu. Zincirin herhangi bir halkası kopuksa kural ölüdür.
TUREV_BAGIMLILIK: Dict[str, Tuple[str, ...]] = {
    "bytes_out": ("bytes_out",),
    "usb_count": ("source", "action"),
    "files_accessed": ("resource",),
    "distinct_resources": ("resource",),
    "sensitive_access_count": ("resource",),
    "proc_count": ("source",),
    "recon_process_count": ("process", "cmdline"),
    "distinct_apps_n": ("app",),
    "sensitive_app_count": ("app",),
    "cloud_app_count": ("app",),
    "webmail_count": ("app",),
    "ext_email_bytes": ("app", "bytes_out"),
    "ext_email_count": ("app",),
    "logon_count": ("source", "action"),
    "offhours_logon_count": ("time", "source"),
    "failed_logon_count": ("outcome",),
}

# CERT ham dosyalarında bir kolonun yokluğunun hangi olay alanını sakatladığı.
# `cert.py` bu türetmeleri yapar; burada yalnız BAĞIMLILIK kayıtlıdır.
#
# Üçüncü alan `kritik`: kolonun yokluğu ayrıştırıcı tarafından ELE ALINIYORSA False'tur ve uyarı
# üretilmez. Örnek: r4.2'de `file.csv` zaten "taşınabilir medyaya kopya" kaydıdır, dolayısıyla
# `to_removable_media` kolonunun olmaması bir eksiklik değil sürüm farkıdır (`cert.py` bunu
# `fl_removable` ile ayırır). Bu ayrım olmadan profilleyici yanlış alarm üretir — ilk koşuda üretti.
HAM_BAGIMLILIK: Dict[str, Tuple[str, str, bool]] = {
    "http.csv:content": ("bytes_out", "web yükleme hacmi — yoksa UEBA-0003 web tarafında ÖLÜ", True),
    "email.csv:size": ("bytes_out", "e-posta hacmi — yoksa UEBA-0023 ölü", True),
    "http.csv:url": ("app", "URL kategorileri — yoksa bulut/webmail/iş arama sinyalleri ölü", True),
    "device.csv:activity": ("action", "USB bağlantı eylemi — yoksa usb_count üretilemez", True),
    "email.csv:attachments": ("ext_email_attachments", "ek sayısı", False),
    "file.csv:content": ("bytes_out", "dosya kopya boyutu", False),
    "file.csv:to_removable_media": ("action", "r4.2'de yokluğu NORMAL: dosya kaydı zaten kopya demek", False),
}


@dataclass(frozen=True)
class AlanDurumu:
    """Tek bir alanın profili."""

    ad: str
    var: bool
    doluluk: float = 0.0  # boş/sıfır olmayan oran
    tekil: int = 0
    ornek: Tuple[str, ...] = ()

    @property
    def durum(self) -> str:
        if not self.var:
            return "yok"
        if self.doluluk < MIN_DOLULUK:
            return "bos"
        if self.tekil < MIN_TEKIL:
            return "sabit"
        return "kullanilabilir"

    @property
    def kullanilabilir(self) -> bool:
        return self.durum == "kullanilabilir"

    def ozet(self) -> dict:
        return dict(ad=self.ad, durum=self.durum, var=self.var, doluluk=round(self.doluluk, 4), tekil=self.tekil)


@dataclass
class OzellikHaritasi:
    """Bir veri setinde hangi sinyalin üretilebileceğinin kaydı."""

    veri_seti: str
    ham_kolonlar: Dict[str, List[str]] = field(default_factory=dict)  # dosya → kolonlar
    alanlar: Dict[str, AlanDurumu] = field(default_factory=dict)  # olay tablosu alanı → durum
    uyarilar: List[str] = field(default_factory=list)  # kural öldüren eksikler
    notlar: List[str] = field(default_factory=list)  # ayrıştırıcının ele aldığı sürüm farkları

    def alan(self, ad: str) -> AlanDurumu:
        return self.alanlar.get(ad, AlanDurumu(ad, var=False))

    def kullanilabilir(self, ad: str) -> bool:
        return self.alan(ad).kullanilabilir

    def turev_uretilebilir(self, turev: str) -> bool:
        """Türev özellik üretilebilir mi: dayandığı HAM alanların hepsi kullanılabilir olmalı."""
        bagimlilik = TUREV_BAGIMLILIK.get(turev)
        if bagimlilik is None:
            return True  # bilinmeyen türev: karar verilmez, engellenmez
        return all(self.kullanilabilir(a) for a in bagimlilik)

    def olu_turevler(self) -> Dict[str, List[str]]:
        """Üretilemeyen türev özellikler ve eksik oldukları alanlar."""
        out = {}
        for turev, bagimlilik in sorted(TUREV_BAGIMLILIK.items()):
            eksik = [a for a in bagimlilik if not self.kullanilabilir(a)]
            if eksik:
                out[turev] = eksik
        return out

    def ozet(self) -> dict:
        return dict(
            veri_seti=self.veri_seti,
            ham_dosya=len(self.ham_kolonlar),
            alan=len(self.alanlar),
            kullanilabilir=sum(1 for a in self.alanlar.values() if a.kullanilabilir),
            olu_turev=self.olu_turevler(),
            uyarilar=self.uyarilar,
            notlar=self.notlar,
        )


def ham_basliklar(dizin: Path, dosyalar: Sequence[str] = ()) -> Dict[str, List[str]]:
    """Ham CSV başlıkları — dosya başına TEK satır okunur, 17 GB'lık dosyada bile anlık.

    Başlıksız dosya (CERT r1'in `http.csv`'si gibi) boş liste döndürür; çökmez.
    """
    dizin = Path(dizin)
    adlar = list(dosyalar) or sorted(p.name for p in dizin.glob("*.csv"))
    out: Dict[str, List[str]] = {}
    for ad in adlar:
        yol = dizin / ad
        if not yol.exists():
            out[ad] = []
            continue
        try:
            with open(yol, newline="", encoding="utf-8", errors="replace") as f:
                satir = next(csv.reader(f), [])
        except OSError as exc:  # pragma: no cover - dosya sistemi
            LOG.warning("Başlık okunamadı %s: %s", yol, exc)
            satir = []
        # Başlıksız dosyada ilk satır veridir: kolon adı gibi görünmeyen değerler (tarih, {kimlik}) varsa boş say
        basliksiz = any(h.startswith("{") or "/" in h or h.count("-") >= 2 for h in satir)
        out[ad] = [] if basliksiz else [h.strip() for h in satir]
    return out


def olay_alanlari(events: pd.DataFrame, alanlar: Optional[Iterable[str]] = None, ornek: int = 200_000) -> Dict[str, AlanDurumu]:
    """Ayrıştırılmış olay tablosunda her alanın doluluk ve tekillik profili.

    `ornek` satırdan büyük tabloda örnekleme yapılır (deterministik: baştan alınır, rastgele değil —
    koşu tekrarlanabilirliği 21.2).
    """
    if events is None or not len(events):
        return {}
    df = events.head(ornek) if len(events) > ornek else events
    n = len(df)
    out: Dict[str, AlanDurumu] = {}
    for ad in alanlar or df.columns:
        if ad not in df.columns:
            out[ad] = AlanDurumu(ad, var=False)
            continue
        s = df[ad]
        if pd.api.types.is_numeric_dtype(s):
            dolu = int((s.notna() & (s != 0)).sum())  # sayısal alanda 0 "yok" sayılır: bytes_out=0 bilgi taşımaz
        else:
            dolu = int((s.notna() & (s.astype(str).str.strip() != "")).sum())
        try:
            tekil = int(s.nunique(dropna=True))
        except TypeError:  # karşılaştırılamayan tip
            tekil = 0
        ornekler = tuple(str(v)[:40] for v in s.dropna().unique()[:3]) if tekil else ()
        out[ad] = AlanDurumu(ad, var=True, doluluk=dolu / n if n else 0.0, tekil=tekil, ornek=ornekler)
    return out


def profille(
    veri_seti: str,
    ham_dizin: Optional[Path] = None,
    events: Optional[pd.DataFrame] = None,
    ham_dosyalar: Sequence[str] = (),
) -> OzellikHaritasi:
    """Şema + sinyal düzeyini birleştirip harita üretir. İkisi de isteğe bağlıdır."""
    harita = OzellikHaritasi(veri_seti=veri_seti)
    if ham_dizin is not None:
        harita.ham_kolonlar = ham_basliklar(ham_dizin, ham_dosyalar)
        for anahtar, (alan, aciklama, kritik) in sorted(HAM_BAGIMLILIK.items()):
            dosya, kolon = anahtar.split(":", 1)
            kolonlar = harita.ham_kolonlar.get(dosya)
            if kolonlar is None or not kolonlar:
                continue  # dosya yok ya da başlıksız (CERT r1) — ayrı durum, yanlış alarm üretilmez
            if kolon not in kolonlar:
                (harita.uyarilar if kritik else harita.notlar).append(
                    f"{dosya}: `{kolon}` kolonu yok → `{alan}` ({aciklama})"
                )
    if events is not None:
        harita.alanlar = olay_alanlari(events)
        for ad, durum in sorted(harita.alanlar.items()):
            if durum.var and durum.durum in ("bos", "sabit") and ad in {b for bl in TUREV_BAGIMLILIK.values() for b in bl}:
                harita.uyarilar.append(f"olay alanı `{ad}`: {durum.durum} (doluluk {durum.doluluk:.4f}, tekil {durum.tekil})")
    return harita


def rapor(harita: OzellikHaritasi) -> str:
    """İnsan okunur özet."""
    sat = [f"# Şema profili — {harita.veri_seti}", ""]
    if harita.ham_kolonlar:
        sat += ["## Ham dosyalar", ""]
        for dosya, kolonlar in sorted(harita.ham_kolonlar.items()):
            sat.append(f"- `{dosya}`: " + (", ".join(f"`{k}`" for k in kolonlar) if kolonlar else "_başlıksız ya da yok_"))
        sat.append("")
    if harita.alanlar:
        sat += ["## Olay alanları", "", "| Alan | Durum | Doluluk | Tekil |", "|---|---|---|---|"]
        for ad, d in sorted(harita.alanlar.items()):
            isaret = {"kullanilabilir": "", "bos": " ⚠", "sabit": " ⚠", "yok": " ✘"}[d.durum]
            sat.append(f"| `{ad}` | {d.durum}{isaret} | {d.doluluk:.4f} | {d.tekil} |")
        sat.append("")
    olu = harita.olu_turevler()
    if olu:
        sat += ["## Üretilemeyen türev özellikler", ""]
        for turev, eksik in sorted(olu.items()):
            sat.append(f"- `{turev}` — eksik: " + ", ".join(f"`{e}`" for e in eksik))
        sat.append("")
    if harita.uyarilar:
        sat += ["## Uyarılar — kural öldüren eksikler", ""] + [f"- ⚠ {u}" for u in harita.uyarilar] + [""]
    if harita.notlar:
        sat += ["## Notlar — ayrıştırıcının ele aldığı sürüm farkları", ""] + [f"- {n}" for n in harita.notlar] + [""]
    if not olu and not harita.uyarilar:
        sat.append("Eksik sinyal yok: her türev özellik üretilebilir.")
    return "\n".join(sat) + "\n"
