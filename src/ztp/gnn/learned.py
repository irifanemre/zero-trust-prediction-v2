"""Öğrenen graf gömme — sprint v6 katman C (`[ml]` eklentisi, `docs/sprint-v6-on-kayit.md`).

`TemporalGraphBaseline` elle yazılmış graf istatistikleri üretir (yenilik, seyreklik, tür kayması,
komşu riski) — gömme yok, eğitim yok. Bu modül o boşluğu kapatır.

**Ne olduğu ve ne olmadığı, açıkça.** Bu, yayınlardaki tam bir temporal GNN değildir: zaman kodlaması,
dikkat ve çok katmanlı mesaj geçişi yoktur. Olan şey, kullanıcı–hedef iki parçalı grafı üzerinde
**bir adım komşu toplamalı, kendi kendine denetimli bağlantı tahmini**dir. Böyle adlandırılmasının
sebebi, "GNN ekledik" demenin ölçtüğümüz şeyden fazlasını ima etmesidir.

**Neden kendi kendine denetimli.** Elimizde 34 insider var; denetimli eğitim bu sayıda pozitifle
ezberler. Bağlantı tahmini etiket GEREKTİRMEZ: model "bu kullanıcı hangi kaynaklara dokunur"u öğrenir,
anomali de "bugün dokunduğu şey modele göre şaşırtıcıydı" olur. Literatürün bu veride çalışan yolu
budur (GraphCAD / Anomal-E ailesi).

**Yenmesi gereken eşik 27/34'tür**, 22 değil. Ön kayıt bunu koşmadan önce yazdı: `tam` varyantı r4.2'de
22/34 veriyor ama basit graf ÇARPANI tek başına 27/34 veriyor. Öğrenen graf 24 bulup "tabanı geçtik"
derse geriye gidilmiş olur.

**Sızıntı.** Model yalnız `gun`'den ÖNCEKİ kenarlarla eğitilir; o günün erişimleri skorlanır ama
eğitime girmez. `gun_bitti()` eğitimi tetikler, `skorla()` tahmin eder; sıra `TemporalGrafOgrenen`
içinde zorunludur.
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
        "Öğrenen graf torch gerektirir: `pip install -e '.[ml]'`. "
        "Sessizce elle yazılmış istatistiklere düşülmez — hangi modelin koştuğu koşu kaydından okunabilmeli."
    ) from exc

LOG = logging.getLogger(__name__)

TOHUM = 20261030
# Eğitim için gereken en az (kullanıcı, hedef) çifti. Altında model kurulmaz: az kenardan öğrenilen
# gömme, gömme değil gürültüdür ve "öğrendi" diye raporlanması yanıltıcı olur.
MIN_KENAR = 500
MIN_KULLANICI = 20


class _Gomme(nn.Module):
    """Kullanıcı ve hedef gömmeleri + bir adım komşu toplama.

    Kullanıcının temsili = kendi gömmesi + dokunduğu hedeflerin gömmelerinin ortalaması. Tek adım,
    çünkü iki adım bu veride her kullanıcıyı birbirine bağlar (ortak kaynaklar çok yoğun) ve gömmeler
    birbirine çöker — ölçüldü değil, yoğunluktan beklenen; derinleştirmek ayrı bir deneydir.
    """

    def __init__(self, n_kullanici: int, n_hedef: int, boyut: int):
        super().__init__()
        self.u = nn.Embedding(n_kullanici, boyut)
        self.h = nn.Embedding(n_hedef, boyut)
        self.karisim = nn.Parameter(torch.tensor(0.5))
        nn.init.normal_(self.u.weight, std=0.1)
        nn.init.normal_(self.h.weight, std=0.1)

    def kullanici_temsili(self, u_idx: "torch.Tensor", komsu_ort: "torch.Tensor") -> "torch.Tensor":
        a = torch.sigmoid(self.karisim)
        return a * self.u(u_idx) + (1 - a) * komsu_ort

    def skor(self, temsil: "torch.Tensor", h_idx: "torch.Tensor") -> "torch.Tensor":
        return (temsil * self.h(h_idx)).sum(-1)


class GrafGommeModeli:
    """İki parçalı graf üzerinde kendi kendine denetimli bağlantı tahmini."""

    def __init__(
        self,
        boyut: int = 32,
        devir: int = 120,
        ogrenme_hizi: float = 0.05,
        negatif: int = 4,
        cihaz: Optional[str] = None,
    ):
        if boyut < 4:
            raise ValueError("boyut ≥ 4 olmalı")
        if negatif < 1:
            raise ValueError("negatif ≥ 1 olmalı")
        self.boyut, self.devir, self.ogrenme_hizi, self.negatif = boyut, devir, ogrenme_hizi, negatif
        # CPU VARSAYILAN, hız için değil DETERMİNİZM için: MPS'te `index_add_` kayan nokta toplamasını
        # atomik ve sırasız yapar, aynı kenar kümesi farklı ağırlıklar üretir (ölçüldü). Ağırlık sha256'sı
        # dondurma manifestine giriyor; yeniden üretilemeyen bir model o protokolü bozar. `cihaz="mps"`
        # açıkça seçilebilir ve `etkinlik()` onu rapora yazar — gizli bir hızlandırma olmaz.
        self.cihaz = cihaz or "cpu"
        self._model: Optional[_Gomme] = None
        self._u_idx: Dict[str, int] = {}
        self._h_idx: Dict[str, int] = {}
        self._komsu_ort: Optional["torch.Tensor"] = None
        self.egitim = 0
        self.son_kayip: Optional[float] = None
        self.n_kenar = 0

    @property
    def adi(self) -> str:
        return f"graf-gomme-{self.boyut}"

    @property
    def hazir(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------ eğitim
    def egit(self, kenarlar: Sequence[Tuple[str, str]]) -> bool:
        """`kenarlar`: (kullanıcı, hedef) çiftleri — yalnız GEÇMİŞTEN. Döndürür: eğitim yapıldı mı."""
        tekil = sorted(set(kenarlar))
        kullanicilar = sorted({u for u, _ in tekil})
        if len(tekil) < MIN_KENAR or len(kullanicilar) < MIN_KULLANICI:
            return False
        hedefler = sorted({h for _, h in tekil})
        self._u_idx = {u: i for i, u in enumerate(kullanicilar)}
        self._h_idx = {h: i for i, h in enumerate(hedefler)}
        self.n_kenar = len(tekil)

        torch.manual_seed(TOHUM)
        torch.use_deterministic_algorithms(True, warn_only=True)
        U = torch.tensor([self._u_idx[u] for u, _ in tekil], dtype=torch.long, device=self.cihaz)
        H = torch.tensor([self._h_idx[h] for _, h in tekil], dtype=torch.long, device=self.cihaz)
        model = _Gomme(len(kullanicilar), len(hedefler), self.boyut).to(self.cihaz)
        iyilestirici = torch.optim.Adam(model.parameters(), lr=self.ogrenme_hizi)
        uretec = torch.Generator(device="cpu").manual_seed(TOHUM)  # negatif örnekleme de deterministik
        kayip_f = nn.BCEWithLogitsLoss()
        model.train()
        kayip = None
        for _ in range(self.devir):
            komsu = self._komsu_ortalamasi(model, U, H, len(kullanicilar))
            temsil = model.kullanici_temsili(U, komsu[U])
            pozitif = model.skor(temsil, H)
            neg_h = torch.randint(0, len(hedefler), (len(H) * self.negatif,), generator=uretec).to(self.cihaz)
            neg_temsil = temsil.repeat(self.negatif, 1)
            negatif = model.skor(neg_temsil, neg_h)
            cikti = torch.cat([pozitif, negatif])
            hedef = torch.cat([torch.ones_like(pozitif), torch.zeros_like(negatif)])
            iyilestirici.zero_grad()
            kayip = kayip_f(cikti, hedef)
            kayip.backward()
            iyilestirici.step()
        model.eval()
        with torch.no_grad():
            self._komsu_ort = self._komsu_ortalamasi(model, U, H, len(kullanicilar))
        self._model = model
        self.egitim += 1
        self.son_kayip = round(float(kayip.detach().cpu()), 4) if kayip is not None else None
        LOG.debug("Graf gömme eğitildi: %d kenar, %d kullanıcı, kayıp %.4f", len(tekil), len(kullanicilar), self.son_kayip or 0)
        return True

    @staticmethod
    def _komsu_ortalamasi(model: _Gomme, U: "torch.Tensor", H: "torch.Tensor", n_kullanici: int) -> "torch.Tensor":
        """Her kullanıcı için dokunduğu hedeflerin gömme ortalaması — bir adım mesaj geçişi."""
        toplam = torch.zeros((n_kullanici, model.h.embedding_dim), device=U.device)
        toplam.index_add_(0, U, model.h(H))
        sayi = torch.zeros((n_kullanici, 1), device=U.device)
        sayi.index_add_(0, U, torch.ones((len(U), 1), device=U.device))
        return toplam / sayi.clamp(min=1.0)

    # ------------------------------------------------------------------ skorlama
    def skorla(self, kullanici: str, hedefler: Sequence[str]) -> Optional[float]:
        """Bugünkü erişimlerin ŞAŞIRTICILIĞI [0,1]: model bunları ne kadar beklemiyordu?

        Modelde hiç görülmemiş kullanıcı ya da bilinmeyen hedef → `None`. Uydurulmuş bir skor,
        skorun olmamasından kötüdür: kuyruğa sahte bir sinyalle girilmesine yol açar.
        """
        if self._model is None or self._komsu_ort is None or not hedefler:
            return None
        ui = self._u_idx.get(kullanici)
        if ui is None:
            return None
        hi = [self._h_idx[h] for h in hedefler if h in self._h_idx]
        if not hi:
            return None
        with torch.no_grad():
            u = torch.tensor([ui], dtype=torch.long, device=self.cihaz)
            temsil = self._model.kullanici_temsili(u, self._komsu_ort[u])
            h = torch.tensor(hi, dtype=torch.long, device=self.cihaz)
            olasilik = torch.sigmoid(self._model.skor(temsil.expand(len(hi), -1), h))
            # Şaşırtıcılık = en beklenmedik erişim (ortalama değil: tek bir uç erişim ortalamada kaybolur)
            return float(1.0 - olasilik.min().cpu())

    def agirlik_ozeti(self) -> Optional[str]:
        if self._model is None:
            return None
        h = hashlib.sha256()
        for ad, p in sorted(self._model.state_dict().items()):
            h.update(ad.encode("utf-8"))
            h.update(np.ascontiguousarray(p.detach().cpu().numpy()).tobytes())
        return h.hexdigest()

    def etkinlik(self) -> dict:
        return dict(
            graf_ogrenen_model=self.adi,
            graf_ogrenen_egitim=self.egitim,
            graf_ogrenen_kenar=self.n_kenar,
            graf_ogrenen_kullanici=len(self._u_idx),
            graf_ogrenen_hedef=len(self._h_idx),
            graf_ogrenen_kayip=self.son_kayip,
            graf_ogrenen_cihaz=self.cihaz,
            graf_ogrenen_agirlik_sha256=self.agirlik_ozeti(),
        )


class TemporalGrafOgrenen:
    """Günlük işletim: periyodik eğitim (geçmişten) + günlük skorlama (bugünden).

    Sıra bariyeri `gun()` içindedir: önce SKORLA (model geçmişle eğitilmiş), sonra bugünün kenarlarını
    geçmişe ekle. Tersi, modelin kendi cevabını görmesi olurdu.
    """

    def __init__(self, model: GrafGommeModeli, egitim_periyodu_gun: int = 14, gecmis_gun: int = 30):
        self.model = model
        self.egitim_periyodu_gun, self.gecmis_gun = egitim_periyodu_gun, gecmis_gun
        self._kenarlar: List[Tuple[pd.Timestamp, str, str]] = []
        self._son_egitim: Optional[pd.Timestamp] = None
        self.skorlanan = 0
        self.atlanan = 0

    def gun(self, gun: pd.Timestamp, bugunku: Dict[str, Sequence[str]]) -> Dict[str, float]:
        """`bugunku`: {kullanıcı: bugün dokunduğu hedefler}. Döndürür: {kullanıcı: şaşırtıcılık}."""
        gun = pd.Timestamp(gun)
        if self._egitim_gerekli(gun):
            esik = gun - self.gecmis_gun * pd.Timedelta(days=1)
            gecmis = [(u, h) for g, u, h in self._kenarlar if esik <= g < gun]
            if self.model.egit(gecmis):
                self._son_egitim = gun
        skorlar: Dict[str, float] = {}
        for sid in sorted(bugunku):
            s = self.model.skorla(sid, list(bugunku[sid]))
            if s is None:
                self.atlanan += 1
            else:
                skorlar[sid] = s
                self.skorlanan += 1
        for sid in sorted(bugunku):  # SKORLAMADAN SONRA: bugünün kenarları ancak şimdi geçmişe girer
            for h in bugunku[sid]:
                self._kenarlar.append((gun, sid, h))
        self._kirp(gun)
        return skorlar

    def _egitim_gerekli(self, gun: pd.Timestamp) -> bool:
        if not self.model.hazir:
            return len(self._kenarlar) >= MIN_KENAR
        return (gun - self._son_egitim).days >= self.egitim_periyodu_gun if self._son_egitim else True

    def _kirp(self, gun: pd.Timestamp) -> None:
        """Pencere dışına düşen kenarlar bellekte durmasın (r6.2'de 51M kenar görüldü)."""
        esik = gun - (self.gecmis_gun + 7) * pd.Timedelta(days=1)
        if len(self._kenarlar) > 4 * MIN_KENAR and self._kenarlar[0][0] < esik:
            self._kenarlar = [k for k in self._kenarlar if k[0] >= esik]

    def etkinlik(self) -> dict:
        return dict(
            **self.model.etkinlik(),
            graf_ogrenen_skorlanan=self.skorlanan,
            graf_ogrenen_atlanan=self.atlanan,
            graf_ogrenen_bellek_kenar=len(self._kenarlar),
        )
