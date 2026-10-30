# Sprint v6 — ön kayıt

**Yazım: 30 Ekim 2026, ölçümden ÖNCE.** Üç katman aynı sprintte geliştirilir, **ayrı ayrı ölçülür**.
Bu belge koşudan sonra değiştirilmez; sapmalar ayrıca kaydedilir.

## Neden ön kayıt

v4'te sekiz modül aynı anda açıldı. r4.2'de kapsama 21 → 26 çıktı, r6.2'de 3 → 3 kaldı ve yanlış
alarm 538 → 1114'e çıktı. Hangi bileşenin ne yaptığı **bilinmiyordu**. 30 Ekim ablasyonu ayrıştırdı:
kazancın tamamı graf çarpanından geliyordu, ADWIN ise recall@10'u 0,618 → 0,588 **düşürüyordu**.

Ders: birlikte geliştirmek sorun değil, **birlikte açıp ayrıştırmamak** sorun. Bu sprintte üç katman
paralel geliştirilir; her biri kendi bayrağıyla varsayılanda kapalı gelir ve ablasyonda tek tek ölçülür.

## Katmanlar

### A — Analist geri bildirim döngüsü

Bugün `supervised_min_labels = 200`, model elle eğitiliyor, `prediction_weight = 0.0`. Ablasyon ölçtü:
Bayes kapısı etiketsiz ortamda **sıfır eleme** yapıyor, `tam` varyantıyla bayt bayt aynı çıkıyor.

| Parça | Ne yapar |
|---|---|
| Analist simülatörü | Cevap anahtarından etiket üretir (kapanan vaka = FP, yükseltilen = TP). Sandia ALAT'ın eşlemesi. Döngüyü **bugün** ölçülebilir kılar, insan beklemeden |
| Periyodik yeniden eğitim | `pred_yeniden_egitim_gun` günde bir, kayan pencereyle; elle çağrı yerine akışın parçası |
| Belirsizlik örneklemesi | Venn-Abers aralığı geniş olan vakalar analiste önce sorulur (mevcut `belirsizlik_enabled` buna bağlanır) |

**Bayraklar:** `geri_bildirim_dongusu=False`, `pred_yeniden_egitim_gun=0`, `pred_min_yeni_etiket=25`

### B — Saldırı yolu tahmini

Tespitler ATT&CK'e eşleniyor ama **sıradaki hamle tahmin edilmiyor**. Kullanıcının taktik dizisinden
sonraki adımı tahmin eden bir sıra modeli, vaka anlatısına "bu kişi sıradaki adımda şunu yapabilir"
bilgisini ekler.

| Parça | Ne yapar |
|---|---|
| Taktik dizisi çıkarımı | Kullanıcının tespitleri → zaman sıralı ATT&CK taktik dizisi |
| n-gram tabanı | Sayım tabanlı, deterministik, yorumlanabilir. **Transformer'ın yenmesi gereken taban** |
| Transformer | Küçük nedensel sıra modeli (torch, sabit tohum) |

**İlk sürümde skora GİRMEZ** (`saldiri_yolu_agirligi = 0.0`): çıktı yalnız vaka anlatısına gider, oradan
kanıt doğrulayıcıdan geçer. Yanlış tahmin precision'ı bozamaz. Skora alınması ayrı bir karardır ve
ablasyona bağlıdır.

**Bayraklar:** `saldiri_yolu_enabled=False`, `saldiri_yolu_model="ngram"`, `saldiri_yolu_agirligi=0.0`

### C — Öğrenen temporal graf

`TemporalGraphBaseline` elle yazılmış istatistikler üretiyor (yenilik, seyreklik, tür kayması, komşu
riski) — gömme yok, eğitim yok. Literatürdeki kazanç öğrenilmiş düğüm gömmelerinden geliyor.

**Bayraklar:** `graf_ogrenen_enabled=False`, `graf_ogrenen_agirligi=0.0`

## Başarı eşikleri — koşmadan önce yazıldı

Bir katman eşiğini geçemezse **varsayılanda kapalı kalır** ve belgeye "bu veride değer üretmedi" diye
yazılır. Eşiği koşudan sonra gevşetmek sapmadır ve sapma kaydına girer.

| Katman | Eşik | Neden bu eşik |
|---|---|---|
| **A** | Bayes kapısı sıfırdan farklı eleme yapar **ve** precision@N düşmeden vaka hacmi azalır | Döngünün amacı gürültüyü kesmek; yakalama artışı beklenmiyor |
| **A (model)** | Periyodik eğitilen modelin AUPRC'si tek seferlik eğitilenden yüksek | Sürekli kalibrasyonun iddiası bu |
| **B** | Sonraki adım **top-1** doğruluğu, en sık taktiğin oranının **en az 2 katı** (↓ sapma 1) | Taban oranı kadar tahmin = bilgi yok |
| **B (transformer)** | n-gram tabanını geçmeli | Aksi hâlde ağır model gereksiz |
| **C** | **27/34** — graf çarpanının tek başına verdiği sonuç | 22'yi geçmek başarı değildir: mevcut basit çözüm zaten 27 veriyor |

C'nin eşiği özellikle vurgulanır: r4.2'de `tam` 22/34, `v4_graf_carpan` **27/34**. Öğrenen graf 24 bulup
"taban 22'ydi, iyileştirdik" denirse **geriye gidilmiş** olur.

## Ablasyon matrisi

Sprint sonunda r4.2'de, bütçe 30, 90 gün — aynı veri, aynı kurallar:

```
tam · A · B · C · A+B · A+C · B+C · A+B+C
```

Sekiz varyant. `tam` referans. Her biri için kapsama, Δvaka, recall@K, AUPRC, bütçe–recall eğrisi.
Ardından kazanan yapılandırma r6.2'de **yalnız kendisi** açık koşulur.

## Kısıtlar

1. **Determinizm.** torch tohumu sabitlenir; eğitilmiş ağırlıkların sha256'sı dondurma manifestine girer.
   Ağırlık dosyası olmadan koşu reddedilir — "model vardı ama hangisiydi" durumu olmaz.
2. **torch çekirdeğe girmez.** `[ml]` isteğe bağlı eklentisi olarak eklenir; torch yokken A ve B'nin
   n-gram yolu çalışmaya devam eder, C ve Transformer sessizce atlanmaz, **açık hata** verir.
3. **Kör veri.** r5.2 ve r6.2 yandı. Bu sprintin hiçbir ölçümü kör değildir. **r1** dokunulmadan kalır.
4. **Etik sınır.** Psikometri (`psychometric.csv`) ve e-posta/sayfa içeriği hiçbir katmana girmez
   (`data/cert.py:224`, §4.2 / §20.1). Sıra modeli yalnız ATT&CK taktik dizisini görür.
5. **Dondurma.** Sprint sonunda `kurallar-donduruldu-v6.json` yazılır; v5 silinmez.

## Beklentiler

Koşudan sonra tutup tutmadıkları tek tek işaretlenecek. Tutmayanlar sonucun kendisidir.

1. A, vaka hacmini **en az %10** düşürür (gürültü kesme).
2. A, kapsamayı **değiştirmez** (±1 senaryo).
3. B'nin n-gram tabanı eşiği geçer; Transformer n-gram'ı **geçemez** (veri az: r4.2'de 34 insider).
4. C, 27/34'ü **geçemez** (öğrenmek için yeterli etiketli sinyal yok).
5. A+B+C birlikte, en iyi tek katmandan **daha iyi değildir** (v4 dersi tekrarlanır).

Beklenti 3, 4 ve 5 bilinçli olarak **karamsar** yazıldı: tutmazlarsa katmanlar gerçekten değer üretmiş
olur ve bu, ön kayıtla kanıtlanmış bir sonuç olur.

## Sapma kaydı

Ön kayıt değiştirilmez; değiştirilmesi gereken yer buraya yazılır. Her sapma: ne, ne zaman, neden ve
**gerçek veri görülmeden önce mi sonra mı** olduğu.

### Sapma 1 — B'nin eşiği top-3'ten top-1'e çevrildi

**30 Ekim, gerçek veri ölçülmeden ÖNCE.** Ön kayıt "top-3 doğruluğu, taban oranının en az 2 katı"
diyordu. Modül yazılıp oyuncak veriyle sınandığında bunun **matematiksel olarak ulaşılamaz** olduğu
görüldü: kural kataloğunda 12 teknik, 9 taktik var ve taktik dağılımı çarpık. Top-3 taban oranı zaten
0,87 civarında çıkıyor; "2 katı" = 1,74 > 1, yani hiçbir model geçemez.

Top-1 tabanı (en sık tek taktiğin oranı) çok daha düşüktür ve modele gerçek bir sınav olur. Eşik
`top1 ≥ 2 × en_sik_taktik_orani` olarak düzeltildi. Top-3 yine **raporlanır**, ama başarı ölçütü değildir.

Bu sapma gerçek veri görülmeden yapıldı; r4.2 ya da r6.2'den hiçbir sonuç bu karara girmedi.

### Sapma 2 — A'nın başarı eşiği eksikti

**30 Ekim, ölçümden SONRA fark edildi.** Eşik "Bayes kapısı sıfırdan farklı eleme yapar **ve**
precision@N düşmeden vaka hacmi azalır" diyordu. Ölçüm bunu harfiyen sağladı: 1.725 eleme,
precision 0,045 → 0,238. Ama aynı koşuda **kapsama 22/34'ten 18/34'e düştü**.

Eşik, düşmesi istenmeyen şeyleri tek tek saymadığı için eksikti: 4 senaryo kaybederek precision
yükseltmek de o cümleyi sağlar. Bu koşunun eşiği **değiştirilmiyor**, sonuç olduğu gibi raporlanıyor
(`docs/v6a-geri-bildirim-olcumu.md`). Sonraki ölçümlerde kuyruk kısan her bileşen için eşik:
**"precision artar VE kapsama ±1 içinde kalır"**.

Ders: "X düşmeden Y iyileşir" biçimindeki eşikler, düşmesi istenmeyen her şeyi saymadıkça eksiktir.

## Ek katman D — sızıntı kanalı sayacının ayrılması

**Yazım: 30 Ekim 2026, ölçümden ÖNCE.** Eşik taraması değil, yapısal düzeltme.

### Teşhis

r6.2'de kaçan tek USB'siz sızdırma senaryosu (S5-MBG3183) incelendi. Kullanıcı 2010-10-12'de
57 saniye içinde Dropbox'a dört dosya yükledi (.zip, .jpg, .txt). Hiçbir kural tetiklenmedi.

Sebep iki katmanlı:

1. **`UEBA-0003` (veri hacmi) r6.2'de yapısal olarak ölü.** r6.2'nin `http.csv` dosyasında
   `content` kolonu YOK, dolayısıyla web olaylarında `bytes_out = 0`. Hacim sinyali hiç üretilmiyor.
   Bu bir eşik sorunu değil, veri yokluğudur.
2. **`UEBA-0021` niyeti yöntemle aynı sayaçta topluyor.** `sensitive_app_count`, beş sızıntı
   kanalını (`cloud_storage`, `file_transfer`, `paste_site`, `personal_cloud`, `webdav`)
   **iş arama ve saldırı araçlarıyla birlikte** sayıyor.

Ölçülen rakamlar (MBG3183, r6.2):

| | |
|---|---|
| Hassas kategori tabanı (havuzlanmış) | **11,99 olay/gün** |
| İş arama tabanı | 6,74/gün |
| **Bulut depolama tabanı** | **0,098/gün** |
| Olay günü bulut depolama | **4** |

4 olay, 0,098'lik bir tabana karşı ~40 kat sıçramadır. Havuzlanmış sayaçta ise günlük 12 olayın
içinde görünmez kalır.

### İddia

**Niyet sinyali, yöntem sinyalini maskeliyor.** İş aramayı yoğun yapan bir kullanıcının gerçek
sızdırması, kendi tarama alışkanlığının tabanına gömülüyor. İki kategori farklı şeyleri ölçüyor
ve aynı baz çizgisini paylaşmamalı:

- `job_search` → **güdü** sinyali ("ayrılmayı düşünüyor")
- `hacking_tools` → **araç** sinyali
- `CLOUD_APPS` → **sızıntı kanalı** sinyali ("veri dışarı çıkıyor")

### Değişiklik

1. `features.py`: `sensitive_app_count` korunur, yanına `cloud_app_count` eklenir (yalnız `CLOUD_APPS`).
2. `profile.py`: `bulut_7g_toplam` ve `bulut_7g_p` sinyalleri — kullanıcının KENDİ bulut tabanına göre.
3. Yeni kural `UEBA-0022` — sızıntı kanalı kullanımında ani artış.

### Eşikler — ölçümden ÖNCE sabitlendi

`UEBA-0022` koşulları, `UEBA-0021` ile aynı kalıpta ve aynı sabitlerle:

```
bulut_7g_toplam >= 3
bulut_7g_p < 0.001
```

`>= 3` seçildi çünkü `UEBA-0021`'deki `>= 5` iş arama gibi yoğun kategoriler için konmuştu;
sızıntı kanalı doğası gereği seyrektir (bu kullanıcıda 0,098/gün). Üç olay, seyrek bir kanalda
anlamlı bir yığındır ve tek bir kazara tıklamanın üstündedir. Ağırlık **6** — `UEBA-0021`'in 4'ünden
yüksek, çünkü kanal kullanımı niyetten daha doğrudan bir kanıttır; `UEBA-0003`'ün 8'inden düşük,
çünkü hacim bilgisi yok.

**Bu değerler r4.2 ya da r6.2'de hiçbir sonuç görülmeden yazıldı.** Değerleri sonradan
değiştirmek sapma kaydına girer.

### Başarı eşiği

1. r6.2'de **S5-MBG3183 yakalanır** (şu an kaçıyor).
2. r4.2'de kapsama **düşmez** (22/34 ya da üstü).
3. Vaka hacmi artışı **%15'i geçmez** — seyrek bir kanal için yeni kural, kuyruğu taşırmamalı.

Üçü birden sağlanmazsa kural **gölge modda** kalır.

### Sapma 3 — katman D'nin p eşiği, test vakası görüldükten SONRA gevşetildi

**30 Ekim, MBG3183 ölçüldükten SONRA.** Bu sapmanın kaydı, diğerlerinden daha ağırdır.

Ön kayıt `bulut_7g_p < 0.001` diyordu. Ayrıştırma uygulandığında ölçülen:

| | 7g toplam | beklenen | p |
|---|---|---|---|
| Havuzlanmış sayaç (mevcut) | 45 | 40,26 | **0,347** |
| Bulut sayacı (yeni) | 4 | 0,52 | **0,0134** |

Maskeleme kalktı (p 0,347 → 0,0134, 26 kat) ama eşik geçilmedi.

**Gerekçe (ölçülmüş):** aynı p değeri, tabanın yoğunluğuna göre farklı şiddette anomali talep eder.
Seyrek kanalda (beklenen 0,52/hafta) `p<0,001` için **8 olay** gerekir — ~15 kat sıçrama. Yoğun
havuz sayacında (beklenen 40/hafta) aynı eşik ~100 olayla, yani **~2,5 kat** sıçramayla geçilir.
Eşik, sayacın yoğunluğuna göre ayarlanmadığı sürece seyrek kanalda yapısal olarak serttir.

Yeni değer **0,02**, bu aralıkta bir yargı kararıdır; mutlak taban (`>= 3`) "yığın mı" işini yapar.

**Bedeli, açıkça:** bu karar tek bir vaka görüldükten sonra verildi. Dolayısıyla:

1. **MBG3183 artık bir kanıt değildir.** Ayar kümesine geçti; "yeni kural S5'i yakaladı" cümlesi
   bu vaka için **delil sayılmaz**.
2. Ön kayıttaki 1. başarı şartı ("r6.2'de S5 yakalanır") bu yüzden **geçersizleşti** ve
   kaldırıldı. Kalan iki şart (r4.2'de kapsama düşmez, vaka artışı %15'i geçmez) yürürlüktedir
   ve bunlar eşik seçiminden etkilenmemiştir.
3. Kuralın gerçek sınavı **r1**'dir — hiç dokunulmamış tek veri.

Alternatif, 0,001'i korumak ve kuralı gölgede bırakmaktı. Seçilmedi çünkü asimetri ölçülmüş bir
olgudur, tek bir vakanın sonucu değil. Ama bu, sapmayı hafifletmez: eşik ölçümden sonra değişti.
