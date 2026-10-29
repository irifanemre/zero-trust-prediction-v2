"""Belirsizlik modellemesi — tahmine kalibre edilmiş olasılık aralığı (revizeler.txt §1.2).

Sorun: model analiste "%81 risk" diyor ama bu sayının ne kadar güvenilir olduğunu söylemiyor. 20 günlük gözlemi
olan kullanıcıyla 200 günlük gözlemi olanın %81'i aynı şey değildir. r6.2 koşusunda bu açıkça görüldü: 670.535
satırda 55 pozitif vardı, model AUC 0,769 üretirken Brier beceri skoru −128 çıktı — yani skorlar sıralama olarak
anlamlı, olasılık olarak değersizdi.

## Neden Venn-Abers, neden klasik conformal değil

Klasik split conformal, uygunsuzluk `|y − p|` ile çalışır ve **ikili etiketi** (0 ya da 1) kapsayan bir aralık
üretir. İstenen ise olasılığın aralığıdır (%81 → [%74, %88]). İkisi aynı şey değildir: p = 0,5 olan bir tahminde
etiket-kapsayan aralık zorunlu olarak `[0, 1]`'dir, çünkü gerçek etiket 0 da olabilir 1 de. Bu, analize hiçbir
şey katmaz.

**Venn-Abers predictor (IVAP)** doğrudan olasılığı aralıklandırır ve şu güçlü özelliği taşır: üretilen
`[p0, p1]` aralığının **en az biri mükemmel kalibredir** — model yanlış, aşırı güvenli ya da bozuk olsa bile.
Dağılım varsayımı yoktur; tek varsayım kalibrasyon ve test verisinin değiştirilebilir (exchangeable) olmasıdır.

Çalışma prensibi: test nesnesinin skoru kalibrasyon kümesine önce etiket 0, sonra etiket 1 ile eklenir; her
ikisinde izotonik regresyon (PAVA) uydurulur ve o noktadaki değerler okunur. `p0 ≤ p1` daima sağlanır.
Aralığın genişliği doğrudan "bu bölgede ne kadar veri var" sorusunun cevabıdır: komşuluğunda bol kalibrasyon
verisi olan skorlarda daralır, seyrek bölgelerde genişler. "Yetersiz veri" uyarısı bu genişlikten türer,
ayrıca bir eşiğe gerek kalmaz.

Etiket kümesi (`tahmin_kumesi`) ayrı bir iştir ve orada klasik split conformal doğru araçtır; ikisi karıştırılmaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

# %95 etiket-kapsama garantisi için gereken en az kalibrasyon noktası: ceil((n+1)·0,95) <= n  →  n >= 19
MIN_KALIBRASYON = 19
# Venn-Abers anlamlı bir aralık için daha fazlasını ister; altında aralık neredeyse [0,1] çıkar ve zaten uyarır.
VA_MIN = 20


def _gerekli_n(alpha: float) -> int:
    """Verilen alpha'da sonlu conformal kuantilin tanımlı olması için gereken en az kalibrasyon noktası."""
    n = max(1, math.ceil(1.0 / alpha) - 1)
    while math.ceil((n + 1) * (1.0 - alpha)) > n:
        n += 1
    return n


def _kuantil(sirali: Sequence[float], alpha: float) -> Optional[float]:
    """Conformal kuantil: sıralı uygunsuzluk skorlarının ceil((n+1)(1−alpha))'inci elemanı (1 tabanlı)."""
    n = len(sirali)
    if n == 0:
        return None
    k = math.ceil((n + 1) * (1.0 - alpha))
    return None if k > n else float(sirali[k - 1])  # sonlu örneklemde tanımsız — uydurma yapılmaz


def _pava(y: Sequence[float], w: Sequence[float]) -> List[float]:
    """Pool Adjacent Violators: ağırlıklı izotonik (azalmayan) regresyon. O(n).

    Komşu bloklar sıralamayı bozduğu sürece birleştirilir; her blok kendi ağırlıklı ortalamasını alır.
    """
    deger: List[float] = []
    agirlik: List[float] = []
    sayi: List[int] = []
    for yi, wi in zip(y, w):
        deger.append(float(yi))
        agirlik.append(float(wi))
        sayi.append(1)
        while len(deger) > 1 and deger[-2] > deger[-1]:
            w2 = agirlik[-2] + agirlik[-1]
            deger[-2] = (deger[-2] * agirlik[-2] + deger[-1] * agirlik[-1]) / w2
            agirlik[-2] = w2
            sayi[-2] += sayi[-1]
            deger.pop()
            agirlik.pop()
            sayi.pop()
    out: List[float] = []
    for v, c in zip(deger, sayi):
        out.extend([v] * c)
    return out


@dataclass
class Aralik:
    """Bir tahminin kalibre edilmiş olasılık aralığı ve analiste gösterilecek karşılığı."""

    nokta: float
    alt: float
    ust: float
    ham_skor: float
    kalibrasyon_n: int
    yetersiz_veri: bool

    @property
    def genislik(self) -> float:
        return round(self.ust - self.alt, 4)

    @property
    def guven(self) -> str:
        """Aralık genişledikçe karar dayanağı zayıflar."""
        if self.yetersiz_veri:
            return "yetersiz_veri"
        if self.genislik >= 0.30:
            return "zayif"
        if self.genislik >= 0.12:
            return "orta"
        return "guclu"

    @property
    def uyari(self) -> Optional[str]:
        if self.yetersiz_veri:
            return "Yetersiz veri — gözlem süresi uzatılmalı; bu skora dayanarak karar verilmemeli."
        if self.guven == "zayif":
            return "Geniş güven aralığı — skor tek başına karar dayanağı değil, kanıtlara bakılmalı."
        return None

    def ozet(self) -> dict:
        return dict(
            nokta=round(self.nokta, 4),
            aralik=[round(self.alt, 4), round(self.ust, 4)],
            genislik=self.genislik,
            ham_skor=round(self.ham_skor, 4),
            guven_seviyesi=self.guven,
            kalibrasyon_n=self.kalibrasyon_n,
            uyari=self.uyari,
        )

    def metin(self) -> str:
        """Analist ekranı için tek satır: '%81 (güven aralığı %74–%88)'."""
        if self.yetersiz_veri:
            return f"%{self.nokta * 100:.0f} — yetersiz veri, aralık belirlenemedi"
        return f"%{self.nokta * 100:.0f} (güven aralığı %{self.alt * 100:.0f}–%{self.ust * 100:.0f})"


@dataclass
class VennAbersKalibrator:
    """Kalibrasyon kümesinden olasılık aralığı üretir. Eğitim verisi KULLANILMAZ — ayrı bir parça gerekir.

    `fit`'e geçen skorlar modelin kalibrasyon parçasındaki tahminleri, etiketler gerçek sonuçlardır.
    """

    alpha: float = 0.05  # yalnız `tahmin_kumesi` (etiket kümesi) için; aralık alpha'ya bağlı değildir
    _skor: List[float] = field(default_factory=list)
    _etiket: List[int] = field(default_factory=list)
    _uygunsuzluk: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha 0 ile 1 arasında olmalı")

    def fit(self, skorlar: Sequence[float], etiketler: Sequence[int]) -> "VennAbersKalibrator":
        if len(skorlar) != len(etiketler):
            raise ValueError("skor ve etiket sayısı eşit olmalı")
        ciftler = []
        for p, y in zip(skorlar, etiketler):
            p = float(p)
            if not 0.0 <= p <= 1.0:
                raise ValueError(f"skor [0,1] aralığında olmalı: {p}")
            if int(y) not in (0, 1):
                raise ValueError(f"etiket 0 ya da 1 olmalı: {y!r}")
            ciftler.append((p, int(y)))
        ciftler.sort(key=lambda t: t[0])
        self._skor = [p for p, _ in ciftler]
        self._etiket = [y for _, y in ciftler]
        self._uygunsuzluk = sorted(abs(y - p) for p, y in ciftler)
        return self

    @property
    def n(self) -> int:
        return len(self._skor)

    @property
    def hazir(self) -> bool:
        return self.n >= VA_MIN

    def _izotonik_degeri(self, skor: float, varsayilan_etiket: int) -> float:
        """Skoru `varsayilan_etiket` ile ekleyip izotonik uydurur, o noktadaki değeri döndürür.

        Eşit skorlar tek grupta toplanır (standart IVAP). Gruplama şart: aksi hâlde test noktası kendisiyle aynı
        skora sahip kalibrasyon noktalarının **önüne** düşer ve PAVA onu ayrı bir blokta bırakabilir — tüm
        kalibrasyon skorlarının eşit olduğu uçta p0 = 0 gibi anlamsız bir sonuç çıkar.
        """
        gruplar: List[Tuple[float, float, float]] = []  # (skor, etiket toplamı, adet)
        for p, y in zip(self._skor, self._etiket):
            if gruplar and gruplar[-1][0] == p:
                s, t, c = gruplar[-1]
                gruplar[-1] = (s, t + y, c + 1)
            else:
                gruplar.append((p, float(y), 1.0))
        i = 0
        while i < len(gruplar) and gruplar[i][0] < skor:
            i += 1
        if i < len(gruplar) and gruplar[i][0] == skor:  # test noktası kendi eşitlik grubuna katılır
            s, t, c = gruplar[i]
            gruplar[i] = (s, t + varsayilan_etiket, c + 1)
        else:
            gruplar.insert(i, (skor, float(varsayilan_etiket), 1.0))
        uydurulan = _pava([t / c for _, t, c in gruplar], [c for _, _, c in gruplar])
        return uydurulan[i]

    def aralik(self, skor: float) -> Aralik:
        """Venn-Abers olasılık aralığı. Genişlik, o skor bölgesindeki kalibrasyon yoğunluğunu yansıtır."""
        if not 0.0 <= skor <= 1.0:
            raise ValueError("skor [0,1] aralığında olmalı")
        if not self.hazir:
            return Aralik(skor, 0.0, 1.0, skor, self.n, True)
        p0 = self._izotonik_degeri(skor, 0)
        p1 = self._izotonik_degeri(skor, 1)
        alt, ust = min(p0, p1), max(p0, p1)
        # Venn-Abers'ın standart nokta kestirimi: iki uçtan türetilen ve daima aralık içinde kalan değer
        payda = 1.0 - p0 + p1
        nokta = p1 / payda if payda > 0 else (alt + ust) / 2.0
        return Aralik(min(max(nokta, alt), ust), alt, ust, skor, self.n, False)

    def tahmin_kumesi(self, skor: float, alpha: Optional[float] = None) -> Tuple[int, ...]:
        """Hangi ETİKETLER bu güven düzeyinde elenemiyor (klasik split conformal). `(0, 1)` → model kararsız.

        Boş küme dönmez: ikili problemde her iki etiketin reddi çelişkidir, o durumda yakın olan döndürülür.
        """
        a = self.alpha if alpha is None else alpha
        q = _kuantil(self._uygunsuzluk, a)
        if q is None:  # yeterli kalibrasyon yok — hiçbir etiket elenemez
            return (0, 1)
        kume = tuple(y for y in (0, 1) if abs(y - skor) <= q)
        return kume or ((1,) if skor >= 0.5 else (0,))

    def kapsama_olc(self, skorlar: Sequence[float], etiketler: Sequence[int]) -> dict:
        """Ayrı bir kümede kalibrasyonu ölçer: aralığın gözlenen sıklığı kapsaması ve ortalama genişlik."""
        n = len(skorlar)
        if not n:
            return dict(n=0, kalibrasyon_n=self.n)
        kapsanan = genislik = sapma = 0.0
        for p, y in zip(skorlar, etiketler):
            ar = self.aralik(float(p))
            kapsanan += ar.alt <= int(y) <= ar.ust
            genislik += ar.genislik
            sapma += (ar.nokta - int(y)) ** 2
        return dict(
            n=n,
            olculen_kapsama=round(kapsanan / n, 4),
            ortalama_genislik=round(genislik / n, 4),
            brier=round(sapma / n, 4),
            kalibrasyon_n=self.n,
        )
