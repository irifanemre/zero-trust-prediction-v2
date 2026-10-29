"""ADWIN — kavram kayması tespiti ve kendi kendini güncelleyen baz çizgisi (revizeler.txt §1.4).

Sorun: baz çizgisi sabit 90 günlük geçmişten hesaplanıyor. Kullanıcı yıllık izinden döndüğünde, projesi
değiştiğinde ya da departman geçişi yaptığında bu geçmiş artık o kişiyi anlatmıyor; sistem **yapay anomali**
üretiyor. 90 günü kısaltmak ise gerçek yavaş kaymaları kaçırmaya yol açar. Pencere uzunluğu sabit seçilemez.

ADWIN (Bifet & Gavaldà, 2007) pencereyi veriye göre ayarlar: `W` penceresini her olası noktadan iki parçaya
böler ve iki parçanın ortalamaları **istatistiksel olarak ayırt edilebilir** hâle geldiğinde eski parçayı atar.
Eşik Hoeffding sınırından gelir, dolayısıyla yanlış alarm oranı `delta` ile sınırlıdır — sezgisel bir eşik değildir.

    eps = sqrt( (2/m) · var · ln(2/delta') ) + (2/(3m)) · ln(2/delta')
    m   = 1/(1/n0 + 1/n1)      (iki parçanın harmonik ortalaması)
    delta' = delta / ln(n)     (çoklu karşılaştırma düzeltmesi)

Bellek: pencere ham tutulmaz, **üstel histogram**da tutulur. Her kova 2^i gözlem taşır ve her boyuttan en çok
`M+1` kova bulunur; böylece n gözlem için O(M·log n) bellek yeter. 516 günlük CERT penceresinde bu, kullanıcı
başına birkaç düzine kova demektir.

Sistemdeki yeri: `stats.py::drift_suspicion` bir kaymanın **olup olmadığını** söyler ve bir tespit sinyalidir.
ADWIN ise kayma gerçekleştiğinde **baz çizgisini kısaltır**, yani tespit değil uyarlama katmanıdır. İkisi
birbirinin yerine geçmez: biri "bu kullanıcı değişti" der, diğeri "o hâlde eski geçmişine bakmayı bırak" der.

Varsayılan olarak KAPALIDIR (`TenantConfig.adwin_enabled = False`). Açıldığında baz çizgisini değiştirir,
dolayısıyla ablasyonla ölçülmeden üretime alınmaz (14.5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

MAX_KOVA = 5  # her boyuttan en çok MAX_KOVA+1 kova (ADWIN2'nin M parametresi)


@dataclass
class Kova:
    """Üstel histogramın bir kovası: 2^us gözlemin toplamı ve kare toplamı."""

    toplam: float
    kare_toplam: float
    adet: int

    def birlestir(self, digeri: "Kova") -> "Kova":
        return Kova(self.toplam + digeri.toplam, self.kare_toplam + digeri.kare_toplam, self.adet + digeri.adet)


@dataclass
class KaymaOlayi:
    """Pencere kısaltıldığında üretilen kayıt — denetlenebilir olması şart."""

    atilan: int
    kalan: int
    eski_ortalama: float
    yeni_ortalama: float
    esik: float

    @property
    def fark(self) -> float:
        return round(abs(self.yeni_ortalama - self.eski_ortalama), 6)

    def ozet(self) -> dict:
        return dict(
            atilan_gozlem=self.atilan,
            kalan_gozlem=self.kalan,
            eski_ortalama=round(self.eski_ortalama, 4),
            yeni_ortalama=round(self.yeni_ortalama, 4),
            fark=self.fark,
            esik=round(self.esik, 4),
        )


@dataclass
class Adwin:
    """Uyarlanabilir pencere. `ekle` yeni gözlemi alır ve kayma saptanırsa pencereyi kısaltır.

    `delta`: yanlış kayma alarmı üst sınırı. Küçültmek kaymayı geç ama daha emin saptar.
    `min_pencere`: bu uzunluğun altında bölme denenmez; kısa pencerede Hoeffding sınırı zaten çok gevşektir.
    """

    delta: float = 0.002
    min_pencere: int = 10
    max_kova: int = MAX_KOVA
    _kovalar: List[List[Kova]] = field(default_factory=list)  # _kovalar[i] → 2^i boyutlu kovalar (eskiden yeniye)
    _toplam: float = 0.0
    _kare_toplam: float = 0.0
    _adet: int = 0
    kayma_sayisi: int = 0
    son_kayma: Optional[KaymaOlayi] = None

    def __post_init__(self) -> None:
        if not 0.0 < self.delta < 1.0:
            raise ValueError("delta 0 ile 1 arasında olmalı")
        if self.min_pencere < 2:
            raise ValueError("min_pencere en az 2 olmalı")

    # ------------------------------------------------------------------ durum
    @property
    def adet(self) -> int:
        return self._adet

    @property
    def ortalama(self) -> float:
        return self._toplam / self._adet if self._adet else 0.0

    @property
    def varyans(self) -> float:
        if self._adet < 2:
            return 0.0
        return max(0.0, self._kare_toplam / self._adet - self.ortalama**2)

    # ------------------------------------------------------------------ histogram
    def _kova_ekle(self, deger: float) -> None:
        if not self._kovalar:
            self._kovalar.append([])
        self._kovalar[0].append(Kova(deger, deger * deger, 1))
        i = 0
        while len(self._kovalar[i]) > self.max_kova + 1:
            # en eski iki kova birleşip bir üst boyuta taşınır
            a, b = self._kovalar[i].pop(0), self._kovalar[i].pop(0)
            if i + 1 == len(self._kovalar):
                self._kovalar.append([])
            # `append`: birleşmeler zaman sırasıyla olur, ilk birleşen en eski veridir. Başa eklenirse sıra
            # tersine döner ve bölmede eski/yeni parçalar yer değiştirir — kayma yönü yanlış okunur.
            self._kovalar[i + 1].append(a.birlestir(b))
            i += 1

    def _sirali_kovalar(self) -> List[Kova]:
        """Eskiden yeniye tüm kovalar — bölme noktaları yalnız kova sınırlarında aranır."""
        out: List[Kova] = []
        for i in range(len(self._kovalar) - 1, -1, -1):
            out.extend(self._kovalar[i])
        return out

    def _en_eskiyi_at(self) -> int:
        """En eski (en büyük) kovayı pencereden çıkarır; atılan gözlem sayısını döndürür."""
        for i in range(len(self._kovalar) - 1, -1, -1):
            if self._kovalar[i]:
                k = self._kovalar[i].pop(0)
                self._toplam -= k.toplam
                self._kare_toplam -= k.kare_toplam
                self._adet -= k.adet
                return k.adet
        return 0

    # ------------------------------------------------------------------ sınır
    def _esik(self, n0: int, n1: int) -> float:
        """Hoeffding tabanlı kesme eşiği (varyansa duyarlı ADWIN2 biçimi)."""
        m = 1.0 / (1.0 / n0 + 1.0 / n1)
        delta_u = self.delta / max(math.log(self._adet), 1.0)
        log_terim = math.log(2.0 / delta_u)
        return math.sqrt(2.0 / m * self.varyans * log_terim) + 2.0 / (3.0 * m) * log_terim

    # ------------------------------------------------------------------ ana akış
    def ekle(self, deger: float) -> Optional[KaymaOlayi]:
        """Yeni gözlemi ekler. Kayma saptanırsa eski parça atılır ve olay döndürülür."""
        v = float(deger)
        self._kova_ekle(v)
        self._toplam += v
        self._kare_toplam += v * v
        self._adet += 1
        return self._kayma_ara()

    def _kayma_ara(self) -> Optional[KaymaOlayi]:
        olay: Optional[KaymaOlayi] = None
        kesildi = True
        while kesildi and self._adet >= self.min_pencere:
            kesildi = False
            kovalar = self._sirali_kovalar()
            n0 = 0
            t0 = 0.0
            for k in kovalar[:-1]:  # son kovadan sonra bölme yok (sağ parça boş kalır)
                n0 += k.adet
                t0 += k.toplam
                n1 = self._adet - n0
                if n0 < 1 or n1 < 1:
                    continue
                mu0 = t0 / n0
                mu1 = (self._toplam - t0) / n1
                esik = self._esik(n0, n1)
                if abs(mu0 - mu1) > esik:
                    atilan = self._en_eskiyi_at()
                    self.kayma_sayisi += 1
                    olay = KaymaOlayi(atilan, self._adet, mu0, mu1, esik)
                    self.son_kayma = olay
                    kesildi = True
                    break
        return olay

    def sifirla(self) -> None:
        self._kovalar.clear()
        self._toplam = self._kare_toplam = 0.0
        self._adet = 0


def gecerli_gecmis(adwin: Adwin, gecmis: List[Tuple], varsayilan: int) -> List[Tuple]:
    """ADWIN'in kabul ettiği pencere kadar geçmiş döndürür; kapalıysa `varsayilan` gün.

    Sözleşme: ADWIN hiç kayma görmediyse davranış **birebir eskisi gibidir** (son `varsayilan` kayıt).
    Kayma gördüyse pencere kısalır ve baz çizgisi yalnız kayma sonrasına bakar.
    """
    n = min(len(gecmis), adwin.adet if adwin.kayma_sayisi else varsayilan)
    return gecmis[-n:] if n else []
