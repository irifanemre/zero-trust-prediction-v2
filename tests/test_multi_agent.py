"""Çok ajanlı SOC raporlaması (revizeler.txt §7.3): Investigator / Verifier / Reporter.

Ana sözleşme: olgular ve teknik teyidi DETERMİNİSTİKTİR; model yalnızca anlatır. Bir halüsinasyon rapor
metnini bozabilir, kanıtı ya da teknik eşlemesini bozamaz.
"""

from dataclasses import dataclass

import pytest

from ztp.reporting.multi_agent import Investigator, MultiAgentSoc, Reporter, Verifier, pasaj_haritasi

VAKA = {
    "kullanici": "U-0042",
    "tespitler": [
        {"kural": "UEBA-0001", "ad": "Mesai dışı giriş", "kanit": ["E-0011223"], "katki": 2.0, "teknikler": ["T1078"]},
        {"kural": "UEBA-0005", "ad": "USB kopya", "kanit": ["E-a1b2c3d"], "katki": 7.5, "teknikler": ["T1052"]},
    ],
}


@dataclass
class SahteOzet:
    text: str


class SahteModel:
    def __init__(self, metin):
        self.metin = metin

    def summarize(self, case):
        return SahteOzet(self.metin)


class PatlayanModel:
    def summarize(self, case):
        raise RuntimeError("model çöktü")


class SahtePasaj:
    def __init__(self, t):
        self.technique = t

    def as_text(self):
        return f"{self.technique} açıklaması"


class SahteKb:
    def __init__(self, bilinen):
        self.bilinen = set(bilinen)

    def get(self, tid):
        return SahtePasaj(tid) if tid in self.bilinen else None


# ---------------------------------------------------------------- Investigator
def test_investigator_katkiya_gore_siralar():
    olgular = Investigator().calistir(VAKA)
    assert [o.kural for o in olgular] == ["UEBA-0005", "UEBA-0001"]  # katkısı yüksek önce
    assert olgular[0].sira == 1 and "E-a1b2c3d" in olgular[0].metin()


def test_investigator_bos_vakada_coksmez():
    assert Investigator().calistir({}) == []


# ---------------------------------------------------------------- Verifier
def test_verifier_tabanda_olmayani_teyit_etmez():
    teyitli, teyitsiz, pasajlar = Verifier(SahteKb(["T1078"])).calistir(["T1078", "T1052"])
    assert teyitli == ["T1078"] and teyitsiz == ["T1052"]
    assert pasaj_haritasi(pasajlar) == {"T1078": "T1078 açıklaması"}


def test_imzali_taban_yoksa_hicbiri_teyitli_degil():
    """Bilgi tabanı yüklenemediyse teknik teyidi yapılamaz; hepsi teyitsiz sayılır."""
    teyitli, teyitsiz, _ = Verifier(None).calistir(["T1078", "T1052"])
    assert teyitli == [] and teyitsiz == ["T1052", "T1078"]


# ---------------------------------------------------------------- Reporter
def test_model_yoksa_sablona_duser():
    metin, kaynak, _ = Reporter(None).calistir(VAKA, Investigator().calistir(VAKA), ["T1078"])
    assert kaynak == "sablon" and "UEBA-0005" in metin and "T1078" in metin


def test_model_cokerse_rapor_yine_cikar():
    metin, kaynak, ayrinti = Reporter(PatlayanModel()).calistir(VAKA, Investigator().calistir(VAKA), [])
    assert kaynak == "sablon" and metin and "model çöktü" in ayrinti["hata"]


def test_uydurma_cumle_silinir_gerisi_kalir():
    model = SahteModel("USB kopya yapıldı [E-a1b2c3d]. Ayrıca E-ffffff0 olayı görüldü.")
    metin, kaynak, dogrulama = Reporter(model).calistir(VAKA, [], [])
    assert kaynak == "llm+silme"
    assert "E-a1b2c3d" in metin and "E-ffffff0" not in metin
    assert dogrulama["silinen"] == 1


def test_tum_cumleler_silinirse_sablona_duser():
    """Model hiçbir şeyi kanıta bağlayamadıysa metni kullanmak yerine deterministik şablon üretilir."""
    model = SahteModel("E-ffffff0 olayı görüldü. E-eeeeee1 olayı da görüldü.")
    metin, kaynak, _ = Reporter(model).calistir(VAKA, Investigator().calistir(VAKA), [])
    assert kaynak == "sablon" and "UEBA-0005" in metin


# ---------------------------------------------------------------- orkestrasyon
def test_zincir_uctan_uca_ve_iz_kaydi():
    soc = MultiAgentSoc(kb=SahteKb(["T1052"]), ozetleyici=SahteModel("USB kopya [E-a1b2c3d]."))
    r = soc.calistir(VAKA)
    assert r.kaynak == "llm"
    assert r.teyitli_teknikler == ["T1052"] and r.teyitsiz_teknikler == ["T1078"]
    assert [a.ajan for a in r.iz] == ["investigator", "verifier", "reporter"]
    assert len(r.olgular) == 2 and r.soc_talimati


def test_teyitsiz_teknik_rapora_girmez():
    """Doğrulanmamış teknik adı şablon metninde geçemez."""
    soc = MultiAgentSoc(kb=SahteKb([]), ozetleyici=None)
    r = soc.calistir(VAKA)
    assert "T1078" not in r.yonetici_ozeti and "T1052" not in r.yonetici_ozeti
    assert set(r.teyitsiz_teknikler) == {"T1078", "T1052"}


def test_olgular_model_bagimsiz():
    """Aynı vaka, farklı modeller: olgular ve teknik teyidi DEĞİŞMEZ."""
    a = MultiAgentSoc(SahteKb(["T1052"]), SahteModel("USB kopya [E-a1b2c3d].")).calistir(VAKA)
    b = MultiAgentSoc(SahteKb(["T1052"]), PatlayanModel()).calistir(VAKA)
    assert [o.metin() for o in a.olgular] == [o.metin() for o in b.olgular]
    assert a.teyitli_teknikler == b.teyitli_teknikler
    assert a.kaynak != b.kaynak  # yalnız anlatım değişti


def test_ozet_denetlenebilir():
    r = MultiAgentSoc(SahteKb(["T1052"]), None).calistir(VAKA)
    o = r.ozet()
    assert o["olgu"] == 2 and o["teyitli_teknik"] == ["T1052"]
    assert [i["ajan"] for i in o["iz"]] == ["investigator", "verifier", "reporter"]


def test_bos_vaka():
    r = MultiAgentSoc(None, None).calistir({})
    assert r.olgular == [] and "raporlanabilir tespit yok" in r.yonetici_ozeti


@pytest.mark.parametrize("katilik", ["siki", "dengeli"])
def test_katilik_duzeyi_gecirilebiliyor(katilik):
    soc = MultiAgentSoc(None, SahteModel("Vaka incelenmeli. USB kopya [E-a1b2c3d]."), katilik=katilik)
    r = soc.calistir(VAKA)
    assert ("Vaka incelenmeli." in r.yonetici_ozeti) is (katilik == "dengeli")
