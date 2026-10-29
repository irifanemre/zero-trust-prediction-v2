"""Temporal graph risk sinyalleri — ATHITD'in sinyal katmanı (revizeler2.txt §1, §3; revizeler.txt §1.1).

`temporal_graph.py` veriyi kurar; bu modül ondan **sinyal** üretir. Dört sinyal ve bunların birleşimi:

| Sinyal | Soru | Neden graf gerekir |
|---|---|---|
| `graf_yenilik` | Bugünkü ilişkilerin kaçı bu kullanıcı için ilk kez? | Sayım tabanlı özellikler "10 dosya açtı" der; hangilerinin **yeni** olduğunu söylemez |
| `graf_seyreklik` | Dokunduğu hedeflere kaç akranı dokunuyor? | Tek başına meşru bir dosya, kimsenin açmadığı bir dosyaysa başka anlam taşır |
| `graf_tur_kaymasi` | Davranışın **şekli** değişti mi? | Hacim sabit kalırken dosyadan USB'ye kayan bir profil sayımlarda görünmez |
| `graf_komsu_riski` | Riskli kullanıcılarla paylaşılan varlıklar üzerinden ne kadar yakın? | İlişkisel; hiçbir tekil özellikte yoktur |

## Neden eğitilmiş bir TGN değil

`revizeler.txt §1.1` PyTorch Geometric ile TGN öneriyor. Bu modül **eğitimsiz bir graf temel çizgisidir** ve
bilerek öyledir:

1. **Ölçülebilir bir Model B gerekiyor.** Ablasyon (revizeler2 §10: Model A/B/C/D) için önce "graf eklemek
   fayda sağlıyor mu" sorusunun ağır makine öğrenmesi olmadan cevaplanması gerekir. Temel çizgi fayda
   vermiyorsa eğitilmiş model de büyük olasılıkla vermez; veriyorsa TGN'in aşması gereken çizgi belli olur.
2. **r6.2 dersi.** 670.535 satırda 55 pozitif vardı. Bu yoğunlukta eğitilen bir model ezberler; nitekim lojistik
   regresyonun Brier beceri skoru −128 çıktı. Parametresiz bir sinyal bu riski taşımaz.
3. **Dondurma protokolü.** Eğitilen her model yeni bir dondurma sürümü ve yeni bir veri seti ister. Temel
   çizgi deterministiktir: aynı girdi her zaman aynı çıktıyı verir, tohum ya da ağırlık dosyası yoktur.

Eğitilmiş TGN bu modülün yerini almaz, **üstüne** gelir: aynı `GrafSinyalleri` arayüzünü dolduran ikinci bir
uygulama olur ve ablasyonda bu temel çizgiye karşı ölçülür.

## Varsayılan: kapalı

`graf_agirligi = 0` iken sinyaller üretilir ama skoru **değiştirmez** (gölge mod, 14.5). Açılması ablasyon
ölçümüne bağlıdır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

import pandas as pd

from ztp.gnn.temporal_graph import TemporalHeteroGraph

VARSAYILAN_GECMIS_GUN = 30
VARSAYILAN_ADIM = 2
VARSAYILAN_SONUM = 0.5
SEYREK_ESIK = 3  # bu sayıdan az akranın dokunduğu hedef "seyrek" sayılır


@dataclass
class GrafSinyalleri:
    """Bir kullanıcı-gün için graf türevli sinyaller. Hepsi [0, 1] aralığında ve yorumlanabilir."""

    kullanici: str
    gun: pd.Timestamp
    graf_yenilik: float = 0.0
    graf_seyreklik: float = 0.0
    graf_tur_kaymasi: float = 0.0
    graf_komsu_riski: float = 0.0
    yeni_hedefler: Tuple[Tuple[str, str], ...] = ()
    seyrek_hedefler: Tuple[Tuple[str, str], ...] = ()
    gozlem_yetersiz: bool = False

    @property
    def graf_riski(self) -> float:
        """Dört sinyalin birleşimi. Ağırlıklar eşit — veriye uydurulmuş bir ağırlık ablasyonsuz savunulamaz."""
        if self.gozlem_yetersiz:
            return 0.0
        return round((self.graf_yenilik + self.graf_seyreklik + self.graf_tur_kaymasi + self.graf_komsu_riski) / 4.0, 4)

    def sozluk(self) -> Dict[str, float]:
        """Kural motoruna verilecek sinyal sözlüğü (`graf_` öneki, çakışma olmasın diye)."""
        return {
            "graf_yenilik": round(self.graf_yenilik, 4),
            "graf_seyreklik": round(self.graf_seyreklik, 4),
            "graf_tur_kaymasi": round(self.graf_tur_kaymasi, 4),
            "graf_komsu_riski": round(self.graf_komsu_riski, 4),
            "graf_riski": self.graf_riski,
        }

    def aciklama(self) -> str:
        """Analist için tek satır gerekçe — skor kutusu olmasın."""
        if self.gozlem_yetersiz:
            return "Graf sinyali üretilmedi: yeterli geçmiş yok."
        parcalar = []
        if self.yeni_hedefler:
            ornek = ", ".join(f"{t}:{h}" for t, h in self.yeni_hedefler[:3])
            parcalar.append(f"{len(self.yeni_hedefler)} yeni ilişki ({ornek})")
        if self.seyrek_hedefler:
            parcalar.append(f"{len(self.seyrek_hedefler)} hedefe akranları dokunmuyor")
        if self.graf_tur_kaymasi >= 0.3:
            parcalar.append("davranışın şekli geçmişinden ayrıştı")
        if self.graf_komsu_riski >= 0.3:
            parcalar.append("riskli kullanıcılarla varlık paylaşıyor")
        return "; ".join(parcalar) or "Grafta öne çıkan bir değişiklik yok."


def _l1_mesafe(a: Mapping[str, int], b: Mapping[str, int]) -> float:
    """İki tür dağılımı arasındaki normalize L1 mesafesi ∈ [0, 1]. Dağılımlar ayrı ayrı normalize edilir."""
    ta, tb = sum(a.values()), sum(b.values())
    if not ta or not tb:
        return 0.0
    anahtarlar = set(a) | set(b)
    return round(sum(abs(a.get(k, 0) / ta - b.get(k, 0) / tb) for k in anahtarlar) / 2.0, 6)


def risk_yayilimi(
    graf: TemporalHeteroGraph,
    tohum_riskleri: Mapping[str, float],
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    adim: int = VARSAYILAN_ADIM,
    sonum: float = VARSAYILAN_SONUM,
) -> Dict[str, float]:
    """RiskScore-Guided GNN (revizeler2.txt §3): davranışsal riski paylaşılan varlıklar üzerinden yayar.

    Mevcut skorlama **kaldırılmaz**, grafa tohum olarak verilir. Kullanıcı → hedef → başka kullanıcı yolu bir
    mesaj geçişi adımıdır; her adımda sinyal `sonum` ile zayıflar. Kullanıcı kendi tohumunu geri almaz, aksi
    hâlde yüksek riskli bir kullanıcı kendi riskini kendisine pekiştirir.

    Tohumlar [0, 1] aralığına getirilmiş davranışsal risklerdir. Çıktı aynı aralıkta normalize edilir.
    """
    if not tohum_riskleri or adim < 1:
        return {}
    if not 0.0 < sonum <= 1.0:
        raise ValueError("sonum 0 ile 1 arasında olmalı")
    # Mesajlar KAYNAĞIYLA birlikte taşınır: {alıcı: {kaynak: değer}}. Kaynak izlenmezse iki adımda
    # A→hedef→B→hedef2→A yolu A'nın riskini A'ya geri verir ve kullanıcı kendi riskini kendisi pekiştirir.
    mevcut: Dict[str, Dict[str, float]] = {sid: {sid: float(r)} for sid, r in tohum_riskleri.items() if r}
    birikim: Dict[str, float] = {}
    komsu_onbellek: Dict[Tuple[str, str], Set[str]] = {}
    for _ in range(adim):
        sonraki: Dict[str, Dict[str, float]] = {}
        for sid, paketler in mevcut.items():
            for tur, hedef in graf.komsular(sid, t0, t1):
                anahtar = (tur, hedef)
                if anahtar not in komsu_onbellek:
                    komsu_onbellek[anahtar] = graf.hedefe_dokunan_kullanicilar(tur, hedef, t0, t1)
                akranlar = komsu_onbellek[anahtar] - {sid}
                if not akranlar:
                    continue
                # Paylaşım ne kadar genişse mesaj o kadar zayıf: herkesin dokunduğu kaynak bilgi taşımaz.
                for komsu in akranlar:
                    hedef_paket = sonraki.setdefault(komsu, {})
                    for kaynak, r in paketler.items():
                        if kaynak == komsu:  # kendi riskin sana geri dönmez
                            continue
                        hedef_paket[kaynak] = hedef_paket.get(kaynak, 0.0) + r * sonum / len(akranlar)
        sonraki = {k: v for k, v in sonraki.items() if v}
        if not sonraki:
            break
        for sid, paketler in sonraki.items():
            birikim[sid] = birikim.get(sid, 0.0) + sum(paketler.values())
        mevcut = sonraki
    en_buyuk = max(birikim.values(), default=0.0)
    return {sid: round(min(1.0, r / en_buyuk), 4) for sid, r in birikim.items()} if en_buyuk > 0 else {}


@dataclass
class TemporalGraphBaseline:
    """Eğitimsiz, deterministik graf sinyali üreticisi. Aynı girdi → aynı çıktı; ağırlık dosyası yoktur."""

    gecmis_gun: int = VARSAYILAN_GECMIS_GUN
    seyrek_esik: int = SEYREK_ESIK
    min_gecmis_kenar: int = 5  # bunun altında geçmiş varsa sinyal üretilmez, sıfır dönülür
    adim: int = VARSAYILAN_ADIM
    sonum: float = VARSAYILAN_SONUM
    _yayilim_onbellek: Dict[Tuple[pd.Timestamp, int], Dict[str, float]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.gecmis_gun < 1:
            raise ValueError("gecmis_gun en az 1 olmalı")
        if self.seyrek_esik < 1:
            raise ValueError("seyrek_esik en az 1 olmalı")

    def hesapla(
        self,
        graf: TemporalHeteroGraph,
        kullanici: str,
        gun: pd.Timestamp,
        tohum_riskleri: Optional[Mapping[str, float]] = None,
    ) -> GrafSinyalleri:
        gun = pd.Timestamp(gun).normalize()
        gun_sonu = gun + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        gecmis_bas = gun - pd.Timedelta(days=self.gecmis_gun)
        gecmis_son = gun - pd.Timedelta(microseconds=1)

        bugun = graf.komsular(kullanici, gun, gun_sonu)
        gecmis_kenar = graf.kenarlar(kullanici, gecmis_bas, gecmis_son)
        if len(gecmis_kenar) < self.min_gecmis_kenar or not bugun:
            return GrafSinyalleri(kullanici, gun, gozlem_yetersiz=True)

        gecmis_komsu: Set[Tuple[str, str]] = {(k.hedef_tur, k.hedef) for k in gecmis_kenar}
        yeni = bugun - gecmis_komsu
        yenilik = len(yeni) / len(bugun)

        seyrek: list = []
        for tur, hedef in sorted(bugun):
            akran = graf.hedefe_dokunan_kullanicilar(tur, hedef, gecmis_bas, gun_sonu)
            if len(akran) < self.seyrek_esik:
                seyrek.append((tur, hedef))
        seyreklik = len(seyrek) / len(bugun)

        tur_kaymasi = _l1_mesafe(
            graf.tur_dagilimi(kullanici, gun, gun_sonu), graf.tur_dagilimi(kullanici, gecmis_bas, gecmis_son)
        )

        komsu_riski = 0.0
        if tohum_riskleri:
            anahtar = (gun, len(tohum_riskleri))
            if anahtar not in self._yayilim_onbellek:
                self._yayilim_onbellek[anahtar] = risk_yayilimi(graf, tohum_riskleri, gecmis_bas, gun_sonu, self.adim, self.sonum)
            komsu_riski = self._yayilim_onbellek[anahtar].get(kullanici, 0.0)

        return GrafSinyalleri(
            kullanici=kullanici,
            gun=gun,
            graf_yenilik=round(yenilik, 4),
            graf_seyreklik=round(seyreklik, 4),
            graf_tur_kaymasi=round(tur_kaymasi, 4),
            graf_komsu_riski=round(komsu_riski, 4),
            yeni_hedefler=tuple(sorted(yeni)),
            seyrek_hedefler=tuple(seyrek),
        )

    def toplu(
        self,
        graf: TemporalHeteroGraph,
        kullanicilar: Iterable[str],
        gun: pd.Timestamp,
        tohum_riskleri: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, GrafSinyalleri]:
        return {sid: self.hesapla(graf, sid, gun, tohum_riskleri) for sid in kullanicilar}

    @staticmethod
    def sinyal_adlari() -> Tuple[str, ...]:
        """Kural motorunun görebileceği sinyal adları — dondurma denetimi bunları bilir."""
        return ("graf_yenilik", "graf_seyreklik", "graf_tur_kaymasi", "graf_komsu_riski", "graf_riski")


def ablasyon_karsilastir(
    taban: Mapping[str, float], graf_sinyalleri: Mapping[str, GrafSinyalleri], agirlik: float
) -> Dict[str, float]:
    """Model A (yalnız davranış) ile Model B (davranış + graf) skorlarını üretir — ablasyon için (revizeler2 §10).

    `agirlik = 0` iken çıktı taban skorlarıyla **birebir aynıdır**; sözleşme budur.
    """
    if not 0.0 <= agirlik <= 1.0:
        raise ValueError("agirlik 0 ile 1 arasında olmalı")
    if agirlik == 0.0:
        return dict(taban)
    out: Dict[str, float] = {}
    for sid, skor in taban.items():
        g = graf_sinyalleri.get(sid)
        out[sid] = round(skor * (1.0 + agirlik * (g.graf_riski if g else 0.0)), 6)
    return out


def erken_uyari_suresi(risk_serisi: Sequence[Tuple[pd.Timestamp, float]], olay_gunu: pd.Timestamp, esik: float) -> Optional[int]:
    """Early-warning time (revizeler2.txt §6): risk eşiği gerçek olaydan kaç gün önce aşıldı.

    Yörünge `[(gün, risk)]` olarak verilir. Eşiği ilk aşan ve olaya kadar **düşmeyen** gün aranır; tek günlük
    sıçrama erken uyarı sayılmaz, çünkü analist onu gürültüden ayıramaz.
    """
    olay = pd.Timestamp(olay_gunu).normalize()
    sirali = sorted(((pd.Timestamp(g).normalize(), r) for g, r in risk_serisi), key=lambda x: x[0])
    once = [(g, r) for g, r in sirali if g <= olay]
    if not once:
        return None
    ilk: Optional[pd.Timestamp] = None
    for g, r in once:
        if r >= esik:
            ilk = ilk or g
        else:
            ilk = None  # eşiğin altına düştü, sayaç sıfırlanır
    return int((olay - ilk).days) if ilk is not None else None


def risk_yorungesi_egimi(risk_serisi: Sequence[Tuple[pd.Timestamp, float]]) -> float:
    """Yörüngenin eğimi (revizeler2.txt §6): "riskli duruma doğru ilerliyor mu". En küçük kareler, gün başına."""
    noktalar = sorted(((pd.Timestamp(g).normalize(), float(r)) for g, r in risk_serisi), key=lambda x: x[0])
    n = len(noktalar)
    if n < 2:
        return 0.0
    t0 = noktalar[0][0]
    xs = [float((g - t0).days) for g, _ in noktalar]
    ys = [r for _, r in noktalar]
    ox, oy = sum(xs) / n, sum(ys) / n
    payda = sum((x - ox) ** 2 for x in xs)
    if math.isclose(payda, 0.0):
        return 0.0
    return round(sum((x - ox) * (y - oy) for x, y in zip(xs, ys)) / payda, 6)
