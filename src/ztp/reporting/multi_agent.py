"""Çok ajanlı SOC raporlaması — Investigator / Verifier / Reporter (revizeler.txt §7.3).

Tek bir modele "şu vakayı incele ve raporla" demek üç işi birbirine karıştırır: kanıt toplamak, tekniği teyit
etmek ve anlatmak. Karıştığında hata da karışır — model bir tekniği yanlış hatırlayıp o yanlışın üstüne
anlatı kurar ve çıktı tutarlı göründüğü için yakalanması zorlaşır.

Burada üç ajan ayrı sorumlulukla ve **azalan yetkiyle** çalışır:

| Ajan | İşi | LLM kullanır mı | Çıktısı |
|---|---|---|---|
| 1. Investigator | Ham kanıtı toplar, zaman serisine dizer | **hayır** | olgu listesi |
| 2. Verifier | ATT&CK tekniğini SHA-256 imzalı yerel tabandan teyit eder | **hayır** | teyit/ret + pasaj |
| 3. Reporter | Yönetici özeti ve SOC talimatı üretir | evet (varsa) | metin |

Tasarım kararları:

- **Investigator ve Verifier deterministiktir.** Olgular ve teknik teyidi modele bırakılmaz; model yalnızca
  *anlatır*. Böylece bir halüsinasyon rapor metnini bozabilir ama kanıtı ya da teknik eşlemesini bozamaz.
- **Verifier yalnızca imzalı tabandan konuşur.** Tabanda karşılığı olmayan teknik `teyit_edilmedi` olarak
  işaretlenir ve Reporter'a **verilmez**; rapor doğrulanmamış teknik adı içeremez.
- **Reporter'ın çıktısı kanıt doğrulayıcıdan geçer** (`llm_guards.claim_verifier`): referansı olmayan cümleler
  silinir. Model hiç çalışmazsa ya da tüm cümleleri silinirse Investigator'ın olgularından deterministik bir
  metin üretilir — rapor **her hâlükârda** çıkar ve kaynağı `kaynak` alanında yazar.
- **Zincir kaydedilir.** `AjanIzi` her adımın girdisini, çıktısını ve kararını tutar; "bu cümle nereden çıktı"
  sorusu adım adım cevaplanabilir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence

from ztp.llm_guards.claim_verifier import Katilik, dogrula
from ztp.reporting.rag import AttackKnowledgeBase, Passage

LOG = logging.getLogger(__name__)
MAX_OLGU = 20


class Ozetleyici(Protocol):
    """Reporter'ın kullandığı model arayüzü — `LLMReporter` bunu karşılar."""

    def summarize(self, case: dict) -> object: ...


@dataclass
class AjanIzi:
    ajan: str
    karar: str
    ayrinti: dict = field(default_factory=dict)


@dataclass
class Olgu:
    """Investigator'ın ürettiği tek bir doğrulanabilir olgu."""

    sira: int
    kural: str
    ad: str
    kanit: List[str]
    katki: float = 0.0

    def metin(self) -> str:
        ev = ", ".join(self.kanit[:3]) if self.kanit else "seri"
        return f"{self.ad} [{self.kural}] [{ev}]"


@dataclass
class SocRaporu:
    yonetici_ozeti: str
    soc_talimati: List[str]
    olgular: List[Olgu]
    teyitli_teknikler: List[str]
    teyitsiz_teknikler: List[str]
    kaynak: str  # "llm" | "llm+silme" | "sablon"
    iz: List[AjanIzi] = field(default_factory=list)
    dogrulama: dict = field(default_factory=dict)

    def ozet(self) -> dict:
        return dict(
            kaynak=self.kaynak,
            olgu=len(self.olgular),
            teyitli_teknik=self.teyitli_teknikler,
            teyitsiz_teknik=self.teyitsiz_teknikler,
            dogrulama=self.dogrulama,
            iz=[dict(ajan=a.ajan, karar=a.karar, **a.ayrinti) for a in self.iz],
        )


# --------------------------------------------------------------------------------- 1. Investigator
class Investigator:
    """Ham kanıtı toplar ve zaman serisine dizer. LLM kullanmaz — olgular modele bırakılmayacak kadar önemlidir."""

    def calistir(self, case: dict) -> List[Olgu]:
        tespitler = case.get("tespitler") or []
        sirali = sorted(tespitler, key=lambda h: (-float(h.get("katki", 0) or 0), str(h.get("kural", ""))))
        return [
            Olgu(
                sira=i,
                kural=str(h.get("kural", "?")),
                ad=str(h.get("ad", "")),
                kanit=[str(e) for e in (h.get("kanit") or [])][:3],
                katki=float(h.get("katki", 0) or 0),
            )
            for i, h in enumerate(sirali[:MAX_OLGU], 1)
        ]


# --------------------------------------------------------------------------------- 2. Verifier
class Verifier:
    """ATT&CK tekniklerini SHA-256 imzalı yerel bilgi tabanından teyit eder. Tabanda yoksa teyit YOK."""

    def __init__(self, kb: Optional[AttackKnowledgeBase] = None):
        self.kb = kb

    def calistir(self, teknikler: Sequence[str]) -> tuple[List[str], List[str], List[Passage]]:
        benzersiz = sorted({str(t).strip().upper() for t in teknikler if str(t).strip()})
        if self.kb is None:
            return [], benzersiz, []  # taban yoksa hiçbir teknik teyitli sayılmaz
        teyitli, teyitsiz, pasajlar = [], [], []
        for t in benzersiz:
            p = self.kb.get(t)
            if p is None:
                teyitsiz.append(t)
            else:
                teyitli.append(t)
                pasajlar.append(p)
        return teyitli, teyitsiz, pasajlar


# --------------------------------------------------------------------------------- 3. Reporter
class Reporter:
    """Yönetici özeti ve SOC talimatı üretir. Model çıktısı kanıt doğrulayıcıdan geçmeden rapora girmez."""

    def __init__(self, ozetleyici: Optional[Ozetleyici] = None, katilik: Katilik = "dengeli"):
        self.ozetleyici = ozetleyici
        self.katilik = katilik

    @staticmethod
    def _sablon(olgular: Sequence[Olgu], teyitli: Sequence[str]) -> str:
        if not olgular:
            return "Vakada raporlanabilir tespit yok."
        bas = "; ".join(o.metin() for o in olgular[:3])
        tek = f" Teyit edilen ATT&CK teknikleri: {', '.join(teyitli)}." if teyitli else ""
        return f"Öne çıkan tespitler: {bas}.{tek}"

    @staticmethod
    def _talimat(olgular: Sequence[Olgu], teyitli: Sequence[str]) -> List[str]:
        adimlar = [f"{o.kural} tespitinin kanıtını doğrula: {', '.join(o.kanit) or 'seri kanıtı'}" for o in olgular[:5]]
        if teyitli:
            adimlar.append(f"Teyit edilen teknikler için runbook'u uygula: {', '.join(teyitli)}")
        adimlar.append("Bulguyu etiketle (doğru/yanlış pozitif) — etiket bir sonraki kalibrasyona girer")
        return adimlar

    def calistir(self, case: dict, olgular: Sequence[Olgu], teyitli: Sequence[str]) -> tuple[str, str, dict]:
        sablon = self._sablon(olgular, teyitli)
        if self.ozetleyici is None:
            return sablon, "sablon", {}
        try:
            sonuc = self.ozetleyici.summarize(case)
            ham = getattr(sonuc, "text", "") or ""
        except Exception as exc:  # model hatası raporu düşürmez
            LOG.warning("Reporter modeli başarısız (%s) — şablona düşüldü", exc)
            return sablon, "sablon", {"hata": str(exc)[:120]}
        if not ham.strip():
            return sablon, "sablon", {"hata": "boş model çıktısı"}
        d = dogrula(ham, case, katilik=self.katilik)
        if not d.metin.strip():  # her cümlesi silindi — model hiçbir şeyi kanıta bağlayamamış
            return sablon, "sablon", d.ozet()
        return d.metin, ("llm" if d.temiz else "llm+silme"), d.ozet()


# --------------------------------------------------------------------------------- orkestrasyon
class MultiAgentSoc:
    """Üç ajanı sırayla çalıştırır ve zinciri kaydeder."""

    def __init__(
        self,
        kb: Optional[AttackKnowledgeBase] = None,
        ozetleyici: Optional[Ozetleyici] = None,
        katilik: Katilik = "dengeli",
    ):
        self.investigator = Investigator()
        self.verifier = Verifier(kb)
        self.reporter = Reporter(ozetleyici, katilik)

    @staticmethod
    def _teknikler(case: dict) -> List[str]:
        out: List[str] = []
        for h in case.get("tespitler") or []:
            out.extend(str(t) for t in (h.get("teknikler") or h.get("attack") or []))
        out.extend(str(t) for t in (case.get("teknikler") or []))
        return out

    def calistir(self, case: dict) -> SocRaporu:
        iz: List[AjanIzi] = []

        olgular = self.investigator.calistir(case)
        iz.append(AjanIzi("investigator", "olgular derlendi", {"olgu": len(olgular)}))

        teyitli, teyitsiz, pasajlar = self.verifier.calistir(self._teknikler(case))
        iz.append(
            AjanIzi(
                "verifier",
                "teknikler denetlendi",
                {"teyitli": teyitli, "teyitsiz": teyitsiz, "imzali_taban": self.verifier.kb is not None},
            )
        )
        if teyitsiz:
            LOG.info("Teyit edilemeyen teknikler rapora alınmadı: %s", teyitsiz)

        metin, kaynak, dogrulama = self.reporter.calistir(case, olgular, teyitli)
        iz.append(AjanIzi("reporter", f"özet üretildi ({kaynak})", {"silinen": dogrulama.get("silinen", 0)}))

        return SocRaporu(
            yonetici_ozeti=metin,
            soc_talimati=Reporter._talimat(olgular, teyitli),
            olgular=list(olgular),
            teyitli_teknikler=teyitli,
            teyitsiz_teknikler=teyitsiz,
            kaynak=kaynak,
            iz=iz,
            dogrulama=dogrulama,
        )


def pasaj_haritasi(pasajlar: Sequence[Passage]) -> Dict[str, str]:
    """Teyitli tekniklerin pasaj metinleri — raporu okuyan analist için referans."""
    return {p.technique: p.as_text() for p in pasajlar if getattr(p, "technique", None)}
