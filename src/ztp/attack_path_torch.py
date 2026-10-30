"""Saldırı yolu tahmini — Transformer kolu (sprint v6 katman B, `[ml]` eklentisi).

`attack_path.NgramModeli` ile **aynı arayüz**: `ogren_gecis`, `gun_bitti`, `tahmin`, `etkinlik`,
`en_uzun_baglam`. Böylece `SaldiriYoluTahmincisi` hangi modelin koştuğunu bilmek zorunda kalmaz ve
ablasyonda tek bayrakla değiştirilebilir.

**Yenmesi gereken taban n-gram'dır**, sıfır değil. Ön kayıt (`docs/sprint-v6-on-kayit.md`) bunu
koşmadan önce yazdı: Transformer n-gram'ı geçemezse ağır model gereksizdir ve varsayılanda kapalı kalır.
Veri azdır (r4.2'de 34 insider), bu yüzden model de küçük tutulmuştur — 2 katman, 32 boyut. Daha büyüğü
bu veride ezberler.

**Determinizm.** torch tohumu sabitlenir, eğitim tek iş parçacığında koşar ve sıralama hep aynı sırada
yapılır. Aynı girdi aynı ağırlıkları üretir; `agirlik_ozeti()` koşu kaydına yazılır ki "model vardı ama
hangisiydi" durumu olmasın (21.2 / dondurma protokolü).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import torch
    import torch.nn as nn
except ImportError as exc:  # pragma: no cover - ortam bağımlı
    raise ImportError(
        "Transformer kolu torch gerektirir: `pip install -e '.[ml]'`. "
        "Sessizce n-gram'a düşülmez — hangi modelin koştuğu koşu kaydından okunabilmeli."
    ) from exc

from ztp.attack_path import BASLA, MIN_GECIS, YolTahmini

LOG = logging.getLogger(__name__)

PAD = "<pad>"
TOHUM = 1337


class _Govde(nn.Module):
    """Nedensel maskeli küçük kodlayıcı: gömme + konum + N katman + doğrusal baş."""

    def __init__(self, sozluk: int, boyut: int, katman: int, baslik: int, baglam: int):
        super().__init__()
        self.gomme = nn.Embedding(sozluk, boyut, padding_idx=0)
        self.konum = nn.Embedding(baglam, boyut)
        kat = nn.TransformerEncoderLayer(
            d_model=boyut, nhead=baslik, dim_feedforward=4 * boyut, batch_first=True, dropout=0.1
        )
        self.govde = nn.TransformerEncoder(kat, num_layers=katman)
        self.bas = nn.Linear(boyut, sozluk)
        self.baglam = baglam

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        n = x.shape[1]
        konumlar = torch.arange(n, device=x.device).unsqueeze(0)
        h = self.gomme(x) + self.konum(konumlar)
        maske = nn.Transformer.generate_square_subsequent_mask(n, device=x.device)
        return self.bas(self.govde(h, mask=maske, is_causal=True))


class TransformerModeli:
    """Taktik dizisi üzerinde nedensel dil modeli.

    `ogren_gecis` artımlı eğitmez — geçişleri biriktirir. Eğitim `gun_bitti()` ile periyodik yapılır,
    çünkü tek geçişle gradyan adımı atmak hem gürültülü hem pahalıdır.
    """

    def __init__(
        self,
        en_uzun_baglam: int = 8,
        boyut: int = 32,
        katman: int = 2,
        baslik: int = 4,
        egitim_periyodu_gun: int = 14,
        min_dizi: int = 30,
        devir: int = 60,
        ogrenme_hizi: float = 3e-3,
        cihaz: Optional[str] = None,
    ):
        if en_uzun_baglam < 2:
            raise ValueError("en_uzun_baglam ≥ 2 olmalı")
        if boyut % baslik:
            raise ValueError("boyut, baslik'in katı olmalı")
        self.en_uzun_baglam = en_uzun_baglam
        self.boyut, self.katman, self.baslik = boyut, katman, baslik
        self.egitim_periyodu_gun, self.min_dizi, self.devir, self.ogrenme_hizi = (
            egitim_periyodu_gun,
            min_dizi,
            devir,
            ogrenme_hizi,
        )
        # CPU varsayılan — determinizm için (bkz. `gnn/learned.py`: MPS'te kayan nokta toplama sırası
        # sabit değil ve ağırlık özeti değişiyor). `cihaz="mps"` açıkça seçilir ve rapora yazılır.
        self.cihaz = cihaz or "cpu"
        self._diziler: Dict[int, List[str]] = {}
        self._aktif: List[str] = []
        self._sozluk: List[str] = [PAD, BASLA]
        self._indeks: Dict[str, int] = {PAD: 0, BASLA: 1}
        self._model: Optional[_Govde] = None
        self._son_egitim: Optional[pd.Timestamp] = None
        self.gecis = 0
        self.egitim = 0
        self.son_kayip: Optional[float] = None

    @property
    def adi(self) -> str:
        return f"transformer-{self.katman}x{self.boyut}"

    # ------------------------------------------------------------------ veri
    def _id(self, taktik: str) -> int:
        if taktik not in self._indeks:
            self._indeks[taktik] = len(self._sozluk)
            self._sozluk.append(taktik)
        return self._indeks[taktik]

    def ogren_gecis(self, baglam: Sequence[str], sonraki: str) -> None:
        """Geçişi biriktirir. Bağlamın son elemanı dizinin devamıdır; yeni dizi BASLA ile başlar."""
        self._id(sonraki)
        if not self._aktif or list(baglam[-1:]) == [BASLA]:
            if self._aktif:
                self._diziler[len(self._diziler)] = self._aktif
            self._aktif = []
        self._aktif.append(sonraki)
        self.gecis += 1

    def ogren(self, dizi: Sequence[str]) -> None:
        for t in dizi:
            self._id(t)
        self._diziler[len(self._diziler)] = list(dizi)
        self.gecis += len(dizi)

    def _tum_diziler(self) -> List[List[str]]:
        d = [v for v in self._diziler.values() if v]
        if self._aktif:
            d = d + [self._aktif]
        return d

    def _toplu(self, diziler: Sequence[Sequence[str]]) -> Tuple["torch.Tensor", "torch.Tensor"]:
        """(girdi, hedef) — her dizi BASLA ile başlar, PAD ile hizalanır; hedefte PAD yok sayılır."""
        n = min(self.en_uzun_baglam, max(len(d) for d in diziler) + 1)
        X, Y = [], []
        for d in diziler:
            jeton = [self._indeks[BASLA]] + [self._id(t) for t in d]
            for bas in range(0, max(1, len(jeton) - 1), n - 1):
                parca = jeton[bas : bas + n]
                if len(parca) < 2:
                    continue
                girdi = parca[:-1] + [0] * (n - 1 - len(parca[:-1]))
                hedef = parca[1:] + [0] * (n - 1 - len(parca[1:]))
                X.append(girdi)
                Y.append(hedef)
        if not X:
            return torch.zeros((0, 1), dtype=torch.long), torch.zeros((0, 1), dtype=torch.long)
        return torch.tensor(X, dtype=torch.long), torch.tensor(Y, dtype=torch.long)

    # ------------------------------------------------------------------ eğitim
    def gun_bitti(self, gun: pd.Timestamp) -> bool:
        """Periyot dolduysa ve yeterli dizi varsa modeli SIFIRDAN eğitir.

        Sıfırdan eğitmek bilinçli: artımlı ince ayar, eski verinin ağırlığını zamanla kaybettirir ve
        sonucu eğitim sırasına bağımlı kılar. Veri küçük olduğu için tam eğitim zaten saniyeler sürer.
        """
        gun = pd.Timestamp(gun)
        if self._son_egitim is not None and (gun - self._son_egitim).days < self.egitim_periyodu_gun:
            return False
        diziler = self._tum_diziler()
        if len(diziler) < self.min_dizi:
            return False
        self._egit(diziler)
        self._son_egitim = gun
        return True

    def _egit(self, diziler: Sequence[Sequence[str]]) -> None:
        torch.manual_seed(TOHUM)
        torch.use_deterministic_algorithms(True, warn_only=True)
        X, Y = self._toplu(diziler)
        if not len(X):
            return
        model = _Govde(len(self._sozluk), self.boyut, self.katman, self.baslik, self.en_uzun_baglam).to(self.cihaz)
        model.train()
        iyilestirici = torch.optim.Adam(model.parameters(), lr=self.ogrenme_hizi)
        kayip_f = nn.CrossEntropyLoss(ignore_index=0)
        X, Y = X.to(self.cihaz), Y.to(self.cihaz)
        kayip = None
        for _ in range(self.devir):
            iyilestirici.zero_grad()
            cikti = model(X)
            kayip = kayip_f(cikti.reshape(-1, cikti.shape[-1]), Y.reshape(-1))
            kayip.backward()
            iyilestirici.step()
        model.eval()
        self._model = model
        self.egitim += 1
        self.son_kayip = round(float(kayip.detach().cpu()), 4) if kayip is not None else None
        LOG.debug("Saldırı yolu Transformer eğitildi: %d dizi, kayıp %.4f", len(diziler), self.son_kayip or 0.0)

    # ------------------------------------------------------------------ tahmin
    def tahmin(self, gecmis: Sequence[str], ust: int = 3) -> YolTahmini:
        gecmis = tuple(gecmis) or (BASLA,)
        if self._model is None or self.gecis < MIN_GECIS:
            return YolTahmini(gecmis[-3:], (), self.gecis, 0, self.adi)
        jeton = [self._indeks.get(t, self._indeks[BASLA]) for t in (BASLA, *gecmis)][-(self.en_uzun_baglam - 1) :]
        with torch.no_grad():
            cikti = self._model(torch.tensor([jeton], dtype=torch.long, device=self.cihaz))
            olasilik = torch.softmax(cikti[0, -1], dim=-1).cpu().numpy()
        # PAD ve BASLA aday değildir: ikisi de gerçek bir hamle değil
        adaylar = [(self._sozluk[i], float(olasilik[i])) for i in range(2, len(self._sozluk))]
        adaylar.sort(key=lambda x: (-x[1], x[0]))  # eşitlikte alfabetik — determinizm
        return YolTahmini(gecmis[-3:], tuple(adaylar[:ust]), self.gecis, len(jeton), self.adi)

    # ------------------------------------------------------------------ denetim
    def agirlik_ozeti(self) -> Optional[str]:
        """Eğitilmiş ağırlıkların sha256'sı — koşu kaydına yazılır, dondurma protokolünün gereği."""
        if self._model is None:
            return None
        h = hashlib.sha256()
        for ad, p in sorted(self._model.state_dict().items()):
            h.update(ad.encode("utf-8"))
            h.update(np.ascontiguousarray(p.detach().cpu().numpy()).tobytes())
        return h.hexdigest()

    def etkinlik(self) -> dict:
        return dict(
            yol_model=self.adi,
            yol_gecis=self.gecis,
            yol_sozluk=max(0, len(self._sozluk) - 2),
            yol_egitim_sayisi=self.egitim,
            yol_kayip=self.son_kayip,
            yol_cihaz=self.cihaz,
            yol_agirlik_sha256=self.agirlik_ozeti(),
        )
