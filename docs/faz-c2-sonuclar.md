# Faz C-2a — ufuk başına kalibrasyon: ECE 5 kat düzeldi, beceri skoru hâlâ NEGATİF

**Ölçüm: 5 Kasım 2026.** Ön kayıt: `docs/faz-c2-on-kayit.md` (koddan önce yazıldı).
Araç: `scripts/ufuk_kalibrasyon.py`. Hiçbir donmuş dosya değişmedi, dondurma v10 aynı,
boru hattına hiçbir şey bağlanmadı.

> **Ön kayıt gereği C-2b YAZILMIYOR.** Ölçüt 1 (beceri skoru pozitife geçer) kaldı. Kalibrasyon
> beklenenden çok daha iyi çalıştı ama yetmedi — ve *neden* yetmediği, ön kayıtta öngörülmemiş
> yapısal bir sınır.

## Ölçüm — 120 kullanıcı, 24 günlük pencere, tohum 7

Zamansal bölme: `[kalibrasyon] [h günlük TAMPON] [değerlendirme]`. Tampon, ufuk h'nin sonucunun
ancak d+h'de bilinmesinden dolayı zorunlu; olmazsa kalibrasyon değerlendirme penceresine taşan
sonuçları görür.

| Ufuk | kalib. n | değ. n | pozitif | beceri ÖNCE | beceri SONRA | ECE ÖNCE | ECE SONRA | AUC önce | AUC sonra |
|---|---|---|---|---|---|---|---|---|---|
| 1 gün | 1.343 | 1.473 | 54 | −0,906 | **−0,066** | 0,1228 | **0,0241** | 0,845 | 0,846 |
| 3 gün | 1.343 | 1.238 | 43 | −0,987 | **−0,112** | 0,1231 | **0,0206** | 0,855 | 0,852 |
| 7 gün | 1.343 | 964 | 18 | −2,037 | **−0,373** | 0,1262 | **0,0371** | 0,942 | 0,942 |
| 14 gün | 1.343 | 354 | 2 | — | **ÖLÇÜLEMEDİ** | — | — | — | — |

## Ön kayıtlı ölçütler

| # | Ölçüt (ölçümden önce yazıldı) | Sonuç |
|---|---|---|
| 1 | Beceri skoru dört ufukta da **pozitife** geçer | **KALDI** — iyileşti ama negatif kaldı |
| 2 | ECE en az **yarıya** düşer | **GEÇTİ** — 3,4–6 kat düştü |
| 3 | AUC **değişmez** (±0,005) | **GEÇTİ** — en büyük sapma 0,003 |
| 4 | Dört ufuk da ölçülebilir | **KALDI** — 14 günlük ufukta 2 pozitif |

Ön kayıt: *"C-2b ancak ölçüt 1 ve 3 geçerse yazılacak."* Ölçüt 1 kaldı → **C-2b yazılmıyor.**

### Ölçüt 3 bir doğruluk kontrolüydü ve geçti

Kalibrasyon monoton bir eşlemedir, sıralamayı bozmamalıydı. AUC üç ufukta da sabit kaldı
(0,845→0,846, 0,855→0,852, 0,942→0,942). Yani uygulama doğru: kuyruk, bütçe ve yakalama
**etkilenmiyor** — etkilenmemesi gerekiyordu.

## Kalibrasyon aslında ÇOK İYİ çalıştı — ama yanlış sorunu çözüyor

Beceri skorundaki boşluğun **%93'ü kapandı** (1 gün: −0,906 → −0,066) ve ECE **5 kat** düzeldi
(0,123 → 0,024). Bunlar küçük sayılar değil. Yine de beceri negatif kaldı, yani:

> Sabit taban oranını tahmin etmek, kalibre edilmiş olasılıktan **hâlâ** daha iyi Brier veriyor.

Sebebi şu ayrımda ve ön kayıtta öngörülmemişti:

| | Ne ölçer | Kalibrasyon düzeltir mi |
|---|---|---|
| **Yanlılık** (bias) | olasılıklar sistematik olarak yüksek/düşük mü | **Evet** — ECE'nin 5 kat düzelmesi bu |
| **Çözünürlük** (resolution) | olasılıklar birbirinden ne kadar ayrışıyor | **Hayır** — monoton eşleme ayrışmayı artırmaz |

Beceri skoru ikisine birden bakıyor. Kalibrasyon yanlılığı giderdi; kalan negatiflik
**çözünürlük sınırıdır** ve monoton bir eşlemeyle giderilemez — tanım gereği.

Ve taban oranı %3 olan bir problemde Brier, kalabalık negatif sınıfın egemenliğinde: sabit 0,03
tahmini zaten çok iyi bir Brier verir. Sıralama gücü yüksek (AUC 0,85–0,94) olsa bile Brier'de
onu geçmek zordur.

> **Sonuç: `p7` iyi bir sıralayıcı, ve kalibrasyondan sonra bile kötü bir olasılık.** C-1'in
> bulgusu yalnız doğrulanmadı, **sebebi** de bulundu.

### Beceri skorunun kendisi kırılgan — yan bulgu

Aynı ölçüm üç pencere boyunda tekrarlandı ve kalibrasyon ÖNCESİ beceri skoru pencereyle birlikte
çılgınca değişiyor:

| Pencere | 1 günlük ufukta pozitif | beceri ÖNCE | beceri SONRA |
|---|---|---|---|
| 24 gün | 54 | −0,906 | −0,066 |
| 30 gün | 35 | −2,101 | −0,033 |
| 40 gün | 11 | **−7,239** | −0,371 |

Pozitif seyreldikçe `Brier_taban` küçülüyor ve beceri skoru uçuyor. **Kalibrasyon sonrası değerler
ise kararlı** (−0,03 … −0,37). Yani kalibrasyon aynı zamanda ölçütü stabilize ediyor.

Bu, beceri skorunun seyrek olay problemlerinde **tek başına güvenilmez** olduğunu gösteriyor — ve
bu projede ufuk kalibrasyonu raporlarında ana ölçüt olarak kullanılıyordu.

## Ölçüt 4 kaldı — ve sebebi test aracının yapısal bir eksiği

Ön kayıt "pencere büyütülecek (60 gün)" diyordu. Büyütüldü ve **daha kötü** oldu:

| Pencere | 1g pozitif | 3g | 7g | 14g |
|---|---|---|---|---|
| 24 gün | 54 | 43 | 18 | 2 |
| 30 gün | 35 | 24 | 9 | 0 |
| 40 gün | 11 | 7 | 1 | 0 |
| 60 gün | **0** | **0** | **0** | **0** |

Sebep ölçüldü: **sentetik üreteç senaryoları pencerenin BAŞINA sabitliyor.** Olay günleri
E0+6 … E0+21 aralığında, yani 15 günlük sabit bir bant. Pencere uzadıkça bu bant oransal olarak
başa sıkışıyor ve ikinci yarıda hiç pozitif kalmıyor.

> **Bu, Faz C'nin ötesinde bir bulgu.** Projedeki her uzun pencereli ölçümde bütün olaylar ilk
> üçte birde oluyor, kalan iki üçte iki saf arka plan. Zamana bağlı hiçbir etki (ısınma, taban
> olgunluğu, sürüklenme) senaryo tespitinden ayrıştırılamaz.

Düzeltilmedi ve bilinçli: senaryo zamanlamasını değiştirmek **projedeki her kapsama rakamını**
değiştirir. Kendi ön kaydıyla yapılacak bir iş.

## Operasyonel sonuç: rapordan olasılık cümlesi çıkmalı

Sistem iki şey yapıyor:

| Kullanım | Dayanak | Güvenilir mi |
|---|---|---|
| Kuyruk sıralaması, bütçe (13.5) | **sıralama** | **Evet** — AUC 0,85–0,94, AUPRC tabanın 13 katı |
| Rapora yazılan "%X olasılıkla 7 gün içinde" | **olasılık** | **Hayır** — kalibrasyondan sonra bile beceri negatif |

Doğru düzeltme model değil **rapor dili**: olasılık yerine sıra/öncelik ifade edilmeli
("kuyrukta ilk %1'de", "benzer profillerin 13 katı risk"). Bu bir sonraki iş ve kodu değil
`reporting/` katmanını ilgilendiriyor.

## Sınırlar

- **Etiketler cevap anahtarından.** Ön kayıtta yazıldığı gibi bu bir **üst sınır**: üretimde etiket
  analistten gelir, gecikmeli ve eksiktir. Gerçek kazanç buradan **az** olacak. Yani ölçüt 1
  üretimde de geçmez, daha da geçmez.
- **Sentetik veri, tek tohum.** CERT'te koşu yok (r4.2 ayar verisi, r5.2/r6.2 yanmış, r1 saklı).
- **14 günlük ufuk hiç ölçülemedi.** Brief'in istediği dört ufuktan biri hakkında bu fazdan
  **hiçbir bilgi yok** ve bu gizlenmiyor.
