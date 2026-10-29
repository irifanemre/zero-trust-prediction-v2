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
    _hedef_kullanicilari: Dict[Tuple[str, str], List[Tuple[pd.Timestamp, str]]] = field(default_factory=lambda: defaultdict(list))
    _sirali: bool = False
    # Zaman dizileri `sonlandir()`'da BİR KEZ kurulur. Sorgu başına yeniden kurmak O(n) maliyet demekti ve
    # gerçek veride (13M+ olay, 90 gün × ~1000 kullanıcı sorgu) ikinci dereceden davranışa yol açıyordu.
    _kullanici_zaman: Dict[str, "np.ndarray"] = field(default_factory=dict, repr=False)
    _hedef_zaman: Dict[Tuple[str, str], "np.ndarray"] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ kurulum
    def ekle(self, kenar: Kenar) -> None:
        self._kullanici_kenarlari[kenar.kaynak].append(kenar)
        self._hedef_kullanicilari[(kenar.hedef_tur, kenar.hedef)].append((kenar.zaman, kenar.kaynak))
        self._sirali = False

    def sonlandir(self) -> "TemporalHeteroGraph":
        """Sorgulardan önce bir kez çağrılır: listeler sıralanır ve zaman dizileri (int64 ns) kurulur."""
        self._kullanici_zaman.clear()
        self._hedef_zaman.clear()
        for sid, liste in self._kullanici_kenarlari.items():
            liste.sort(key=lambda k: k.zaman)
            self._kullanici_zaman[sid] = np.fromiter((k.zaman.value for k in liste), dtype=np.int64, count=len(liste))
        for anahtar, liste in self._hedef_kullanicilari.items():
            liste.sort(key=lambda t: t[0])
            self._hedef_zaman[anahtar] = np.fromiter((t.value for t, _ in liste), dtype=np.int64, count=len(liste))
        self._sirali = True
        return self

    @classmethod
    def olaylardan(cls, events: pd.DataFrame, aktor_kolonu: str = "canonical") -> "TemporalHeteroGraph":
        """Olay tablosundan graf kurar. Yalnız aktörü çözülmüş satırlar kullanılır."""
        g = cls()
        if events is None or not len(events):
            return g.sonlandir()
        ev = events[events[aktor_kolonu].notna()]
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

    # ------------------------------------------------------------------ sorgular
    def _dilim(self, liste: Sequence, zamanlar: "np.ndarray", t0, t1) -> Sequence:
        """Önceden kurulmuş int64 zaman dizisinde ikili arama — sorgu başına O(log n)."""
        if not self._sirali:
            raise RuntimeError("sonlandir() çağrılmadan sorgu yapılamaz")
        if not len(liste):
            return []
        bas = int(np.searchsorted(zamanlar, pd.Timestamp(t0).value, "left")) if t0 is not None else 0
        son = int(np.searchsorted(zamanlar, pd.Timestamp(t1).value, "right")) if t1 is not None else len(liste)
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
        liste = self._hedef_kullanicilari.get(anahtar, [])
        if not liste:
            return set()
        return {sid for _, sid in self._dilim(liste, self._hedef_zaman[anahtar], t0, t1)}

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
            hedef=len(self._hedef_kullanicilari),
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
