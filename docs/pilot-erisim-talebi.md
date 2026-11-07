# Pilot için gereken erişim ve bilgiler

**Hazırlayan:** İrfan Emre Durmuş · 6 Kasım 2026
**Amaç:** Zero Trust Prediction (içeriden tehdit davranış analitiği) sisteminin gerçek ortamda
sınanabilmesi için gereken asgari erişim listesi.

---

## Önce bir şeyi netleştirmek gerekiyor: neyi ölçebiliriz, neyi ölçemeyiz

Pilotun sonunda hangi soruya cevap verebileceğimiz, hangi veriyi aldığımıza bağlı:

| Soru | Ölçmek için gereken | Erişim olmadan |
|---|---|---|
| Kaç uyarı üretiyor? Analist kapasitesine sığıyor mu? | yalnız **log** | ✅ ölçülür |
| 25 kuralın kaçı bu ortamda çalışabiliyor? | yalnız **log** | ✅ ölçülür |
| Uyarılar işe yarıyor mu? (precision) | log + **analist kararı** | ❌ |
| **Gerçek vakaları yakalıyor mu? (recall)** | log + **bilinen geçmiş olay** | ❌ |

> **En kritik satır sonuncusu.** Geçmişte tespit edilmiş, kapanmış bir içeriden tehdit vakası
> paylaşılmazsa, sistemin "yakalayıp yakalamadığını" **hiçbir şekilde ölçemeyiz** — yalnız kaç
> uyarı ürettiğini ve analistin onları faydalı bulup bulmadığını ölçebiliriz.
>
> Bu bir eksiklik değil, her davranış analitiği pilotunun doğası. Ama baştan bilinmezse pilot
> sonunda cevaplanamayacak bir soru sorulur.

---

## Kademe 0 — Uygunluk kontrolü *(1 günlük örnek, taahhüt yok)*

**İstenen:** Herhangi bir **1 günlük** olay dökümü, CSV ya da Parquet.

| Alan | Açıklama |
|---|---|
| `time` | olay zamanı |
| `source` | kaynak (ad / proxy / email / file_server / dlp / edr / vpn) |
| `actor_raw` | kaynaktaki hâliyle kullanıcı/IP — normalize edilmemiş hâli yeterli |
| `device`, `src_ip` | cihaz, IP |
| `action`, `outcome` | eylem ve sonucu |
| `bytes_out` | giden bayt (varsa) |
| `resource`, `app`, `category` | kaynak adı, uygulama/URL kategorisi |
| `process`, `cmdline` | süreç bilgisi (varsa) |

**Ne yapılacak:** Hazır bir araç (`scripts/kurulum_hazirlik.py`) bu dökümü okuyup şu raporu
üretiyor — **5 dakikada, veriyi dışarı çıkarmadan**:

- Hangi alan dolu, hangisi boş
- **25 kuralın kaçı bu ortamda çalışabilir, hangileri çalışamaz ve neden**
- Dış e-posta hacim dağılımı (bir eşik ayarı için gerekli)

**Neden önemli:** Test veri setimizde iki kural (toplam ağırlık 11) **yapısal olarak ölüydü** ve
bu aylarca fark edilmedi — raporda masum bir "bu veride desen görülmedi" satırı olarak görünüyordu.
Aynısı gerçek kurulumda olursa ürün "25 kural" diye anlatılır, 23'ü çalışır. Bu kontrol onu
önceden söyler.

**Barikat tarafındaki iş:** Bir SIEM sorgusu, tek seferlik. Yazma yetkisi yok, canlı bağlantı yok.

---

## Kademe 1 — Ölçüm verisi *(geçmiş log)*

**İstenen:** Aynı şemada **en az 120 gün** geçmiş veri.

Neden 120:

| | gün | ne için |
|---|---|---|
| Uzun pencere | 90 | kişisel ve akran taban çizgisi |
| Profil olgunluğu | 30 | kurallar `profil_gun >= 30` şartı arıyor |
| Değerlendirme | +30 | asıl ölçüm penceresi |
| **Toplam** | **~150 ideal, 120 asgari** | |

Daha kısa veriyle sistem çalışır ama **taban çizgisi oturmaz** ve her kullanıcı "yeni" görünür —
yanlış alarm patlar. Bu, sonucun sistemin değil verinin kısalığının eseri olmasına yol açar.

**Hangi kaynaklar, öncelik sırasıyla** (kural sayısı ölçülmüş değerdir):

| # | Kaynak | Ürün karşılığı | Kural | Not |
|---|---|---|---|---|
| 1 | AD / IdP oturum kayıtları | Active Directory, Entra ID, Okta | **12** | en kritik |
| 2 | Web proxy / SWG | Zscaler, Netskope, Forcepoint | **7** | USB yasaksa **birincil sızıntı kanalı** |
| 3 | Dosya sunucusu denetim logu | Windows File Server audit, SharePoint | 5 | |
| 4 | **İK sistemi** | Workday, SuccessFactors | **4** | aşağıya bakınız |
| 5 | E-posta ağ geçidi | M365, Proofpoint, Mimecast | 1 | USB yasaksa önemi artıyor |
| 6 | DLP / uç nokta | — | 2 | **USB yasaksa düşük öncelik** |
| 7 | EDR | CrowdStrike, Defender | 1 | yalnız sağlık kontrolü |

> **4. madde özellikle vurgulanmalı.** İK verisi (işe giriş, **ayrılık bildirimi**, rol/yetki
> değişimi tarihleri) 4 kuralı besliyor ve test veri setimizde **hiç yoktu** — yani o 4 kural
> bugüne kadar **hiç sınanamadı**. "Ayrılık öncesi veri sızdırma" içeriden tehdidin en güçlü ve
> en çok çalışılmış desenidir; İK entegrasyonu olmadan o desen görülemez.
>
> İstenen alanlar küçük: `kullanıcı, işe giriş tarihi, ayrılık bildirim tarihi, ayrılış tarihi,
> departman, yönetici, rol değişim tarihi`. Maaş, performans, kişisel bilgi **istenmiyor**.

**Barikat tarafındaki iş:** Bir SIEM export'u. Canlı bağlantı gerekmiyor; pilot için tek seferlik
döküm yeterli.

---

## Kademe 2 — Analist kararı *(precision ölçümü için)*

**İstenen:** Kapanmış vakaların sonucu — salt okunur, haftalık CSV bile yeterli:

```
vaka_id, karar (gerçek_pozitif | yanlış_pozitif | belirsiz), analist, tarih, kısa gerekçe
```

**Ne açar:**

| Şu an bloke olan | Açılır mı |
|---|---|
| **5 kural gölge modda bekliyor** (kataloğun %20'si) — yayına alınma şartı analist kararıyla ölçülen precision | ✅ |
| Yanlış pozitif bastırma ("bu örüntü bu kullanıcıda bilinen FP") | ✅ |
| Öğrenen modelin eğitimi | ✅ |
| Olasılık kalibrasyonu | ✅ |

**Neden bu kadar önemli:** Sistemin öğrendiği **tek şey** analistin kapattığı vakanın sonucudur.
O veri gelmezse sistem ilk günkü hâliyle kalır — aynı yanlış alarmı sonsuza kadar üretir.

**Açıkça belirtmek isterim: SOAR'a yazma yetkisi istemiyoruz.** Vaka açma, aksiyon tetikleme,
engelleme — hiçbiri bu kademede yok. Yalnız kapanmış vakaların sonuç alanı.

---

## Kademe 3 — Tam entegrasyon *(pilot başarılıysa)*

| | |
|---|---|
| Vaka yazma | Sistemde hazır: HMAC imzalı HTTP POST (`WebhookSink`). SOAR'da bir test kuyruğu + URL yeterli |
| Müdahale aksiyonu | **Bu kademede istenmiyor.** Sistem tasarımı gereği otomatik engelleme yapmaz; erişim kısıtlama yalnız doğrulanmış olay + yetkili insan kararıyla mümkün |

---

## Barikat'ın altyapısı — araştırıldı, somutlaştı

Kamuya açık kaynaklardan doğrulanan iki şey, talebi çok daha somut hâle getiriyor:

| Bulgu | Kaynak |
|---|---|
| **Barikat'ın teknoloji listesinde UEBA / davranış analitiği / içeriden tehdit YOK** (38 kategori listeli: DLP, e-posta güvenliği, URL filtreleme, honeypot, SIEM, SOAR…) | [barikat.com.tr — SOC hizmetleri](https://www.barikat.com.tr/en/services/cyber-security-operation-center) |
| **MDR hizmeti Microsoft Azure Sentinel üzerinde çalışıyor**; Barikat SOC'u içinde MS Sentinel SIEM & SOAR hizmetleri sunuluyor | [Azure Marketplace](https://azuremarketplace.microsoft.com/en-au/marketplace/consulting-services/barikatinternetguvenligibilisimticas1600948639670.csmrs) · [Barikat–Microsoft iş birliği](https://www.barikat.com.tr/en/news/collaboration-in-cyber-security-barikat) |

İkincisi sayesinde yukarıdaki üç kademe **Sentinel diliyle** yazılabiliyor:

### Kademe 0 / 1 — Sentinel tabloları

| İstenen kaynak | Sentinel tablosu (tipik) |
|---|---|
| AD / IdP oturum | `SigninLogs`, `AADNonInteractiveUserSignInLogs`, `SecurityEvent` (4624/4625) |
| Web proxy / SWG | `CommonSecurityLog`, `ZscalerNSS_CL` ya da kullanılan konnektörün tablosu |
| E-posta ağ geçidi | `EmailEvents`, `OfficeActivity` |
| Dosya sunucusu | `DeviceFileEvents`, `SecurityEvent` (4663) |
| DLP / uç nokta | `DeviceEvents`, `DlpEvents` |
| İK | Sentinel'de yoktur — **doğrudan İK sisteminden** CSV |

Tablo adları kuruma göre değişir; **Kademe 0'ın amacı tam olarak bunu tespit etmek.**

### Kademe 2 — `SecurityIncident` tablosu

Bu, talebin en kolay kısmı ve Barikat tarafında **yeni bir süreç gerektirmiyor**. Sentinel
incident'ları kapanırken `Classification` alanını zaten dolduruyor ve değerleri bizim ihtiyacımızla
neredeyse birebir eşleşiyor:

| Sentinel `Classification` | Bizdeki karşılığı |
|---|---|
| `TruePositive` | `gerçek_pozitif` |
| `FalsePositive` | `yanlış_pozitif` |
| `BenignPositive` | `yanlış_pozitif` (meşru aktivite) |
| `Undetermined` | `belirsiz` |

İstenen, tek bir KQL sorgusunun çıktısı:

```kql
SecurityIncident
| where TimeGenerated > ago(90d) and Status == "Closed"
| project IncidentNumber, Classification, ClassificationReason,
          ClassificationComment, ClosedTime, Owner.assignedTo
```

Yani *"bana analist kararlarını verin"* talebi, onlar için **bir sorgu** — yeni entegrasyon, yeni
alan, yeni iş akışı yok.

### Kademe 3 — Sentinel'e incident yazma

Sistemde hazır (`WebhookSink`: HMAC imzalı HTTP POST). Sentinel tarafında bir **Logic App** ya da
`Microsoft.SecurityInsights` REST API uç noktası yeterli.

---

## ⚠️ Toplantıda kesin gelecek soru: "Sentinel'in UEBA'sı zaten var"

Microsoft Sentinel'in yerleşik bir UEBA modülü (Entity Behavior Analytics) bulunuyor. Barikat UEBA
**satmıyor** ama üzerinde çalıştıkları platformda bu modül **var**. Müşterilerinde açık olup
olmadığını bilmiyoruz — **öğrenilmesi gereken ilk şey bu.**

Cevap hazır ve ölçülmüş olmalı:

| Sentinel UEBA | Bu sistem |
|---|---|
| Genel anomali skorlaması, varlık bazlı | **İçeriden tehdide özel** 25 kural, detection-as-code (YAML, sürümlenebilir, denetlenebilir) |
| Uyarı üretir | **Analist kapasitesine göre günde N vaka** seçer — bütçe mekanizması |
| Skor kapalı kutu | Her bileşen **ablasyonla** ayrı ölçülmüş; 18 isteğe bağlı bileşenin 18'i ölçüm sonucu kapalı |
| — | **Gölge mod**: yeni kural müşteriye gürültü vermeden olgunlaşır |
| — | **Kör koşu protokolü**: ön kayıt, tek koşu, sapma kaydı |

Konumlandırma cümlesi: **"Sentinel UEBA'nın yerine geçmez; onun üstüne, içeriden tehdit özelinde
bir katman."**

---

## Önerilen konumlandırma

> **MxDR By BARİKAT hizmetinin içine, Sentinel'den besleyip Sentinel'e incident yazan bir içeriden
> tehdit modülü.** Ayrı bir ürün olarak değil.

Gerekçeler:

1. **MxDR onların kendi markalı hizmeti** — farklılaşma aradıkları yer orası
2. Portföylerinde **UEBA yok** → çakışma değil boşluk
3. Sentinel hem girdi hem çıktı için **standart arayüz** veriyor
4. **Honeypot / aldatma teknolojileri portföylerinde var** — sistemin 3 `HONEY-*` kuralı doğrudan oraya bağlanır
5. Sistemin ölçülmüş gücü **sıralama** (precision@1 0,958) ve bu tam olarak bir SOC'un ihtiyacı: "bugün önce kime bak"

## Ayrıca bilmemiz gerekenler *(erişim değil, bilgi)*

| Soru | Neden |
|---|---|
| ~~Barikat'ın UEBA ürünü var mı?~~ **Araştırıldı: yok.** Ama **Sentinel'in yerleşik UEBA'sı müşterilerde AÇIK mı?** | Açıksa konumlandırma değişir |
| ~~SOC hangi SIEM üzerinde?~~ **Araştırıldı: Microsoft Sentinel.** Hangi konnektörler bağlı? | Tablo adlarını belirler |
| ~~Vaka yönetimi neyle?~~ **Sentinel incident.** Logic App yetkisi kimde? | Kademe 3'ün bağlanacağı yer |
| **Analist başına günlük vaka kapasitesi kaç?** | Sistemin bütçe parametresi doğrudan bu — varsayılan 30/gün |
| Geçmişte tespit edilmiş içeriden tehdit vakası var mı? | **Recall ölçümünün tek yolu** (en üstteki tabloya bakınız) |

---

## Özet — tek paragraf

> Kademe 0 için **tek günlük bir log dökümü** yeterli ve 5 dakikada hangi tespitlerin bu ortamda
> çalışabileceğini söylüyor; taahhüt gerektirmiyor. Kademe 1 için **120 günlük geçmiş log**
> istiyoruz, öncelikle AD, web proxy ve İK verisi. Kademe 2 için **kapanmış vakaların sonuç
> alanını** istiyoruz — yazma yetkisi değil, salt okunur. Bu üçü olmadan sistemin kaç uyarı
> ürettiğini ölçebiliriz ama **işe yarayıp yaramadığını** ölçemeyiz.

---

## Sistemin bugünkü olgunluk seviyesi *(dürüstlük payı)*

| | |
|---|---|
| Doğrulama | Kamuya açık CERT içeriden tehdit veri setleri (r4.2, r5.2, r6.2) |
| Kör koşu | **1 kez** yapıldı (r6.2): 4 senaryodan 3'ü yakalandı, 538 yanlış pozitif |
| Seviye | **Pilot** — ürün değil |
| Bilinen sınırlar | `README.md` → "Bilinen sınırlar" bölümünde 6 madde hâlinde yazılı |

Bu, abartılmış bir iddiayla girip ilk teknik soruda dağılmaktansa baştan söylenmesi gereken bir
şey. Sistemin ölçülmüş gücü **sıralama** (analistin baktığı ilk vaka 20'de 19 kez gerçek);
zayıflığı **kapsama** ve kalibrasyon — ikisi de belgelenmiş durumda.
