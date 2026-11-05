# Faz C-2 ön kaydı — ufuk başına kalibrasyon

**Yazıldı: 5 Kasım 2026, kod değişikliğinden ÖNCE.** Dayanak: `docs/faz-c1-sonuclar.md`.

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## C-1 ne gösterdi, C-2 ne yapıyor

C-1'in asıl bulgusu şu: `p7` iyi bir **sıralayıcı** (AUC 0,90, AUPRC tabanın 13 katı), kötü bir
**olasılık** (beceri skoru dört ufukta ve dört tohumda da negatif, −0,30 … −1,05).

C-1'in karar kuralı ufuk başına ayrı MODEL diyordu ama o kural yanlış şeyi ölçüyordu (sapma 2).
Ölçümün gerçekten desteklediği şey daha dar:

| Değişmeyecek | Değişecek |
|---|---|
| Sıralayıcı: bileşen toplamı (`Σcomp`) | Olasılık eşlemesi: `sigmoid(-3.5 + Σcomp)` |
| Özellikler, ağırlıklar | Ufuk başına kalibrasyon eğrisi |
| Kuyruk sıralaması (13.5) | Rapora yazılan olasılık cümlesi |

Sebep kodda görünüyor: tek bir elle konulmuş kesme noktası (`-3.5`), tek ufka göre. Taban oranı
ufka göre iki kat değişiyor (0,031 → 0,063). Aynı kesme noktası dört farklı taban oranına doğru
olasılık veremez.

## C-2a — ÖNCE çevrimdışı ölçüm (bu faz)

Soru: *ufuk başına kalibrasyon, beceri skorunu negatiften pozitife çevirebilir mi?*

Bu, boru hattına bir şey bağlamadan ölçülebilir ve ölçülmeden bağlanmayacak.

| # | Ne | Dosya | Donmuş |
|---|---|---|---|
| 1 | Zamansal bölme: ilk yarıda kalibre, ikinci yarıda değerlendir | `scripts/ufuk_kalibrasyon.py` (yeni) | hayır |
| 2 | Ufuk başına PAVA izotonik eşleme (`VennAbersKalibrator`) | aynı — mevcut sınıf kullanılır | hayır |
| 3 | Önce/sonra: beceri skoru, ECE, Brier, AUC | aynı | hayır |

**Hiçbir donmuş dosya değişmeyecek, dondurma sürümü değişmeyecek, boru hattına hiçbir şey
bağlanmayacak.**

### Sızıntı bariyeri — bu fazın en kritik tasarım kısıtı

Ufuk h için gün d'nin sonucu ancak **d + h** gününde bilinir. Dolayısıyla:

- Kalibrasyon kümesi yalnız **sonucu kesinleşmiş** günlerden kurulur.
- Değerlendirme kümesi kalibrasyon kümesinden **en az h gün sonra** başlar.
- Aradaki h günlük bant **hiçbir kümeye girmez** (tampon).

Tampon olmazsa kalibrasyon, değerlendirme penceresine taşan sonuçları görür ve beceri skoru
yapay olarak yükselir. Bu, projedeki "geçmiş yalnızca geçmişten" kuralının (21.2) ufuk versiyonudur.

### Etiket kaynağı — ölçümün iyimser olduğu nokta, şimdiden yazılıyor

Kalibrasyon **etiket** gerektiriyor. Bu ölçümde etiketler **cevap anahtarından** gelecek, çünkü
sentetik veride analist etiketi yok. Üretimde etiket analistten gelir, gecikmelidir ve eksiktir.

> Dolayısıyla C-2a'nın sonucu bir **üst sınırdır**: "mükemmel etiketle kalibrasyon bu kadar
> kazandırıyor". Gerçek kazanç daha az olacak. Bu, sonucu geçersiz kılmaz ama **abartmamak
> gerekir** ve raporda açıkça yazılacak.

## Başarı eşikleri — ölçümden ÖNCE

1. **Beceri skoru dört ufukta da pozitife geçer** (şu an −0,30 … −1,05). Asıl ölçüt bu.
2. **ECE belirgin düşer**: dört ufukta da en az yarıya (şu an 0,084–0,120).
3. **AUC DEĞİŞMEZ** (±0,005). Kalibrasyon monoton bir eşlemedir, sıralamayı değiştirmemelidir.
   Değişirse uygulama hatalıdır — bu bir **doğruluk kontrolü**, iyileştirme ölçütü değil.
4. **Değerlendirme kümesi yeterli**: ufuk başına en az 300 satır ve en az 10 pozitif. Altında
   kalırsa o ufuk "ölçülemedi" raporlanır, uydurma sayı verilmez.

1 ve 3 birlikte geçmeli: biri kalibrasyonun işe yaradığını, diğeri sıralamayı bozmadığını sınıyor.

C-2b (boru hattına bağlama) **ancak ölçüt 1 ve 3 geçerse** yazılacak ve kendi ön kaydı olacak.

## Beklentiler — karamsar

1. **Ölçüt 4 en olası başarısızlık.** 20 günlük değerlendirme penceresinde, 14 gün ufuk + 14 gün
   tampon çıkınca değerlendirmeye çok az gün kalır. Pencere büyütülecek (60 gün), yine yetmezse
   14 günlük ufuk "ölçülemedi" raporlanacak — **eşik gevşetilmeyecek**.
2. **Beceri skoru pozitife geçse bile az geçecek.** İzotonik kalibrasyon, taban oranı 0,03 olan
   bir problemde çoğu skoru taban civarına çeker; Brier düzelir ama dramatik olmaz.
3. **Kalibrasyon aşırı uyum yapabilir.** PAVA, az pozitifle basamaklı ve kırılgan eğri üretir.
   Ölçüt 4'ün pozitif sayısı şartı bunu kollamak için var.
4. **Bu, sıralamayı İYİLEŞTİRMEYECEK.** Yakalama, recall@K, kuyruk — hiçbiri değişmeyecek,
   değişmemesi gerekiyor (ölçüt 3). Kazanç yalnız **rapora yazılan olasılığın dürüstlüğü**.
   Yani bu faz da yakalama artırmıyor; bu beklenti değil, tasarım.

---

# Sapmalar — ölçümden SONRA eklendi (5 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Sonuçlar: `docs/faz-c2-sonuclar.md`.

## Sapma 1 — ÖLÇÜT 1 KALDI → C-2b yazılmadı

Beceri skoru üç ölçülebilen ufukta da negatif kaldı (−0,066 / −0,112 / −0,373). Ön kayıt
"C-2b ancak ölçüt 1 ve 3 geçerse yazılacak" diyordu; yazılmadı.

Ama kalibrasyon **beklenenden çok daha iyi** çalıştı: beceri boşluğunun %93'ü kapandı, ECE 5 kat
düzeldi. Karamsar beklenti 2 ("pozitife geçse bile az geçecek") yönü doğru tahmin etmiş ama
büyüklüğü yanlış — iyileşme büyük, yeterlilik yok.

## Sapma 2 — ön kayıtta öngörülmeyen sebep: YANLILIK ≠ ÇÖZÜNÜRLÜK

Ön kayıt kalibrasyonun beceri skorunu neden düzeltebileceğini sorgulamamıştı. Ölçüm ayrımı
gösterdi: kalibrasyon **yanlılığı** giderir (ECE'nin 5 kat düzelmesi), **çözünürlüğü** değil —
monoton bir eşleme olasılıkların birbirinden ayrışmasını artırmaz, tanım gereği. Beceri skoru
ikisine birden bakıyor; kalan negatiflik bir çözünürlük sınırıdır.

Yani C-1'in bulgusu ("iyi sıralayıcı, kötü olasılık") yalnız doğrulanmadı, **sebebi** bulundu.
Ve bu, hiçbir kalibrasyon yönteminin çözemeyeceği bir sınır: model olasılık uzayında yeterince
ayrıştırmıyor.

## Sapma 3 — ÖLÇÜT 4 kaldı, ve ön kayıtın çözümü sorunu BÜYÜTTÜ

Ön kayıt "pencere büyütülecek (60 gün)" diyordu. Büyütülünce dört ufukta da pozitif **sıfıra**
düştü. Sebep ölçüldü: sentetik üreteç senaryoları pencerenin **başına** sabitliyor (olay günleri
E0+6 … E0+21, 15 günlük sabit bant). Pencere uzadıkça bant başa sıkışıyor.

Yani ön kayıtta yazdığım çözüm, sorunun tersi yöndeydi. Doğru pencere **kısa** olanmış: 24 günde
3/4 ufuk ölçülebilir hâle geldi.

Bu, Faz C'nin ötesinde bir **test aracı** bulgusu: projedeki her uzun pencereli ölçümde bütün
olaylar ilk üçte birde oluyor. Düzeltilmedi — senaryo zamanlamasını değiştirmek projedeki her
kapsama rakamını değiştirir, kendi ön kaydıyla yapılacak iş.

## Sapma 4 — yan bulgu: beceri skorunun kendisi kırılgan

Kalibrasyon öncesi beceri skoru pencere boyuyla uçuyor (−0,906 → −2,101 → −7,239), çünkü pozitif
seyreldikçe `Brier_taban` küçülüyor. Kalibrasyon sonrası değerler kararlı (−0,03 … −0,37).

Bu ön kayıtta yoktu ve önemli: beceri skoru seyrek olay problemlerinde tek başına güvenilmez, ama
bu projede ufuk/kalibrasyon raporlarının ana ölçütüydü.

## Sapma 5 — asıl çıktı koddan değil rapor dilinden geçiyor

Ön kayıt C-2b'yi "boru hattına bağlama" olarak tasarlamıştı. Ölçüm başka bir yere çıktı: sistem
sıralamayı güvenilir biçimde kullanıyor (AUC 0,85–0,94) ama olasılığı **rapora yazıyor** ve o
cümle kalibrasyondan sonra bile dayanaksız. Doğru düzeltme model değil **rapor dili** —
`reporting/` katmanında, olasılık yerine sıra/öncelik. Bu fazın kapsamı dışında, kayda geçiyor.
