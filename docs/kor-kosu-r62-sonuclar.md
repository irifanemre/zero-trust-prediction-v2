# CERT r6.2 kör koşu — sonuçlar

**Koşu: 29 Ekim 2026.** Tek koşu, ön kayıt `docs/kor-kosu-r62-plani.md` (commit `adf4a59`).
HEAD `0ed0472`, dondurma `kurallar-donduruldu-v3` → koşudan hemen önce **`donmuş durumla aynı`**.
Örneklem `cert-r6.2-orneklem.json` (sha256 `9f694b1…`), bölme sha256 `6f7168f…`, model sha256 `2beabe4…`.

Bu belge koşudan **sonra** yazıldı. Ön kayıt değiştirilmedi.

## 1. Koşunun kapsamı

| # | Dönem | Olay | Kullanıcı | Vaka | Tepe bellek | Süre |
|---|---|---|---|---|---|---|
| 1 | 2010-06-07 – 2010-09-04 | 35.880.282 | 2801 | 2205 | 17,53 GB | 62 dk |
| 2 | 2010-09-05 – 2010-12-03 | 34.854.925 | 2801 | 2173 | 15,77 GB | 55 dk |
| 3 | 2010-12-04 – 2011-03-03 | 33.827.626 | 2801 | 2061 | 16,85 GB | 45 dk |
| 4 | 2011-03-04 – 2011-06-01 | 32.807.311 | 2801 | 2077 | 16,67 GB | 50 dk |

Toplam **8.516 vaka / 360 gün** = günde 23,7. Bir pencere plan gereği atlandı (111 günlük tarihçesi veri
başlangıcından önceye düşüyor).

## 2. Önceden yazılmış beklentiler: tuttu mu?

Ön kayıt §5'te altı beklenti vardı. **İkisi tutmadı** ve bu, sonucun kendisidir:

| # | Beklenti | Sonuç | |
|---|---|---|---|
| 1 | 5 insider'ın 2–4'ü kuyruğa girer | **3** | ✔ |
| 2 | Masum kullanıcıların %10–25'i en az bir kez kuyruğa düşer | **%19,2** (538/2796) | ✔ |
| 3 | precision@1 **0,05–0,20** | **0,014** | ✘ |
| 4 | 30'luk bütçe **çoğu gün dolmaz** | neredeyse her gün doldu (23,7/gün) | ✘ |
| 5 | 22 kuralın 8–12'si tetiklenir | 8 canlı + 2 gölge | ✔ |
| 6 | S3 ve S5 yüksek olasılıkla kaçar | **S3 yakalandı**, S5 kaçtı | yarı |

### Beklenti 3 ve 4 neden tutmadı

İkisi aynı sebebin iki yüzü. Ön kayıt, v2 doğrulama kapısının sınırlayıcı olacağını ve bütçenin boş kalacağını
varsayıyordu; sentetik veride günlük ortalama 4,4 vakaydı. Gerçekte 2801 kullanıcıda kapıdan **günde ~24 vaka**
geçti. Bütçe dolunca precision@1 kaçınılmaz olarak düştü: 2801 kullanıcıda 1 insider varken (binde 0,36) ilk
sıradaki vakanın insider olma olasılığı zaten çok düşüktür.

**Bu, kuralların r6.2'ye göre ayarlanması için gerekçe değildir.** Ön kayıt §6 böyle bir değişikliği yasaklar.
Bulgu, yol haritası maddesidir: kapı nüfusla ölçeklenmiyor.

## 3. Yakalama

| Senaryo | Değerlendirilebilir | Yakalandı | Erkenlik |
|---|---|---|---|
| S1 | 1 | **evet** | 11 gün önce |
| S2 | 0 (pencereye kısmi düştü) | — | — |
| S3 | 1 | **evet** | 0 gün |
| S4 | 1 | **evet** | 0 gün |
| S5 | 1 | hayır | — |
| **Toplam** | **4** | **3 (0,75)** | medyan 0 gün |

S4 ancak ön kayıt §2.2'deki tarih onarımı sayesinde ölçülebildi; onarım olmasaydı test parçasının tek insider'ı
düşecek ve değerlendirilebilir senaryo 3'e inecekti.

**S5 kaçtı** ve bu beklenen bir bedeldi: S5 tek dakikalık bir olay, sistem ise varlık-gün toplulaştırmasıyla
çalışıyor. S3 (tek gün, 8 saat) beklentinin aksine yakalandı.

## 4. Yanlış alarm — r6.2'nin asıl ölçtüğü şey

| | Değer |
|---|---|
| Negatif kullanıcı | 2796 |
| En az bir kez kuyruğa düşen | **538 (%19,2)** |
| TP 3 · FN 1 · FP 538 · TN 2258 | precision 0,006 · recall 0,750 |

r6.2'nin değeri yakalama oranında değil burada: insider yoğunluğu binde 0,36 ile gerçek bir kuruma en yakın ölçüm.
%19,2, r4.2'deki %24–29 ve r5.2'deki %18–26 aralığının altında — v2 doğrulama kapısı işini yapıyor. Ama mutlak
sayı olarak **90 günde 538 masum kullanıcı** bir SOC için yüksektir.

## 5. Kural sağlığı

| Kural | Canlı | Gölge |
|---|---|---|
| UEBA-0005 | 20.762 | 0 |
| UEBA-0001 | 3.810 | 0 |
| UEBA-0002 | 2.125 | 0 |
| UEBA-0017 | 1.772 | 0 |
| UEBA-0021 | 534 | 0 |
| PRED-0012 | 297 | 0 |
| UEBA-0003 | 7 | 0 |
| UEBA-0007 | 10 | 0 |
| UEBA-0009 | 0 | 13.536 |
| UEBA-IF01 | 0 | 10.432 |

**22 kuralın 12'si hiç tetiklenmedi.** Sebep kuralların kötülüğü değil, CERT'te o telemetrinin olmaması: İK
sinyalleri (PRED-0011/13/14), EDR süreç ağacı, konum, ilişkisel kurallar (REL-0015/16) ve aldatma katmanı
(HONEY-0018/19/20) r6.2'de de **sınanmamış** kaldı. Aldatma katmanının neden bağlanmadığı ön kayıt §2.1'de.

## 6. Öğrenen model

| | AUC | Brier beceri | ECE |
|---|---|---|---|
| Birincil (r4.2'de eğitilen, C=0,001) | 0,769 | −127,96 | 0,0328 |
| Sezgisel taban | 0,747 | −255,11 | 0,0757 |
| İkincil (r6.2 içi, test parçası) | 0,945 | −0,0 | 0,0 |

670.535 satırda **55 pozitif** (binde 0,08). Bu yoğunlukta Brier beceri skoru anlamını yitirir; AUC 0,769 ise
r4.2'deki 0,834'ün altında. Model skora **katılmıyor** (`prediction_weight = 0`) ve bu koşu onu değiştirmek için
gerekçe üretmiyor. İkincil modelin 0,945 AUC'si 7 pozitif satıra dayanıyor — karar dayanağı yapılamaz.

## 7. r4.2 / r5.2 / r6.2

| | r4.2 (ayar verisi) | r5.2 (1. kör) | r6.2 (2. kör) |
|---|---|---|---|
| Kullanıcı | 1000 | ~1000 | **2801** (4000'den %70 örneklem) |
| İnsider | 70 | 99 | **5** |
| İnsider yoğunluğu | %7,0 | %9,9 | **%0,18** |
| Bütçe | 10 | 10 | **30** |
| Yakalama | — | — | 3/4 (0,75) |
| precision@1 | 0,188* | 0,20 | **0,014** |
| Yanlış alarm | %24–29 | %18–26 | **%19,2** |
| AUC (birincil model) | 0,834 | 0,86→0,69 | **0,769** |

\* doğrulama parçası

precision@1'in düşüşü model kötüleşmesi değil, **taban oranı etkisidir**: insider yoğunluğu r5.2'ye göre 55 kat
düşük. Aynı sistem, aynı kurallarla. Yanlış alarm oranının üç veri setinde de %18–29 bandında kalması ise
kuralların veri setine ezberlenmediğinin göstergesi.

## 8. Plandan sapmalar

Ön kayıt §6, sapmaların ayrı başlıkta yazılmasını şart koşar. Üç sapma var; **üçü de koşudan önce** yapıldı ve
plana o anda işlendi:

1. **§2.2 — cevap anahtarı tarih onarımı.** r6.2'nin resmi `insiders.csv` dosyasında CDE1846 (S4) başlangıcı
   `/21/2011` biçiminde, ayı eksik. Deterministik onarım kuralı yazıldı (ay yalnız bitişten, gün/saat/yıl dosyadan,
   bitişi aşamaz, 60 günü geçemez). Yan bulgu: pandas bu deseni günü 12'den küçükken **sessizce yanlış** okuyordu.
2. **§2.3 — bellek uyarlaması.** Eşdeğerlik testi (r4.2'de optimizasyon açık/kapalı) kategorik dtype'ın grafa
   hayalet kenar eklediğini yakaladı; `observed=True` ile giderildi ve `source` kolonu optimizasyon dışı bırakıldı.
   Düzeltme sonrası çıktı birebir aynı: `"esdeger": true`, vaka 729 = 729.
3. **§3.1 — örneklem katmanı.** Plan katmanları "S1–S5 ve benign" diye tanımlıyordu; bölme de örnekleyici de aynı
   sıralı nüfusu tohum 42 ile karıştırdığından örneklem **eğitim parçasına çakışıyordu** (doğrulama %17, test %7,5).
   Katman (parça × senaryo) olarak inceltildi; her parçadan tam %70.

**Dördüncü sapma, koşu sırasında ortaya çıktı ve düzeltilmedi:** ön kayıt §3 tepe belleği 12 GB ile sınırlıyordu
ve `f = 0,70` bu hedefe göre seçilmişti. Gerçekleşen tepe **15,8–17,5 GB** oldu, yani tahmin modeli (r4.2'den
devşirilen ×1,126 tespit payı) 2801 kullanıcıda yetersiz kaldı. Koşu 24 GB'lık makinede tamamlandı; sonuçlar
etkilenmedi, ancak bellek tahmini yöntemi nüfusla ölçeklenmiyor.

## 9. Bu koşudan çıkan yol haritası maddeleri

Hiçbiri bu veriye göre kural ayarlamak değildir; hepsi ayrı veri setinde sınanmak üzere kaydedilir:

1. **Kapı nüfusla ölçeklenmiyor** (beklenti 4). Doğrulama kapısı 1000 kullanıcıda sınırlayıcıyken 2801'de değil.
2. **Tek günlük/tek dakikalık olaylar** (S5) varlık-gün toplulaştırmasıyla yakalanamıyor; saatlik veya olay bazlı
   bir yol gerekiyor.
3. **12 kural hâlâ sınanmamış** — CERT ailesinde o telemetri yok. Gerçek kurum verisi gerekiyor.
4. **Bellek tahmini** nüfusla ölçeklenmiyor; tespit payı kullanıcı sayısına bağlı ölçülmeli.
5. **Öğrenen model** bu yoğunlukta karar dayanağı olamıyor; sınıf dengesizliği yöntemleri gerekiyor.

## 10. Çıktılar

`ztp_out_kor_r62/sonuclar.json`, `ozet.md`, `pencere_1..4.json` (+ `.npz`). Plan gereği depo dışında tutulur.
