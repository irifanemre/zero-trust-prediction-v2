"""Müşteri (tenant) yapılandırması — 17.1. Sayısal değerler kalibrasyon başlangıç değerleridir (Bölüm 0)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import yaml

from ztp.deception import HoneytokenRegistry


@dataclass
class TenantConfig:
    tenant_id: str = "musteri-A"
    # 13.5 Alarm bütçesi: N = analist kapasitesi (sabit eşik YOK — ADR-005)
    alarm_budget_per_day: int = 8
    critical_percentile: float = 0.999  # 13.5 kritik eşik istisnası (bütçeden bağımsız)
    # v2 doğrulama kapısı: bütçe hedef değil üst sınır — tek kuralın tek seferlik sinyali analiste değil izleme listesine
    # gider. Kuyruk için: 2+ farklı kural, aynı sinyalin kuyruk_tekrar_gun farklı günde tekrarı, güçlendirici çarpan ya da
    # kritik; tek ama çok güçlü sinyal kurum yüzdeliği kuyruk_kacis_yuzdelik'i aşarsa yine geçer. CERT r5.2 eğitim
    # parçasında yanlış alarm alan kullanıcı 331 → 120, yakalanan insider 29 → 27 (doğrulama: 56 → 15, 6 → 6).
    kuyruk_dogrulama: bool = True
    kuyruk_tekrar_gun: int = 3
    kuyruk_kacis_yuzdelik: float = 0.998
    # 9.2 / 10.4 pencereler
    short_window_days: int = 7
    long_window_days: int = 90
    poisoning_drift_z: float = 2.5  # kısa/uzun pencere farkı bu robust-z'yi aşarsa "zehirleme şüphesi"
    # 9.1 akran grubu
    min_peer_group: int = 8
    behavioral_peer_min_days: int = 30
    # 13.2 zaman bozunumu
    decay_full_hours: float = 24.0
    decay_floor_7d: float = 0.3
    # 4. tahmin ufku
    horizon_days: int = 7
    # 8.3 veri kalitesi eşikleri
    dq_min_volume_ratio: float = 0.3
    dq_max_late_ratio: float = 0.2
    dq_max_unresolved_ratio: float = 0.2
    # 13.6 gölge mod protokolü
    shadow_min_days: int = 14
    shadow_min_precision: float = 0.25
    shadow_max_daily_alerts: float = 2.0
    # 12.5 bastırma varsayılan ömrü
    suppression_default_days: int = 90
    # 21.2 eşik keşfine karşı kısmi rastgeleleştirme (ondalık eşiklerde ±%)
    threshold_jitter: float = 0.05
    # 14.5 denetimli model giriş şartı (etiket sayısı)
    supervised_min_labels: int = 200
    # 13.x füzyon ağırlıkları (POC başlangıç değeri; ablasyon ile doğrulanır — 19.5)
    fusion_temporal_weight: float = 0.7
    fusion_structural_weight: float = 0.3
    # 14.4 / 15 raporlama
    llm_backend: str = "none"  # none | ollama | anthropic
    ollama_model: str = "llama3.1"
    ollama_url: str = "http://localhost:11434"
    anthropic_model: str = "claude-opus-5"
    rag_enabled: bool = True  # ATT&CK bilgi tabanı bağlamı (ADR-009: yalnızca açıklama, skorlamada değil)
    llm_on_injection: str = "template"  # kanıtta talimat benzeri içerik varsa: template (LLM çağrılmaz) | sanitized (redakte edilmiş veriyle çağrılır)
    llm_max_field_len: int = 200  # LLM'e giden her metin alanının üst sınırı
    # 20.1 takma adlaştırma anahtarı (üretimde KMS/vault'tan gelir)
    pseudonym_secret: str = "degistir-bu-anahtari"
    # 11.1 kademeli işlevsellik: bu müşteride mevcut log kaynakları
    available_sources: Tuple[str, ...] = ("ad", "hr", "proxy", "edr", "vpn", "file_server", "dlp")
    # 11.6 kritik varlıklar (graf analizi hedefleri)
    critical_assets: Tuple[str, ...] = ()
    # 12.5 müşteri bastırma kuralları: [{rule_id, sid|pseudonym, start, end, reason, owner}]
    suppressions: List[dict] = field(default_factory=list)
    # 17.6 vaka çıkış entegrasyonları: [{type: jsonl}, {type: webhook, url, secret_env, headers, timeout, retries}]
    sinks: List[dict] = field(default_factory=list)
    # kalıcı durum: müşteri dizinindeki SQLite dosyası (günlük servis modu); boş → yalnızca bellek
    state_file: str = "state.sqlite"
    # 19.5 ablasyon anahtarları: bileşenin gerçekten değer ürettiğini ölçmek için kapatılabilir (üretimde True)
    correlation_multipliers: bool = True  # 13.3 çarpanlar
    peer_context: bool = True  # 9.2 akran ağırlığı (False → yalnızca kişisel baseline; yeni hesapta akran zorunlu kalır)
    # 14.6 "model skoru kural skorunu ezmez, ona eklenir": öğrenen modelin 7g olasılığı ham skora bu ağırlıkla eklenir (0 = kapalı)
    prediction_weight: float = 0.0
    # 13.2 / ADR-015 akran çarpanının nötr noktası: akran oranı bu kattayken şiddet çarpanı 1,0 (1.1'deki VE eşiği 5×)
    peer_neutral_ratio: float = 5.0
    # aldatma katmanı: tuzak varlıklar {hesaplar: [...], kaynaklar: [fnmatch kalıpları], cihazlar: [...]} — meşru kullanımı yok,
    # her etkileşim deterministik kritik tespit (13.5 tek-sinyal istisnası); boş → katman kapalı
    honeytokens: Dict[str, List[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.alarm_budget_per_day < 1:
            raise ValueError("alarm_budget_per_day ≥ 1 olmalı (analist kapasitesi)")
        if not 0 < self.critical_percentile <= 1:
            raise ValueError("critical_percentile (0, 1] aralığında olmalı")
        if self.short_window_days >= self.long_window_days:
            raise ValueError("kısa pencere uzun pencereden küçük olmalı (9.2)")
        if abs(self.fusion_temporal_weight + self.fusion_structural_weight - 1.0) > 1e-9:
            raise ValueError("füzyon ağırlıkları toplamı 1 olmalı")
        if self.llm_backend not in ("none", "ollama", "anthropic"):
            raise ValueError("llm_backend: none | ollama | anthropic")
        if self.peer_neutral_ratio <= 1.0:
            raise ValueError("peer_neutral_ratio > 1 olmalı (log ölçeğinde nötr nokta)")
        if self.llm_on_injection not in ("template", "sanitized"):
            raise ValueError("llm_on_injection: template | sanitized")
        self.available_sources = tuple(self.available_sources)
        self.critical_assets = tuple(self.critical_assets)
        HoneytokenRegistry.from_config(self.honeytokens)  # şema hatası açık hata verir; sessiz düşüş yok

    @property
    def honeytoken_registry(self) -> HoneytokenRegistry:
        return HoneytokenRegistry.from_config(self.honeytokens)

    @classmethod
    def from_yaml(cls, path: Union[str, Path], **overrides: Any) -> "TenantConfig":
        """Müşteri bazında yapılandırma dosyası (17.1); komut satırı değerleri dosyayı ezer."""
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        unknown = set(raw) - {f_.name for f_ in fields(cls)}
        if unknown:
            raise ValueError(f"Bilinmeyen yapılandırma alanları: {sorted(unknown)}")
        raw.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**raw)
