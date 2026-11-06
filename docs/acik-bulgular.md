# Açık bulgular — ölçüldü, henüz ele alınmadı

Bu dosya, ölçüm sırasında çıkan ama kendi fazı olmayan bulguları tutar. Amacı, "sonra bakarız"
denip kaybolmalarını engellemek. Her madde: ne bulundu, nerede ölçüldü, neden ertelendi.

---

## 1. Erkenlik medyanı NEGATİFLERİ gizliyor

**Ne:** Erkenlik, olay tarihinden kaç gün önce kuyruğa girildiğidir. Bazı senaryolarda **negatif**
çıkıyor — yani tespit olaydan *sonra* geldi:

```
S5_log_sessizligi    erkenlik=-5
S7_yanal_hareket     erkenlik=-3
```

Ama özet yalnız **medyan** raporluyor (`ablation.py:304`, `kor_kosu_r52.py:346`):

```python
erkenlik_medyan=_median([v for v in summ["erkenlik_gun"].values() if v is not None])
```

Negatifler medyana karışıyor ve "erkenlik medyanı 8 gün" cümlesi, bazı tespitlerin **geç**
olduğunu söylemiyor. Erken uyarı iddiasının tam ortasındaki bir boşluk.

**Nerede görüldü:** Faz D ve Faz E koşularının kapsama çıktıları (6 Kasım 2026).

**Neden ertelendi:** Bulgu, r4.2 ablasyon koşusu çalışırken çıktı ve düzeltme `ablation.py`'ye
dokunmayı gerektiriyor — koşan bir ölçümün bağımlı olduğu dosyayı değiştirmek sonucu şüpheli
yapar.

**Yapılacak:** Medyanın yanına **geç tespit sayısı** (erkenlik ≤ 0) eklenecek. Tek satırlık
değişiklik, donmuş dosya değil. Ölçüt: hiçbir rakam değişmeyecek, yalnız bir sayı eklenecek.

---

## 2. `UEBA-0023`'ün eşiği operasyonel karar bekliyor

**Ne:** Eşik veriden türetilemedi (`docs/v10-sonuclar.md`): türetme kuralı kendi doğrulama
sınamasını geçemedi (`bytes_out` için 50 MB üretti, bilinen-iyi sabit 5 MB). Şu anki taban
(50.000) sentetik veride kullanıcıların **%64'ünde** tetikliyor.

**Durum:** Kural **gölge modda**, yani hiçbir yanlış alarm analiste gitmiyor. Risk kontrol
altında, sorun çözülmemiş — ikisi karıştırılmamalı.

**Yapılacak:** Hedef ortamın e-posta ağ geçidinden bir aylık hacim dağılımı alınacak;
`scripts/kurulum_hazirlik.py` o dağılımı (medyan, p90, p99, kullanıcı başına MAD) çıkarıyor.
Karar istatistiksel değil operasyonel: *bir günde normalinin ne kadar üstüne çıkan dış e-posta
hacmi bir analistin zamanına değer?*

---

## 3. `min MAD (>0)` taban türetme kuralı — sınanmamış hipotez

**Ne:** `FEATURE_FLOOR`'daki 13 sabite karşı yedi aday kural denendi; "en küçük sıfır olmayan MAD"
9/10 sabiti ±3 kat içinde yeniden üretiyor (medyan oran 1,00) ve yapısal gerekçeyle de tutarlı
(taban `max(mad, floor)` içinde durduğu için yalnız MAD'i küçük olan kullanıcılarda bağlar).

**Neden uygulanmadı:** Yedi aday arasından **sonuçlar görüldükten sonra** seçildi — doğrulama
kümesi üzerinde model seçimi, doğrulama değil. On nokta ve yedi adayla bir uyum bulmak güçlü
kanıt değil.

**Yapılacak:** Ayrı bir ön kayıtla, tercihen **CERT'in gerçek dağılımları** üzerinde sınanacak.
Geçerse bütün `FEATURE_FLOOR` sabitleri türetilmiş olur — şu an hepsi elle konmuş.

---

## 4. Sentetik üreteç senaryoları pencerenin başına sıkıştırıyor

**Ne:** Olay günleri `E0+2 … E0+22`, pencere uzunluğundan bağımsız 21 günlük sabit bant. 60 günlük
pencerede senaryolar ilk %38'de kalıyor; zamansal bölme gerektiren ölçümler orada yanıltıcı
(Faz C-2a'da 14 günlük ufuk bu yüzden ölçülemedi).

**Durum:** Düzeltilmedi ama **uyarılıyor** — `senaryo_kapsamasi()` oranı ölçüyor ve %75'in altında
`build()` uyarı basıyor. Testle bağlı.

**Neden ertelendi:** Senaryo zamanlamasını değiştirmek üretecin 13 senaryo tanımını yeniden
düzenlemek demek ve **her sentetik kapsama rakamı ona dayanıyor**. Yalnız 40+ günlük pencerelerde
ısıran bir kusur için her ölçümün dayandığı yapıyı riske atmak doğru takas değil. CERT ölçümleri
etkilenmiyor (orada senaryolar gerçek cevap anahtarından gelir).

---

## 5. ADWIN'in girdisi kavramsal olarak yanlış olabilir

**Ne:** ADWIN'e **risk skorunun kendisi** besleniyor (`pipeline.py`: `a.ekle(results[sid].raw)`) ve
sürüklenme bulunca kişisel taban sıfırlanıyor. Yani insider'ın tırmanışı "yeni normal" ilan
ediliyor olabilir.

**Ölçüm (`docs/faz-e-sonuclar.md`):** Hipotez **doğrulanamadı** — toplam kesme 4, ön kayıtlı eşik
10. Ama yön çok net: insider'ların %27'si kesme aldı, temiz kullanıcıların %0,3'ü.

**Yapılacak:** Sürüklenme, tespit çıktısından değil **ham davranış sinyallerinden** izlenmeli
(`bytes_out`, `logon_count`, `distinct_apps_n`). O zaman "kullanıcı yeni role geçti" (meşru) ile
"risk skoru tırmanıyor" (tespitin kendisi) ayrışır. `profile.py` donmuş; kendi ön kaydını
gerektirir.
