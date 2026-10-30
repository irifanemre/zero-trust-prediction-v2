"""Saldırı yolu tahmini — sprint v6 katman B (`docs/sprint-v6-on-kayit.md`).

Sistem tespitleri ATT&CK'e eşliyor ama **sıradaki hamleyi tahmin etmiyor**. Analist vakayı açtığında
"bu kişi şunları yaptı" görüyor, "sıradaki adımda şunu yapabilir" görmüyor. Bu modül o eksiği kapatır:
kullanıcının taktik dizisinden sonraki adımı tahmin eder.

**Çıktı skora GİRMEZ** (`saldiri_yolu_agirligi = 0.0`). Yalnız vaka anlatısına gider ve oradan kanıt
doğrulayıcıdan geçer. Gerekçe: yanlış bir tahmin precision'ı bozmasın. Skora alınması ayrı bir karardır
ve ablasyona bağlıdır.

İki model:

- `NgramModeli` — sayım tabanlı, deterministik, yorumlanabilir; geri çekilmeli (backoff) bağlam.
  **Transformer'ın yenmesi gereken taban budur.** Önce bunu kurmanın sebebi 30 Ekim dersi: ağır modelin
  neyi geçtiği önceden yazılmazsa, zayıf bir sonuç "iyileştirme" diye okunur.
- `TransformerModeli` — küçük nedensel dizi modeli (torch). `[ml]` eklentisi kurulu değilse açık hata
  verir, sessizce n-gram'a düşmez.

**Sızıntıya karşı tek kural:** gün D'de önce TAHMİN edilir, sonra o günün geçişleriyle ÖĞRENİLİR.
`SaldiriYoluTahmincisi.gun()` bu sırayı zorunlu kılar; tersine çevrilirse model kendi cevabını görür.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

LOG = logging.getLogger(__name__)

# Dizi sınırları. BASLA bir kullanıcının ilk taktiğinden önce gelir ki "ilk hamle ne olur" da modellenebilsin.
BASLA = "<basla>"
BILINMIYOR = "Bilinmiyor"  # KnowledgeGraph.tactic eşleyemediğinde döndürdüğü değer

# Kill-chain sırası — yalnız GÖSTERİM için (tahmin bu sıraya göre yapılmaz, veriden öğrenilir).
TAKTIK_SIRASI: Tuple[str, ...] = (
    "Initial Access",
    "Execution",
    "Persistence",
    "Privilege Escalation",
    "Defense Evasion",
    "Credential Access",
    "Discovery",
    "Lateral Movement",
    "Collection",
    "Exfiltration",
    "Impact",
)


@dataclass(frozen=True)
class YolTahmini:
    """Bir kullanıcı için sıradaki hamle tahmini."""

    gecmis: Tuple[str, ...]  # gözlenen taktik dizisi (en fazla son birkaç adım)
    adaylar: Tuple[Tuple[str, float], ...]  # (taktik, olasılık), olasılığa göre sıralı
    gozlem: int  # tahminin dayandığı geçiş sayısı — analistin ne kadar güveneceğini belirler
    baglam_uzunlugu: int  # kaç adımlık bağlam kullanıldı (geri çekilme sonrası)
    model: str

    @property
    def yeterli(self) -> bool:
        return self.gozlem >= MIN_GECIS and bool(self.adaylar)

    def ozet(self) -> dict:
        return dict(
            model=self.model,
            gecmis=list(self.gecmis),
            baglam_uzunlugu=self.baglam_uzunlugu,
            gozlem=self.gozlem,
            adaylar=[dict(taktik=t, olasilik=round(p, 4)) for t, p in self.adaylar],
            yeterli=self.yeterli,
        )

    def metin(self) -> str:
        """Analiste gösterilecek cümle. Gözlem sayısı HER ZAMAN yazılır: 3 geçişten öğrenilmiş bir
        tahminle 300 geçişten öğrenilmiş bir tahmin aynı cümleyle sunulamaz."""
        if not self.yeterli:
            return ""
        ilk = ", ".join(f"{t} (%{100 * p:.0f})" for t, p in self.adaylar)
        return f"Sıradaki olası hamle: {ilk} — {self.gozlem} benzer geçişten öğrenildi ({self.model})"


# Bir tahminin analiste gösterilmesi için gereken en az geçiş sayısı. Altında tahmin üretilmez:
# az gözlemden çıkan olasılık, olasılık değil gürültüdür.
MIN_GECIS = 20


def taktik_dizisi(hits: Iterable, kg, bilinmeyeni_at: bool = True) -> List[Tuple[pd.Timestamp, str]]:
    """Tespitlerden zaman sıralı taktik dizisi. Ardışık tekrarlar TEKİLLEŞTİRİLİR.

    Tekilleştirmenin sebebi: aynı gün beş kez Discovery tetiklenmesi "beş adım" değil, bir adımdır.
    Tekrar bilgisi zaten şiddet ve ağırlıkta var; dizi modelinin öğrenmesi gereken şey SIRA.
    """
    olaylar = []
    for h in hits:
        for t in getattr(h, "attack", ()) or ():
            taktik = kg.tactic(t)
            if bilinmeyeni_at and taktik == BILINMIYOR:
                continue
            olaylar.append((h.day, taktik))
    olaylar.sort(key=lambda x: (x[0], x[1]))
    out: List[Tuple[pd.Timestamp, str]] = []
    for gun, taktik in olaylar:
        if not out or out[-1][1] != taktik:
            out.append((gun, taktik))
    return out


class NgramModeli:
    """Geri çekilmeli n-gram: P(sonraki | son k taktik), k = `en_uzun_baglam` … 0.

    Bağlam, en az `min_baglam_gozlem` kez görülmüş en UZUN bağlamdır; yoksa bir kısalır. Hiçbiri yoksa
    marjinal dağılıma (k=0) düşülür. Laplace düzeltmesi görülmemiş taktiğe de sıfırdan büyük olasılık
    verir — aksi hâlde model "bu asla olmaz" der ki elimizdeki veriyle söylenemez.
    """

    def __init__(self, en_uzun_baglam: int = 2, min_baglam_gozlem: int = 5, alfa: float = 0.5):
        if en_uzun_baglam < 1:
            raise ValueError("en_uzun_baglam ≥ 1 olmalı")
        if min_baglam_gozlem < 1:
            raise ValueError("min_baglam_gozlem ≥ 1 olmalı")
        if alfa <= 0:
            raise ValueError("alfa > 0 olmalı (Laplace düzeltmesi)")
        self.en_uzun_baglam, self.min_baglam_gozlem, self.alfa = en_uzun_baglam, min_baglam_gozlem, float(alfa)
        self._sayim: Dict[Tuple[str, ...], Counter] = defaultdict(Counter)
        self._sozluk: set = set()
        self.gecis = 0

    @property
    def adi(self) -> str:
        return f"ngram-{self.en_uzun_baglam}"

    def ogren_gecis(self, baglam: Sequence[str], sonraki: str) -> None:
        self._sozluk.add(sonraki)
        for k in range(0, self.en_uzun_baglam + 1):
            self._sayim[tuple(baglam[len(baglam) - k :]) if k else ()][sonraki] += 1
        self.gecis += 1

    def ogren(self, dizi: Sequence[str]) -> None:
        """Bir kullanıcının tam taktik dizisinden bütün geçişleri çıkarır."""
        tam = [BASLA, *dizi]
        for i in range(1, len(tam)):
            self.ogren_gecis(tam[max(0, i - self.en_uzun_baglam) : i], tam[i])

    def _baglam_sec(self, gecmis: Sequence[str]) -> Tuple[Tuple[str, ...], Counter]:
        """Yeterince gözlenmiş en uzun bağlam; yoksa kısalır, sonunda marjinale düşer."""
        for k in range(min(self.en_uzun_baglam, len(gecmis)), 0, -1):
            anahtar = tuple(gecmis[len(gecmis) - k :])
            sayim = self._sayim.get(anahtar)
            if sayim and sum(sayim.values()) >= self.min_baglam_gozlem:
                return anahtar, sayim
        return (), self._sayim.get((), Counter())

    def tahmin(self, gecmis: Sequence[str], ust: int = 3) -> YolTahmini:
        gecmis = tuple(gecmis) or (BASLA,)
        anahtar, sayim = self._baglam_sec(gecmis)
        toplam = sum(sayim.values())
        if not toplam:
            return YolTahmini(gecmis[-3:], (), 0, 0, self.adi)
        sozluk = sorted(self._sozluk)
        payda = toplam + self.alfa * len(sozluk)
        olasilik = [(t, (sayim.get(t, 0) + self.alfa) / payda) for t in sozluk]
        olasilik.sort(key=lambda x: (-x[1], x[0]))  # eşitlikte alfabetik — determinizm
        return YolTahmini(gecmis[-3:], tuple(olasilik[:ust]), toplam, len(anahtar), self.adi)

    def gun_bitti(self, gun: pd.Timestamp) -> bool:
        """Gün sonu kancası. n-gram artımlı öğrendiği için hiçbir şey yapmaz; Transformer burada eğitilir."""
        return False

    def etkinlik(self) -> dict:
        return dict(yol_model=self.adi, yol_gecis=self.gecis, yol_sozluk=len(self._sozluk))


def taban_orani(diziler: Sequence[Sequence[str]], ust: int = 3) -> float:
    """Boş model: "her zaman en sık görülen `ust` taktiği söyle". Modelin yenmesi gereken budur.

    Tekdüze tahmin (1/sözlük) yanlış bir tabandır: taktik dağılımı çarpıktır ve hiçbir şey öğrenmeden
    en sık üçünü söylemek zaten yüksek isabet verir. Eşik bu gerçek tabana göre konur.
    """
    sayim = Counter(t for d in diziler for t in d)
    toplam = sum(sayim.values())
    if not toplam:
        return 0.0
    return sum(n for _, n in sayim.most_common(ust)) / toplam


def degerlendir(model, diziler: Sequence[Sequence[str]], ust: int = 3) -> dict:
    """Sonraki adım isabeti: top-1 ve top-`ust`, gerçek taban oranıyla birlikte.

    Model, `diziler` üzerinde EĞİTİLMEMİŞ olmalıdır; aksi hâlde ölçüm kendi eğitim verisini okur.
    """
    top1 = topk = toplam = 0
    for dizi in diziler:
        gecmis: List[str] = [BASLA]
        for gercek in dizi:
            t = model.tahmin(gecmis, ust=ust)
            if t.adaylar:
                adlar = [a for a, _ in t.adaylar]
                top1 += adlar[0] == gercek
                topk += gercek in adlar
                toplam += 1
            gecmis.append(gercek)
    taban = taban_orani(diziler, ust)
    return dict(
        n=toplam,
        top1=round(top1 / toplam, 4) if toplam else None,
        topk=round(topk / toplam, 4) if toplam else None,
        ust=ust,
        taban=round(taban, 4),
        taban_kat=round((topk / toplam) / taban, 2) if toplam and taban else None,
        # Başarı ölçütü TOP-1'dir (sapma 1): 9 taktiklik sözlükte top-3 tabanı ~0,87 çıkar ve "2 katı" 1'i aşar.
        taban_top1=round(taban_orani(diziler, 1), 4),
        top1_kat=round((top1 / toplam) / taban_orani(diziler, 1), 2) if toplam and taban_orani(diziler, 1) else None,
    )


@dataclass
class SaldiriYoluTahmincisi:
    """Günlük işletim: önce tahmin, sonra öğrenme. Sıra sızıntı bariyeridir.

    Model her gün o güne kadar TAMAMLANMIŞ geçişlerle güncellenir; bugünün geçişi ancak gün bittikten
    sonra öğrenilir. Böylece bir kullanıcı için üretilen tahmin, o kullanıcının o günkü davranışını
    hiçbir zaman görmemiş olur.
    """

    model: object
    _gecmis: Dict[str, List[str]] = field(default_factory=dict, init=False)
    tahmin_sayisi: int = field(default=0, init=False)
    ogrenilen_gun: int = field(default=0, init=False)
    egitim_sayisi: int = field(default=0, init=False)

    def tahmin_et(self, sid: str, yeni_taktikler: Sequence[str] = ()) -> YolTahmini:
        """`sid` için sıradaki hamle. `yeni_taktikler` bugünkülerdir: bağlama girer, modele ÖĞRETİLMEZ."""
        gecmis = [*self._gecmis.get(sid, []), *yeni_taktikler]
        self.tahmin_sayisi += 1
        return self.model.tahmin(gecmis or [BASLA])

    def ogren_gun(self, gun: pd.Timestamp, gunun_taktikleri: Dict[str, Sequence[str]]) -> int:
        """Gün bitti: o günün geçişlerini modele öğret ve kullanıcı geçmişlerini uzat."""
        n = 0
        for sid in sorted(gunun_taktikleri):  # sıralı: determinizm (sözlük sırası girdi sırasına bağlıdır)
            gecmis = self._gecmis.setdefault(sid, [])
            for t in gunun_taktikleri[sid]:
                if gecmis and gecmis[-1] == t:
                    continue  # ardışık tekrar tekilleşir (bkz. taktik_dizisi)
                self.model.ogren_gecis([BASLA, *gecmis][-self.model.en_uzun_baglam :], t)
                gecmis.append(t)
                n += 1
        self.ogrenilen_gun += 1
        if self.model.gun_bitti(gun):
            self.egitim_sayisi += 1
        return n

    def diziler(self) -> List[List[str]]:
        return [list(v) for v in self._gecmis.values() if v]

    def etkinlik(self) -> dict:
        return dict(
            **self.model.etkinlik(),
            yol_tahmin=self.tahmin_sayisi,
            yol_ogrenilen_gun=self.ogrenilen_gun,
            yol_egitim=self.egitim_sayisi,
            yol_kullanici=len(self._gecmis),
        )


def model_kur(tur: str = "ngram", **kw):
    """`tur`: ngram | transformer. Transformer için `[ml]` eklentisi (torch) gerekir.

    torch yoksa **açık hata** verilir, sessizce n-gram'a düşülmez: hangi modelin koştuğu koşu kaydından
    okunabilmeli, "transformer istedim ama n-gram koştu" durumu olmamalı.
    """
    if tur == "ngram":
        return NgramModeli(**kw)
    if tur == "transformer":
        from ztp.attack_path_torch import TransformerModeli  # torch yoksa ImportError

        return TransformerModeli(**kw)
    raise ValueError("saldiri_yolu_model: ngram | transformer")


def _kill_chain_sirasi(taktik: str) -> int:
    return TAKTIK_SIRASI.index(taktik) if taktik in TAKTIK_SIRASI else len(TAKTIK_SIRASI)


def ilerleme(gecmis: Sequence[str]) -> Optional[float]:
    """Kullanıcının kill-chain'de ne kadar ilerlediği [0,1] — yalnız gösterim için.

    Tahmin değil, gözlem özeti: "bu kişi zincirin neresinde". Skora girmez.
    """
    bilinen = [t for t in gecmis if t in TAKTIK_SIRASI]
    if not bilinen:
        return None
    return round(max(_kill_chain_sirasi(t) for t in bilinen) / (len(TAKTIK_SIRASI) - 1), 3)
