"""Kurulum hazırlık raporu — "bu ortamda 25 kuralın kaçı gerçekten çalışır?"

CERT'te iki kural **yapısal olarak ölü** çıktı (`UEBA-0006`, `UEBA-0007` değil — `UEBA-0006` ve
`UEBA-0008`; toplam ağırlık 11) ve bu aylarca fark edilmedi: raporda masum bir "bu veride desen
görülmedi" satırı olarak göründü (`docs/faz-a2-sonuclar.md`). Aynısı gerçek kurulumda olursa
daha pahalı — ürün "25 kural" diye satılır, 23'ü çalışır.

Bu betik hedef ortamın KENDİ verisine bakıp şunları söyler:

1. Hangi olay alanı dolu, hangisi boş/sabit (şema profili)
2. Hangi kural bu veride **sınanamaz** ve hangi alan eksik olduğu için
3. Hangi kanalda hangi alan ölü (alan × kaynak)
4. Dış e-posta hacim dağılımı — `UEBA-0023`'ün eşiği için gereken girdi
   (`docs/v10-sonuclar.md`: o eşik türetilemedi, operasyonel karar bekliyor)

Girdi: sistemin kendi olay şemasında (`EVENT_COLUMNS`) bir CSV ya da Parquet. Kolonların hepsi
olmak zorunda değil — eksik olan zaten raporlanacak şey.

    python scripts/kurulum_hazirlik.py --olaylar /yol/olaylar.csv
    python scripts/kurulum_hazirlik.py --olaylar /yol/olaylar.parquet --out hazirlik.md

Hiçbir şey yazmaz, hiçbir karar değiştirmez — yalnız okur ve raporlar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ztp.availability import SINYAL_TUREV, kural_kanallari, kural_mevcudiyeti  # noqa: E402
from ztp.detection.catalog import load_catalog  # noqa: E402
from ztp.schema import EVENT_COLUMNS  # noqa: E402
from ztp.schema_profiler import TUREV_BAGIMLILIK, profille, rapor  # noqa: E402


def _oku(yol: Path) -> pd.DataFrame:
    if yol.suffix.lower() in (".parquet", ".pq"):
        return pd.read_parquet(yol)
    return pd.read_csv(yol, dtype=str, keep_default_na=False, low_memory=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--olaylar", required=True, help="olay tablosu (CSV ya da Parquet)")
    ap.add_argument("--ad", default="hedef-ortam", help="rapordaki veri seti adı")
    ap.add_argument("--out", default=None, help="markdown rapor dosyası")
    ap.add_argument("--json", default=None, help="makine okunur çıktı")
    a = ap.parse_args()

    yol = Path(a.olaylar).expanduser()
    ev = _oku(yol)
    # sayısal alanlar: profilleyici 0'ı "yok" sayar, string olarak gelirse göremez
    for k in ("bytes_out",):
        if k in ev.columns:
            ev[k] = pd.to_numeric(ev[k], errors="coerce").fillna(0)

    sat = [f"# Kurulum hazırlık raporu — {a.ad}", ""]
    sat.append(f"Kaynak: `{yol}` · {len(ev):,} olay · {len(ev.columns)} kolon")
    eksik_kolon = [c for c in EVENT_COLUMNS if c not in ev.columns]
    if eksik_kolon:
        sat.append("")
        sat.append(f"**Şemada olmayan kolonlar:** {', '.join(f'`{c}`' for c in eksik_kolon)}")
    sat.append("")

    kanal_var = "source" in ev.columns
    harita = profille(a.ad, events=ev, kanal_duzeyi=kanal_var)
    sat.append(rapor(harita))

    katalog = load_catalog()
    m = kural_mevcudiyeti(katalog, harita, kanal_duzeyi=kanal_var)
    sat += ["## Kural sınanabilirliği", ""]
    if not m.olu:
        sat.append("**Her kural bu veride sınanabilir.** Şemadan ölü kural yok.")
    else:
        agirlik = {r["id"]: r.get("agirlik", 0) for r in katalog}
        sat.append(f"**{len(m.olu)} kural bu veride SINANAMAZ** (toplam ağırlık {sum(agirlik.get(k, 0) for k in m.olu)}):")
        sat.append("")
        sat += ["| Kural | Ağırlık | Kanal | Eksik |", "|---|---|---|---|"]
        for rid in sorted(m.olu):
            d = m.kurallar[rid]
            kan = ", ".join(f"`{k}`" for k in d.kanallar) or "—"
            sat.append(f"| `{rid}` | {agirlik.get(rid, '?')} | {kan} | {', '.join(f'`{x}`' for x in d.eksik_alanlar)} |")
        sat.append("")
        sat.append("> Bu kurallar **sessizce** 'desen görülmedi' diye raporlanırdı. Artık sayılıyorlar.")
    sat.append("")

    # kuralların beyan ettiği kanallar veride var mı
    gorulen = set(ev["source"].dropna().unique()) if kanal_var else set()
    # `hr` olay akışında DEĞİL, İK/AD dizininde gelir — olay tablosunda aranması yanlış alarmdır.
    DIZIN_KAYNAKLARI = {"hr"}
    sat += ["## Kuralların beklediği kanallar", "", "| Kanal | Veride var mı | Bağımlı kural |", "|---|---|---|"]
    kanal_kural: dict = {}
    for r in katalog:
        for k in kural_kanallari(r):
            kanal_kural.setdefault(k, []).append(r["id"])
    for k in sorted(kanal_kural):
        if k in DIZIN_KAYNAKLARI:
            isaret = "_(dizinden gelir, olay akışında aranmaz)_"
        elif not kanal_var:
            isaret = "—"
        else:
            isaret = "✔" if k in gorulen else "**YOK**"
        sat.append(f"| `{k}` | {isaret} | {len(kanal_kural[k])} kural |")
    sat.append("")

    # UEBA-0023'ün eşiği için gereken girdi
    sat += ["## `UEBA-0023` eşiği için hacim dağılımı", ""]
    dis = ev[ev["app"] == "email_external"] if "app" in ev.columns else ev.iloc[0:0]
    if not len(dis) or "bytes_out" not in dis.columns:
        sat.append("Dış e-posta olayı (`app == \"email_external\"`) bulunamadı — eşik türetilemez.")
        dagilim = None
    else:
        gunluk = dis.copy()
        if "time" in gunluk.columns and "actor_raw" in gunluk.columns:
            gunluk["gun"] = pd.to_datetime(gunluk["time"], errors="coerce").dt.normalize()
            g = gunluk.groupby(["actor_raw", "gun"])["bytes_out"].sum()
            mads = g.groupby(level=0).apply(lambda v: float((v - v.median()).abs().median()))
            mads = mads[np.isfinite(mads)]
            dagilim = dict(
                kullanici_gun=int(len(g)),
                medyan=float(g.median()),
                p90=float(g.quantile(0.90)),
                p99=float(g.quantile(0.99)),
                maks=float(g.max()),
                mad_medyan=float(mads.median()) if len(mads) else None,
                mad_p10=float(np.percentile(mads, 10)) if len(mads) else None,
            )
            sat += ["| Ölçüt | Değer (bayt) |", "|---|---|"]
            for ad2, v in dagilim.items():
                sat.append(f"| {ad2} | {v:,.0f} |" if isinstance(v, float) else f"| {ad2} | {v:,} |")
            sat.append("")
            sat.append(
                "Tetikleme koşulu `x > medyan + 5,19 × taban`. Şu anki taban **50.000** ve sentetik "
                "veride kullanıcıların %64'ünde tetikliyordu (`docs/v10-sonuclar.md`). Doğru değer "
                "**operasyonel bir karar**: bir günde normalinin ne kadar üstüne çıkan dış e-posta "
                "hacmi bir analistin zamanına değer?"
            )
        else:
            sat.append("`time` ya da `actor_raw` kolonu yok — kullanıcı-gün dağılımı çıkarılamadı.")
            dagilim = None
    sat.append("")

    sat += ["## Haritalanan sinyaller", "", f"{len(SINYAL_TUREV)} veri bağımlı sinyal, {len(TUREV_BAGIMLILIK)} türev özellik üzerinden izleniyor.", ""]
    metin = "\n".join(sat)
    print(metin)
    if a.out:
        Path(a.out).write_text(metin, encoding="utf-8")
        print(f"\nyazıldı: {a.out}")
    if a.json:
        Path(a.json).write_text(
            json.dumps(
                dict(ad=a.ad, olay=len(ev), eksik_kolon=eksik_kolon, sema=harita.ozet(),
                     mevcudiyet=m.ozet(), kanallar=sorted(gorulen), eposta_dagilimi=dagilim),
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"yazıldı: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
