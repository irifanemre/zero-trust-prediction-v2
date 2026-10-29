"""Bayesian risk kapısı — sakin günlerde bütçeyi zorla doldurmayı önler (revizeler.txt §1.3).

## Sorunu r6.2 ölçtü

Kör koşu, ön kayıtta yazdığım beklentiyi çürüttü. "30'luk bütçe çoğu gün dolmaz" demiştim; gerçekte 2801
kullanıcıda **günde ortalama 23,7 vaka** üretildi ve bütçe neredeyse her gün doldu. Sebep basit: bütçe sabit
bir **sayı**, kapı ise sabit bir **kural**. Nüfus büyüyünce kapıdan geçen mutlak sayı da büyüyor ve kuyruk,
sırf yer olduğu için zayıf kanıtlı vakalarla doluyor.

Bunun bedeli yalnız boşa giden analist zamanı değil: analist kuyruğun üst sıralarının da zayıf olduğunu
öğrenirse sisteme güvenmeyi bırakır (alert fatigue). Bütçeyi düşürmek çözüm değildir — yoğun günlerde gerçek
vakaları keser.

## Çözüm: kuyruk eksik kapanabilsin

Her vaka için "bu kanıt örüntüsü geçmişte ne sıklıkla gerçek çıktı" sorusu sorulur ve cevap bir **olasılık**
olarak hesaplanır. Olasılık eşiğin altındaysa vaka, bütçede yer olsa bile kuyruğa **alınmaz**. Sakin günlerde
kuyruk 30 yerine 4 vakayla kapanır; yoğun günlerde hiçbir şey değişmez.

Tahmin Beta-Binom modelidir: her kanıt örüntüsü (tetiklenen kural kümesi) için analist etiketlerinden
`dogru`/`yanlis` sayıları tutulur ve sonsal ortalama

    P(gerçek | örüntü) = (alfa + dogru) / (alfa + beta + dogru + yanlis)

olarak hesaplanır. Beta önseli, az gözlemli örüntülerin aşırı iddialı olmasını engeller: hiç etiketi olmayan
bir örüntü önselin kendisini alır ve **eşiği geçer** — yani sistem bilmediği şeyi susturmaz. Susturma ancak
yeterli kanıt biriktiğinde başlar.

## Güvenlik sınırları

- **Kritik vakalar kapıdan muaftır.** Honeytoken teması gibi deterministik sinyaller olasılığa bakılmaz
  (mimari 13.5 istisnası); bu modül onları asla elemez.
- **Yeni kurallar susturulmaz.** `min_gozlem` altındaki örüntüler önsel ortalamayla geçer.
- **Varsayılan kapalı.** `esik = 0` iken hiçbir vaka elenmez ve davranış birebir eskisi gibidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class OruntuIstatistigi:
    dogru: int = 0
    yanlis: int = 0

    @property
    def toplam(self) -> int:
        return self.dogru + self.yanlis


@dataclass
class KapiKarari:
    kullanici: str
    gecti: bool
    olasilik: float
    gerekce: str
    oruntu: Tuple[str, ...]
    gozlem: int

    def ozet(self) -> dict:
        return dict(
            kullanici=self.kullanici,
            gecti=self.gecti,
            olasilik=round(self.olasilik, 4),
            gerekce=self.gerekce,
            oruntu=list(self.oruntu),
            gozlem=self.gozlem,
        )


@dataclass
class BayesKapisi:
    """Kanıt örüntüsünün geçmiş başarısına göre vaka eler. `esik = 0` → kapalı, davranış değişmez.

    `alfa`/`beta`: Beta önseli. Varsayılan (1, 1) düzgün önseldir; önsel ortalama 0,5 olduğundan hiç gözlemi
    olmayan bir örüntü makul her eşiği geçer.
    `min_gozlem`: bu sayıdan az etiketi olan örüntü elenmez — yeni kurallar susturulmasın diye.
    """

    esik: float = 0.0
    alfa: float = 1.0
    beta: float = 1.0
    min_gozlem: int = 10
    _istatistik: Dict[Tuple[str, ...], OruntuIstatistigi] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.esik < 1.0:
            raise ValueError("esik 0 ile 1 arasında olmalı (0 = kapalı)")
        if self.alfa <= 0 or self.beta <= 0:
            raise ValueError("alfa ve beta pozitif olmalı")
        if self.min_gozlem < 0:
            raise ValueError("min_gozlem negatif olamaz")

    # ------------------------------------------------------------------ öğrenme
    @staticmethod
    def oruntu(kurallar: Iterable[str]) -> Tuple[str, ...]:
        """Kanıt örüntüsü = tetiklenen kuralların sırasız, tekil kümesi. Sıra bilgi taşımaz."""
        return tuple(sorted({str(k) for k in kurallar if str(k)}))

    def ogren(self, kurallar: Iterable[str], dogru: bool) -> None:
        """Analist etiketini işler. `dogru=True` gerçek pozitif, `False` yanlış pozitif."""
        anahtar = self.oruntu(kurallar)
        if not anahtar:
            return
        mevcut = self._istatistik.get(anahtar, OruntuIstatistigi())
        self._istatistik[anahtar] = OruntuIstatistigi(mevcut.dogru + int(dogru), mevcut.yanlis + int(not dogru))

    def etiketlerden(self, etiketler: Iterable[Mapping]) -> "BayesKapisi":
        """`feedback.LabelStore` kayıtlarından toplu öğrenme. Beklenen alanlar: `kurallar`, `dogru`."""
        for e in etiketler:
            kurallar = e.get("kurallar") or e.get("rules") or []
            if "dogru" in e or "true_positive" in e:
                self.ogren(kurallar, bool(e.get("dogru", e.get("true_positive"))))
        return self

    # ------------------------------------------------------------------ karar
    def olasilik(self, kurallar: Iterable[str]) -> Tuple[float, int]:
        """Sonsal ortalama ve bu örüntü için gözlem sayısı."""
        ist = self._istatistik.get(self.oruntu(kurallar), OruntuIstatistigi())
        payda = self.alfa + self.beta + ist.toplam
        return (self.alfa + ist.dogru) / payda, ist.toplam

    def degerlendir(self, kullanici: str, kurallar: Sequence[str], kritik: bool = False) -> KapiKarari:
        oruntu = self.oruntu(kurallar)
        p, gozlem = self.olasilik(kurallar)
        if self.esik <= 0.0:
            return KapiKarari(kullanici, True, p, "kapı kapalı", oruntu, gozlem)
        if kritik:
            return KapiKarari(kullanici, True, p, "kritik vaka — kapıdan muaf (13.5)", oruntu, gozlem)
        if gozlem < self.min_gozlem:
            return KapiKarari(kullanici, True, p, f"yetersiz gözlem ({gozlem}<{self.min_gozlem}) — susturulmaz", oruntu, gozlem)
        if p < self.esik:
            return KapiKarari(kullanici, False, p, f"sonsal olasılık {p:.3f} < eşik {self.esik:.3f}", oruntu, gozlem)
        return KapiKarari(kullanici, True, p, f"sonsal olasılık {p:.3f} ≥ eşik {self.esik:.3f}", oruntu, gozlem)

    def suz(
        self,
        sirali_kuyruk: Sequence[str],
        kurallar_haritasi: Mapping[str, Sequence[str]],
        kritikler: Optional[Iterable[str]] = None,
    ) -> Tuple[List[str], List[KapiKarari]]:
        """Sıralı kuyruğu süzer. Dönen kuyruk bütçeden KISA olabilir — amaç budur.

        Sıra korunur: kapı yalnız eler, yeniden sıralamaz (sıralama `scoring.priority`'nin işidir).
        """
        kritik_kume = set(kritikler or ())
        gecen: List[str] = []
        elenen: List[KapiKarari] = []
        for sid in sirali_kuyruk:
            karar = self.degerlendir(sid, kurallar_haritasi.get(sid, ()), sid in kritik_kume)
            if karar.gecti:
                gecen.append(sid)
            else:
                elenen.append(karar)
        return gecen, elenen

    # ------------------------------------------------------------------ raporlama
    def ozet(self) -> dict:
        satirlar = [
            dict(
                oruntu=list(k),
                dogru=v.dogru,
                yanlis=v.yanlis,
                sonsal=round((self.alfa + v.dogru) / (self.alfa + self.beta + v.toplam), 4),
            )
            for k, v in sorted(self._istatistik.items())
        ]
        return dict(
            esik=self.esik,
            onsel=[self.alfa, self.beta],
            min_gozlem=self.min_gozlem,
            oruntu_sayisi=len(satirlar),
            oruntuler=sorted(satirlar, key=lambda r: r["sonsal"]),
        )
