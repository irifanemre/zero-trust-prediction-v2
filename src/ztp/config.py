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
    alarm_budget_per_day: int = 30
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
    # ---- v3 revizyonları (r5.2 derslerinden). Hepsi ayarlanabilir ve VARSAYILAN KAPALI: 14.5 gereği bir bileşen
    # ablasyonla değer ürettiği gösterilmeden açılmaz. Açık hâlleri `ablation.VARIANTS` ile ölçülür.
    # #1 çok ufuklu kanıt biriktirici: sayım sinyalleri bu pencerelerde de toplanır (7g zaten vardı)
    accumulator_windows: Tuple[int, ...] = (1, 3, 7, 14, 30)
    # #3 kanıt çeşitliliği: aynı gün N+ FARKLI veri kaynağından tespit varsa çarpan (0 = kapalı)
    source_diversity_min: int = 3
    source_diversity_multiplier: float = 0.0
    # #4 varlık katmanlandırma: {tier0: [fnmatch kalıpları], tier1: [...]}; erişim varsa çarpan (0 = kapalı)
    asset_tiers: Dict[str, List[str]] = field(default_factory=dict)
    tier0_multiplier: float = 0.0
    tier1_multiplier: float = 0.0
    # #2 öncelik sıralayıcı: kuyruk sırası ham skordan AYRILIR. Ağırlıklar 0 iken sıra bugünküyle birebir aynıdır.
    priority_momentum_weight: float = 0.0  # risk yörüngesi eğimi (PRED sinyali)
    priority_diversity_weight: float = 0.0  # farklı veri kaynağı sayısı
    priority_asset_weight: float = 0.0  # dokunulan en yüksek varlık katmanı
    priority_peer_weight: float = 0.0  # akran grubundan yapısal sapma

    # --- v4: revizeler.txt / revizeler2.txt bileşenleri. HEPSİ varsayılanda kapalı; açılması ablasyona bağlı (14.5)
    graf_enabled: bool = False  # temporal heterogeneous graph sinyalleri üretilsin mi (üretmek skoru değiştirmez)
    graf_agirligi: float = 0.0  # graf riskinin skor çarpanına katkısı: 1 + agirlik·graf_riski. 0 → skor değişmez
    graf_gecmis_gun: int = 30  # graf sinyallerinde kişisel geçmiş penceresi
    graf_seyrek_esik: int = 3  # bu sayıdan az akranın dokunduğu hedef "seyrek"
    graf_yayilim_adim: int = 2  # risk yayılımı kaç adım (revizeler2 §3)
    graf_yayilim_sonum: float = 0.5
    bayes_kapi_esigi: float = 0.0  # 0 → kapalı. Sonsal olasılığı bunun altındaki vaka kuyruğa alınmaz (§1.3)
    bayes_min_gozlem: int = 10  # bu kadar etiketi olmayan örüntü susturulmaz
    adwin_enabled: bool = False  # kavram kayması baz çizgisini kessin mi (§1.4)
    adwin_delta: float = 0.002
    belirsizlik_enabled: bool = False  # Venn-Abers olasılık aralığı vakaya eklensin mi (§1.2)
    kanit_dogrulama: str = "kapali"  # kapali | dengeli | siki — LLM özetinde referanssız cümleler (§7.2)
    cok_ajanli_rapor: bool = False  # Investigator/Verifier/Reporter zinciri (§7.3)

    # --- v5: r6.2 ölçümünün yapısal bulgusuna cevap (`docs/r62-v4-olcumu.md`, `docs/literatur-katman-haritasi.md`).
    # Bulgu: graf ÇARPAN olduğu için tabanı sıfır olan kullanıcıya ulaşamaz (1,5 × 0 = 0) ve kaçan insider tam
    # bu durumdaydı. Aşağıdaki iki yol o tavanı kaldırır; ikisi de varsayılanda KAPALI (14.5).
    # (1) Graf riskini çarpan yerine TOPLAMSAL terim olarak ekle: raw += agirlik · graf_riski · 10
    graf_toplamsal_agirlik: float = 0.0
    # (2) Kurala bağlı olmayan denetimsiz anomali kanalı (literatür §1.2–1.4): ECOD / Isolation Forest
    anomali_enabled: bool = False  # kanal sinyal üretsin mi (üretmek skoru değiştirmez)
    anomali_tur: str = "ecod"  # ecod (parametresiz, deterministik, boyut katkılı) | orman (Isolation Forest)
    anomali_agirligi: float = 0.0  # raw += agirlik · anomali_skoru · 10. 0 → skor değişmez
    anomali_pencere_gun: int = 30  # uyum penceresi; skorlanan günden ÖNCE biter (sızıntı yok)
    anomali_yenileme_gun: int = 7  # kaç günde bir yeniden uyumlanır
    # Denetimsiz skor bu yüzdeliği aşarsa v2 doğrulama kapısında "güçlü tek sinyal" sayılır (0 = kapalı).
    # Kapalıyken kurala bağlı olmayan bir vaka kuyruğa yalnız `kuyruk_kacis_yuzdelik` üzerinden girebilir.
    anomali_dogrulama_esigi: float = 0.0
    # Lojistik modelde sınıf ağırlığı: sıralama (AUPRC, recall@bütçe) ile kalibrasyon (Brier) arasında TAKAS.
    # Varsayılan kapalı — gerekçe `prediction_model.LogisticModel.fit` içinde; ikisi birlikte raporlanır.
    pred_sinif_agirligi: bool = False

    # --- v6 katman A: analist geri bildirim döngüsü (`docs/sprint-v6-on-kayit.md`).
    # 30 Ekim ablasyonu ölçtü: Bayes kapısı etiketsiz ortamda SIFIR eleme yapıyor, `belirsizlik_enabled`
    # ise hiçbir yerden okunmuyordu. Bu üç bayrak döngüyü kapatır; hepsi varsayılanda kapalı (14.5).
    geri_bildirim_dongusu: bool = False  # kuyruk → analist kararı → etiket → kapı + model
    analist_gecikme_gun: int = 2  # etiket bu kadar gün SONRA görünür (sızıntıya karşı; gerçekte analist anında kapatmaz)
    analist_hata_orani: float = 0.0  # etiketin bu oranı ters çevrilir — gürültülü etikete dayanıklılık ölçümü
    pred_yeniden_egitim_gun: int = 0  # 0 → kapalı. Kaç günde bir model yeniden eğitilir
    pred_min_yeni_etiket: int = 25  # son eğitimden beri bu kadar yeni etiket yoksa eğitilmez

    # --- v6 katman B: saldırı yolu tahmini. Çıktı ilk sürümde SKORA GİRMEZ (agirlik 0) — yalnız vaka
    # anlatısına gider ve kanıt doğrulayıcıdan geçer, böylece yanlış tahmin precision'ı bozamaz.
    saldiri_yolu_enabled: bool = False
    saldiri_yolu_model: str = "ngram"  # ngram (sayım, deterministik) | transformer ([ml] eklentisi gerekir)
    saldiri_yolu_baglam: int = 2  # n-gram bağlam uzunluğu; transformer'da pencere
    saldiri_yolu_agirligi: float = 0.0  # 0 → skora girmez. Açılması ablasyona bağlıdır (14.5)

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
        if not self.accumulator_windows or any(int(w) < 1 for w in self.accumulator_windows):
            raise ValueError("accumulator_windows: pozitif gün listesi olmalı")
        if any(int(w) > self.long_window_days for w in self.accumulator_windows):
            raise ValueError("accumulator_windows uzun pencereyi aşamaz (9.2)")
        unknown_tiers = set(self.asset_tiers) - {"tier0", "tier1"}
        if unknown_tiers:
            raise ValueError(f"asset_tiers: yalnız tier0/tier1 (bilinmeyen: {sorted(unknown_tiers)})")
        if self.graf_agirligi < 0 or self.graf_agirligi > 5:
            raise ValueError("graf_agirligi [0, 5] aralığında olmalı")
        if self.graf_agirligi and not self.graf_enabled:
            raise ValueError("graf_agirligi > 0 için graf_enabled açık olmalı (sinyal üretilmeden çarpan uygulanamaz)")
        if self.graf_gecmis_gun < 1 or self.graf_gecmis_gun > self.long_window_days:
            raise ValueError("graf_gecmis_gun 1 ile uzun pencere arasında olmalı")
        if self.graf_seyrek_esik < 1:
            raise ValueError("graf_seyrek_esik ≥ 1 olmalı")
        if self.graf_yayilim_adim < 1 or not 0 < self.graf_yayilim_sonum <= 1:
            raise ValueError("graf_yayilim_adim ≥ 1 ve graf_yayilim_sonum (0, 1] olmalı")
        if not 0 <= self.bayes_kapi_esigi < 1:
            raise ValueError("bayes_kapi_esigi [0, 1) aralığında olmalı (0 = kapalı)")
        if self.bayes_min_gozlem < 0:
            raise ValueError("bayes_min_gozlem negatif olamaz")
        if not 0 < self.adwin_delta < 1:
            raise ValueError("adwin_delta (0, 1) aralığında olmalı")
        if self.kanit_dogrulama not in ("kapali", "dengeli", "siki"):
            raise ValueError("kanit_dogrulama: kapali | dengeli | siki")
        if self.graf_toplamsal_agirlik < 0 or self.graf_toplamsal_agirlik > 5:
            raise ValueError("graf_toplamsal_agirlik [0, 5] aralığında olmalı")
        if self.graf_toplamsal_agirlik and not self.graf_enabled:
            raise ValueError("graf_toplamsal_agirlik > 0 için graf_enabled açık olmalı (sinyal üretilmeden terim eklenemez)")
        if self.anomali_tur not in ("ecod", "orman"):
            raise ValueError("anomali_tur: ecod | orman")
        if self.anomali_agirligi < 0 or self.anomali_agirligi > 5:
            raise ValueError("anomali_agirligi [0, 5] aralığında olmalı")
        if self.anomali_agirligi and not self.anomali_enabled:
            raise ValueError("anomali_agirligi > 0 için anomali_enabled açık olmalı")
        if not 0 <= self.anomali_dogrulama_esigi < 1:
            raise ValueError("anomali_dogrulama_esigi [0, 1) aralığında olmalı (0 = kapalı)")
        if self.anomali_dogrulama_esigi and not self.anomali_enabled:
            raise ValueError("anomali_dogrulama_esigi > 0 için anomali_enabled açık olmalı")
        if self.anomali_pencere_gun < 1 or self.anomali_pencere_gun > self.long_window_days:
            raise ValueError("anomali_pencere_gun 1 ile uzun pencere arasında olmalı")
        if self.anomali_yenileme_gun < 1:
            raise ValueError("anomali_yenileme_gun ≥ 1 olmalı")
        if self.analist_gecikme_gun < 0:
            raise ValueError("analist_gecikme_gun negatif olamaz")
        if not 0 <= self.analist_hata_orani < 1:
            raise ValueError("analist_hata_orani [0, 1) aralığında olmalı")
        if self.pred_yeniden_egitim_gun < 0:
            raise ValueError("pred_yeniden_egitim_gun negatif olamaz (0 = kapalı)")
        if self.pred_min_yeni_etiket < 1:
            raise ValueError("pred_min_yeni_etiket ≥ 1 olmalı")
        if self.pred_yeniden_egitim_gun and not self.geri_bildirim_dongusu:
            raise ValueError("pred_yeniden_egitim_gun > 0 için geri_bildirim_dongusu açık olmalı (etiket gelmeden eğitilemez)")
        if self.saldiri_yolu_model not in ("ngram", "transformer"):
            raise ValueError("saldiri_yolu_model: ngram | transformer")
        if self.saldiri_yolu_baglam < 1:
            raise ValueError("saldiri_yolu_baglam ≥ 1 olmalı")
        if self.saldiri_yolu_agirligi < 0 or self.saldiri_yolu_agirligi > 5:
            raise ValueError("saldiri_yolu_agirligi [0, 5] aralığında olmalı")
        if self.saldiri_yolu_agirligi and not self.saldiri_yolu_enabled:
            raise ValueError("saldiri_yolu_agirligi > 0 için saldiri_yolu_enabled açık olmalı")
        self.accumulator_windows = tuple(sorted({int(w) for w in self.accumulator_windows}))
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
