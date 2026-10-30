"""Ablasyon ve duyarlılık koşusu — 19.5: sistemin yalnızca toplam performansı değil, her bileşenin gerçekten değer
üretip üretmediği ölçülür. Bileşen kapatılır, aynı veri üzerinde kapsama / precision@k / vaka hacmi farkı raporlanır.

Varyantlar tespit kataloğunu (durum → gölge) ya da yapılandırma anahtarlarını değiştirir; kod yolu aynıdır.
Sonuç, "prediction katmanı olmasa ne kaybederdik?" sorusuna sayısal cevap verir — aksi hâlde katman doğrulanmamış sayılır.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import replace
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from ztp.config import TenantConfig
from ztp.data.dataset import Dataset
from ztp.pipeline import ZeroTrustPredictionPipeline

LOG = logging.getLogger(__name__)


def _shadow(prefixes: tuple) -> Callable[[List[dict]], List[dict]]:
    def f(catalog: List[dict]) -> List[dict]:
        out = copy.deepcopy(catalog)
        for r in out:
            if r["id"].startswith(prefixes) and r["durum"] == "yayinda":
                r["durum"] = "golge-modda"
        return out

    return f


def _yayina(ids: tuple) -> Callable[[List[dict]], List[dict]]:
    """Gölgedeki kuralı ÖLÇÜM için yayına alır. Katalogdaki YAML gölgede kalır; 13.6 ihlal edilmez —
    bir kuralın yayına çıkıp çıkamayacağı ancak yayındaymış gibi ölçülerek bilinebilir."""

    def f(catalog: List[dict]) -> List[dict]:
        out = copy.deepcopy(catalog)
        for r in out:
            if r["id"] in ids and r["durum"] == "golge-modda":
                r["durum"] = "yayinda"
        return out

    return f


VARIANTS: Dict[str, dict] = {
    "tam": dict(aciklama="tüm bileşenler açık (referans)"),
    "prediction_yok": dict(aciklama="PRED-* kuralları gölgede", catalog=_shadow(("PRED-",))),
    "iliskisel_yok": dict(aciklama="REL-* (derin graf) kuralları gölgede", catalog=_shadow(("REL-",))),
    "carpan_yok": dict(aciklama="13.3 korelasyon çarpanları kapalı", cfg=dict(correlation_multipliers=False)),
    "akran_yok": dict(aciklama="9.2 akran ağırlığı kapalı (yalnızca kişisel baseline)", cfg=dict(peer_context=False)),
    # ---- v3 revizyonları: varsayılanda KAPALI olan bileşenler burada AÇILARAK ölçülür (14.5 giriş şartı).
    "kaynak_cesitliligi": dict(
        aciklama="#3 üç+ farklı veri kaynağından tespit varsa ×1,5",
        cfg=dict(source_diversity_multiplier=1.5),
    ),
    "oncelik_momentum": dict(
        aciklama="#2 kuyruk sırası ham skordan ayrı: risk yörüngesi momentumu",
        cfg=dict(priority_momentum_weight=0.5),
    ),
    "oncelik_cesitlilik": dict(
        aciklama="#2 kuyruk sırası: veri kaynağı çeşitliliği",
        cfg=dict(priority_diversity_weight=0.5),
    ),
    "oncelik_akran": dict(
        aciklama="#2 kuyruk sırası: akran grubundan yapısal sapma",
        cfg=dict(priority_peer_weight=0.5),
    ),
    # ---- v4 bileşenleri TEK TEK. r6.2 ve r4.2 ölçümlerinde hepsi BİRLİKTE açılmıştı; hangisinin hangi etkiyi
    # ürettiği bu yüzden bilinmiyordu (`docs/r62-v4-olcumu.md` §6.1). Aşağıdaki varyantlar o soruyu ayrıştırır.
    "v4_graf_carpan": dict(
        aciklama="v4 graf riski yalnız ÇARPAN olarak (1 + 0,5·graf) — r4.2/r6.2'de kullanılan hâli",
        cfg=dict(graf_enabled=True, graf_agirligi=0.5),
    ),
    "v4_adwin": dict(
        aciklama="v4 yalnız ADWIN: davranış kayarsa kişisel baz çizgisi o günden başlar",
        cfg=dict(adwin_enabled=True),
    ),
    "v4_bayes": dict(
        aciklama="v4 yalnız Bayes kapısı (etiket yoksa hiçbir şey elemez — ölçümün amacı bunu göstermek)",
        cfg=dict(bayes_kapi_esigi=0.3),
    ),
    "v4_belirsizlik": dict(
        aciklama="v4 yalnız Venn-Abers belirsizlik aralığı (vakaya bilgi ekler, sıralamayı değiştirmemeli)",
        cfg=dict(belirsizlik_enabled=True),
    ),
    # ---- v5: r6.2'nin yapısal bulgusuna cevap. ÇARPAN tabanı sıfır olana ulaşamaz (1,5 × 0 = 0); kaçan insider
    # tam o durumdaydı. İki ayrı yol ayrı ayrı ölçülür, sonra birlikte.
    "v5_graf_toplamsal": dict(
        aciklama="v5 graf riski ÇARPAN yerine TOPLAMSAL terim (raw += 0,5·graf·10)",
        cfg=dict(graf_enabled=True, graf_agirligi=0.0, graf_toplamsal_agirlik=0.5),
    ),
    "v5_anomali_ecod": dict(
        aciklama="v5 denetimsiz ECOD kanalı, skora toplamsal (kural tetiklenmesini beklemez)",
        cfg=dict(anomali_enabled=True, anomali_agirligi=0.5, anomali_dogrulama_esigi=0.995),
    ),
    "v5_anomali_orman": dict(
        aciklama="v5 denetimsiz Isolation Forest kanalı (ECOD ile karşılaştırma)",
        cfg=dict(anomali_enabled=True, anomali_tur="orman", anomali_agirligi=0.5, anomali_dogrulama_esigi=0.995),
    ),
    "v5_anomali_sinyalsiz": dict(
        aciklama="v5 ECOD kanalı AÇIK ama ağırlık 0 — sinyal üretmek tek başına skoru değiştirmemeli (kontrol)",
        cfg=dict(anomali_enabled=True, anomali_agirligi=0.0),
    ),
    "v5_toplamsal_hepsi": dict(
        aciklama="v5 toplamsal graf + ECOD kanalı birlikte",
        cfg=dict(
            graf_enabled=True,
            graf_agirligi=0.0,
            graf_toplamsal_agirlik=0.5,
            anomali_enabled=True,
            anomali_agirligi=0.5,
            anomali_dogrulama_esigi=0.995,
        ),
    ),
    "pred_sinif_agirligi": dict(
        aciklama="lojistik modelde dengeleme: sıralama ↔ kalibrasyon takası (AUPRC ile Brier birlikte okunur)",
        cfg=dict(pred_sinif_agirligi=True),
    ),
    # ---- v6 katman A: geri bildirim döngüsü. Ön kayıt eşiği (`docs/sprint-v6-on-kayit.md`):
    # Bayes kapısı sıfırdan farklı eleme yapar VE precision@N düşmeden vaka hacmi ≥%10 azalır.
    "v6_geri_bildirim": dict(
        aciklama="v6-A döngü: analist etiketi → Bayes kapısı + Venn-Abers + periyodik yeniden eğitim",
        cfg=dict(
            geri_bildirim_dongusu=True,
            analist_gecikme_gun=2,
            bayes_kapi_esigi=0.3,
            bayes_min_gozlem=10,
            belirsizlik_enabled=True,
            pred_yeniden_egitim_gun=14,
            pred_min_yeni_etiket=25,
        ),
    ),
    "v6_geri_bildirim_kapisiz": dict(
        aciklama="v6-A döngü ama Bayes kapısı KAPALI — etkinin kapıdan mı başka yerden mi geldiğini ayırır",
        cfg=dict(
            geri_bildirim_dongusu=True,
            analist_gecikme_gun=2,
            belirsizlik_enabled=True,
            pred_yeniden_egitim_gun=14,
            pred_min_yeni_etiket=25,
        ),
    ),
    # ---- v6 katman D: sızıntı kanalı sayacının ayrılması. Kural gölgede doğdu; yayına çıkma şartı
    # ön kayıtta yazılı iki eşik (r4.2'de kapsama düşmez, vaka hacmi artışı %15'i geçmez).
    "v6d_sizinti_kanali": dict(
        aciklama="v6-D: UEBA-0022 (sızıntı kanalı ani artış) ÖLÇÜM için yayında",
        catalog=_yayina(("UEBA-0022",)),
    ),
    # ---- v6 katman B: saldırı yolu tahmini. Ağırlık 0 olduğu için kuyruğu DEĞİŞTİRMEMELİ —
    # bu varyant hem o sözleşmeyi sınar hem sonraki adım isabetini ölçer (eşik: top-1 ≥ 2× taban).
    "v6b_saldiri_yolu": dict(
        aciklama="v6-B: n-gram saldırı yolu tahmini (skora girmez, yalnız anlatıya)",
        cfg=dict(saldiri_yolu_enabled=True, saldiri_yolu_model="ngram", saldiri_yolu_baglam=2),
    ),
    # ---- v6 katman C: öğrenen graf gömme. Eşik 27/34 — graf ÇARPANININ tek başına verdiği.
    "v6c_ogrenen_graf": dict(
        aciklama="v6-C: öğrenen graf gömme, skora toplamsal (eşik: 27/34'ü geçmeli)",
        cfg=dict(graf_ogrenen_enabled=True, graf_ogrenen_agirligi=0.5),
    ),
    "v6c_ogrenen_graf_sinyalsiz": dict(
        aciklama="v6-C kontrol: öğrenen graf AÇIK ama ağırlık 0 — sinyal üretmek skoru değiştirmemeli",
        cfg=dict(graf_ogrenen_enabled=True, graf_ogrenen_agirligi=0.0),
    ),
    "v6_gurultulu_etiket": dict(
        aciklama="v6-A döngü, analistin %15'i yanılıyor — gürültülü etikete dayanıklılık",
        cfg=dict(
            geri_bildirim_dongusu=True,
            analist_gecikme_gun=2,
            analist_hata_orani=0.15,
            bayes_kapi_esigi=0.3,
            bayes_min_gozlem=10,
            belirsizlik_enabled=True,
        ),
    ),
}
# Varlık katmanlandırma (#4) ablasyona ayrı eklenir: kalıplar müşteriye özgüdür, CERT'te varlık envanteri yoktur.
# Kullanımı: run_ablation(..., variants={**VARIANTS, "varlik_katmani": varlik_varyanti(tier0=[...], tier1=[...])}).


def varlik_varyanti(tier0: Optional[List[str]] = None, tier1: Optional[List[str]] = None) -> dict:
    return dict(
        aciklama="#4 Tier-0/Tier-1 varlığa erişimde çarpan",
        cfg=dict(
            asset_tiers={"tier0": tier0 or [], "tier1": tier1 or []},
            tier0_multiplier=2.0,
            tier1_multiplier=1.5,
        ),
    )


def run_ablation(
    cfg: TenantConfig,
    data: Dataset,
    catalog: List[dict],
    out_dir: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    warmup_days: int,
    variants: Optional[Dict[str, dict]] = None,
) -> List[dict]:
    """Her varyantı ayrı bir müşteri kimliğiyle koşar; özet tablo döndürür (metrics.json'lar da diske yazılır)."""
    rows = []
    for name, spec in (variants or VARIANTS).items():
        vcfg = replace(cfg, tenant_id=f"{cfg.tenant_id}__{name}", llm_backend="none", sinks=[], **spec.get("cfg", {}))
        vcat = spec["catalog"](catalog) if "catalog" in spec else copy.deepcopy(catalog)
        vdata = Dataset(
            data.name,
            data.directory.copy(),
            data.ip_leases.copy(),
            data.events.copy(),
            data.leaves.copy(),
            copy.deepcopy(data.ground_truth),
            list(data.critical_assets),
            honeytokens=dict(data.honeytokens),
        )
        LOG.info("Ablasyon varyantı: %s — %s", name, spec["aciklama"])
        pipe = ZeroTrustPredictionPipeline(vcfg, vdata, vcat, out_dir)
        pipe.run(start, end, warmup_days)
        summ = pipe.metrics.summary(
            pipe.labels, pipe.engine.shadow_log, pipe.engine.suppressed_log, pipe.engine, end, prediction_rows=pipe.pred.rows
        )
        lp = summ.get("etiketli_veri_precision") or {}
        cal = (summ.get("tahmin_kalibrasyonu") or {}).get("sezgisel") or {}
        egri = summ.get("butce_recall_egrisi") or {}
        rows.append(
            dict(
                varyant=name,
                aciklama=spec["aciklama"],
                kapsama=f"{summ['kapsama']['tespit']}/{summ['kapsama']['senaryo']}",
                kapsama_oran=summ["kapsama"]["oran"],
                vaka=summ["vaka_hacmi"]["toplam"],
                precision_at_n=lp.get("precision_at_n"),
                precision_at_3=lp.get("precision@3"),
                # Recall@bütçe: precision taban oranıyla çöktüğü için tek başına kapsama/precision yetmiyor (A4)
                recall_30_kullanici=lp.get("recall@30_kullanici"),
                recall_10_kullanici=lp.get("recall@10_kullanici"),
                erkenlik_medyan=_median([v for v in summ["erkenlik_gun"].values() if v is not None]),
                tahmin_auc=cal.get("auc"),
                tahmin_auprc=cal.get("auprc"),
                tahmin_auprc_kat=cal.get("auprc_kat"),  # taban oranının kaç katı (şans seviyesine göre)
                tahmin_brier=cal.get("brier"),
                butce_egrisi=egri.get("egri"),
                anomali_etkinlik=(pipe.anomali.etkinlik() if pipe.anomali is not None else None),
            )
        )
    ref = next((r for r in rows if r["varyant"] == "tam"), None)
    if ref:
        for r in rows:
            r["kapsama_farki"] = (
                None
                if r["kapsama_oran"] is None or ref["kapsama_oran"] is None
                else round(r["kapsama_oran"] - ref["kapsama_oran"], 3)
            )
            r["precision_farki"] = (
                None
                if r["precision_at_n"] is None or ref["precision_at_n"] is None
                else round(r["precision_at_n"] - ref["precision_at_n"], 3)
            )
            # Kapsama artışının BEDELİ: vaka hacmi farkı. r6.2 dersi — kapsama sabitken vaka iki katına çıkabiliyor.
            r["vaka_farki"] = r["vaka"] - ref["vaka"]
    return rows


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    return float(s[len(s) // 2]) if len(s) % 2 else float((s[len(s) // 2 - 1] + s[len(s) // 2]) / 2)


def format_ablation(rows: List[dict]) -> str:
    head = (
        f"{'varyant':<22}{'kapsama':>10}{'Δkaps':>8}{'vaka':>7}{'Δvaka':>8}{'prec@N':>9}{'Δprec':>8}"
        f"{'rec@10k':>9}{'rec@30k':>9}{'erken':>7}{'AUPRC':>8}{'×taban':>8}  açıklama"
    )
    lines = ["ABLASYON (19.5) — aynı veri, tek bileşen değişken:", head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r['varyant']:<22}{r['kapsama']:>10}{_f(r.get('kapsama_farki'), True):>8}{r['vaka']:>7}"
            f"{_f(r.get('vaka_farki'), True):>8}{_f(r['precision_at_n']):>9}{_f(r.get('precision_farki'), True):>8}"
            f"{_f(r.get('recall_10_kullanici')):>9}{_f(r.get('recall_30_kullanici')):>9}{_f(r['erkenlik_medyan']):>7}"
            f"{_f(r.get('tahmin_auprc')):>8}{_f(r.get('tahmin_auprc_kat')):>8}  {r['aciklama']}"
        )
    lines += [
        "Okuma: Δ, 'tam' varyantına göre farktır. Δkaps > 0 ise bileşen kapsamayı ARTIRIYOR; ~0 ise katkısı bu",
        "veride ölçülemedi (14.5 giriş şartı sağlanmaz). Δvaka, bedelini verir: kapsama artmadan vaka artıyorsa",
        "bileşen yalnız yanlış alarm üretmiştir — r6.2'de v4 bileşenlerinin birlikte yaptığı tam buydu.",
        "AUPRC tek başına okunmaz: '×taban' kolonu şans seviyesinin kaç katı olduğunu verir.",
    ]
    return "\n".join(lines)


def _f(v, signed: bool = False) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:+.3f}" if signed else f"{v:.3f}"
    return str(v)
