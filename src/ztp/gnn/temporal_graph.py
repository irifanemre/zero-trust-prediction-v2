"""Temporal heterogeneous graph — ATHITD yaklaşımının veri katmanı (revizeler2.txt §1, revizeler.txt §1.1).

Mevcut `graph/observation.py` bir **gözlem grafı** kurar: kenarlar birikir, her kenarda `count`, `first_ts` ve
`last_ts` tutulur. Bu, "kullanıcı bu cihazı kullanır mı" sorusuna cevap verir ama "ne zaman, hangi sırayla ve
bu ilişki **yeni mi**" sorularına veremez — çünkü zaman kenarın içinde özetlenmiştir.

Bu modül kenarları **akış** olarak tutar: her etkileşim kendi zaman damgasıyla ayrı bir kayıttır. Böylece

- belirli bir `[t0, t1]` aralığındaki komşuluk sorulabilir (temporal neighborhood),
- bir ilişkinin kullanıcı için **ilk kez** mi görüldüğü kesin olarak bilinir (novelty),
- aynı hedefe dokunan **kaç farklı kullanıcı** olduğu zamana bağlı hesaplanır (akran seyrekliği),
- grafın zaman içindeki değişimi (yeni kenar türü, yeni hedef sınıfı) ölçülebilir.

## Heterojenlik

Düğümler türlüdür: `kullanici`, `cihaz`, `kaynak` (dosya/paylaşım), `site` (URL kategorisi), `surec`, `medya`
(USB/çıkarılabilir). İlişkiler de türlüdür: `kullandi`, `eristi`, `ziyaret`, `calistirdi`, `kopyaladi`.
Tür bilgisi kaybedilmez; `kullanici→kaynak` ile `kullanici→site` aynı kenar sayılmaz.

## Ölçek kararı

Kenar akışı CERT r6.2'de 35 milyon olaya kadar çıkabiliyor. Bu yüzden:
- kenarlar `array` tabanlı sütunlarda değil, düğüm başına **sıralı listelerde** tutulur (sorgu zaman penceresine
  göre ikili arama ile kesilir),
- düğüm adları **içselleştirilir** (string interning): aynı cihaz adı bir kez saklanır,
- graf **pencere başına** kurulur ve pencere bitince bırakılır; kalıcı depo bu modülün işi değildir.

Varsayılan olarak hiçbir skora katılmaz; üretilen sinyaller `gnn/tgn_model.py` üzerinden **gölge modda** okunur.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

# (olay kolonu, hedef düğüm türü, ilişki türü) — CERT ve OCSF şemasının ortak alanları
KENAR_SEMASI: Tuple[Tuple[str, str, str], ...] = (
    ("device", "cihaz", "kullandi"),
    ("resource", "kaynak", "eristi"),
    ("category", "site", "ziyaret"),
    ("process", "surec", "calistirdi"),
    ("app", "uygulama", "kullandi"),
)
MEDYA_EYLEMLERI = ("usb_copy", "removable_copy")


@dataclass(frozen=True, slots=True)
class Kenar:
    """Tek bir zaman damgalı etkileşim. `slots`: 13M+ kenarda sözlük yükü ~40 bayt/nesne tasarruf eder."""

    zaman: pd.Timestamp
    kaynak: str  # kullanıcı (canonical sid)
    hedef_tur: str
    hedef: str
    iliski: str


@dataclass
class TemporalHeteroGraph:
    """Zaman damgalı heterojen kenar akışı ve üzerindeki zaman kısıtlı sorgular."""

    _kullanici_kenarlari: Dict[str, List[Kenar]] = field(default_factory=lambda: defaultdict(list))
    # Hedef indeksi build sırasında (ns, sid) ikilileri tutar; `sonlandir()` bunu sid listesi + int64 diziye
    # ayırır ve ikilileri bırakır. Kenar başına bir tuple + bir Timestamp nesnesi (~100 B) böylece düşer —
    # 76M kenarlı bir grafta tek başına ~7 GB demek.
    _hedef_kullanicilari: Dict[Tuple[str, str], List[Tuple[int, str]]] = field(default_factory=lambda: defaultdict(list))
    _hedef_sid: Dict[Tuple[str, str], List[str]] = field(default_factory=dict, repr=False)
    _sirali: bool = False
    # Zaman dizileri `sonlandir()`'da BİR KEZ kurulur. Sorgu başına yeniden kurmak O(n) maliyet demekti ve
    # gerçek veride (13M+ olay, 90 gün × ~1000 kullanıcı sorgu) ikinci dereceden davranışa yol açıyordu.
    _kullanici_zaman: Dict[str, "np.ndarray"] = field(default_factory=dict, repr=False)
    _hedef_zaman: Dict[Tuple[str, str], "np.ndarray"] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ kurulum
    def ekle(self, kenar: Kenar) -> None:
        self._kullanici_kenarlari[kenar.kaynak].append(kenar)
        self._hedef_kullanicilari[(kenar.hedef_tur, kenar.hedef)].append((kenar.zaman.value, kenar.kaynak))
        self._sirali = False

    def sonlandir(self) -> "TemporalHeteroGraph":
        """Sorgulardan önce bir kez çağrılır: listeler sıralanır ve zaman dizileri (int64 ns) kurulur."""
        self._kullanici_zaman.clear()
        self._hedef_zaman.clear()
        for sid, liste in self._kullanici_kenarlari.items():
            liste.sort(key=lambda k: k.zaman)
            self._kullanici_zaman[sid] = np.fromiter((k.zaman.value for k in liste), dtype=np.int64, count=len(liste))
        self._hedef_sid.clear()
        # `popitem` ile tek tek alınır: dönüştürülen liste HEMEN serbest kalır. Döngü sonunda topluca clear()
        # yapmak, iki temsilin (ikili listesi + sid listesi/dizisi) bir süre YAN YANA durması demekti ve tepe
        # bellek asıl bağlayıcı kısıt olduğu için bu fark kritik.
        while self._hedef_kullanicilari:
            anahtar, liste = self._hedef_kullanicilari.popitem()
            liste.sort(key=lambda t: t[0])
            self._hedef_zaman[anahtar] = np.fromiter((ns for ns, _ in liste), dtype=np.int64, count=len(liste))
            self._hedef_sid[anahtar] = [sid for _, sid in liste]
            del liste
        self._sirali = True
        return self

    @classmethod
    def olaylardan(
        cls,
        events: pd.DataFrame,
        aktor_kolonu: str = "canonical",
        baslangic: Optional[pd.Timestamp] = None,
    ) -> "TemporalHeteroGraph":
        """Olay tablosundan graf kurar. Yalnız aktörü çözülmüş satırlar kullanılır.

        `baslangic` verilirse ondan ÖNCEKİ olaylar grafa alınmaz. Sinyaller yalnız `graf_gecmis_gun` kadar
        geriye bakar; boru hattı ise ısınma ve baz çizgisi için çok daha uzun bir tarihçe yükler. O tarihçeyi
        grafa koymak saf israftır: r6.2'de 201 günün tamamından kurmak ~29 GB, yalnız sorgulanan 120 günden
        kurmak ~17 GB demek.
        """
        g = cls()
        if events is None or not len(events):
            return g.sonlandir()
        ev = events[events[aktor_kolonu].notna()]
        if baslangic is not None:
            ev = ev[pd.to_datetime(ev["time"]) >= pd.Timestamp(baslangic)]
        zamanlar = pd.to_datetime(ev["time"]).to_numpy()
        aktorler = ev[aktor_kolonu].astype(str).to_numpy()
        for kolon, hedef_tur, iliski in KENAR_SEMASI:
            if kolon not in ev.columns:
                continue
            degerler = ev[kolon].astype("object").to_numpy()
            for t, sid, v in zip(zamanlar, aktorler, degerler):
                if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
                    continue
                g.ekle(Kenar(pd.Timestamp(t), sid, hedef_tur, str(v), iliski))
        if "action" in ev.columns:
            medya = ev[ev["action"].astype(str).isin(MEDYA_EYLEMLERI)]
            for t, sid, hedef in zip(
                pd.to_datetime(medya["time"]).to_numpy(),
                medya[aktor_kolonu].astype(str).to_numpy(),
                (medya["device"] if "device" in medya.columns else medya[aktor_kolonu]).astype(str).to_numpy(),
            ):
                g.ekle(Kenar(pd.Timestamp(t), sid, "medya", str(hedef), "kopyaladi"))
        return g.sonlandir()

    # ------------------------------------------------------------------ kayan pencere
    def kirp(self, esik: pd.Timestamp) -> int:
        """`esik`ten ESKİ kenarları atar ve atılan sayıyı döndürür. Davranışı değiştirmez, belleği düşürür.

        Sinyaller en fazla `graf_gecmis_gun` geriye bakar; o sınırın gerisindeki kenarlar hiçbir hesaba girmez.
        Buna rağmen grafı baştan sona bellekte tutmak r6.2'de 16,8 GB demekti ve 24 GB'lık makineye sığmıyordu.
        Kayan pencere, değerlendirme kurulumunu (pencere uzunluğu, örneklem, bölme) hiç değiştirmeden belleği
        kırpar — yani önceki koşularla karşılaştırılabilirlik korunur.

        Çağıran taraf eşiği güvenli seçmekle yükümlüdür: `gun - graf_gecmis_gun` ve biraz pay. Daha agresif bir
        eşik sinyalleri sessizce değiştirir, bu yüzden eşik yapılandırmadan türetilir, elle verilmez.
        """
        if not self._sirali:
            raise RuntimeError("sonlandir() çağrılmadan kırpılamaz")
        ns = pd.Timestamp(esik).value
        atilan = 0
        for sid in list(self._kullanici_kenarlari):
            zaman = self._kullanici_zaman[sid]
            kes = int(np.searchsorted(zaman, ns, "left"))
            if kes == 0:
                continue
            atilan += kes
            kalan = self._kullanici_kenarlari[sid][kes:]
            if kalan:
                self._kullanici_kenarlari[sid] = kalan
                self._kullanici_zaman[sid] = zaman[kes:]
            else:
                del self._kullanici_kenarlari[sid]
                del self._kullanici_zaman[sid]
        for anahtar in list(self._hedef_sid):
            zaman = self._hedef_zaman[anahtar]
            kes = int(np.searchsorted(zaman, ns, "left"))
            if kes == 0:
                continue
            kalan = self._hedef_sid[anahtar][kes:]
            if kalan:
                self._hedef_sid[anahtar] = kalan
                self._hedef_zaman[anahtar] = zaman[kes:]
            else:
                del self._hedef_sid[anahtar]
                del self._hedef_zaman[anahtar]
        return atilan

    # ------------------------------------------------------------------ sorgular
    @staticmethod
    def _sinirlar(n: int, zamanlar: "np.ndarray", t0, t1) -> Tuple[int, int]:
        """Zaman penceresinin [bas, son) indeksleri — dilim KOPYALAMADAN."""
        bas = int(np.searchsorted(zamanlar, pd.Timestamp(t0).value, "left")) if t0 is not None else 0
        son = int(np.searchsorted(zamanlar, pd.Timestamp(t1).value, "right")) if t1 is not None else n
        return bas, son

    def _dilim(self, liste: Sequence, zamanlar: "np.ndarray", t0, t1) -> Sequence:
        """Önceden kurulmuş int64 zaman dizisinde ikili arama — sorgu başına O(log n)."""
        if not self._sirali:
            raise RuntimeError("sonlandir() çağrılmadan sorgu yapılamaz")
        if not len(liste):
            return []
        bas, son = self._sinirlar(len(liste), zamanlar, t0, t1)
        return liste[bas:son]

    def kenarlar(self, kullanici: str, t0: Optional[pd.Timestamp] = None, t1: Optional[pd.Timestamp] = None) -> List[Kenar]:
        """Kullanıcının `[t0, t1]` aralığındaki kenarları (uçlar dahil)."""
        if not self._sirali:
            raise RuntimeError("sonlandir() çağrılmadan sorgu yapılamaz")
        liste = self._kullanici_kenarlari.get(kullanici, [])
        if not liste:
            return []
        return list(self._dilim(liste, self._kullanici_zaman[kullanici], t0, t1))

    def komsular(
        self,
        kullanici: str,
        t0: Optional[pd.Timestamp] = None,
        t1: Optional[pd.Timestamp] = None,
        hedef_tur: Optional[str] = None,
    ) -> Set[Tuple[str, str]]:
        """Zaman kısıtlı komşuluk: `{(hedef_tur, hedef)}`."""
        return {(k.hedef_tur, k.hedef) for k in self.kenarlar(kullanici, t0, t1) if hedef_tur is None or k.hedef_tur == hedef_tur}

    def ilk_gorulme(self, kullanici: str, hedef_tur: str, hedef: str) -> Optional[pd.Timestamp]:
        """Bu kullanıcının bu hedefi ilk kez dokunduğu an. Novelty hesabının temeli."""
        for k in self._kullanici_kenarlari.get(kullanici, []):
            if k.hedef_tur == hedef_tur and k.hedef == hedef:
                return k.zaman
        return None

    def hedefe_dokunan_kullanicilar(
        self, hedef_tur: str, hedef: str, t0: Optional[pd.Timestamp] = None, t1: Optional[pd.Timestamp] = None
    ) -> Set[str]:
        """Akran seyrekliği için: bu hedefe `[t0, t1]` içinde kaç farklı kullanıcı dokundu."""
        if not self._sirali:
            raise RuntimeError("sonlandir() çağrılmadan sorgu yapılamaz")
        anahtar = (hedef_tur, hedef)
        liste = self._hedef_sid.get(anahtar, [])
        if not liste:
            return set()
        return set(self._dilim(liste, self._hedef_zaman[anahtar], t0, t1))

    def akran_sayisi(
        self,
        hedef_tur: str,
        hedef: str,
        t0: Optional[pd.Timestamp] = None,
        t1: Optional[pd.Timestamp] = None,
        en_fazla: Optional[int] = None,
    ) -> int:
        """Hedefe dokunan farklı kullanıcı sayısı; `en_fazla` verilirse o sayıya ulaşınca **durur**.

        Seyreklik sorusu "3'ten az kullanıcı mı dokundu" biçimindedir; tam sayıya gerek yoktur. Popüler bir
        hedefte (ör. tek bir site kategorisinde milyonlarca kayıt) ilk birkaç kayıt cevabı verir. Erken çıkış
        olmadan her sorgu listenin tamamını tarıyordu ve gerçek veride gün başına dakikalara çıkıyordu.
        Döndürülen değer `en_fazla` ile sınırlıdır: eşik karşılaştırması için yeterli, tam sayım için değil.
        """
        if not self._sirali:
            raise RuntimeError("sonlandir() çağrılmadan sorgu yapılamaz")
        anahtar = (hedef_tur, hedef)
        liste = self._hedef_sid.get(anahtar, [])
        if not liste:
            return 0
        # Dilim KOPYALANMAZ: popüler bir hedefte milyonlarca kayıt var ve kopyalamanın kendisi erken çıkışı
        # anlamsız kılardı. İndeks aralığında gezilir, eşiğe ulaşınca durulur.
        bas, son = self._sinirlar(len(liste), self._hedef_zaman[anahtar], t0, t1)
        if en_fazla is None:
            return len(set(liste[bas:son]))
        gorulen: Set[str] = set()
        for i in range(bas, son):
            gorulen.add(liste[i])
            if len(gorulen) >= en_fazla:
                break
        return len(gorulen)

    def yeni_komsular(
        self, kullanici: str, t0: pd.Timestamp, t1: pd.Timestamp, gecmis_baslangic: Optional[pd.Timestamp] = None
    ) -> Set[Tuple[str, str]]:
        """`[t0, t1]` içinde dokunulan ama ÖNCESİNDE hiç dokunulmamış hedefler — ilişkisel yenilik."""
        simdi = self.komsular(kullanici, t0, t1)
        onceki = self.komsular(kullanici, gecmis_baslangic, t0 - pd.Timedelta(microseconds=1))
        return simdi - onceki

    # ------------------------------------------------------------------ istatistik
    @property
    def kullanicilar(self) -> List[str]:
        return sorted(self._kullanici_kenarlari)

    @property
    def kenar_sayisi(self) -> int:
        return sum(len(v) for v in self._kullanici_kenarlari.values())

    def tur_dagilimi(
        self, kullanici: str, t0: Optional[pd.Timestamp] = None, t1: Optional[pd.Timestamp] = None
    ) -> Dict[str, int]:
        """Kullanıcının kenarlarının hedef türüne göre dağılımı — davranış 'şekli'."""
        out: Dict[str, int] = defaultdict(int)
        for k in self.kenarlar(kullanici, t0, t1):
            out[k.hedef_tur] += 1
        return dict(out)

    def ozet(self) -> dict:
        turler: Dict[str, int] = defaultdict(int)
        for liste in self._kullanici_kenarlari.values():
            for k in liste:
                turler[k.hedef_tur] += 1
        return dict(
            kullanici=len(self._kullanici_kenarlari),
            kenar=self.kenar_sayisi,
            hedef=len(self._hedef_sid) or len(self._hedef_kullanicilari),
            tur_dagilimi=dict(sorted(turler.items())),
        )


def kenar_akisi(graf: TemporalHeteroGraph, kullanicilar: Optional[Iterable[str]] = None) -> List[Kenar]:
    """Tüm kenarları zaman sırasında döndürür — sıra modelleri (sequence model) için girdi."""
    hedef = list(kullanicilar) if kullanicilar is not None else graf.kullanicilar
    out: List[Kenar] = []
    for sid in hedef:
        out.extend(graf.kenarlar(sid))
    out.sort(key=lambda k: k.zaman)
    return out
