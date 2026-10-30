"""Denetimsiz anomali kanalı — kurala BAĞLI OLMAYAN paralel skor (literatür haritası §1.2–1.4).

Neden var: r6.2 ölçümünde (`docs/r62-v4-olcumu.md`) kaçan insider **hiçbir kural tetiklemedi**. Graf riski skora
ÇARPAN olarak girdiği için `1,5 × 0 = 0` — tabanı sıfır olan kullanıcıya hiçbir çarpan ulaşamaz. v4'ün 1.173 ek
yanlış alarmı sıfır ek insider getirmesinin yapısal nedeni bu. Bu modül o tavanı kaldırır: kural tetiklenmese de
kullanıcı-gün özellik vektöründen doğrudan bir anomali skoru üretir.

İki dedektör, ikisi de `features.NUM_FEATURES` üzerinde çalışır:

- `Ecod` — ECOD (Li ve ark. 2022): her boyutun ampirik kuyruk olasılığı, toplanıp en uç yöne göre seçilir.
  Bu sistem için Isolation Forest'tan **daha uygun**: (1) parametresiz — ayarlanacak bir şey yok, dolayısıyla
  aşırı uyum riski yok; (2) tamamen deterministik — rastgelelik içermez; (3) sıra tabanlı olduğu için monoton
  dönüşümlere (log, ölçekleme) duyarsız; (4) **boyut başına katkı bedava gelir** → açıklanabilir (14.6).
- `Orman` — Isolation Forest (sklearn, sabit tohum). Literatürün standart tabanı; karşılaştırma için.

Kanal `AnomaliKanali` ile işletilir ve sızıntıya karşı iki kuralı vardır:
1. Uyum penceresi **skorlanan günden ÖNCE** biter; o günün verisi uyuma girmez.
2. Etiket kullanılmaz — ne cevap anahtarı ne analist etiketi. Tamamen denetimsiz.

Skor [0, 1] aralığına uyum penceresinin **kendi skor dağılımındaki yüzdelik** ile çevrilir; ham ECOD değeri
boyut sayısına bağlı olduğundan yorumlanamaz, yüzdelik yorumlanır (13.4 ile aynı gerekçe).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ztp.features import NUM_FEATURES

LOG = logging.getLogger(__name__)

# Uyum için gereken en az kullanıcı-gün. Altında kanal skor ÜRETMEZ (0 döner) — az veriyle uydurulan kuyruk
# olasılığı gürültüdür. 2801 kullanıcılı bir kurumda bir günlük veri bile bunu aşar; küçük kurumlarda ısınma uzar.
MIN_UYUM_SATIR = 200
# Ampirik kuyruk olasılığının tabanı: 1/(n+1). log(0) olmaz, skor sonlu kalır.
EPS_KUYRUK = 1e-12


@dataclass(frozen=True)
class AnomaliSonucu:
    skor: float  # [0, 1] — uyum penceresindeki yüzdelik
    ham: float  # ham dedektör çıktısı (boyut sayısına bağlı, karşılaştırılamaz)
    yon: str  # "sol" (beklenenden az) | "sag" (beklenenden çok) | "carpiklik"
    katkilar: Dict[str, float]  # boyut → o yöndeki -log(kuyruk olasılığı) katkısı

    def aciklama(self) -> str:
        if self.skor <= 0:
            return ""
        ilk = sorted(self.katkilar.items(), key=lambda kv: -kv[1])[:3]
        detay = ", ".join(f"{k} ({v:.1f})" for k, v in ilk if v > 0)
        taraf = {"sol": "beklenenden az", "sag": "beklenenden çok", "carpiklik": "çarpıklık yönünde"}[self.yon]
        return f"denetimsiz anomali: kurum dağılımında yüzdelik {self.skor:.3f} ({taraf}) — baskın boyutlar: {detay}"


class Ecod:
    """ECOD: boyut başına ampirik kuyruk olasılıkları, üç toplamın en büyüğü.

    Uyum: her boyutun sıralı değerleri ve çarpıklığı. Skor:
        sol_j  = P(X_j ≤ x_j),  sag_j = P(X_j ≥ x_j)       (ampirik, (n+1) paydasıyla)
        O_sol  = Σ_j −log sol_j
        O_sag  = Σ_j −log sag_j
        O_çarp = Σ_j −log (çarpıklık_j < 0 ? sol_j : sag_j)
        O      = max(O_sol, O_sag, O_çarp)
    Bir boyut tek değerden oluşuyorsa (varyans 0) katkısı sabittir ve sıralamayı etkilemez.
    """

    def __init__(self, ozellikler: Sequence[str] = tuple(NUM_FEATURES)):
        self.ozellikler = tuple(ozellikler)
        self._sirali: Optional[np.ndarray] = None  # (n, d) boyut başına sıralı uyum değerleri
        self._carpiklik: Optional[np.ndarray] = None  # (d,)
        self._uyum_skorlari: Optional[np.ndarray] = None  # (n,) sıralı — yüzdeliğe çevirmek için
        self.n_uyum = 0

    def uyumla(self, X: np.ndarray) -> "Ecod":
        X = np.asarray(X, dtype=float)
        if X.ndim != 2 or X.shape[1] != len(self.ozellikler):
            raise ValueError(f"ECOD: ({'n'}, {len(self.ozellikler)}) bekleniyordu, {X.shape} geldi")
        if len(X) < MIN_UYUM_SATIR:
            raise ValueError(f"ECOD: uyum için en az {MIN_UYUM_SATIR} satır gerekir ({len(X)} geldi)")
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        self._sirali = np.sort(X, axis=0)
        ort = X.mean(axis=0)
        std = X.std(axis=0)
        std_guvenli = np.where(std > 0, std, 1.0)
        self._carpiklik = (((X - ort) / std_guvenli) ** 3).mean(axis=0)
        self.n_uyum = len(X)
        # kendi uyum kümesini skorla: yüzdelik dönüşümünün referansı
        ham, _, _ = self._ham(X)
        self._uyum_skorlari = np.sort(ham)
        return self

    def _kuyruklar(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Her (satır, boyut) için ampirik sol ve sağ kuyruk olasılıkları."""
        assert self._sirali is not None
        n = self.n_uyum
        sol = np.empty(X.shape, dtype=float)
        sag = np.empty(X.shape, dtype=float)
        for j in range(X.shape[1]):
            kolon = self._sirali[:, j]
            # sol_j = #(uyum ≤ x) / (n+1);  sag_j = #(uyum ≥ x) / (n+1)
            sol[:, j] = np.searchsorted(kolon, X[:, j], side="right") / (n + 1.0)
            sag[:, j] = (n - np.searchsorted(kolon, X[:, j], side="left")) / (n + 1.0)
        taban = 1.0 / (n + 1.0)
        return np.maximum(sol, taban), np.maximum(sag, taban)

    def _ham(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(skor, yon_indeksi, boyut_katkilari) — yon: 0 sol, 1 sağ, 2 çarpıklık."""
        assert self._carpiklik is not None
        X = np.nan_to_num(np.asarray(X, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        sol, sag = self._kuyruklar(X)
        t_sol, t_sag = -np.log(np.maximum(sol, EPS_KUYRUK)), -np.log(np.maximum(sag, EPS_KUYRUK))
        t_carp = np.where(self._carpiklik[None, :] < 0, t_sol, t_sag)
        yiginlar = np.stack([t_sol.sum(axis=1), t_sag.sum(axis=1), t_carp.sum(axis=1)], axis=1)
        yon = np.argmax(yiginlar, axis=1)
        skor = yiginlar[np.arange(len(X)), yon]
        katki = np.stack([t_sol, t_sag, t_carp], axis=0)[yon, np.arange(len(X))]
        return skor, yon, katki

    def skorla(self, X: np.ndarray) -> List[AnomaliSonucu]:
        if self._uyum_skorlari is None:
            raise RuntimeError("ECOD: önce uyumla() çağrılmalı")
        ham, yon, katki = self._ham(X)
        n = len(self._uyum_skorlari)
        yuzdelik = np.searchsorted(self._uyum_skorlari, ham, side="left") / n
        adlar = ("sol", "sag", "carpiklik")
        return [
            AnomaliSonucu(
                skor=float(yuzdelik[i]),
                ham=float(ham[i]),
                yon=adlar[int(yon[i])],
                katkilar={ad: float(v) for ad, v in zip(self.ozellikler, katki[i])},
            )
            for i in range(len(ham))
        ]


class Orman:
    """Isolation Forest sarmalayıcı — literatürün standart tabanı (sabit tohum → deterministik).

    ECOD'un aksine parametre taşır (`n_estimators`, `max_samples`) ve sıra tabanlı değildir, bu yüzden ağır
    kuyruklu sayımlarda `log1p` uygulanır. Yalnız karşılaştırma için: üretim yolu ECOD'dur.
    """

    def __init__(self, ozellikler: Sequence[str] = tuple(NUM_FEATURES), n_agac: int = 200, tohum: int = 0):
        self.ozellikler = tuple(ozellikler)
        self.n_agac, self.tohum = n_agac, tohum
        self._model = None
        self._uyum_skorlari: Optional[np.ndarray] = None
        self.n_uyum = 0

    @staticmethod
    def _don(X: np.ndarray) -> np.ndarray:
        X = np.nan_to_num(np.asarray(X, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        return np.sign(X) * np.log1p(np.abs(X))

    def uyumla(self, X: np.ndarray) -> "Orman":
        from sklearn.ensemble import IsolationForest

        X = np.asarray(X, dtype=float)
        if len(X) < MIN_UYUM_SATIR:
            raise ValueError(f"Orman: uyum için en az {MIN_UYUM_SATIR} satır gerekir ({len(X)} geldi)")
        self._model = IsolationForest(n_estimators=self.n_agac, random_state=self.tohum, n_jobs=1).fit(self._don(X))
        self.n_uyum = len(X)
        self._uyum_skorlari = np.sort(-self._model.score_samples(self._don(X)))
        return self

    def skorla(self, X: np.ndarray) -> List[AnomaliSonucu]:
        if self._model is None or self._uyum_skorlari is None:
            raise RuntimeError("Orman: önce uyumla() çağrılmalı")
        ham = -self._model.score_samples(self._don(X))
        n = len(self._uyum_skorlari)
        yuzdelik = np.searchsorted(self._uyum_skorlari, ham, side="left") / n
        # Isolation Forest boyut başına katkı vermez; katkı sözlüğü boş bırakılır (uydurulmaz).
        return [AnomaliSonucu(skor=float(yuzdelik[i]), ham=float(ham[i]), yon="sag", katkilar={}) for i in range(len(ham))]


DEDEKTORLER = {"ecod": Ecod, "orman": Orman}


class AnomaliKanali:
    """Kayan pencereli denetimsiz kanal: periyodik uyum + günlük skorlama.

    `yenileme_gun` günde bir, `[gun − pencere_gun, gun)` aralığındaki kullanıcı-günlerle yeniden uyumlanır.
    Aralık **yarı açıktır**: skorlanan günün verisi uyuma girmez (sızıntı yok).
    """

    def __init__(self, tur: str = "ecod", pencere_gun: int = 30, yenileme_gun: int = 7):
        if tur not in DEDEKTORLER:
            raise ValueError(f"anomali dedektörü: {' | '.join(DEDEKTORLER)}")
        self.tur, self.pencere_gun, self.yenileme_gun = tur, int(pencere_gun), int(yenileme_gun)
        self._dedektor = None
        self._uyum_gunu: Optional[pd.Timestamp] = None
        self.uyum_sayisi = 0
        self.skorlanan = 0
        self.atlanan_gun = 0

    def _uyum_gerekli(self, gun: pd.Timestamp) -> bool:
        if self._dedektor is None or self._uyum_gunu is None:
            return True
        return (gun - self._uyum_gunu).days >= self.yenileme_gun

    def gun(self, gun: pd.Timestamp, feats: pd.DataFrame, bugun: pd.DataFrame) -> Dict[str, AnomaliSonucu]:
        """`feats`: tüm geçmiş kullanıcı-günler (en az `sid`, `day` + NUM_FEATURES). `bugun`: o günün satırları."""
        if bugun is None or not len(bugun):
            return {}
        kolonlar = [k for k in NUM_FEATURES if k in feats.columns]
        if len(kolonlar) != len(NUM_FEATURES):
            eksik = sorted(set(NUM_FEATURES) - set(kolonlar))
            raise ValueError(f"anomali kanalı: özellik kolonları eksik: {eksik}")
        if self._uyum_gerekli(gun):
            pencere = feats[(feats["day"] >= gun - self.pencere_gun * pd.Timedelta(days=1)) & (feats["day"] < gun)]
            if len(pencere) < MIN_UYUM_SATIR:
                self.atlanan_gun += 1
                return {}
            self._dedektor = DEDEKTORLER[self.tur]().uyumla(pencere[kolonlar].to_numpy(dtype=float))
            self._uyum_gunu = gun
            self.uyum_sayisi += 1
            LOG.debug("Anomali kanalı (%s) uyumlandı: %d satır, gün %s", self.tur, len(pencere), gun.date())
        if self._dedektor is None:
            self.atlanan_gun += 1
            return {}
        sonuc = self._dedektor.skorla(bugun[kolonlar].to_numpy(dtype=float))
        self.skorlanan += len(sonuc)
        return {str(sid): s for sid, s in zip(bugun["sid"].tolist(), sonuc)}

    def etkinlik(self) -> dict:
        return dict(
            anomali_tur=self.tur,
            anomali_uyum=self.uyum_sayisi,
            anomali_skorlanan=self.skorlanan,
            anomali_atlanan_gun=self.atlanan_gun,
            anomali_uyum_satir=(self._dedektor.n_uyum if self._dedektor is not None else 0),
        )
