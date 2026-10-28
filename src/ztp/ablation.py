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
        rows.append(
            dict(
                varyant=name,
                aciklama=spec["aciklama"],
                kapsama=f"{summ['kapsama']['tespit']}/{summ['kapsama']['senaryo']}",
                kapsama_oran=summ["kapsama"]["oran"],
                vaka=summ["vaka_hacmi"]["toplam"],
                precision_at_n=lp.get("precision_at_n"),
                precision_at_3=lp.get("precision@3"),
                erkenlik_medyan=_median([v for v in summ["erkenlik_gun"].values() if v is not None]),
                tahmin_auc=cal.get("auc"),
                tahmin_brier=cal.get("brier"),
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
    return rows


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    return float(s[len(s) // 2]) if len(s) % 2 else float((s[len(s) // 2 - 1] + s[len(s) // 2]) / 2)


def format_ablation(rows: List[dict]) -> str:
    head = f"{'varyant':<16}{'kapsama':>10}{'Δkaps':>8}{'vaka':>7}{'prec@N':>9}{'Δprec':>8}{'prec@3':>9}{'erken':>7}{'AUC':>7}  açıklama"
    lines = ["ABLASYON (19.5) — aynı veri, bileşen kapalı:", head, "-" * len(head)]
    for r in rows:
        lines.append(
            f"{r['varyant']:<16}{r['kapsama']:>10}{_f(r.get('kapsama_farki'), True):>8}{r['vaka']:>7}{_f(r['precision_at_n']):>9}"
            f"{_f(r.get('precision_farki'), True):>8}{_f(r['precision_at_3']):>9}{_f(r['erkenlik_medyan']):>7}{_f(r['tahmin_auc']):>7}  {r['aciklama']}"
        )
    lines.append(
        "Yorum: Δ negatifse bileşen kapsama/precision'a katkı sağlıyor; ~0 ise katkısı bu veride ölçülemedi (14.5 giriş şartı sağlanmaz)."
    )
    return "\n".join(lines)


def _f(v, signed: bool = False) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:+.3f}" if signed else f"{v:.3f}"
    return str(v)
