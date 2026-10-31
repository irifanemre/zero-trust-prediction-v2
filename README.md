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
| Geri besleme / ölçüm | `ztp/feedback.py`, `ztp/metrics.py`, `ztp/ablation.py` | Etiket deposu, FP sebebi zorunlu, kapsama/erkenlik/precision@k **ve Recall@K**, kural sağlığı, sistem sağlığı, ablasyon |
| Kalıcı durum / entegrasyon | `ztp/state.py`, `ztp/integrations.py`, `ztp/data/files.py` | SQLite durum deposu (günlük servis, idempotent), imzalı webhook + JSONL sink, dosya girişi |
| Orkestrasyon | `ztp/pipeline.py`, `ztp/cli.py` | Toplu ve artımlı koşu (eşdeğerlik testli); CLI |

### v4 katmanı — ilişkisel, zamansal ve belirsizlik bileşenleri

Araştırma literatüründen (temporal heterogeneous GNN, conformal prediction, ADWIN, çok ajanlı LLM) türetilen
bileşenler ayrı modüller olarak eklendi. **Hepsi varsayılanda kapalıdır** ve açılmaları ablasyon ölçümüne bağlıdır;
gerekçesi [aşağıda](#neden-hepsi-varsay%C4%B1landa-kapal%C4%B1).

| Bileşen | Modül | Ne sorar / ne yapar | Bayrak |
|---|---|---|---|
| Temporal heterogeneous graph | `ztp/gnn/temporal_graph.py` | Kenarları **akış** olarak tutar: her etkileşim kendi zaman damgasıyla. "Bu ilişki yeni mi", "aralıkta kimler dokundu" sorulabilir | `graf_enabled` |
| Graf risk sinyalleri | `ztp/gnn/tgn_model.py` | `graf_yenilik`, `graf_seyreklik`, `graf_tur_kaymasi`, `graf_komsu_riski` | `graf_agirligi` |
| RiskScore-Guided yayılım | `ztp/gnn/tgn_model.py::risk_yayilimi` | Davranışsal skoru **kaldırmaz**, grafa tohum verir; risk paylaşılan varlıklar üzerinden yayılır. Mesajlar kaynağıyla taşınır, kullanıcı kendi riskini geri almaz | `graf_yayilim_adim` |
| Erken uyarı / yörünge | `ztp/gnn/tgn_model.py` | `erken_uyari_suresi`: eşik gerçek olaydan kaç gün önce aşıldı. Eşiği aşıp düşen tek günlük sıçrama sayılmaz | — |
| Belirsizlik (Venn-Abers) | `ztp/gnn/conformal_eval.py` | Tekil olasılık yerine kalibre aralık (%81 → [%74, %88]); aralık genişliği "bu bölgede ne kadar veri var"ın ölçüsü. 20 noktanın altında `[0,1]` ve "gözlem süresi uzatılmalı" uyarısı | `belirsizlik_enabled` |
| Bayesian risk kapısı | `ztp/gnn/bayesian_gate.py` | Kuyruk **eksik kapanabilir**: zayıf kanıtlı vaka bütçede yer olsa da alınmaz. Kritik vakalar muaf; etiketi olmayan örüntü susturulmaz | `bayes_kapi_esigi` |
| ADWIN kavram kayması | `ztp/drift.py` | Yıllık izin dönüşü / departman geçişinde kişisel baz çizgisini keser; Hoeffding sınırı, üstel histogram (10.000 gözlem < 100 kova) | `adwin_enabled` |
| Kanıt doğrulayıcı | `ztp/llm_guards/claim_verifier.py` | LLM özetini **cümle cümle** denetler; vakada olmayan olay/kural kimliği ya da kanıtta geçmeyen sayı içeren cümleyi siler ve gerekçesini döndürür | `kanit_dogrulama` |
| Çok ajanlı SOC | `ztp/reporting/multi_agent.py` | Investigator (olgular) ve Verifier (imzalı ATT&CK tabanı) **deterministiktir, LLM kullanmaz**; model yalnızca anlatır. Teyit edilemeyen teknik rapora giremez | `cok_ajanli_rapor` |
| Recall@K | `ztp/metrics.py` | SOC kapasitesi ölçütü: "günde K vaka bakabiliyorsam insider'ların kaçını görürüm". precision@k'nin aksine taban oranından bağımsız | her koşuda açık |

#### Neden hepsi varsayılanda kapalı

Bu projede iki ekleme ölçüldü ve **reddedildi**:

- **Öğrenen modelin skora katılması** (`prediction_weight`): "tümü" üzerinde iyi görünüyordu; doğrulama parçasında
  precision@1 **0,188 → 0,145** düştü. Kazanç eğitim bulaşmasıydı.
- **Tuzak (decoy) dosyalarının honeytoken'a bağlanması**: r6.2'de 31.095 tuzak dosyası var, ama kullanıcıların
  **%80'i** bunlara rutin olarak dokunuyor. Bağlansaydı günde ~890 kritik vaka üretirdi.

İkisi de "mantıklı görünen ama ölçünce zarar veren" eklemelerdi. Bu yüzden her yeni bileşen önce gölge modda
ölçülür (14.5); fayda ölçülmeden karar yoluna girmez. Kapalı davranışın birebir korunduğu
`scripts/surum_karsilastir.py` ile r4.2'de doğrulanır ve test takımı bunu ayrıca korur.

Bağımlılık yönü tek taraflıdır: `schema/stats → features/identity/quality/graph → profile/prediction/detection → scoring → reporting/metrics → pipeline → cli`. Tespit motoru raporlama katmanına bağımlı değildir (açıklama üretici enjekte edilir).

## Kurulum

```bash
git clone https://github.com/irifanemre/zero-trust-prediction-v2.git
cd zero-trust-prediction-v2
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
pytest                                             # 117 test (~3 dk; uçtan uca, güvenlik ve toplu≡artımlı eşdeğerlik testleri dahil)
```

Çıktılar `ztp_out/<tenant>/` altında: `queue_<gün>.txt` (analist kuyruğu), `cases/*.json`, `metrics.json`,
`coverage_report.json`, `health.json`, `shadow_log.jsonl`, `suppressed.jsonl`, `labels.json`,
`detections/*.yaml` (çalışan katalog), `identity_vault.RESTRICTED.json`, `audit.jsonl`.

## CERT Insider Threat Test Dataset ile doğrulama

Veri: SEI/CMU, https://doi.org/10.1184/R1/12841247 (CC BY 4.0). `scripts/download_cert.py` sha256 doğrulamalı indirir.

Veri **repo dışında** durur (açılınca ~15–20 GB; repo OneDrive gibi senkronlanan bir klasördeyse oraya indirmeyin).
Yol repoya gömülmez, `ZTP_CERT_PATH` ortam değişkeniyle verilir. Değişken sürüm dizinini (`…/r4.2`) ya da onu içeren
kök dizini gösterebilir; sürüm dizin adından okunduğu için dizin adı `r4.2` biçiminde kalmalıdır.

```bash
python scripts/download_cert.py --release r4.2 --dest C:/data/cert_r4.2   # ~4.8 GB + cevap anahtarı (answers/)
```

```powershell
# Windows PowerShell — yalnızca bu oturum:
$env:ZTP_CERT_PATH = "C:\data\cert_r4.2\r4.2"
# kalıcı (yeni açılan terminallerde geçerli olur):
setx ZTP_CERT_PATH "C:\data\cert_r4.2\r4.2"
```

```bash
# Linux / macOS
export ZTP_CERT_PATH=/data/cert_r4.2/r4.2

# --cert-dir değersiz verilirse yol ZTP_CERT_PATH'ten okunur; açık yol verilirse o kullanılır
ztp --cert-dir --end 2010-11-30 --days 90 --budget 10 --tenant cert-r42 --out ./ztp_out
```

Cevap anahtarı varsayılan olarak sürüm dizininin kardeşi `answers/` altında aranır (`--answers-dir` ile değiştirilebilir).
Değişken ayarlı olsa bile kaynak belirtmeyen `ztp` sentetik veriyle çalışır; CERT yalnızca `--cert-dir` ile seçilir.

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
prediction ve ilişkisel kurallar bu veride fark yaratmadı (İK sinyali yok) — ölçüldü ve belgelendi, saklanmadı. Ayrıntılar ve sınırlar: [docs/bulgular.md](docs/bulgular.md). Önemli uyarı: kurallar r4.2 sonuçları
görüldükten sonra ayarlanmıştır; yansız rakam için henüz bakılmamış bir sürümde tekrar gerekiyordu — r5.2 kör koşusu aşağıda.

**r5.2 kör koşu** (kurallar dondurulmuş, tek koşu; 1102 kullanıcılık katmanlı örneklem, 56 insider, 360 gün): değerlendirilebilir yakalama **25/30 (0,83)**, ayarda hiç görülmemiş S4 senaryosu 4/4, precision@1 **0,20**, erkenlik medyanı 9 gün. r4.2'de eğitilen öğrenen model r5.2'ye taşınmadı (AUC 0,69). 90 günlük pencere başına yanlış alarm alan normal kullanıcı r4.2'de %26, r5.2'de %24. 70/15/15 grup bazında karşılaştırma ve sapma kaydı: [docs/cert-r42-r52-karsilastirma.md](docs/cert-r42-r52-karsilastirma.md).

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
  getirir; çıktı olay kimliği/takma ad/sayı/aksiyon dili açısından doğrulanmadan analiste ulaşmaz. Ayrıntı: mimari doküman Ek D.4.

## Operasyon

Günlük servis modu (`--daily`), SQLite durum deposu, imzalı webhook/JSONL sink'leri ve runbook'lar için mimari doküman
Ek D.2; prediction katmanının kalibrasyon ölçümü, öğrenen model ve ablasyon için Ek D.3.

## Dokümantasyon

Beş belge var; dizin ve okuma sırası için [docs/README.md](docs/README.md). Başka md yok (runbook'lar
`src/ztp/detection/runbooks/` altında, kodun parçasıdır).

- [docs/mimari-dokuman.md](docs/mimari-dokuman.md) — mimari dokümanın md sürümü (**1.2**): Final 1.0 metni + uygulama ve CERT
  doğrulamasıyla düzeltilen bölümler (`1.1 düzeltmesi` blokları), mimari ↔ uygulama denetiminden çıkan düzeltmeler
  (`1.2 düzeltmesi` blokları), 1.0→1.1 ve 1.1→1.2 değişiklik günlükleri, ADR-011…015. Ek D: uygulama ayrıntıları
  (modüller ve bilinen sınırlar, operasyon, prediction ölçümü, LLM güvenliği). PDF üretmek için
  (`pip install -e ".[docs]"`, pango gerekir):
  `python scripts/build_pdf.py docs/mimari-dokuman.md docs/Zero_Trust_Prediction_Mimari_v1.2.pdf`.
- [docs/bulgular.md](docs/bulgular.md) — mimari ↔ uygulama denetiminin bulguları (ne beklendi, ne bulundu, yapılan
  değişiklik, önce/sonra ölçümü) ve CERT r4.2 doğrulaması (veri eşlemesi, sonuçlar, sınırlar).
- [docs/cert-r42-r52-karsilastirma.md](docs/cert-r42-r52-karsilastirma.md) — CERT r4.2 ve r5.2'nin 70/15/15 (eğitim / doğrulama / test)
  karşılaştırması: kural sistemi, öğrenen model, kural sağlığı, kör koşu ve sapma kaydı.
- **Ön kayıt belgeleri** — [docs/kor-kosu-r52-plani.md](docs/kor-kosu-r52-plani.md) ve
  [docs/kor-kosu-r62-plani.md](docs/kor-kosu-r62-plani.md). Her ikisi de ilgili veri seti **görülmeden** yazıldı:
  pencereler, bütçe, metrikler ve önceden yazılmış beklentiler. Koşu bir kezdir; sonucu görüp kural değiştirmek yasaktır.
  Kronoloji git'ten doğrulanabilir (bkz. docs/README.md).

## Kör koşu yöntemi

Bir tespit sistemini kendi ayarlandığı veriyle sınamak hiçbir şey kanıtlamaz. Bu depodaki rakamların dayanağı şu üç kural:

1. **Dondurma.** Kurallar, eşikler ve ağırlıklar `configs/freeze/` altında bir manifeste yazılır; manifest 34 dosyanın
   karmasını tutar. Koşudan hemen önce doğrulanır:
   `python -m ztp.freeze --check configs/freeze/kurallar-donduruldu-v3.json` → `donmuş durumla aynı`.
2. **Ön kayıt.** Veri görülmeden plan yazılır — beklenen sonuç dahil. Tutmayan beklenti sonucun kendisidir.
3. **Tek koşu.** Sonucu görüp kural/eşik/bütçe değiştirip yeniden koşmak yasaktır; böyle bir değişiklik yeni bir
   dondurma sürümü ve yeni bir veri seti gerektirir. Plandan sapmalar silinmez, ayrı başlık olarak yazılır.

r4.2 kuralların ayarlandığı veridir, yani **üst sınır**. r5.2 ve r6.2 kör veri setleridir.

## Bilinen sınırlar

ATT&CK bilgi grafı örnek alt kümedir; saklama süresi / silme hakkı uygulanmadı; öğrenen model yalnızca cevap anahtarı
(test) veya analist etiketiyle eğitilir ve varsayılan olarak skora eklenmez (`prediction_weight: 0`); CERT'te İK sinyalleri
olmadığından PRED-0011/13/14 gerçek veride sınanamadı. Yol haritası için mimari doküman §23 ve Ek D.1.

**v4 bileşenlerinin bilinen sınırları:**

- **Graf sinyalleri çarpan olarak girer** (`ham = taban × çarpan`). Hiçbir kuralı tetiklememiş bir kullanıcının
  tabanı sıfırdır ve çarpan onu yukarı taşıyamaz. r4.2'de kaçırılan 13 insider'ın **7'si** bu durumda; graf ancak
  sinyalleri **okuyan bir kural** yazıldığında onlara ulaşabilir — bu da yeni bir dondurma sürümü ve yeni bir
  veri seti gerektirir.
- **Bayesian kapı analist etiketi ister.** Etiketsiz bir CERT koşusunda tasarım gereği hiçbir şey elemez
  ("etiketi olmayan örüntü susturulmaz"). Cevap anahtarından öğrenmesi eğitim bulaşması olurdu.
- **TGN eğitilmiş değil.** `tgn_model.py` deterministik bir graf temel çizgisidir: ağırlık dosyası yoktur, aynı
  girdi aynı çıktıyı verir. Eğitilmiş bir TGN bunun yerine değil **üstüne** gelir ve ablasyonda buna karşı ölçülür.
- **Akış ve graf motoru altyapısı yok.** Kafka/Flink akış işleme ve Memgraph/Neo4j graf motoru geçişi
  tasarlanmış ama uygulanmamıştır; mevcut uygulama parça parça toplu işleme ve NetworkX üzerinedir.

## Ölçüm sonuçları

| Veri | Rolü | Kullanıcı | İnsider | Yakalama | precision@1 | Yanlış alarm |
|---|---|---|---|---|---|---|
| CERT r4.2 | kuralların ayarlandığı veri (**üst sınır**) | 1000 | 34 | 21/34 | 0,42 | %24–29 |
| CERT r5.2 | 1. kör koşu | ~1000 | 99 | — | 0,20 | %18–26 |
| CERT r6.2 | 2. kör koşu | 2801 | 5 | 3/4 | 0,014 | %19,2 |

precision@1'in r6.2'de düşmesi model kötüleşmesi değil **taban oranı etkisidir**: insider yoğunluğu r5.2'ye göre
55 kat düşük (binde 0,36). Yanlış alarm oranının üç veri setinde de %18–29 bandında kalması, kuralların tek bir
veri setine ezberlenmediğini gösterir. Ayrıntı ve sapma kayıtları: [`docs/kor-kosu-r62-sonuclar.md`](docs/kor-kosu-r62-sonuclar.md).

### v4 bileşenlerinin ölçümü (r4.2, 90 gün, bütçe 10)

Aynı veri, aynı pencere, aynı kurallar; tek değişken yapılandırma. **Model A** = bütün v4 bileşenleri kapalı,
**hepsi açık** = graf + ADWIN + Bayes kapısı + belirsizlik birlikte.

| Ölçüt | Model A | Hepsi açık | |
|---|---|---|---|
| **Yakalanan insider** (34 üzerinden) | 21 | **26** | ▲ +5 |
| Kuyruğa giren kullanıcı | 112 | 221 | ▼ iki katı |
| Toplam vaka | 729 | 958 | ▼ +%31 |
| Doğru / yanlış | 74 / 655 | 125 / 833 | |
| **precision@1** | **0,42** | 0,244 | ▼ |
| precision@10 | 0,109 | **0,135** | ▲ |
| **recall@1** (kullanıcı) | **0,471** | 0,353 | ▼ |
| recall@5 (kullanıcı) | 0,618 | **0,676** | ▲ |
| **recall@10** (kullanıcı) | 0,618 | **0,765** | ▲ |
| recall@30 (kullanıcı) | 0,618 | 0,765 | ▲ |
| Süre | 822 sn | 3508 sn | ▼ 4,3× |

**Doygunluk kırıldı, ama ilk sıra bozuldu.** Model A'da K=5'ten sonra hiçbir kazanım yoktu; v4 ile kazanım K=10'a
kadar sürüyor (0,618 → 0,765) ve "sıralaması yetmediği için kuyruğa giremedi" diyen 6 insider 2'ye iniyor.
Buna karşılık sıralama **düzleşiyor**: insider'lar ilk 10'a yayılıyor ama tepeden düşüyor. Yalnız en üstteki
vakaya bakan bir analist için sistem **kötüleşti**, 10 vakaya bakan için iyileşti.

**Bedava bir kazanç değil:** +5 insider karşılığında +178 yanlış pozitif kullanıcı. Oran kabaca orantılı — "daha
çok gör, daha çok çalış". İyi bir takas olup olmadığı analist kapasitesine bağlıdır.

**Bileşenler gerçekte ne yaptı:**

| Bileşen | Etki |
|---|---|
| Temporal graf | 28,3M kenar, 977 kullanıcı, 1930 hedef |
| ADWIN | **117 kullanıcıda** baz çizgisini kesti (958 izlenen) |
| Bayes kapısı | **0 vaka eledi** — tasarım gereği: analist etiketi yok, etiketsiz örüntü susturulmaz |

"Hiç tetiklenmedi" grubu 7 → 6'ya indi. Bu belgenin önceki sürümünde kazanımın ADWIN'den gelmiş olabileceği
yazıyordu — ölçüm değil **çıkarım** olduğu da belirtilmişti. **30 Ekim ablasyonu o çıkarımı çürüttü:** ADWIN tek
başına yakalamayı hiç artırmıyor, recall@10'u 0,618'den 0,588'e **düşürüyor** ve +79 vaka maliyeti getiriyor.
Kazancın tamamı graf çarpanından geliyor (aşağıdaki ablasyon tablosu).

**Çekinceler:** (1) r4.2 kuralların ayarlandığı veridir, yani üst sınır. (2) Bileşenler birlikte açıldı; tek tek
ablasyon aşağıda. (3) Süre 4,3 katına çıktı — gerçek kurumda günlük koşu için ciddi bir maliyet.

### Aynı bileşenler r6.2'de (2801 kullanıcı, 360 gün, bütçe 30)

r4.2'deki kazanç başka veride tekrarlanmadı. Aynı yedi bayrak, aynı bölme, aynı model, tek fark yapılandırma:

| Ölçüt | v3 (kapalı) | v4 (hepsi açık) | |
|---|---|---|---|
| **Yakalanan insider** | **3/4** | **3/4** | — değişmedi |
| Yanlış pozitif kullanıcı | 538 | **1114** | ▼ 2,07× |
| precision@1 | 0,014 | **0,003** | ▼ ⅕'i |
| **Erkenlik medyanı** | 0 gün | **10 gün** | ▲ +10 (n=3) |
| Toplam vaka | 8.516 | 10.993 | ▼ +%29 |
| Süre | 212 dk | 309 dk | ▼ 1,46× |

**1.173 ek yanlış alarm, sıfır ek insider.** Kaçırılan senaryo (S5) hiçbir kural tetiklemiyor; graf skora
*çarpan* olarak girdiği için `1,5 × 0 = 0` — tabanı sıfır olan kullanıcıya ulaşamaz. Yapısal tavan budur ve
bu ölçüm onu doğruladı. Kuyruğun 1,93× şişmesi, zaten tetiklenen kuralların büyütülmesinden geliyor
(PRED-0012 3,8×, UEBA-0017 3,2×).

Tek gerçek kazanç erkenlik: S4 sızıntı gününde değil **10 gün önce** kuyruğa girdi. Ama n=3; bir senaryonun
öne gelmesi üç gözlemlik medyanı sıfırdan ona taşır, bu "sistem 10 gün önce uyarır" demek değildir.

Bu, v4 kazancının **r4.2'ye aşırı uyum** olduğuna dair ilk ciddi kanıttır — bayrak değerleri
(`graf_agirligi=0,5`, `bayes_kapi_esigi=0,3`) orada seçildi. **Bu yüzden varsayılanlar değişmiyor:** v4
bileşenlerinin tamamı `config.py`'de kapalı kalıyor, yalnızca `--ac` ile açılıyor ve açıldığı koşunun
kaydına yazılıyor.

> Bu ölçüm **kör değil**: r6.2 kör koşusu bir kez yapıldı, o veri yandı. Koşu kaydı bunu dosyanın içinde
> taşıyor (`"tur": "… KÖR DEĞİL"`). Geriye kalan tek kör veri **r1** ve dokunulmadı.
> Ayrıntı: [`docs/r62-v4-olcumu.md`](docs/r62-v4-olcumu.md).

### Bileşen ablasyonu (r4.2, 90 gün, bütçe 30)

v4 bileşenleri r4.2 ve r6.2'de hep **birlikte** açılmıştı; hangisinin ne yaptığı bilinmiyordu.
30 Ekim ablasyonu ayrıştırdı — her satır aynı veride, tek bileşen değişkenle:

| Varyant | Yakalanan | Δ | Vaka | Δvaka | recall@10 (kull.) |
|---|---|---|---|---|---|
| `tam` (hepsi kapalı) | 22/34 | — | 1.939 | — | 0,618 |
| **`graf_carpan`** | **27/34** | **+5** | 2.069 | +130 | **0,824** |
| `graf_toplamsal` | 22/34 | +0 | 1.967 | +28 | 0,676 |
| `anomali_ecod` | 22/34 | +0 | 2.010 | +71 | 0,676 |
| `anomali_orman` | 22/34 | +0 | 2.111 | +172 | 0,676 |
| `adwin` | 22/34 | +0 | 2.018 | +79 | **0,588** ▼ |
| `bayes_kapi` · `belirsizlik` | 22/34 | +0 | 1.939 | +0 | 0,618 |

**Kayıp tespitte değil sıralamada.** Kaçan 12 insider'ın **5'i zaten tespit edilmişti** — kural tetiklendi,
kanıt vardı, bütçe yarışını kaybetti. Graf çarpanı bu 5'in **tamamını** kurtardı (`BÜTÇE DIŞI` 5 → 0).

Üç şey ölçümle ortaya çıktı:

1. **Kazancın tamamı graf çarpanından geliyor.** Toplamsal yol (+28 vaka) hiçbir ek insider getirmedi:
   çarpan sıralamayı *açar*, toplama *ezer*.
2. **ADWIN zarar veriyor** — recall@10'u 0,618'den 0,588'e düşürüyor, +79 vaka maliyetiyle.
   README'nin önceki sürümünde "+5 insider ADWIN'den gelmiş olmalı" diye bir **çıkarım** vardı
   (ölçüm değil diye işaretliydi); ölçüm onu çürüttü.
3. **İki bayrak hiçbir şey okumuyormuş.** `BayesKapisi.ogren()` hiçbir yerden çağrılmıyor,
   `belirsizlik_enabled` hiçbir yerde okunmuyordu. v6-A'da ikisi de bağlandı.

Ayrıntı: [`docs/r62-v4-olcumu.md`](docs/r62-v4-olcumu.md) · ham çıktı `ztp_out_ablasyon_r42/ablasyon.md`.

### v6-A: analist geri bildirim döngüsü (r4.2)

| Ölçüt | `tam` | **döngü** | döngü, kapı kapalı | %15 gürültülü etiket |
|---|---|---|---|---|
| **Yakalanan** | **22/34** | **18/34** | **22/34** | **18/34** |
| Vaka | 1.939 | **214** | 1.939 | 217 |
| precision@N | 0,045 | **0,238** | 0,045 | 0,235 |
| precision@1 | 0,420 | **0,537** | 0,443 | 0,529 |
| recall@10 (kull.) | 0,618 | 0,529 | **0,647** | 0,529 |
| Bayes elediği | 0 | **1.725** | 0 | 1.722 |

**Döngünün etkisi Bayes kapısından ibaret.** Kapı kapalıyken etiket, Venn-Abers ve periyodik yeniden
eğitim birlikte kuyruğun **içeriğini değiştirmiyor** — `prediction_weight = 0` olduğu için modelin
olasılığı skora zaten girmiyor. Ama **sırası** değişiyor (recall@10 0,618 → 0,647): analistin
"yanlış pozitif" etiketi `×0,2` çarpanını canlandırıyor — v1'den beri kodda duran ama etiketsiz
ortamda hiç çalışmamış bir mekanizma. Döngünün bedelsiz tek kazancı budur.

**Kapının kendisi sert bir takas:** vaka −%89, precision 5,3×, ama **4 senaryo kayıp**. Analist
günde 21 yerine 2,4 vaka görüyor ve %24'ü gerçek (önceden %4,5) — kaçan 4 insider pahasına.

**Gürültülü etikete dayanıklı:** analistin %15'i yanılsa bile sonuç neredeyse değişmiyor (18/34,
217 vaka). Beta-binom sonsalı biriken sayımlara baktığı için tek tek hatalar sönüyor.

Ön kayıttaki iki beklentiden **biri tuttu** (vaka ≥%10 düşer), **biri tutmadı** (kapsama ±1 içinde
kalır). Başarı eşiğinin kendisi de eksikti: "precision düşmeden vaka azalır" diyordu ve harfiyen
tuttu, ama kapsama kaybını saymıyordu. Sapma kaydına yazıldı.

Ayrıntı: [`docs/v6a-geri-bildirim-olcumu.md`](docs/v6a-geri-bildirim-olcumu.md) ·
ön kayıt [`docs/sprint-v6-on-kayit.md`](docs/sprint-v6-on-kayit.md).

### v6-D: sızıntı kanalı sayacının ayrılması (r4.2)

Bir teşhisten doğdu. r6.2'de kaçırılan tek **USB'siz** sızdırma senaryosu (S5) açıldı: kullanıcı 57 saniyede
Dropbox'a dört dosya yükledi, hiçbir kural tetiklenmedi. İki yapısal sebep çıktı:

1. **`UEBA-0003` r6.2'de yapısal olarak ölü.** r6.2'nin `http.csv` dosyasında `content` kolonu **yoktur**,
   dolayısıyla web olaylarında `bytes_out = 0`. En ağır UEBA kurallarından biri o koşuda hiç tetiklenemez.
   Eşik sorunu değil, veri yokluğu — r6.2 sonuçları okunurken bilinmesi gereken bir sınır.
2. **Niyet sinyali yöntem sinyalini maskeliyordu.** `sensitive_app_count` beş sızıntı kanalını iş arama ve
   saldırı araçlarıyla **aynı sayaçta** topluyordu.

| | 7g toplam | beklenen | p |
|---|---|---|---|
| Havuzlanmış sayaç | 45 | 40,26 | **0,347** — hiç anormal değil |
| Ayrılmış bulut sayacı | 4 | 0,52 | **0,0134** |

İş aramayı yoğun yapan kullanıcının gerçek yüklemesi kendi tarama tabanına gömülüyordu. Ayırma **26 kat**
anlamlılık kazandırdı. Eklenen: `cloud_app_count` özelliği, `bulut_7g_*` sinyalleri, **`UEBA-0022`** kuralı.

**Ölçüm (r4.2):** kapsama 22/34 → **22/34** (değişmedi), vaka 1.939 → 1.960 (**+%1,08**), değişen senaryo **0**.
Kural 143 kez tetiklendi, precision'ı **%15,8** — sistem ortalamasının (%4,7) **3,4 katı**.

**Karar: kural GÖLGEDE kalıyor.** Sprintin iki güvenlik şartı geçti ama projenin kendi gölge-mod mezuniyet
standardı (13.6: precision ≥ %25) geçilmedi — 0,158 < 0,25. Daha katı olan standart geçerlidir.

**r4.2 bu kuralın faydasını ölçemez:** senaryolarının 31/34'ü USB'ye bağımlı ve r4.2'de `content` kolonu
var, yani bu kuralın doldurduğu boşluk orada mevcut değil. Yansız sınav **r1**'dir.

**Sapma 3 (ağır):** p eşiği `0,001 → 0,02`, test vakası **görüldükten sonra** değiştirildi. Gerekçe ölçülmüş
(seyrek sayaçta 0,001 için 8 olay / 15× sıçrama gerekirken yoğun sayaçta ~2,5× yetiyor) ama bedeli kaydedildi:
o vaka artık kanıt değil, ayar kümesinin parçası.

Ayrıntı: [`docs/v6d-sizinti-kanali-olcumu.md`](docs/v6d-sizinti-kanali-olcumu.md).

### Sprint v6 karnesi: üç yeni katman, üçü de eşiğini geçemedi

Üç katman (analist geri bildirim döngüsü, saldırı yolu tahmini, öğrenen graf gömme) aynı sprintte
geliştirildi ve **ayrı ayrı** ölçüldü. Başarı eşikleri ölçümden **önce** yazılmıştı:

| Katman | Eşik | Ölçülen | |
|---|---|---|---|
| **A** geri bildirim döngüsü | kapsamayı değiştirmez (±1) | 22/34 → **18/34** | ✘ |
| **B** saldırı yolu tahmini | top-1 ≥ 2× taban | **1,33×** | ✘ |
| **C** öğrenen graf gömme | > 27/34 | **22/34** | ✘ |

İki sözleşme testi geçti: B ve C, ağırlıkları 0 iken kuyruğu **birebir** değiştirmedi. Kod doğru;
başarısız olan fikirlerdi.

**41 opsiyonel bayraktan ölçülmüş şekilde değer üreten tek bileşen graf çarpanıdır** (+5 insider,
recall@10 0,618 → 0,824). Diğerleri ya nötr ya da (ADWIN) zararlı.

Bu, projenin merkezî iddiasının kendi üzerinde işlemesidir: **ölçülmeden açılmaz.** Üç katman da
yazıldı, test edildi, ölçüldü ve **varsayılanda kapalı kaldı**. Marjinal getirinin sıfıra yakın
olduğu ölçüldüğü için sıradaki iş yeni bileşen eklemek değil, var olanı ayarlamaktır.

Ayrıntı: [`docs/sprint-v6-sonuclar.md`](docs/sprint-v6-sonuclar.md) ·
ön kayıt ve üç sapma: [`docs/sprint-v6-on-kayit.md`](docs/sprint-v6-on-kayit.md).

### v7 ayar taraması: tek kazanan yok, bir verimlilik sınırı var

Sprint v6'da yeni bileşenin marjinal getirisinin sıfıra yakın olduğu ölçüldükten sonra, yalnız **var olanı
ayarlayan** altı varyant koşuldu. Sonuç "hangi ayar en iyi" değil — **doğru cevap analist kapasitesine bağlı**:

| Analist kapasitesi | Yapılandırma | Yakalanan | Günlük vaka | Vaka/insider |
|---|---|---|---|---|
| Yüksek | **graf çarpanı + öncelik** | **27/34** | 23,0 | 76,6 |
| Orta | **graf + Bayes kapısı** | 23/34 | **4,4** | **17,3** |
| Düşük | Bayes kapısı (gözlem 25) | 20/34 | 3,1 | 14,1 |
| *(referans)* | hepsi kapalı | 22/34 | 21,5 | 88,1 |

Dört bulgu:

1. **Kapı eşiği hiç önemli değilmiş.** 0,1 / 0,2 / 0,3 → üçü de 18/34 ve ~215 vaka. "Eşik fazla agresif"
   hipotezim **yanlıştı**.
2. **`bayes_min_gozlem` önemliymiş.** 10 → 25 yapınca **+2 senaryo** (18→20) geri geldi. Kayıp, az kanıtla
   susturulan örüntülerdenmiş — ikinci hipotez doğru çıktı.
3. **Öncelik sıralayıcı bedelsiz bir kazanç.** Vaka sayısı **birebir aynı** (1.939) kalırken recall@10
   0,618 → **0,676**. Tasarım sözleşmesi buydu: kuyruğun üyeliğini değil sırasını değiştirir.
4. **Graf ve kapı birbirini kısmen götürüyor.** Kapı, grafın kazandırdığı 5 senaryonun 4'ünü geri alıyor
   (27 → 23). Ama verimlilik dört katına çıkıyor: 76,6 → 17,3 vaka/insider.

**Graf çarpanı her üç çalışma noktasında da kazandırıyor** — 41 bayrak içinde bu tutarlılığı gösteren tek
bileşen. Buna rağmen varsayılan **henüz değiştirilmedi**: r4.2 ayar verisidir ve karar, r6.2'de yalnız grafın
ölçülmesine bağlıdır.

Ayrıntı: [`docs/v7-ayar-taramasi.md`](docs/v7-ayar-taramasi.md).

### r6.2'de yalnız graf çarpanı: en net aşırı uyum kanıtı

41 bayrak içinde tutarlı değer ürettiğini düşündüğüm **tek bileşen** graf çarpanıydı: r4.2'de
22/34 → **27/34**, recall@10 0,618 → 0,824. r6.2'de tek başına ölçüldü (4 pencere, 360 gün):

| Ölçüt | Taban | Hepsi açık | **Yalnız graf** |
|---|---|---|---|
| **Yakalama** | **3/4** | **3/4** | **3/4** |
| Yanlış pozitif | 538 | 1.114 | **1.295** |
| precision@1 | 0,014 | 0,003 | **0,014** |
| **Erkenlik medyanı** | 0 gün | 10 gün | **10 gün** |

**Hipotez çürüdü.** "r6.2'de graf, zarar veren ADWIN'le birlikte açıldığı için sulanmıştı" diye
düşünmüştüm. Graf tek başına da **tek bir ek insider getirmiyor** ve yanlış pozitifi 538'den
1.295'e çıkarıyor — hepsi açıkken'den (1.114) bile fazla.

Üç sonuç:

1. **r4.2'nin +5'i r6.2'ye taşınmıyor.** Projedeki en net aşırı uyum kanıtı. Bir bileşenin
   varsayılan açılması için iki farklı veride değer üretmesi gerekir; graf sağlamadı.
   **Varsayılan değiştirilmedi.**
2. **Bileşen etkileri veri setine bağlı.** ADWIN r4.2'de zararlıydı; r6.2'de yanlış alarmı bir
   miktar azaltıyormuş. r4.2'de ölçülen bir etki başka veride tersine dönebiliyor.
3. **Erkenlik kazancı grafa ait** — v4'te 0→10 gün görmüş ama kaynağını bilmiyorduk. Artık
   biliyoruz. Ama **n=3**, tek senaryodan. Ayrıca precision@1 graf ile korunuyor (0,014), hepsi
   açıkken 0,003'e düşüyordu — kuyruğun tepesini bozan graf değilmiş.

Bu, **RQ3'ün** ("r4.2 iyileştirmeleri genelleniyor mu?") sayısal cevabıdır: **hayır**.

Ayrıntı: [`docs/r62-graf-tek-basina.md`](docs/r62-graf-tek-basina.md).

### Şema profilleyici: sessiz ölü kuralları yakalar

r6.2'nin `http.csv` dosyasında `content` kolonu **yoktur** → `bytes_out` her web olayında sıfır →
ağırlığı 8 olan `UEBA-0003` o koşuda **hiç tetiklenemez**. Aylarca fark edilmedi çünkü raporda
masum bir "bu veride desen görülmedi" satırı olarak göründü.

`schema_profiler.py` bunu **ilk koşuda** bulur; r4.2'de 0 uyarı, r1'de (tüm dosyalar başlıksız)
yanlış alarm yok. Türev zinciri kayıtlı: `UEBA-0003` → `veri_hacmi_z` → `bytes_out` → `http.csv:content`.

```
PYTHONPATH=src python scripts/sema_profili.py --karsilastir .../r4.2 .../r6.2 .../r1
```

## Lisans

Apache-2.0 — bkz. [LICENSE](LICENSE).
