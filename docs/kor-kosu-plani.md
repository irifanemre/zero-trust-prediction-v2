# Kör koşu planı (ön kayıt) — CERT r5.2

**Durum:** Ön kayıt. Koşudan önce yazıldı: 8 Ekim 2026. Bu tarihte r5.2 indirilmemişti. Sistem r5.2 üzerinde bir kez bile çalıştırılmadı.
**Amaç:** Kuralları ayarlarken hiç görülmemiş bir veri setinde **tek bir** koşuyla yansız rakam üretmek. r4.2 rakamları
kurallar o veride ayarlandığı için üst sınır sayılır (bkz. `cert-validation.md` → Sınırlar).

Bu belge koşudan sonra değiştirilmez. Koşu sırasında plandan sapılırsa sapma, gerekçesiyle birlikte sonuç raporuna ayrı
bir başlık olarak yazılır. Bu belge yine düzeltilmez.

## 1. Kural sürümü

- Kurallar: git etiketi **`kurallar-donduruldu-v1`** (commit `a253b63`), manifest `configs/freeze/kurallar-donduruldu-v1.json`.
- Kapsam: 21 kural YAML'ı; tespit, skorlama ve profil kodu (12 dosya, hash'le); tenant varsayılanları; akran çarpanı
  sabitleri; özellik tabanları; CERT URL kategorileri.
- Koşudan hemen önce `python -m ztp.freeze --check configs/freeze/kurallar-donduruldu-v1.json` çalıştırılır ve
  `donmuş durumla aynı` çıktısını vermelidir. Bu çıktı, koşunun HEAD commit karması ve tam komut satırı sonuç dosyasına yazılır.
- `CERT_SCENARIO_MAP` içindeki beklenen kural listeleri de bugünkü haliyle donmuştur. S4 için beklenen kurallar:
  UEBA-0005, UEBA-0003, PRED-0012.

## 2. Koşudan önce izin verilen tek değişiklik: ayrıştırıcı uyarlaması

r5.2'nin biçimi r4.2'den farklı. Bu fark cevap anahtarı arşivindeki gözlem dosyalarında görülüyor; ayrıntı aşağıdaki
"Bilinen sınırlar" bölümünde. Ayrıştırıcıda **yalnızca biçim okuma** değişebilir. Yeni özellik, yeni sinyal ya da yeni bayt
kaynağı eklenmez; eklenirse bu bir ayar sayılır. Önceden kararlaştırılan eşlemeler:

| Dosya | r5.2 farkı | Eşleme (r4.2 anlamını korur) |
|---|---|---|
| file.csv | `activity`, `to_removable_media`, `from_removable_media` alanları; satırlar artık her tür dosya işlemi | Yalnızca `to_removable_media = True` satırları okunur ve r4.2'deki "taşınabilir medyaya kopya" ile aynı biçimde eşlenir; diğer satırlar okunmaz |
| email.csv | `activity` (Send/View…), `attachments` sayı değil liste | Yalnızca `activity = Send`; `bytes_out = size` (r4.2 ile aynı); ek boyutu **eklenmez** |
| http.csv | (r5.2'de `activity` görülmedi; r6.2'de var) | Yalnızca `url` okunur (r4.2 ile aynı); `content` okunmaz |
| device.csv | `file_tree` alanı | Yok sayılır |
| insiders.csv | Bazı satırlarda bozuk tarih (r6.2'de doğrulandı) | Ayrıştırılamayan satır sessizce düşmez: loglanır ve raporda "değerlendirilemedi" olarak sayılır |
| LDAP | Kolon adları farklı olabilir (doğrulanmadı) | Yalnızca ad eşlemesi |

**Kabul ölçütü:** Uyarlama r4.2'de koşulur. r4.2'nin kural tetikleme sayıları ve kapsama sonuçları birebir aynı kalmalıdır.
Uyarlama commit edilir ve `kor-kosu-r5.2-hazir` etiketiyle işaretlenir. r5.2'de boru hattı ancak bundan sonra koşulur.

**Yasak:** Uyarlama sırasında r5.2'de yalnızca başlık satırlarına, satır sayılarına ve sürüm README'sine bakılır. Tespit,
skor ya da kuyruk çıktısı üreten hiçbir şey koşulmaz.

## 3. Veri, pencere ve ayarlar

- **Pencere:** Veriye bakmadan önce mekanik olarak hesaplanır. D0 = `logon.csv` içindeki ilk gün, D1 = son gün.
  Değerlendirme dönemi D0 + 111 gün ile D1 arasıdır. 111 gün = 90 günlük uzun pencere + 21 günlük ısınma, r4.2 koşusuyla aynı.
- **Parçalama:** Dönem, D1'den geriye doğru ardışık 90 günlük pencerelere bölünür. Her pencere r4.2 koşusuyla aynı
  komutla koşulur: `--days 90 --warmup 21`, kendi 111 günlük tarihçesiyle. Başlangıcı D0 + 111'den önceye düşen pencere
  kısaltılmaz, atlanır ve raporda belirtilir.
- **Senaryo ataması:** Her insider senaryosu, bitiş tarihini içeren pencerede ölçülür. "Kısmi pencere" tanımı r4.2 ile aynıdır.
- **Bütçe:** 10 vaka/gün. Diğer bütün ayarlar `scripts/cert_eval.py` varsayılanları ve donmuş tenant varsayılanlarıdır.
  Eşik varyantı koşulmaz (`--no-variants`).
- **Kullanıcılar:** Tüm kurum. Bellek sınırı (RAM 15,6 GB) şu sırayla çözülür:
  1. **Parça parça işleme (önce bu denenir):** Loglar 1 milyonluk satır parçalarıyla okunur ve okurken pencere dışı
     satırlar atılır. Koşu, yukarıdaki 90 günlük pencerelerle zamanda bölünür; her pencere yalnızca kendi 111 günlük
     tarihçesini belleğe alır. Pencereler sırayla koşulur ve her pencereden sonra bellek boşaltılır. Bellek tahmini
     tespit çıktısı üretmeden yapılır: yalnızca yükleyici koşulur ve olay sayısı ölçülür. r4.2'de ölçülen tepe bellekle
     olay başına bellek hesaplanır.
  2. **Örnekleme (yalnızca 1. adım yetmezse):** En büyük pencerenin tahmini tepe belleği 12 GB'ı aşarsa kullanıcılar
     örneklenir. Örnek **katmanlı** ve **tek oranlıdır**: insider'lar dahil her katmandan (insider senaryo türü S1–S4 ve
     benign) aynı oranda `f` kullanıcı, tohum 42 ile seçilir. Böylece insider oranı korunur.
     `f = min(1, 12 GB / tahmini tepe)`, 0,05'lik adımla aşağı yuvarlanır. `f` koşudan önce, yalnızca yükleyici ölçümüyle
     belirlenir ve bu belgeye eklenerek commit edilir. Tüm sonuçlar `f`, örneklenen kullanıcı ve insider sayıları ve
     insider oranıyla birlikte raporlanır. Örnekleme akran gruplarını küçültür (en az akran grubu boyutu 8), bu da sınır
     olarak raporlanır.
  - **Kullanılmayacak yol:** "Kullanıcıları 1000'e indir, bütün insider'ları tut" yedeği **iptal edildi**. Bu yol insider
    oranını yaklaşık iki katına çıkarır, precision'ı yapay olarak şişirir, akran gruplarını ve bütçe/kullanıcı oranını
    değiştirir. Not: yükleyicideki `max_users` seçeneği bu davranışa sahip, bu yüzden kör koşuda kullanılmaz.

## 4. Raporlanacak metrikler

Tanımlar r4.2 değerlendirmesiyle (`src/ztp/evaluation.py`) aynıdır.

1. **Yakalama:** Değerlendirilebilir ve kısmi pencereli senaryolar ayrı raporlanır. Senaryo bazında (S1–S4) verilir.
   "Kuyruğa girdi" ve "beklenen kuralla girdi" (GEÇTİ / REVİZYON GEREKLİ) ayrı sayılır.
2. **precision@1/3/5/10:** Varlık-gün bazında, cevap anahtarı etiket rolünde. Ayrıca kullanıcı bazında precision verilir.
3. **Erkenlik:** Senaryo bitişi ile ilk kuyruk girişi arasındaki gün farkı. Medyan ve senaryo bazında.
4. **Confusion matrix:** Kullanıcı bazında. Değerlendirilebilir insider'lar pozitif, kısmi pencereliler hariç (r4.2 tanımı).
5. **Kural sağlığı:** 21 kuralın tetikleme sayıları. r4.2 kapsama tablosuyla yan yana verilir.
6. **Lojistik regresyon:**
   - **Birincil:** r4.2'nin tamamında kullanıcı-ayrık protokolle eğitilen model (C = 0,001, r4.2 tamamlayıcı protokolünde
     seçilen değer). Model JSON olarak (`LogisticModel.to_dict`) **koşudan önce** kaydedilir. sha256 değeri bu belgeye
     ek olarak commit edilir. Model r5.2'ye bir kez uygulanır. Raporlanacaklar: AUC, ECE, Brier, Brier tabanı ve r4.2'de
     seçilen eşikte F1. Sezgisel model de aynı satırlarda kıyas için verilir.
   - **İkincil:** r5.2 içinde `lr_protocol`: 70/15/15 kullanıcı bölmesi (tohum 42), 7 günlük embargo, C ızgarası
     doğrulama log-loss'uyla seçilir, her C için F1 raporlanır. Bölme dosyası yalnızca kullanıcı listesi ve cevap
     anahtarıyla, koşudan önce üretilip commit edilir.
7. **Karşılaştırma tablosu:** r4.2 (ayarlanmış) ve r5.2 (kör) yan yana.

## 5. Önceden yazılan beklentiler

Bunlar hipotez, başarı eşiği değil. Sonuç ne çıkarsa çıksın olduğu gibi raporlanır.

- Yakalama ve precision@1'in r4.2'den düşük çıkması beklenir.
- UEBA-0003, r5.2'de de kör kalabilir. Bayt kaynağı yine yalnızca e-posta boyutu ve 5 MB taban değişmedi. Bu durumda S4
  "beklenen kuralla girdi" ölçütünde REVİZYON GEREKLİ çıkabilir. S4'ün başkasının makinesine giriş adımı UEBA-0005 ile
  kuyruğa girebilir.
- S1 ve S2'de URL kategorileri belirleyici olacak. Bu kategoriler r4.2 içeriğine göre yazıldı (ör. `wikileaks`,
  `keylog`). Aynı alan adları r5.2'de de geçiyorsa yakalama oranı bu yüzden yüksek çıkabilir. Rapor bunu ayrıca belirtir.

## 6. Koşudan sonra

- Kurallarda, eşiklerde, ağırlıklarda ve metrik tanımlarında **değişiklik yapılmaz**. Sonuç olduğu gibi
  `docs/bulgular.md` ve README'ye yazılır.
- Yeniden koşu yalnızca teknik bir hata (çökme, okuma hatası) olursa yapılır. Bu durumda hata, düzeltme ve iki koşunun
  sonuçları birlikte raporlanır.
- Daha sonra kural değişirse yeni bir dondurma sürümü (`v2`) yazılır. r5.2 sonucu v1'in sonucu olarak kalır. r5.2 artık
  v2 için kör sayılmaz.

## 7. Bilinen sınırlar ve sızıntılar

- **Senaryo bilgisi:** Senaryo tanımları biliniyor (`answers/scenarios.txt`) ve S1–S3 r4.2'de görüldü. Yalnızca S4 yeni.
- **Gözlem dosyalarına bakıldı:** Cevap anahtarı arşivindeki r5.2 gözlem dosyalarına 8 Ekim 2026'da yalnızca biçimi
  anlamak için bakıldı (satır türü ve alan sayısı, birkaç örnek satır). Bu, kurallar dondurulduktan **sonra** yapıldı.
- **Doğrulanmamış bilgiler:** r5.2'nin kullanıcı sayısı (ikincil kaynaklarda 2000) ve veri dönemi doğrulanmadı. Satır
  sayıları ve dosya listesi indirmeden sonra raporun başına yazılır.
- **İnsider yoğunluğu:** r5.2'de 99 insider var (`answers/insiders.csv`); bu, gerçek bir kuruma göre yüksek bir yoğunluk.
  Precision bu yüzden iyimser çıkar. r4.2 README'si o sürümü açıkça "dense needles" olarak tanımlıyor; r5.2 README'sinde
  aynı ifadenin geçip geçmediği doğrulanmadı.

## 8. Koşu öncesi değişiklik kaydı

- **8 Ekim 2026 — bellek planı:** "1000 kullanıcı + bütün insider'lar" yedeği iptal edildi. Yerine önce parça parça
  işleme, gerekirse insider oranını koruyan tek oranlı katmanlı örnekleme geldi (§3). Gerekçe: eski yedek insider
  oranını değiştirerek precision'ı şişirirdi. Bu değişiklik r5.2 indirilmeden ve tespit çıktısı üretilmeden yapıldı.

## 9. Kayıt

- Çıktılar: `C:\data\ztp_out\kor_r52\`. Repo dışında tutulur.
- `sonuclar.json` dosyası şunları içerir: freeze kontrol çıktısı, HEAD karması, komut satırları, pencere listesi, LR
  model sha256'sı ve bu belgenin commit karması.
