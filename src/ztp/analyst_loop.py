"""Analist geri bildirim döngüsü — sprint v6 katman A (`docs/sprint-v6-on-kayit.md`).

Neden var: 30 Ekim ablasyonu, Bayes kapısının etiketsiz ortamda **sıfır** eleme yaptığını ölçtü — `tam`
varyantıyla bayt bayt aynı çıktı. Aynı şekilde `belirsizlik_enabled` bayrağı hiçbir yerde okunmuyordu;
Venn-Abers kalibratörü yazılmış ve test edilmişti ama hatta bağlanmamıştı. Sistemin bu yarısı etiket
beklediği için ölüydü. Bu modül döngüyü kapatır:

    kuyruk → analist kararı → (gecikmeli) etiket → Bayes kapısı + model yeniden eğitimi → kuyruk

Üç parça:

1. `AnalistSimulatoru` — cevap anahtarından, gerçek bir analistin davranışını taklit eden etiket üreteci.
   Üretimde yerini insan alır; burada döngünün ÖLÇÜLEBİLİR olmasını sağlar.
2. `KalibrasyonZamanlayicisi` — "yeniden eğitme zamanı geldi mi?" kararı; tek seferlik elle eğitim yerine.
3. `belirsizlik_sirasi` — Venn-Abers aralığı en geniş vakayı analiste önce sor (aktif öğrenme).

**Sızıntıya karşı iki kural.** İkisi de testle bağlıdır:

- Etiket GECİKMELİ gelir. D günü kuyruğa giren vaka, `gecikme_gun` sonra etiketlenir; o güne kadar hiçbir
  bileşen onu göremez. Gerçekte analist anında karar vermez, ve gecikme olmadan sistem kendi geleceğini
  okur.
- Yalnız KUYRUĞA GİREN vaka etiketlenir. Analist görmediği şeyi etiketlemez; cevap anahtarının tamamı
  etikete çevrilirse bu denetimli öğrenme olur, geri bildirim döngüsü değil.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from ztp.feedback import LabelStore
from ztp.metrics import MetricsCollector
from ztp.schema import DAY

LOG = logging.getLogger(__name__)

# Yanlış pozitif sebebi zorunludur (17.3). Simülatör gerçek bir analistin en sık verdiği sebebi kullanır;
# sebep dağılımını taklit etmek ölçümü değiştirmez, çünkü hiçbir bileşen sebebe göre karar vermiyor.
VARSAYILAN_FP_SEBEBI = "mesru_is_gerekcesi"


def _kararli_birim(anahtar: str) -> float:
    """Anahtara bağlı, [0,1) aralığında deterministik sayı — sıradan ve çağrı sayısından bağımsız.

    RNG durumu kullanılmaz: aynı vaka, hangi sırayla işlenirse işlensin aynı sayıyı alır. Koşu
    tekrarlanabilirliği (21.2) buna bağlı.
    """
    return int(hashlib.sha256(anahtar.encode("utf-8")).hexdigest()[:8], 16) / 0x1_0000_0000


@dataclass
class AnalistSimulatoru:
    """Cevap anahtarını analist kararına çeviren simülatör.

    `hata_orani` > 0 iken analistin yanıldığı durumu da modeller: gerçek bir SOC'ta etiketler temiz
    değildir ve döngünün gürültülü etikete dayanıklılığı ölçülmelidir. Varsayılan 0 — önce temiz
    etiketle tavan ölçülür.
    """

    ground_truth: Sequence[dict]
    gecikme_gun: int = 2
    hata_orani: float = 0.0
    analist_adi: str = "simulasyon"
    _bekleyen: Dict[pd.Timestamp, List[dict]] = field(default_factory=dict, init=False)
    _pencereler: Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]] = field(default_factory=dict, init=False)
    etiketlenen: int = field(default=0, init=False)
    hatali: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.gecikme_gun < 0:
            raise ValueError("gecikme_gun negatif olamaz")
        if not 0.0 <= self.hata_orani < 1.0:
            raise ValueError("hata_orani [0, 1) aralığında olmalı")
        for g in self.ground_truth:
            if not g.get("negatif"):
                self._pencereler.setdefault(g["sid"], []).append(MetricsCollector._window(g))

    def kuyruga_al(self, gun: pd.Timestamp, vakalar: Sequence[dict]) -> None:
        """O günün kuyruğunu etiketlenmeyi bekleyenlere yazar. Analist bunları `gecikme_gun` sonra kapatır."""
        if vakalar:
            self._bekleyen[pd.Timestamp(gun)] = list(vakalar)

    def _karar(self, sid: Optional[str], gun: pd.Timestamp, case_id: str) -> str:
        gercek = any(a <= gun <= b for a, b in self._pencereler.get(sid or "", []))
        if self.hata_orani > 0 and _kararli_birim(case_id) < self.hata_orani:
            self.hatali += 1
            return "yanlis_pozitif" if gercek else "gercek_pozitif"
        return "gercek_pozitif" if gercek else "yanlis_pozitif"

    def olgunlasan(self, gun: pd.Timestamp) -> List[Tuple[dict, str]]:
        """`gun` itibarıyla analistin kapattığı vakalar: (vaka, karar). Gecikmemiş vakalar görünmez."""
        hedef = pd.Timestamp(gun) - self.gecikme_gun * DAY
        vakalar = self._bekleyen.pop(hedef, [])
        out = []
        for v in vakalar:
            karar = self._karar(v.get("_sid"), hedef, v["case_id"])
            out.append((v, karar))
        return out

    def gun(self, gun: pd.Timestamp, labels: LabelStore) -> List[dict]:
        """Olgunlaşan vakaları etiket deposuna yazar; yazılan kayıtları döndürür."""
        yazilan = []
        for vaka, karar in self.olgunlasan(gun):
            sebep = VARSAYILAN_FP_SEBEBI if karar == "yanlis_pozitif" else None
            yazilan.append(labels.add(vaka, karar, self.analist_adi, reason=sebep, note="otomatik simülasyon"))
        self.etiketlenen += len(yazilan)
        return yazilan

    def etkinlik(self) -> dict:
        return dict(
            analist_etiket=self.etiketlenen,
            analist_gecikme_gun=self.gecikme_gun,
            analist_hata_orani=self.hata_orani,
            analist_hatali_etiket=self.hatali,
            analist_bekleyen_gun=len(self._bekleyen),
        )


@dataclass
class KalibrasyonZamanlayicisi:
    """"Yeniden eğitme zamanı geldi mi?" — tek seferlik elle eğitimin yerine periyodik döngü.

    İki şart birlikte aranır: üzerinden `periyot_gun` geçmiş OLACAK **ve** son eğitimden beri en az
    `min_yeni_etiket` yeni etiket gelmiş olacak. Yalnız gün şartı olsaydı sistem aynı veriyle boşuna
    yeniden eğitilirdi; yalnız etiket şartı olsaydı yoğun bir haftada günde birkaç kez eğitilirdi.
    """

    periyot_gun: int = 0  # 0 → kapalı
    min_yeni_etiket: int = 25
    _son_egitim: Optional[pd.Timestamp] = field(default=None, init=False)
    _son_etiket_sayisi: int = field(default=0, init=False)
    gecmis: List[dict] = field(default_factory=list, init=False)

    @property
    def acik(self) -> bool:
        return self.periyot_gun > 0

    def gerekli_mi(self, gun: pd.Timestamp, etiket_sayisi: int) -> bool:
        if not self.acik:
            return False
        yeni = etiket_sayisi - self._son_etiket_sayisi
        if yeni < self.min_yeni_etiket:
            return False
        if self._son_egitim is None:
            return True
        return (pd.Timestamp(gun) - self._son_egitim).days >= self.periyot_gun

    def kaydet(self, gun: pd.Timestamp, etiket_sayisi: int, rapor: dict) -> None:
        """Eğitim sonucunu tarihçeye yazar. Kalibrasyonun zaman içinde iyileşip iyileşmediği buradan okunur."""
        self._son_egitim = pd.Timestamp(gun)
        self._son_etiket_sayisi = etiket_sayisi
        holdout = rapor.get("holdout_model") or {}
        self.gecmis.append(
            dict(
                gun=str(pd.Timestamp(gun).date()),
                etiket=etiket_sayisi,
                egitildi=bool(rapor.get("egitildi")),
                neden=rapor.get("neden"),
                auprc=holdout.get("auprc"),
                auprc_kat=holdout.get("auprc_kat"),
                auc=holdout.get("auc"),
                brier=holdout.get("brier"),
                ece=holdout.get("ece"),
            )
        )

    def etkinlik(self) -> dict:
        basarili = [g for g in self.gecmis if g["egitildi"]]
        auprclar = [g["auprc"] for g in basarili if g.get("auprc") is not None]
        return dict(
            kalibrasyon_denemesi=len(self.gecmis),
            kalibrasyon_basarili=len(basarili),
            kalibrasyon_ilk_auprc=auprclar[0] if auprclar else None,
            kalibrasyon_son_auprc=auprclar[-1] if auprclar else None,
            kalibrasyon_gecmisi=self.gecmis,
        )


def belirsizlik_sirasi(vakalar: Sequence[dict], en_fazla: Optional[int] = None) -> List[dict]:
    """Aktif öğrenme: Venn-Abers aralığı en GENİŞ vaka analiste önce sorulur.

    Gerekçe: modelin zaten emin olduğu vakayı etiketlemek yeni bilgi vermez. Belirsiz olan, öğrenme
    başına en çok bilgiyi taşıyandır. Aralığı olmayan vaka (kalibrasyon verisi yetersiz) sona konur —
    atılmaz, çünkü atmak kalibrasyonun hiç kurulamamasına yol açardı.
    """

    def genislik(v: dict) -> Tuple[int, float]:
        b = v.get("belirsizlik") or {}
        g = b.get("genislik")
        return (0, -float(g)) if isinstance(g, (int, float)) else (1, 0.0)

    sirali = sorted(vakalar, key=genislik)
    return sirali[:en_fazla] if en_fazla else sirali


def bayes_besle(kapi, etiketler: Iterable[dict]) -> int:
    """Etiketleri Bayes kapısına öğretir. Kapının sonsal olasılığı ancak bu çağrıyla hareket eder.

    30 Ekim ablasyonunda kapı 0 vaka elemişti: `BayesKapisi.ogren` hiçbir yerden çağrılmıyordu. Bu
    fonksiyon o bağlantıdır.
    """
    n = 0
    for lab in etiketler:
        if lab["karar"] == "belirsiz":
            continue  # belirsiz karar örüntüyü ne doğrular ne çürütür
        kapi.ogren(lab["kurallar"], lab["karar"] == "gercek_pozitif")
        n += 1
    return n
