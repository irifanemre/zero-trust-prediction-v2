"""Sinyal mevcudiyeti — "bu kural bu veri setinde DEĞERLENDİRİLEBİLİR mi?"

`schema_profiler` hangi ham alanın dolu olduğunu söyler. Bu modül o bilgiyi **kural düzeyine**
taşır: bir kuralın koşullarındaki sinyaller üretilemiyorsa kural **değerlendirilmez** ve
`sinanamaz` diye sayılır.

Ayrımın neden önemli olduğu ölçüldü: r6.2'de `UEBA-0003` (ağırlık 8) yapısal olarak ölüydü ve
kural sağlığı raporu onu `sinanmadi — bu veride desen görülmedi` diye gösterdi. O cümle teknik
olarak doğru, operasyonel olarak yanlış:

> **Desen görülmedi** ile **bakılamadı** aynı şey değildir.

Zincir üç halkalı ve her halkası burada kayıtlı:

    kural koşulu  →  sinyal  →  türev özellik  →  ham olay alanı
    UEBA-0003     →  veri_hacmi_z  →  bytes_out  →  http.csv:content
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from ztp.schema_profiler import TUREV_BAGIMLILIK, OzellikHaritasi

LOG = logging.getLogger(__name__)

# Sinyal → dayandığı TÜREV özellik. Yalnız **veri bağımlı** sinyaller listelenir; türetilmiş
# (risk serisinden gelen, graf, akran) sinyaller burada yoktur ve haklarında karar verilmez.
#
# Eksik bir sinyal "bilinmiyor" sayılır ve kural ENGELLENMEZ. Sessizce kapatmak, sessizce
# yanlış sonuç vermekten daha kötüdür: en az biri görünür olur.
SINYAL_TUREV: Dict[str, str] = {
    # hacim
    "veri_hacmi_z": "bytes_out",
    "veri_hacmi_7g_z": "bytes_out",
    "veri_hacmi_anomali_z": "bytes_out",
    "veri_hacmi_7g_toplam": "bytes_out",
    "veri_hacmi_akran_kati": "bytes_out",
    "hacim_trend_14g": "bytes_out",
    # taşınabilir medya
    "usb_sayisi": "usb_count",
    "usb_ilk_kez": "usb_count",
    "usb_poisson_p": "usb_count",
    "usb_7g_poisson_p": "usb_count",
    "usb_7g_toplam": "usb_count",
    "usb_anomali_p": "usb_count",
    # dosya erişimi
    "dosya_sayisi": "files_accessed",
    "dosya_sayisi_poisson_p": "files_accessed",
    "dosya_7g_poisson_p": "files_accessed",
    "dosya_7g_toplam": "files_accessed",
    "dosya_sayisi_akran_kati": "files_accessed",
    "mesai_disi_dosya_orani": "files_accessed",
    "kritik_varlik_erisim_sayisi": "sensitive_access_count",
    # uygulama / kanal
    "yeni_uygulama_sayisi": "distinct_apps_n",
    "yeni_uygulama_kisisel": "distinct_apps_n",
    "yeni_hassas_uygulama": "sensitive_app_count",
    "jaccard_uygulama": "distinct_apps_n",
    "hassas_7g_toplam": "sensitive_app_count",
    "hassas_7g_p": "sensitive_app_count",
    "bulut_7g_toplam": "cloud_app_count",
    "bulut_7g_p": "cloud_app_count",
    "webmail_7g_toplam": "webmail_count",
    "webmail_7g_p": "webmail_count",
    "eposta_dis_z": "ext_email_bytes",
    "eposta_dis_bayt": "ext_email_bytes",
    "eposta_dis_sayi": "ext_email_count",
    # süreç / keşif — DİKKAT: iki sinyal farklı kaynaklara dayanır, adları yan yana olsa da.
    # `kesif_genisligi_akran_kati` süreç sayısına DEĞİL, erişilen tekil KAYNAK sayısına bakar
    # (`profile.py:607` → `distinct_resources`). İlk sürümde ikisi de `recon_process_count`a
    # bağlanmıştı: sentetik veride `process`/`cmdline` boşaltıldığında `UEBA-0008` yanlışlıkla ölü
    # ilan edildi, oysa `resource` doluydu ve kural meşru şekilde 6 kez tetikleniyordu. Ön kayıt
    # ölçütü 2 (skor değişmemeli) bu yanlış pozitifi yakaladı — mekanizmanın kendi denetimi işledi.
    "kesif_sureci_sayisi": "recon_process_count",
    "kesif_genisligi_akran_kati": "distinct_resources",
    "kaynak_cesitliligi": "distinct_resources",
    # oturum
    "mesai_disi_giris_sayisi": "offhours_logon_count",
    "mesai_disi_giris_poisson_p": "offhours_logon_count",
    "mesai_disi_orani": "offhours_logon_count",
    "basarisiz_giris_sayisi": "failed_logon_count",
    "basarisiz_giris_poisson_p": "failed_logon_count",
    "saat_sapmasi_z": "logon_hour",
    # cihaz — yalnız kullanıcı profilinden gelenler; `paylasilan_cihaz_sayisi` graf katmanındandır
    # (`graph/analysis.py`) ve aşağıdaki "haritalanmayan aileler" kuralına girer.
    "yeni_cihaz_sayisi": "devices",
    "baskasinin_cihazi_sayisi": "devices",
}

# Bilerek haritalanMAYAN sinyal aileleri — her biri `turev_uretilebilir` yolundan geçmez ve
# dolayısıyla hiçbir kuralı kapatmaz. Gerekçeleri:
#
# | aile | örnek | neden haritada yok |
# |---|---|---|
# | risk serisinden türeyen | `risk_ewma_kisa`, `risk_egim_7g` | ham alana değil, kendi çıktımıza dayanır |
# | graf / akran yapısı | `akran_yapisal_mesafe` | ilişki katmanı; ham şema değil |
# | denetimsiz kanal | `if_anomali_pct` | ECOD/IF çıktısı; bayrakla kapanır, şemayla değil |
# | tuzak (honeytoken) | `tuzak_*` | yerleştirilmiş varlık; veri setinde "eksik" olması normal |
# | dizin / İK | `ayrilik_bildirimi`, `hesap_yasi_gun` | olay tablosundan değil, dizinden gelir |
# | coğrafi | `yeni_ulke_sayisi`, `imkansiz_seyahat` | CERT'te hiç yok; haritalansa her CERT koşusunda
# |      |      | bu kurallar "şema ölü" ilan edilirdi — doğru ama bu fazın konusu değil (Faz B) |
#
# Kural: haritada olmayan sinyal hakkında KARAR VERİLMEZ. Sessizce kapatmak, sessizce yanlış
# ölçmekten daha kötüdür; en az biri görünür olur.

_KARSILASTIRMA = (ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq)


def kosul_sinyalleri(kosul: str) -> Set[str]:
    """Bir koşul ifadesindeki değişken adları. `veri_hacmi_z > 3.5` → {"veri_hacmi_z"}."""
    try:
        agac = ast.parse(kosul, mode="eval")
    except SyntaxError:
        LOG.warning("Koşul ayrıştırılamadı: %s", kosul)
        return set()
    return {d.id for d in ast.walk(agac) if isinstance(d, ast.Name)}


@dataclass(frozen=True)
class KuralDurumu:
    """Bir kuralın bu veri setinde değerlendirilebilir olup olmadığı."""

    kural: str
    degerlendirilebilir: bool
    eksik_sinyaller: Tuple[str, ...] = ()
    eksik_alanlar: Tuple[str, ...] = ()

    @property
    def neden(self) -> str:
        if self.degerlendirilebilir:
            return ""
        s = ", ".join(f"`{x}`" for x in self.eksik_sinyaller)
        a = ", ".join(f"`{x}`" for x in self.eksik_alanlar)
        return f"şema: {s} üretilemiyor (eksik alan: {a})"

    def ozet(self) -> dict:
        return dict(
            kural=self.kural,
            degerlendirilebilir=self.degerlendirilebilir,
            eksik_sinyaller=list(self.eksik_sinyaller),
            eksik_alanlar=list(self.eksik_alanlar),
            neden=self.neden,
        )


@dataclass
class MevcudiyetHaritasi:
    """Katalogdaki her kuralın bu veri setindeki durumu."""

    veri_seti: str
    kurallar: Dict[str, KuralDurumu] = field(default_factory=dict)

    @property
    def olu(self) -> FrozenSet[str]:
        return frozenset(k for k, d in self.kurallar.items() if not d.degerlendirilebilir)

    def degerlendirilebilir(self, kural_id: str) -> bool:
        d = self.kurallar.get(kural_id)
        return True if d is None else d.degerlendirilebilir  # bilinmeyen kural engellenmez

    def neden(self, kural_id: str) -> str:
        d = self.kurallar.get(kural_id)
        return d.neden if d else ""

    def ozet(self) -> dict:
        return dict(
            veri_seti=self.veri_seti,
            kural=len(self.kurallar),
            olu=sorted(self.olu),
            detay={k: d.ozet() for k, d in sorted(self.kurallar.items()) if not d.degerlendirilebilir},
        )


def kural_mevcudiyeti(katalog: Sequence[dict], harita: OzellikHaritasi) -> MevcudiyetHaritasi:
    """Her kural için: koşullarındaki sinyaller bu veri setinde üretilebiliyor mu?

    Bir kural **ancak koşullarındaki TÜM veri bağımlı sinyaller** üretilemiyorsa ölü sayılır.
    Kısmen üretilebilen kural çalışmaya devam eder: `UEBA-0017` gibi `or`'lu bir kuralda bir kol
    ölse bile diğeri tetikleyebilir. Fazla agresif kapatmak, gerçek tespiti susturmak demektir.
    """
    out = MevcudiyetHaritasi(veri_seti=harita.veri_seti)
    for kural in katalog:
        sinyaller: Set[str] = set()
        for kosul in kural.get("mantik", {}).get("kosullar", []):
            sinyaller |= kosul_sinyalleri(kosul)
        veri_bagimli = {s for s in sinyaller if s in SINYAL_TUREV}
        if not veri_bagimli:
            out.kurallar[kural["id"]] = KuralDurumu(kural["id"], True)
            continue
        eksik = {s for s in veri_bagimli if not harita.turev_uretilebilir(SINYAL_TUREV[s])}
        tamami_olu = eksik == veri_bagimli
        alanlar: Set[str] = set()
        for s in eksik:
            alanlar |= {a for a in TUREV_BAGIMLILIK.get(SINYAL_TUREV[s], ()) if not harita.kullanilabilir(a)}
        out.kurallar[kural["id"]] = KuralDurumu(
            kural["id"],
            degerlendirilebilir=not tamami_olu,
            eksik_sinyaller=tuple(sorted(eksik)),
            eksik_alanlar=tuple(sorted(alanlar)),
        )
    return out


def senaryo_olculebilirligi(beklenen: Iterable[str], mevcudiyet: MevcudiyetHaritasi) -> str:
    """Bir senaryonun beklenen tespitleri bu veri setinde ölçülebilir mi?

    - `olculebilir`  : beklenen kuralların hepsi değerlendirilebilir
    - `kismi`        : bir kısmı ölü — senaryo ölçülebilir ama eksik kanıtla
    - `olculemez`    : hepsi ölü — bu senaryo bu veri setinde SINANAMAZ

    `olculemez` bir senaryonun "kaçırıldı" sayılması raporu yanıltır: sistem bakamadığı bir şeyi
    kaçırmış sayılmaz.
    """
    bekl = [b for b in beklenen]
    if not bekl:
        return "olculebilir"
    olu = [b for b in bekl if not mevcudiyet.degerlendirilebilir(b)]
    if not olu:
        return "olculebilir"
    return "olculemez" if len(olu) == len(bekl) else "kismi"
