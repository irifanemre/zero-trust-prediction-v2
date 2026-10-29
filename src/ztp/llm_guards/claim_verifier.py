"""Kanıt doğrulayıcı — referansı olmayan iddiaları rapordan siler (revizeler.txt §7.2).

`reporting/llm.py::validate` rapora **bütün olarak** bakar: bir sorun bulursa tüm özeti reddeder. Bu, iyi
cümlelerle birlikte kötüleri de atar ve modelin tek bir uydurma yüzünden hiç çıktı üretememesine yol açar.

Bu modül daha ince çalışır: metni cümlelere böler, her cümlenin arkasındaki **olay kimliği (E-…)** ve
**kural kimliğini (UEBA-0001 gibi)** vakanın kanıtına karşı çapraz denetler, desteklenmeyen cümleyi **siler** ve
neyin neden silindiğini döndürür. Kalan metin, her cümlesi kanıta bağlı bir rapordur.

## Kararlar

- **Sessiz silme yok.** Her silinen cümle gerekçesiyle `silinenler` listesine girer; çağıran taraf isterse
  denetim kütüğüne yazar. Rapor kısaldıysa bunun nedeni görünür olur.
- **Sayısal topraklama.** 3+ haneli bir sayı kanıt metninde geçmiyorsa cümle uydurma hacim/adet içeriyor
  demektir ve referansı olsa bile silinir.
- **İki katılık düzeyi.** `siki`: her cümle en az bir geçerli referans taşımalı. `dengeli`: yalnız **iddia
  taşıyan** cümleler (sayı, kimlik ya da varlık adı geçenler) referans ister; "Vaka incelemeye alınmalıdır"
  gibi yönlendirme cümleleri referanssız kalabilir. Varsayılan `dengeli`.
- **Geçersiz referans, referanssızlıktan beterdir.** Vakada olmayan bir `E-…` ya da kural kimliği geçen cümle
  her iki düzeyde de silinir; bu, modelin kanıt uydurduğunun en güçlü işaretidir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Sequence, Set, Tuple

OLAY_RX = re.compile(r"E-[0-9a-fA-F]{6,8}")
KURAL_RX = re.compile(r"\b(?:UEBA|PRED|REL|HONEY|DQ)-[0-9A-Z]{2,6}\b")
SERI_RX = re.compile(r"\[(?:seri|graf|ik|akran)[^\]]*\]")  # şablonun ürettiği kanıt işaretleri
SAYI_RX = re.compile(r"(?<![\w.-])\d{3,}(?:[.,]\d+)?")
VARLIK_RX = re.compile(r"\bU-\d{4}\b|\bPC-[\w-]+\b")
# Cümle sonu: nokta/soru/ünlem + boşluk. Kısaltma ve ondalık ayırıcıdan korunmak için basit bakışlar kullanılır.
CUMLE_RX = re.compile(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ])")

Katilik = Literal["siki", "dengeli"]


@dataclass
class CumleKarari:
    cumle: str
    tutuldu: bool
    gerekce: str
    referanslar: List[str] = field(default_factory=list)


@dataclass
class DogrulamaSonucu:
    metin: str
    silinenler: List[CumleKarari]
    tutulanlar: List[CumleKarari]
    katilik: Katilik

    @property
    def temiz(self) -> bool:
        return not self.silinenler

    @property
    def silinen_oran(self) -> float:
        n = len(self.silinenler) + len(self.tutulanlar)
        return round(len(self.silinenler) / n, 3) if n else 0.0

    def ozet(self) -> dict:
        return dict(
            katilik=self.katilik,
            cumle=len(self.silinenler) + len(self.tutulanlar),
            tutulan=len(self.tutulanlar),
            silinen=len(self.silinenler),
            silinen_oran=self.silinen_oran,
            gerekceler=[dict(cumle=s.cumle[:120], gerekce=s.gerekce) for s in self.silinenler],
        )


def izinli_referanslar(clean: dict) -> Tuple[Set[str], Set[str]]:
    """Vakanın kanıtında gerçekten bulunan olay ve kural kimlikleri."""
    olaylar: Set[str] = {e for h in clean.get("tespitler", []) for e in h.get("kanit", []) or []}
    olaylar |= {e for v in (clean.get("kanit_serileri") or {}).values() for e in (v or [])}
    kurallar: Set[str] = {h.get("kural", "") for h in clean.get("tespitler", [])} - {""}
    return {o.upper() for o in olaylar}, {k.upper() for k in kurallar}


def cumlelere_bol(metin: str) -> List[str]:
    """Metni cümlelere böler. Madde imli satırlar kendi başına cümle sayılır."""
    parcalar: List[str] = []
    for satir in metin.splitlines():
        s = satir.strip()
        if not s:
            continue
        parcalar.extend(p.strip() for p in CUMLE_RX.split(s) if p.strip())
    return parcalar


def _iddia_mi(cumle: str) -> bool:
    """Cümle doğrulanabilir bir olgu iddiası taşıyor mu: sayı, kimlik ya da varlık adı geçiyor mu."""
    return bool(SAYI_RX.search(cumle) or OLAY_RX.search(cumle) or KURAL_RX.search(cumle) or VARLIK_RX.search(cumle))


def dogrula(
    metin: str,
    clean: dict,
    katilik: Katilik = "dengeli",
    izinli_olay: Sequence[str] | None = None,
    izinli_kural: Sequence[str] | None = None,
) -> DogrulamaSonucu:
    """Cümle cümle denetler; desteklenmeyen iddiaları siler ve gerekçeleriyle birlikte döndürür."""
    if katilik not in ("siki", "dengeli"):
        raise ValueError("katilik 'siki' ya da 'dengeli' olmalı")
    olaylar, kurallar = izinli_referanslar(clean)
    if izinli_olay is not None:
        olaylar = {o.upper() for o in izinli_olay}
    if izinli_kural is not None:
        kurallar = {k.upper() for k in izinli_kural}
    kanit_metni = json.dumps(clean, ensure_ascii=False)

    tutulan: List[CumleKarari] = []
    silinen: List[CumleKarari] = []
    for cumle in cumlelere_bol(metin):
        olay_ref = [m.upper() for m in OLAY_RX.findall(cumle)]
        kural_ref = [m.upper() for m in KURAL_RX.findall(cumle)]
        seri_ref = SERI_RX.findall(cumle)
        refs = olay_ref + kural_ref + seri_ref

        gecersiz_olay = [r for r in olay_ref if r not in olaylar]
        gecersiz_kural = [r for r in kural_ref if r not in kurallar]
        topraksiz = [n for n in SAYI_RX.findall(cumle) if n not in kanit_metni and n.replace(",", ".") not in kanit_metni]

        if gecersiz_olay:
            karar = CumleKarari(cumle, False, f"vakada olmayan olay kimliği: {sorted(set(gecersiz_olay))[:3]}", refs)
        elif gecersiz_kural:
            karar = CumleKarari(cumle, False, f"vakada olmayan kural kimliği: {sorted(set(gecersiz_kural))[:3]}", refs)
        elif topraksiz:
            karar = CumleKarari(cumle, False, f"kanıtta geçmeyen sayı: {sorted(set(topraksiz))[:3]}", refs)
        elif not refs and (katilik == "siki" or _iddia_mi(cumle)):
            gerekce = "referans yok (sıkı mod)" if katilik == "siki" else "iddia taşıyor ama referansı yok"
            karar = CumleKarari(cumle, False, gerekce, refs)
        else:
            karar = CumleKarari(cumle, True, "kanıta bağlı" if refs else "iddia taşımıyor", refs)
        (tutulan if karar.tutuldu else silinen).append(karar)

    return DogrulamaSonucu(" ".join(k.cumle for k in tutulan), silinen, tutulan, katilik)


def referans_haritasi(metin: str, clean: dict) -> Dict[str, List[str]]:
    """Denetim için: her cümle → dayandığı referanslar. Analist "bu cümle nereden çıktı" diye sorabilsin."""
    return {c: OLAY_RX.findall(c) + KURAL_RX.findall(c) + SERI_RX.findall(c) for c in cumlelere_bol(metin)}
