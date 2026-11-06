# Graf çarpanı kapıyı mı açıyor? — ön kayıt

**Yazıldı: 6 Kasım 2026, koşudan ÖNCE.** Dayanak: `docs/kapi-tanisi-sonuclar.md`.

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Soru

İki tamamen farklı mekanizma r4.2'de **neredeyse birebir aynı** sonucu veriyor:

| Varyant | Kapsama | Vaka |
|---|---|---|
| `tam` | 22/34 | 1.939 |
| `v4_graf_carpan` (30 Ekim) | **27/34** | **2.069** |
| `v12_dogrulama_kapali` (6 Kasım) | **27/34** | **2.068** |

Bir vaka fark. Açıklama `corroborated()` içinde olabilir:

```python
or any(v > 1 for v in r.multipliers.values())   # graf çarpanı buraya giriyor
```

**Hipotez: grafın r4.2'deki +5'i, sıralamayı "germesinden" değil, kanıt doğrulama KAPISINI
AÇMASINDAN geliyor.**

## Test — tek koşuda kesin cevap

Graf çarpanı **ve** kapı **birlikte** açılır:

| Sonuç | Anlamı |
|---|---|
| **27/34** (aynı kalır) | İkisi de **aynı 5** insider'ı kurtarıyor → **hipotez DOĞRU**: grafın tek işlevi kapıyı açmak |
| **27'nin üstü** | **Farklı** insider'ları kurtarıyorlar → **hipotez YANLIŞ**: grafın bağımsız bir mekanizması var |
| 27'nin altı | Beklenmedik etkileşim — ayrıca incelenir |

Bu, "etki toplanıyor mu" testidir ve cevabı ikiye ayırır. Ara yorum yok.

| | |
|---|---|
| Veri | CERT r4.2, 90 gün, bütçe 30 (önceki iki koşuyla aynı) |
| Varyant | `v12_graf_arti_kapi` = `graf_enabled=True, graf_agirligi=0.5, kuyruk_dogrulama=False` |
| Referans | `tam` (aynı koşuda yeniden üretilir) |
| Donmuş dosya | **hiçbiri** — iki bayrak da mevcut |

## Başarı eşikleri — koşudan ÖNCE

1. **Referans aynı:** `tam` yine 22/34, 1.939 vaka. Değilse diğerleri okunmaz.
2. **Kurtarılan insider KİMLİĞİ karşılaştırılır**, yalnız sayısı değil. İki mekanizma aynı sayıyı
   farklı kişilerle verebilir; o hâlde "aynı 5" demek yanlış olur. Beş senaryo adı tek tek
   eşleştirilecek.
3. **Karar kuralı:** kapsama 27/34 **ve** kurtarılan senaryo kümesi `v12_dogrulama_kapali` ile
   **aynı** ise hipotez doğrulanır. Küme farklıysa — sayı aynı olsa bile — hipotez **doğrulanmaz**.

3 numara özellikle yazılıyor: sayıya bakıp "aynı" demek, bu projede daha önce yapılan hatanın
(etiketin adına bakıp teşhis koymak) aynısı olur.

## Beklentiler — karamsar

1. **Hipotez doğrulanacak** (aynı 5, 27/34). Kod yolu bunu güçlü biçimde ima ediyor.
2. **Ama vaka sayısı ikisinden de yüksek çıkacak**: graf çarpanı skoru da değiştiriyor, yani kapı
   açıkken sıralama da kayıyor. 2.068–2.069'un üstü beklenir ve bu hipotezi çürütmez — kapsama
   belirleyici, vaka sayısı değil.
3. **Doğrulansa bile graf "işe yaramaz" DEMEK DEĞİL.** Anlamı şu: grafın r4.2'deki değeri
   *ilişkisel zekâdan* değil, *bir eşik kapısını açmasından* geliyor. Aynı etki kapıyı doğrudan
   gevşeterek de elde ediliyor ve bu daha ucuz, daha anlaşılır.
4. **Varsayılan yine değişmeyecek.** Bu bir teşhis koşusu; ikisi de r4.2'de (ayar verisi) ölçülüyor
   ve graf r6.2'de zaten çökmüştü.

---

# Sapmalar — ölçümden SONRA eklendi (6 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Sonuçlar: `docs/graf-kapi-sonuclar.md`.

## Sapma yok — hipotez karar kuralına göre DOĞRULANDI

Ölçüt 3 iki şart istiyordu: kapsama 27/34 **ve** kurtarılan küme `v12_dogrulama_kapali` ile aynı.
İkisi de sağlandı. Üç varyant da birebir aynı beş senaryoyu kurtardı, hiçbirinde kayıp yok,
birleşim = kesişim = 5.

## Karamsar beklenti 2 yanlış çıktı

"Graf+kapı vaka sayısı ikisinden de yüksek çıkacak, çünkü graf skoru da değiştiriyor" yazmıştım.
Çıkmadı: 2.069 — grafın tek başına verdiğiyle **aynı**. Kapı zaten açıkken grafın skor etkisi
kuyruk bileşimini değiştirmiyor.

## Ön kayıtta öngörülmeyen: İKİ yerleşik açıklama birden düşüyor

Ön kayıt yalnız "grafın +5'i nereden geliyor" sorusunu soruyordu. Sonuç iki kaydı birden
değiştiriyor:

**1. "Çarpan gerer, toplamsal sıkıştırır."** Bu bir sıralama açıklamasıydı. Gerçek sebep:
`contrib["GRAF-TOPLAMSAL"]` `multipliers`'a **hiç girmiyor**, `corroborated()` ise yalnız
`multipliers`'a bakıyor. Toplamsal terim kapıyı **açamaz**. Germe/sıkıştırma ile ilgisi yok.

**2. "Graf r4.2'ye aşırı uydu" (`docs/r62-graf-tek-basina.md`).** Sonuç hâlâ doğru ama teşhis
değişiyor: graf r4.2'de bir kapı açıyordu, r6.2'de o kapı zaten engel değildi. Bu bir **çıkarım**,
r6.2'de ölçülmedi — doğrulaması için r6.2'de kapı varyantı koşulmalı ve r6.2 yanmış veri olduğu
için o koşu hiçbir şey harcamıyor.

## Yapılmayanlar

- **Varsayılan değişmedi.** Mekanizma anlaşıldı ama r6.2'de başarısız olan şeyin tam da "kapıyı
  açmak" olduğu ölçüldü; kapıyı doğrudan gevşetmenin orada farklı davranacağına inanmak için
  sebep yok.
- **`corroborated()` değiştirilmedi.** Doğru düzeltme kapıyı kaldırmak değil, "tek güçlü sinyal"
  koşullarını tek-günlük-tek-kural desenlerini kapsayacak şekilde genişletmek. Ayrı tasarım,
  ayrı ön kayıt.
