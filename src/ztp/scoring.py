"""Risk skorlama — 13.2–13.5: ağırlık × şiddet × bozunum × çarpanlar, yüzdelik kalibrasyon, alarm bütçesi (ADR-005)."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

from ztp.config import TenantConfig
from ztp.detection.engine import Hit
from ztp.feedback import LabelStore
from ztp.graph.knowledge import KnowledgeGraph


@dataclass
class RiskResult:
    sid: str
    raw: float
    base: float
    multipliers: Dict[str, float]
    percentile: float
    hits: List[Hit]
    contributions: Dict[str, float]
    critical: bool = False


class RiskScorer:
    def __init__(self, cfg: TenantConfig, kg: KnowledgeGraph, labels: LabelStore):
        self.cfg, self.kg, self.labels = cfg, kg, labels
        self.hit_log: Dict[str, List[Hit]] = defaultdict(list)
        self.pool: deque = deque()  # (gün, ham skor) — son 90 günün tüm kullanıcı-günleri (sıfırlar dahil)
        self.last_queued: Dict[str, pd.Timestamp] = {}  # açık vaka: yeni kanıt gelmeden yeniden kuyruğa alınmaz
        self.watch_by_day: Dict[pd.Timestamp, List[str]] = {}  # doğrulama kapısından geçemeyen adaylar (izleme listesi)

    def decay(self, age_days: int) -> float:
        """13.2 Zaman bozunumu: son 24 saat tam ağırlık; 7 gün öncesi 0.3."""
        if age_days <= 0:
            return 1.0
        return max(self.cfg.decay_floor_7d, 1.0 - (1.0 - self.cfg.decay_floor_7d) * age_days / 7.0)

    def add_hits(self, sid: str, hits: List[Hit]) -> None:
        self.hit_log[sid].extend(hits)

    def compute(self, sid: str, day: pd.Timestamp, signals: dict) -> RiskResult:
        window = [h for h in self.hit_log[sid] if 0 <= (day - h.day).days <= 7]
        contrib = {}
        base = 0.0
        for h in window:
            c = h.weight * h.severity * self.decay((day - h.day).days)
            contrib[f"{h.rule_id}@{h.day.date()}"] = c
            base += c
        today = [h for h in window if h.day == day]
        mult: Dict[str, float] = {}
        if len({h.rule_id for h in today}) >= 3:
            mult["ayni_gun_3_tespit"] = 2.0
        tactics = {self.kg.tactic(t) for h in today for t in h.attack}
        if len(tactics) >= 2:
            mult["farkli_taktik_2"] = 2.5  # tasarımın merkezi kararı: zincir davranışı en güçlü sinyal (13.3)
        if signals.get("hesap_yasi_gun", 999) < 30:
            mult["hesap_yasi_30"] = 1.5
        if signals.get("ayrilik_bildirimi") == 1:
            mult["ayrilik_bildirimi"] = 1.8
        if signals.get("ayricalikli") == 1:
            mult["ayricalikli_hesap"] = 1.5
        if not self.cfg.correlation_multipliers:  # 19.5 ablasyon: çarpanlar kapalı
            mult = {}
        if today and self.labels.fp_pattern_match(sid, {h.rule_id for h in today}, day):
            mult["daha_once_normal"] = 0.2
        m = float(np.prod(list(mult.values()))) if mult else 1.0
        raw = base * m
        # 14.6: öğrenen modelin olasılığı kural skorunu ezmez, ona EKLENİR (varsayılan ağırlık 0 — ablasyonla doğrulanmadan açılmaz)
        p7 = signals.get("tahmin_7g_olasilik")
        if self.cfg.prediction_weight > 0 and p7 is not None and base > 0:
            add = float(self.cfg.prediction_weight) * float(p7) * 10.0
            raw += add
            contrib["PRED-MODEL"] = add
        contrib = {k: v * m for k, v in contrib.items()}
        return RiskResult(sid, raw, base, mult, 0.0, window, contrib)

    def calibrate(self, day: pd.Timestamp, results: Dict[str, RiskResult]) -> None:
        """13.4 Kalibrasyon: ham skor yorumlanamaz; kurumdaki tüm kullanıcı-günlerine göre yüzdelik dilim."""
        while self.pool and (day - self.pool[0][0]).days > self.cfg.long_window_days:
            self.pool.popleft()
        for r in results.values():
            self.pool.append((day, r.raw))
        arr = np.sort(np.array([v for _, v in self.pool], dtype=float))
        n = len(arr)
        for r in results.values():
            r.percentile = float(np.searchsorted(arr, r.raw, side="left") / n) if n else 0.0
            today = [h for h in r.hits if h.day == day]
            tactics = {self.kg.tactic(t) for h in today for t in h.attack}
            r.critical = (
                (r.percentile >= self.cfg.critical_percentile and r.raw > 0)
                or (len(tactics) >= 2 and r.multipliers.get("ayricalikli_hesap") == 1.5)
                or any(h.kritik for h in today)  # deterministik kanıt (ör. tuzak etkileşimi): tek sinyal, bütçeden bağımsız
            )

    def corroborated(self, r: RiskResult) -> bool:
        """v2 doğrulama kapısı: tek zayıf sinyal kuyruğa girmez. 7 günlük pencerede 2+ farklı kural, aynı sinyalin
        `kuyruk_tekrar_gun` farklı günde tekrarı, güçlendirici çarpan (> 1), kritik ya da kurumun en uç skorları
        (yüzdelik ≥ `kuyruk_kacis_yuzdelik`: tek ama çok güçlü sinyal) yeterlidir."""
        return (
            r.critical
            or r.percentile >= self.cfg.kuyruk_kacis_yuzdelik
            or any(v > 1 for v in r.multipliers.values())
            or len({h.rule_id for h in r.hits}) >= 2
            or len({h.day for h in r.hits}) >= self.cfg.kuyruk_tekrar_gun
        )

    def select_queue(self, day: pd.Timestamp, results: Dict[str, RiskResult]) -> List[str]:
        """13.5 Alarm bütçesi: her gün en riskli N varlık-gün + kritik istisna (bütçeden bağımsız).
        Son 7 günde kuyruğa alınmış ve o günden beri YENİ tespiti olmayan kullanıcı tekrar sunulmaz (vaka zaten açık)."""

        def eligible(r: RiskResult) -> bool:
            # Not: tek zayıf sinyaller sıralamada doğal olarak geride kalır; sessiz günlerde bütçe onlara da yer açar (13.5).
            lq = self.last_queued.get(r.sid)
            if lq is None or (day - lq).days > 7:
                return True
            return any(h.day > lq for h in r.hits)

        ranked = sorted((r for r in results.values() if r.raw > 0 and eligible(r)), key=lambda r: (-int(r.critical), -r.raw))
        # kritik istisna bütçeden BAĞIMSIZDIR: N sıralı vaka + tüm kritikler (kritik, sıradan vakanın yerini almaz)
        chosen = [r.sid for r in ranked if r.critical]
        normal = [r for r in ranked if not r.critical]
        if self.cfg.kuyruk_dogrulama:
            self.watch_by_day[day] = [r.sid for r in normal if not self.corroborated(r)]
            normal = [r for r in normal if self.corroborated(r)]
        chosen += [r.sid for r in normal][: self.cfg.alarm_budget_per_day]
        for sid in chosen:
            self.last_queued[sid] = day
        return chosen
