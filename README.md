# Zero Trust Prediction

**Kullanıcı ve varlık davranışlarından proaktif risk öngörüsü** — MSSP/MSOC ortamları için UEBA + Zero Trust Prediction + Knowledge Graph mimarisinin çalışan, ölçülebilir doğrulama uygulaması.

> *English summary:* A reference implementation of a layered insider-risk architecture: OCSF-style ingestion → identity resolution → data-quality gating → low-cost graph construction → UEBA (robust personal baselines + peer context + Isolation Forest support) → trajectory/regime-change prediction with a 7-day horizon → alarm-budgeted risk scoring → deep graph analysis on the risky subset → evidence-bound reporting → analyst feedback loop. Validated on the CERT Insider Threat Test Dataset (r4.2): 26/34 labeled insiders surfaced with a 10-case/day budget over 1000 users.

## Neden

SOC'lerde iki darboğaz var: alarm hacmi (çoğu yanlış pozitif) ve reaktif yapı (olay olduktan sonra devreye girme). Bu proje, bir kullanıcının risk profilinin **zaman içinde nereye gittiğini** ve **kimle/neyle bağlantılı olduğunu** birlikte değerlendirip analiste **az sayıda ama gerekçeli** vaka üretir. Tahmin hiçbir zaman engelleme kararı vermez; en yüksek aksiyon analiste vaka açmaktır.

## Mimari

```
VERİ TOPLAMA (OCSF-lite) ─▶ KİMLİK EŞLEŞTİRME ─▶ VERİ KALİTESİ ─▶ GRAF OLUŞTURMA (tüm kullanıcılar, düşük maliyet)
      ─▶ UEBA: kişisel robust baseline (ANA) + akran kıyası (BAĞLAM) + Isolation Forest (DESTEK)
      ─▶ ZERO TRUST PREDICTION: risk yörüngesi (EWMA+eğim) + rejim değişimi (changepoint) → 7 günlük olasılık
      ─▶ RİSK SKORLAMA: Σ[ağırlık × şiddet × bozunum] × korelasyon çarpanları → yüzdelik kalibrasyon → ALARM BÜTÇESİ
      ─▶ DERİN GRAF ANALİZİ (yalnızca riskli alt küme): zaman-sıralı yollar, yanal hareket, etki alanı, ATT&CK
      ─▶ BİRLEŞİK SKOR ─▶ KADEMELİ MÜDAHALE (insan kararı) ─▶ ŞABLON / LLM RAPOR (kanıta bağlı) ─▶ ETİKET DEPOSU
```

| Katman | Modül | Temel karar |
|---|---|---|
| Şema ve sabitler | `ztp/schema.py` | OCSF-lite kolonlar; kaynak bağımsızlığı |
| İstatistik | `ztp/stats.py` | Robust z (MAD), Poisson/NegBin, dairesel istatistik, EWMA, changepoint, Jaccard |
| Kimlik | `ztp/identity.py` | Kanonik SID, zaman aralıklı IP→kullanıcı, çözümlenmemiş kuyruk, HMAC takma ad + break-glass |
| Veri kalitesi | `ztp/quality.py` | Kaynak düşerse bağımlı tespitler askıya alınır; takvim etkisi ayrımı |
| Graf | `ztp/graph/` | `GraphStore` soyutlaması (NetworkX uygulaması), bilgi/gözlem grafı ayrımı, derin analiz |
| Özellikler / akran / baseline | `ztp/features.py`, `ztp/peers.py`, `ztp/profile.py` | Varlık-gün özellikleri; yapısal+davranışsal akran; hesap yaşına göre ağırlık (akran hiç sıfırlanmaz) |
| Prediction | `ztp/prediction.py` | Yörünge + rejim değişimi; İK sinyalleri; 7 günlük ufuk |
| Tespit | `ztp/detection/` | Detection-as-code (`rules/*.yaml`), güvenli ifade değerlendirici, yaşam döngüsü, gölge mod, bastırma |
| Aldatma (honeytoken) | `ztp/deception.py` | Tuzak hesap/kaynak/cihaz etkileşimi: baseline yok, deterministik kritik tespit; tuzak hesap kullanımı hesaba değil kaynağa (cihaz sahibi → IP kiralaması) atfedilir |
| Skorlama | `ztp/scoring.py` | Çarpanlar (×2.5 farklı taktik), yüzdelik, alarm bütçesi + kritik istisna, açık vaka |
| Raporlama | `ztp/reporting/` | Deterministik şablon her zaman; LLM (Ollama / Anthropic) yalnızca kanıta bağlı özet; injection'a kapalı istem, bütünlük doğrulamalı ATT&CK bilgi tabanı (RAG), sıkı çıktı doğrulaması |
| Öğrenen tahmin + kalibrasyon | `ztp/prediction_model.py` | Sezgisel başlangıç modeli, JSON'da saklanan lojistik model, Brier/AUC/ECE güvenilirlik raporu; model kural skorunu ezmez, ekler |
| Geri besleme / ölçüm | `ztp/feedback.py`, `ztp/metrics.py`, `ztp/ablation.py` | Etiket deposu, FP sebebi zorunlu, kapsama/erkenlik/precision@k, kural sağlığı, sistem sağlığı, ablasyon |
| Kalıcı durum / entegrasyon | `ztp/state.py`, `ztp/integrations.py`, `ztp/data/files.py` | SQLite durum deposu (günlük servis, idempotent), imzalı webhook + JSONL sink, dosya girişi |
| Orkestrasyon | `ztp/pipeline.py`, `ztp/cli.py` | Toplu ve artımlı koşu (eşdeğerlik testli); CLI |

Bağımlılık yönü tek taraflıdır: `schema/stats → features/identity/quality/graph → profile/prediction/detection → scoring → reporting/metrics → pipeline → cli`. Tespit motoru raporlama katmanına bağımlı değildir (açıklama üretici enjekte edilir).

## Kurulum

```bash
git clone https://github.com/irifanemre/zero-trust-prediction.git
cd zero-trust-prediction
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # LLM raporlama için: pip install -e ".[dev,llm]"
```

## Hızlı başlangıç

```bash
ztp --test-rules                                   # detection-as-code birim testleri
ztp --synthetic --users 150 --days 30 --budget 8 --out ./ztp_out
ztp --synthetic --llm ollama --ollama-model gemma3:12b     # lokal LLM ile rapor (şablon her zaman yedek)
ztp --out ./ztp_out --tenant musteri-A --label C-20260830-2493 --decision yanlis_pozitif --reason bilinen_istisna --analyst a1
ztp --config configs/tenant.example.yaml --synthetic
ztp --synthetic --train-prediction                 # 7g olasılık modelini etiketten eğit, zamansal holdout ile kalibrasyon raporla
ztp --synthetic --ablation                         # 19.5: prediction / ilişkisel / çarpan / akran kapalıyken fark
ztp --synthetic --honeytokens                      # aldatma katmanı: tuzak varlıklar + S10 tuzak etkileşimi senaryosu
ztp --synthetic --state --days 30                  # toplu ısınma + durum kaydı, ardından günlük servis:
ztp --daily 2026-09-17 --events gun.parquet --directory dizin.csv --config musteri.yaml --out ./ztp_out
pytest                                             # 82 test (~3 dk; uçtan uca, güvenlik ve toplu≡artımlı eşdeğerlik testleri dahil)
```

Çıktılar `ztp_out/<tenant>/` altında: `queue_<gün>.txt` (analist kuyruğu), `cases/*.json`, `metrics.json`,
`coverage_report.json`, `health.json`, `shadow_log.jsonl`, `suppressed.jsonl`, `labels.json`,
`detections/*.yaml` (çalışan katalog), `identity_vault.RESTRICTED.json`, `audit.jsonl`.

## CERT Insider Threat Test Dataset ile doğrulama

Veri: SEI/CMU, https://doi.org/10.1184/R1/12841247 (CC BY 4.0). `scripts/download_cert.py` sha256 doğrulamalı indirir.

```bash
python scripts/download_cert.py --release r4.2 --dest ./cert_data     # ~4.8 GB + cevap anahtarı
ztp --cert-dir cert_data/r4.2 --end 2010-11-30 --days 90 --budget 10 --tenant cert-r42 --out ./ztp_out
```

**r4.2** (1000 kullanıcı, 13,3M olay, 2 Eyl–30 Kas 2010, bütçe 10 vaka/gün, 34 etiketli insider):

| Senaryo | n | Kuyruğa girdi | Medyan erkenlik |
|---|---|---|---|
| S1 — mesai dışı + USB + wikileaks yükleme, ayrılış | 14 | **14/14** | 8 gün |
| S2 — iş arama siteleri + USB artışı | 17 | **10/11** değerlendirilebilir (6'sının USB fazı pencere dışında) | 20 gün |
| S3 — sysadmin keylogger, amirin makinesinden giriş | 3 | **2/3** (1'i tetiklendi, bütçe dışı kaldı) | 6 gün |

Cevap anahtarı etiket rolünde precision: **@1 = 0,39 · @3 = 0,22 · @5 = 0,14 · @10 = 0,09** (varlık-gün);
kuyruğa giren 263 kullanıcının 27'si insider. Bütçe sessiz günlerde tek-sinyalli benign kullanıcılarla dolar — bu,
sabit eşik yerine kapasite tabanlı kuyruk tasarımının bilinçli sonucudur ve `precision@k` eğrisiyle raporlanır.

Prediction katmanı (7 günlük olasılık), aynı veride zamansal holdout ile: sezgisel model AUC 0,61 → öğrenen model
**AUC 0,86, ECE 0,002** (Brier 0,0081 ≈ taban 0,0084). Ablasyon: akran bağlamı kapatılınca kapsama 16→13/26;
prediction ve ilişkisel kurallar bu veride fark yaratmadı (İK sinyali yok) — ölçüldü ve belgelendi, saklanmadı. Ayrıntılar ve sınırlar: [docs/cert-validation.md](docs/cert-validation.md). Önemli uyarı: kurallar r4.2 sonuçları
görüldükten sonra ayarlanmıştır; yansız rakam için henüz bakılmamış bir sürümde (r5.2/r6.2) tekrar gerekir.

## Tespit kataloğu (`src/ztp/detection/rules/`)

UEBA-0001 mesai dışı aktivite · 0002 ilk kez görülen uygulama · 0003 anormal veri çıkışı · 0004 imkânsız seyahat ·
0005 yeni cihaz/konum (akran nadirliğiyle ölçekli) · 0006 başarısız giriş yığını · 0007 mesai dışı toplu dosya erişimi ·
0008 hesap yaşı × keşif · 0009 akran yapısal sapma (gölge) · DQ-0010 log sessizliği · PRED-0011 yetki artışı sonrası kayma ·
PRED-0012 risk yörüngesi · PRED-0013 uzun sessizlik sonrası aktivite · PRED-0014 ayrılık öncesi desen ·
REL-0015 paylaşılan cihaz üzerinden yayılma · REL-0016 ortak kaynak · UEBA-0017 taşınabilir medya (günlük + 7g kümülatif) ·
HONEY-0018 tuzak hesap · HONEY-0019 tuzak dosya/paylaşım · HONEY-0020 tuzak sunucu (aldatma katmanı; `kritik: true`) ·
UEBA-IF01 Isolation Forest (gölge).

Her kural: sürüm, durum (`taslak → golge-modda → yayinda → emekli`), ATT&CK, veri kaynakları, koşullar, şiddet tanımı,
ağırlık, bastırma, sahip, runbook, kanıt aileleri ve **test senaryoları**. Runbook'suz kural yayına alınamaz.

## Tasarım ilkeleri

- **Sabit eşik yok:** günlük inceleme kuyruğu analist kapasitesi kadar; kritik olaylar bütçeden bağımsız.
- **Tek sinyal uyarı üretmez:** tespitler varlık-gün bağlamında toplanır, farklı ATT&CK taktiklerinin birleşimi en yüksek çarpanı alır.
  Tek istisna **aldatma katmanı**: tuzak varlıkla etkileşimin meşru açıklaması yoktur; tek etkileşim kritik vaka üretir ve
  bütçeden bağımsız kuyruğa girer (`honeytokens:` yapılandırması).
- **Açıklanabilirlik zorunlu:** her puan bir kurala, her kural olay kimliklerine bağlıdır; LLM skorlama yolunda değildir.
- **Tahmin engellemez:** erişim kısıtlama yalnızca doğrulanmış olay + yetkili insan kararıyla (`authorize_containment`).
- **Gizlilik varsayılan:** analist takma ad görür; kimlik açma ikinci onay ve denetim izi gerektirir.
- **Sessizce yanlış çalışmaktansa açıkça durmak:** kaynak kalitesi düşerse bağımlı tespitler askıya alınır; uyarı hacmi bir sağlık metriğidir.
- **LLM/RAG injection'a kapalı:** log kaynaklı her metin veridir — kanonikleştirilir, talimat benzeri içerik redakte edilip
  bayraklanır, nonce'lu yapısal bloklarda modele gider; RAG yalnızca teknik kimliğiyle, SHA-256 doğrulamalı bilgi tabanından
  getirir; çıktı olay kimliği/takma ad/sayı/aksiyon dili açısından doğrulanmadan analiste ulaşmaz. Ayrıntı: [docs/llm-security.md](docs/llm-security.md).

## Operasyon

Günlük servis modu (`--daily`), SQLite durum deposu, imzalı webhook/JSONL sink'leri ve runbook'lar için
[docs/operations.md](docs/operations.md). Prediction katmanının kalibrasyon ölçümü, öğrenen model ve ablasyon için
[docs/prediction.md](docs/prediction.md).

## Dokümantasyon

- [docs/mimari-dokuman.md](docs/mimari-dokuman.md) — mimari dokümanın md sürümü (**1.2**): Final 1.0 metni + uygulama ve CERT
  doğrulamasıyla düzeltilen bölümler (`1.1 düzeltmesi` blokları), mimari ↔ uygulama denetiminden çıkan düzeltmeler
  (`1.2 düzeltmesi` blokları), 1.0→1.1 ve 1.1→1.2 değişiklik günlükleri, ADR-011…015.
  PDF: [docs/Zero_Trust_Prediction_Mimari_v1.1.pdf](docs/Zero_Trust_Prediction_Mimari_v1.1.pdf) — **1.1 baskısıdır, md 1.2'dir**;
  yeniden üretmek için (`pip install -e ".[docs]"`, pango gerekir):
  `python scripts/build_pdf.py docs/mimari-dokuman.md docs/Zero_Trust_Prediction_Mimari_v1.2.pdf`.
- [docs/bulgular.md](docs/bulgular.md) — mimari ↔ uygulama denetiminin bulguları: ne beklendiği, ne bulunduğu, yapılan
  değişiklik ve önce/sonra ölçümü.
- [docs/architecture.md](docs/architecture.md) doküman→kod eşlemesi · [docs/cert-validation.md](docs/cert-validation.md) ·
  [docs/prediction.md](docs/prediction.md) · [docs/operations.md](docs/operations.md) · [docs/llm-security.md](docs/llm-security.md)

## Bilinen sınırlar

ATT&CK bilgi grafı örnek alt kümedir; saklama süresi / silme hakkı uygulanmadı; öğrenen model yalnızca cevap anahtarı
(test) veya analist etiketiyle eğitilir ve varsayılan olarak skora eklenmez (`prediction_weight: 0`); CERT'te İK sinyalleri
olmadığından PRED-0011/13/14 gerçek veride sınanamadı. Yol haritası için [docs/architecture.md](docs/architecture.md).

## Lisans

Apache-2.0 — bkz. [LICENSE](LICENSE).
