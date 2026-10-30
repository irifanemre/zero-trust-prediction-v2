"""Etiket deposu / geri besleme döngüsü — 11.8, 17.3: analist kararı sistemin öğrenme kanalıdır."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional, Set

import pandas as pd

FP_REASONS = {
    "mesru_is_gerekcesi": "kural revizyonu için sinyal",
    "bilinen_istisna": "bastırma kuralı önerisi (son kullanma tarihli)",
    "veri_hatasi": "veri kalitesi incelemesi (8.3)",
    "kural_mantigi_hatali": "kural sahibine yönlendirme",
}


class LabelStore:
    def __init__(self, path: Path):
        self.path = path
        self.labels: List[dict] = []
        if path.exists():
            self.labels = json.loads(path.read_text(encoding="utf-8"))

    def add(self, case: dict, decision: str, analyst: str, reason: Optional[str] = None, note: str = "") -> dict:
        if decision not in ("gercek_pozitif", "yanlis_pozitif", "belirsiz"):
            raise ValueError("karar: gercek_pozitif | yanlis_pozitif | belirsiz")
        if decision == "yanlis_pozitif" and reason not in FP_REASONS:
            raise ValueError(f"Yanlış pozitifte sebep zorunludur (17.3): {sorted(FP_REASONS)}")
        rec = dict(
            case_id=case["case_id"],
            gun=case["gun"],
            kullanici=case["kullanici"],
            sid=case.get("_sid"),
            karar=decision,
            sebep=reason,
            analist=analyst,
            not_=note,
            kurallar=sorted({h["kural"] for h in case["tespitler"]}),
            # v6-A: Venn-Abers kalibrasyon kümesinin skoru. Etiketle BİRLİKTE saklanır, çünkü vaka
            # dosyasından geriye okumak koşu sonrası dizin düzenine bağımlılık yaratır.
            yuzdelik=case.get("yuzdelik"),
            ts=pd.Timestamp.utcnow().isoformat(),
            tetiklenen_aksiyon=FP_REASONS.get(reason) if reason else None,
        )
        self.labels = [lab for lab in self.labels if lab["case_id"] != case["case_id"]] + [rec]
        self.path.write_text(json.dumps(self.labels, ensure_ascii=False, indent=2), encoding="utf-8")
        return rec

    def fp_pattern_match(self, sid: str, rule_ids: Set[str], day: pd.Timestamp, window_days: int = 90) -> bool:
        """13.3: daha önce 'normal' (yanlış pozitif) olarak işaretlenmiş aynı desen → ×0.2"""
        for lab in self.labels:
            if lab.get("sid") == sid and lab["karar"] == "yanlis_pozitif" and set(lab["kurallar"]) == set(rule_ids):
                if 0 <= (day - pd.Timestamp(lab["gun"])).days <= window_days:
                    return True
        return False

    def metrics(self) -> dict:
        n = len(self.labels)
        tp = sum(lab["karar"] == "gercek_pozitif" for lab in self.labels)
        fp = sum(lab["karar"] == "yanlis_pozitif" for lab in self.labels)
        per_rule = defaultdict(lambda: Counter())
        for lab in self.labels:
            for r in lab["kurallar"]:
                per_rule[r][lab["karar"]] += 1
        sugg = []
        for r, c in per_rule.items():
            tot = sum(c.values())
            if tot >= 5 and c["yanlis_pozitif"] / tot > 0.75:
                sugg.append(f"{r}: FP oranı %{100 * c['yanlis_pozitif'] / tot:.0f} → ağırlık düşür / revizyon (11.8 kalibrasyon)")
        for lab in self.labels:
            if lab.get("sebep") == "bilinen_istisna":
                sugg.append(f"{lab['kullanici']} × {lab['kurallar']}: bastırma kuralı önerisi, 90 gün son kullanma (12.5)")
        return dict(
            etiket=n,
            gercek_pozitif=tp,
            yanlis_pozitif=fp,
            belirsiz=n - tp - fp,
            precision=(tp / (tp + fp)) if (tp + fp) else None,
            analist_mutabakati=(tp / n) if n else None,
            kural_bazinda={r: dict(c) for r, c in per_rule.items()},
            oneriler=sugg,
            denetimli_model_hazir=n >= 200,
        )
