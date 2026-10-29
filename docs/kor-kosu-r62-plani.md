# Kör koşu planı (ön kayıt) — CERT r6.2

**Durum:** Ön kayıt. Koşudan önce yazıldı: 28 Ekim 2026. Bu tarihte r6.2 indirilmiş ve ayrıştırılmıştı, ancak sistem
r6.2 üzerinde **bir kez bile çalıştırılmadı**: yalnız dosya başlıkları, satır sayıları, günlük olay hacmi, LDAP
kullanıcı listesi, cevap anahtarı ve `decoy_file.csv` incelendi. Hiçbir tespit, skor ya da kuyruk çıktısı üretilmedi.

**Amaç:** Kurallar ve skorlama ayarlanırken hiç görülmemiş bir veri setinde **tek bir** koşuyla yansız rakam üretmek.
r4.2 kuralların ayarlandığı veridir (üst sınır). r5.2 ilk kör koşuydu. r6.2 ikinci kör koşudur ve **ölçek** açısından
farklıdır: 4000 kullanıcı, ~17 ay, ama yalnız **5 insider**.

Bu belge koşudan sonra değiştirilmez. Plandan sapılırsa sapma, gerekçesiyle sonuç raporuna ayrı başlık olarak yazılır.

## 1. Kural sürümü

- Kurallar: **`kurallar-donduruldu-v3`**, manifest `configs/freeze/kurallar-donduruldu-v3.json`.
- v3'te **hiçbir kural, eşik ya da ağırlık v2'den farklı değildir** (`tests/test_rule_freeze.py::test_v3_kurallari_v2_ile_ayni`
  bunu doğrular). Değişen: yeni yetenekler eklendi ve hepsi **varsayılanda kapalı**; tenant varsayılanı
  `alarm_budget_per_day` 8 → 30.
- Koşudan hemen önce `python -m ztp.freeze --check configs/freeze/kurallar-donduruldu-v3.json` çalıştırılır ve
  `donmuş durumla aynı` çıktısı, HEAD commit karması ve tam komut satırıyla birlikte sonuç dosyasına yazılır.

### Birincil koşuda KAPALI olan v3 yetenekleri

Bunlar koşuya girmez; birincil sonuç v2 davranışıyla birebir aynı kurallarla üretilir.

| Yetenek | Ayar | Birincil koşu |
|---|---|---|
| #1 çok ufuklu biriktirici (1/3/14/30g sinyalleri) | üretilir ama hiçbir kural kullanmaz | etkisiz |
| #2 öncelik sıralayıcı | `priority_*_weight = 0` | kapalı |
| #3 kanıt çeşitliliği çarpanı | `source_diversity_multiplier = 0` | kapalı |
| #4 varlık katmanlandırma | `asset_tiers = {}` | kapalı (CERT'te varlık envanteri yok) |
| öğrenen modelin skora katkısı | `prediction_weight = 0` | kapalı (r4.2 ablasyonunda hassasiyeti düşürdü) |

## 2. Koşudan önce izin verilen tek değişiklik: ayrıştırıcı uyarlaması

r6.2 biçimi r5.2 ile aynıdır (r5+ ailesi). r5.2 planında ilan edilen eşlemeler **değişmeden** geçerlidir:
`file.csv` yalnız `to_removable_media=True`; `email.csv` yalnız `activity=Send`, `bytes_out = size`;
`http.csv` yalnız `url` (content okunmaz); `insiders.csv`'de ayrıştırılamayan tarih sessizce düşmez.

Bunun dışında **yeni ayrıştırıcı değişikliği yapılmayacaktır**; tek istisna §2.2'deki tarih onarımıdır.

### 2.1 İncelenen ve REDDEDİLEN seçenek: decoy_file.csv

r6.2, r5.2'de olmayan bir dosyayla geliyor: **31.095 tuzak (decoy) dosyasının** listesi. İlk değerlendirme, aldatma
katmanının (HONEY-0018/19/20) nihayet gerçek veride sınanabileceği yönündeydi. Koşudan önce ölçüldü:

| Ölçüm | Değer |
|---|---|
| `file.csv` içinde decoy dosyaya erişim | **458.467** |
| Bunlardan taşınabilir medyaya kopya olan (yükleyicinin gördüğü) | **0** |
| Decoy dosyaya erişen farklı kullanıcı | **3.185** (4000 kullanıcının %80'i) |
| Kullanıcı başına ortalama erişim | **144** |
| Erişim görülen gün | 515 (dönemin tamamı) |

**Karar: decoy dosyaları tuzak olarak bağlanmayacaktır.** Gerekçe: aldatma katmanının tek dayanağı
"meşru kullanımı yoktur" varsayımıdır. r6.2'de decoy dosyalara kullanıcıların %80'i rutin olarak erişiyor; bunlar
simülasyonda sıradan dosyalardır. HONEY-0019'a bağlansaydı (kural `kritik: true`, bütçeden bağımsız) günde
~890 kritik vaka üretilirdi. Aldatma katmanı bu veride de **sınanmamış** kalacaktır ve kural matrisinde öyle raporlanacaktır.

### 2.2 TADİL (koşudan önce): cevap anahtarındaki eksik ay onarımı

**Tadil tarihi: 29 Ekim 2026. Hâlâ hiçbir tespit/skor/kuyruk çıktısı üretilmedi** — bu tadil sonuçlar görülmeden yapıldı.

r6.2'nin resmi cevap anahtarında (`answers/insiders.csv`) **tek bir bozuk tarih** var:

| Kullanıcı | Senaryo | `start` (dosyada) | `end` (dosyada) |
|---|---|---|---|
| CDE1846 | S4 | `/21/2011 11:43:39` — **ay eksik** | `04/25/2011 17:55:00` |

İlk plandaki davranış ("ayrıştırılamayan tarih sessizce düşmez") bu satırı uyarı basıp **atıyordu**. Sonucu: 5 insider'ın
4'ü ölçülebiliyor ve **test parçasının tek insider'ı** (§3 bölmesinde test = 600 kullanıcı / 1 insider = S4) kayboluyor,
yani parça bazlı değerlendirmenin bir parçası tamamen boşalıyordu.

**Tadil:** yalnız "ay alanı boş" biçimindeki (`/GG/YYYY ...`) başlangıç tarihleri, **ay bitiş tarihinden alınarak**
onarılır. Kural (`src/ztp/data/cert.py::_repair_missing_month`), deterministik ve tek seçenekli:

1. Gün, saat ve yıl **dosyadaki değerlerdir**; tahmin edilmez.
2. Ay önce `end.month` denenir. Sonuç geçerli bir tarih olmalı, `end`'i **geçmemeli** ve `end`'den en çok **60 gün** önce olmalı.
3. Tutmazsa bir önceki ay aynı ölçütlerle denenir (ayı aşan gün durumu için).
4. İkisi de tutmazsa **onarım yapılmaz**; satır eskisi gibi "değerlendirilemedi" sayılır.

CDE1846 için sonuç: **2011-04-21 11:43:39 → 2011-04-25 17:55:00**. Ay seçeneği tek: 04 dışındaki her ay ya `end`'i geçer
ya 60 günü aşar. Onarım günlüğe `WARNING` olarak basılır ve sonuç raporunda bu başlıkla birlikte anılır.

**Bu tadilin ölçüme etkisi:** değerlendirilebilir insider 4 → **5**; test parçası 0 → 1 insider. §5'teki önceden yazılmış
beklentiler (2–4 insider yakalanır) **değişmedi** — tadil neyin ölçüldüğünü değiştirmez, S4'ün ölçülebilmesini sağlar.
Onarım kuralı hiçbir tespit kuralına, eşiğe ya da skora dokunmaz; `cert.py` dondurma manifestinde **değildir**
(yükleyici, kural değil), dolayısıyla v3 dondurması bozulmaz.

### 2.3 Bellek uyarlaması ve kabul ölçütünün yakaladığı hata

r6.2'nin en büyük penceresi, r4.2'de ölçülen olay başına 734 baytla **~37 GB** tepe bellek demekti; makinede 24 GB var.
Çözüm, olay tablosundaki tekrar eden metin kolonlarını kategorik tipe çevirmek (olay başına 734 → ~197 bayt).

Bu uyarlamanın şartı §2'de ilan edilmişti: **r4.2'de kural tetikleme sayıları ve kapsama sonuçları birebir aynı kalmalı**
(`scripts/bellek_esdegerlik.py`, aynı veriyi optimizasyon açık ve kapalı iki kez koşar). Ölçüt işe yaradı ve
**sessiz bir davranış değişikliği yakaladı:**

Pandas'ta kategorik bir kolon **groupby anahtarı** olduğunda, `observed=False` (bugünkü varsayılan) o gün hiç
görülmemiş kategoriler için de satır üretir — `count=0`, zaman damgası `NaT`. Nesne dtype'ında böyle satır yoktur.
Ölçülen örnek: 3 satırlık veri, 26 kategorili kolonda **52 satır, 49'u hayalet**.

| Tüketici | Durum | Etki | Düzeltme |
|---|---|---|---|
| `graph/observation.py` (kullanıcı→kaynak/app/ülke/IP, cihaz→süreç kenarları) | donmamış | graf her gün hayalet kenarlarla şişiyordu | her iki `groupby`'a `observed=True` — nesne dtype'ıyla birebir aynı |
| `quality.py:32` (`groupby(["source","day"])`) | **donmuş** | o gün olay görmemiş kaynak için `n=0` satırı → veri kalitesi metrikleri bozulurdu | `source` kolonu kategoriye **çevrilmiyor** (donmuş dosyaya dokunulamaz) |

Kural artık yoruma bırakılmıyor: `tests/test_bellek_optimizasyonu.py` her `groupby` çağrısının anahtarını ve
`observed` bayrağını **AST ile** denetler. Kategoriye çevrilen bir kolon donmuş bir dosyada anahtar olursa test düşer.

**Bu uyarlama tespit mantığına ait değildir:** `cert.py` ve `graph/observation.py` dondurma manifestinde yoktur,
v3 dondurması bozulmadı (`donmuş durumla aynı`). Koşu, eşdeğerlik çıktısında `"esdeger": true` görülmeden başlamaz.

## 3. Veri, pencere ve ayarlar

- **Pencere:** mekanik hesap. D0 = `logon.csv` ilk gün, D1 = son gün. Değerlendirme dönemi [D0 + 111 gün, D1].
  Dönem D1'den geriye ardışık **90 günlük** pencerelere bölünür; her pencere kendi 111 günlük tarihçesiyle
  (`--days 90 --warmup 21`) koşulur. Başlangıcı D0 + 111'den önceye düşen pencere kısaltılmaz, atlanır ve raporlanır.
- **Senaryo ataması:** her insider senaryosu, bitiş tarihini içeren pencerede ölçülür. "Kısmi pencere" tanımı r4.2/r5.2 ile aynı.
- **Bütçe:** **birincil 30 vaka/gün**. Gerekçe: bütçe analist kapasitesidir ve nüfusla ölçeklenir; r4.2/r5.2'de 1000–1100
  kullanıcı için 10 kullanılmıştı, r6.2'de 4000 kullanıcı var. Ayrıca **karşılaştırma için bütçe 10 varyantı** koşulur.
  İki bütçe de burada, koşudan önce ilan edilmiştir; sonuç görülüp "iyi olan" seçilmeyecektir.
- **Kullanıcılar:** tüm kurum (4000). Bellek sınırı (24 GB RAM) şu sırayla çözülür:
  1. Zamanda parçalı işleme (yukarıdaki 90 günlük pencereler, her pencereden sonra bellek boşaltılır).
  2. En büyük pencerenin tahmini tepe belleği **12 GB**'ı aşarsa: tek oranlı katmanlı örneklem — insider senaryo
     katmanları (S1–S5) ve benign katmanından **aynı** oranda `f` kullanıcı, tohum 42. `f = min(1, 12 / tahmini tepe)`,
     0,05 adımla aşağı yuvarlanır. `f` koşudan önce, yalnız yükleyici ölçümüyle belirlenir.
- **Bölme:** `configs/splits/cert-r6.2-kullanici-bolmesi.json` (70/15/15, tohum 42, insider katmanlı).
  Üretildi ve işte sonucu: eğitim 2800 kullanıcı / 3 insider (S2, S3, S5), doğrulama 600 / 1 (S1), test 600 / 1 (S4).

## 4. Bu koşunun NE ölçebileceği — ve ne ölçemeyeceği

r6.2'de senaryo başına tek insider var (toplam 5). Bu, metriklerin yorumunu baştan belirler:

| Metrik | Ölçülebilir mi | Not |
|---|---|---|
| **Yanlış alarm oranı** (masum kullanıcıların kaçı kuyruğa düştü) | **Evet, güçlü** | 3995 negatif kullanıcı; r6.2'nin asıl değeri budur. İnsider yoğunluğu binde 1,25 — gerçek kuruma en yakın ölçüm |
| **Vaka hacmi / bütçe davranışı** | **Evet** | 4000 kullanıcıda kapı ve bütçe nasıl davranıyor |
| **Kural sağlığı matrisi** | **Evet** | Hangi kural tetiklendi, hangisi gerçek vakaya katıldı, hangisi hiç sınanmadı |
| **v2 doğrulama kapısının etkisi** | **Evet, ilk kez uçtan uca** | r5.2'de yalnız kayıtlı vakalar üzerinde yeniden hesapla ölçülmüştü |
| Yakalama oranı (5 insider) | **Zayıf** | Her insider %20; ±1 kişi oranı 20 puan oynatır |
| Parça bazında yakalama (70/15/15) | **Hayır** | Doğrulama ve testte birer insider var; %0 ya da %100 çıkar |
| Öğrenen model (LR protokolü) | **Zayıf** | Pozitif satır sayısı çok düşük olacak; raporlanır ama karar dayanağı yapılmaz |
| Aldatma katmanı | **Hayır** | Bkz. §2.1 |

## 5. Önceden yazılmış beklentiler

Koşudan önce, sonucu görmeden:

1. **Yakalama:** 5 insider'ın **2–4'ü** kuyruğa girer. S3 (tek gün, 8 saat) ve S5 (tek dakika) günlük
   toplulaştırma nedeniyle yüksek olasılıkla kaçar.
2. **Yanlış alarm:** 90 günlük pencerede masum kullanıcıların **%10–25'i** en az bir kez kuyruğa düşer.
   (r4.2'de %24–29, r5.2'de %18–26 idi; v2 kapısı ve daha büyük nüfus bunu aşağı çekmeli.)
3. **precision@1:** **0,05–0,20**. r5.2'de 0,20 idi; r6.2'de insider yoğunluğu 4 kat düşük, dolayısıyla düşmesi beklenir.
4. **Bütçe:** 30'luk bütçe çoğu gün dolmaz; sınırlayıcı v2 kapısı olur (sentetikte günlük ortalama 4,4 vaka).
5. **Kural matrisi:** 22 kuralın **8–12'si** tetiklenir; İK, EDR, konum, tuzak ve ilişkisel kurallar sınanmamış kalır.
6. **S3/S5 kaçarsa** bu, mimarinin "varlık-gün toplulaştırma" kararının bilinen bedelidir ve tek günlük olaylar için
   saatlik/olay bazlı bir yol gerektiğini gösterir — koşudan sonra değerlendirilecek bir yol haritası maddesi olur,
   kuralların bu veriye göre ayarlanması için gerekçe değildir.

## 6. Koşu sonrası yasaklar ve izinler

- **Yasak:** sonucu gördükten sonra kural, eşik, ağırlık, bütçe ya da kapı parametresi değiştirip yeniden koşmak ve
  o sonucu r6.2 sonucu olarak sunmak. Böyle bir değişiklik yeni bir dondurma sürümü (v4) ve **yeni bir veri seti**
  (r6.1 ya da r5.1) gerektirir.
- **İzinli ikincil analizler** (hepsi burada ilan edildi, sonuç raporunda "ikincil" diye işaretlenir):
  1. Bütçe 10 varyantı (r4.2/r5.2 ile karşılaştırma).
  2. v3 bileşen ablasyonları: `kaynak_cesitliligi`, `oncelik_momentum`, `oncelik_cesitlilik`, `oncelik_akran`
     ve `prediction_weight > 0`. Her biri ayrı ayrı; hangisinin açılacağına bu ölçümlerle karar verilir.
  3. Kural matrisi ve karşıt olgu çıktılarının incelenmesi (raporlama katmanı, skoru değiştirmez).

## 7. Çıktılar

`<out>/sonuclar.json`, `<out>/ozet.md`, pencere başına `pencere_<i>.json`. Çıktılar repo dışında tutulur.
Sonuç belgesi `docs/` altına yazılır ve r4.2 / r5.2 / r6.2 karşılaştırma tablosunu içerir.
