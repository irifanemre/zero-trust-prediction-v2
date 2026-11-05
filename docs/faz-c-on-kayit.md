# Faz C ön kaydı — çok ufuklu öngörü: ÖNCE ölçüm, sonra model

**Yazıldı: 5 Kasım 2026, kod değişikliğinden ÖNCE.**

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Brief'in istediği ve neden doğrudan yapılmıyor

Brief "çok ufuklu öngörü (1/3/7/14 gün)" diyor. Doğrudan okunuşu: dört ufuk için dört model başı
eklemek. Bu faz **onu doğrudan yapmıyor**, çünkü bu projede aynı hata beş kez tekrarlandı:

> Bir bileşen eklendi, varsayılan kapalı kondu, ölçüldü, eşiğini geçemedi. Graf, ADWIN, denetimsiz
> anomali kanalı, geri bildirim döngüsü, saldırı yolu tahmini, öğrenen graf — altısı da.

Dolayısıyla sıra tersine çevriliyor: **önce dört ufkun ayrı modele ihtiyaç duyduğu gösterilecek,
sonra model yazılacak.** Gerekmediği gösterilirse model yazılmayacak ve bu bir başarısızlık
sayılmayacak.

## Kritik gözlem: ölçüm altyapısı ZATEN var

`metrics.py::outcomes(rows, horizon_days=7)` ufku **parametre olarak alıyor**. Yani mevcut tek
olasılık (`p7`), yeni bir satır kod yazmadan 1/3/7/14 gün ufuklarına karşı değerlendirilebilir.

Sorulacak soru şu:

> Mevcut `p7`, farklı ufuklarda **farklı** ayırt etme gücü gösteriyor mu?

- **Göstermiyorsa** (AUC ufka göre neredeyse sabit): tek olasılık yeterli, ufuk ailesi yalnız
  rapor etiketi olur. Dört model başı **yazılmayacak**.
- **Gösteriyorsa** (ör. 1 günde AUC yüksek, 14 günde taban seviyesinde): ufuk başına ayrı sinyal
  gerçekten farklı bilgi taşıyor, C-2 gerekçelidir.

## Faz C-1 — ölçüm (bu faz)

| # | Ne | Dosya | Donmuş |
|---|---|---|---|
| 1 | Mevcut `p7` ve `p7_sezgisel`, h ∈ {1, 3, 7, 14} için değerlendirilir | `scripts/ufuk_olcumu.py` (yeni) | hayır |
| 2 | Ufuk başına: AUC, Brier, beceri skoru, taban oranı, n | aynı | hayır |

**Hiçbir donmuş dosya değişmeyecek. Hiçbir model eklenmeyecek. Dondurma sürümü değişmeyecek.**

### Nasıl ölçülecek

Aynı koşunun tahmin satırları, dört ufka karşı ayrı ayrı `outcomes()`'tan geçirilir ve her biri
için `calibration_report` alınır. Tek koşu, dört değerlendirme — yani ufuklar arası fark
**modelden değil yalnız hedef tanımından** gelir. Karşılaştırma adil olur.

Taban oranı her ufukta farklı olacak (uzun ufukta daha çok pozitif), bu yüzden **Brier doğrudan
karşılaştırılamaz**; karşılaştırılacak ölçütler **AUC** (taban oranından bağımsız sıralama gücü)
ve **beceri skoru** (tabana göre normalize).

## Başarı eşikleri — ölçümden ÖNCE

C-1 bir **karar ölçümü**, bir iyileştirme değil. Dolayısıyla "geçti/kaldı" yerine karar kuralı:

1. **C-2 yazılır** ancak ufuklar arasında AUC farkı **≥ 0,10** ise (en iyi ufuk − en kötü ufuk).
   O fark, ufukların gerçekten farklı bilgi taşıdığının eşiğidir.
2. **C-2 yazılmaz** fark < 0,10 ise. Bu durumda rapor "tek olasılık dört ufku da aynı güçle
   sıralıyor" der ve ufuk ailesi **yalnız raporlama etiketi** olarak kalır.
3. Her hâlde: **ölçüm belgelenir**, çünkü "7 gün" ufkunun neden 7 olduğu bu projede hiç
   sorgulanmamıştı.

0,10 eşiği keyfi değil: `docs/r62-v4-olcumu.md`'de graf çarpanının r4.2'de ürettiği recall@10
farkı 0,206'ydı ve o "belirgin" sayıldı; yarısı, anlamlı saymak için makul bir alt sınır.

## Beklentiler — karamsar

1. **Fark 0,10'u geçmeyecek.** Gerekçe: `p7`'nin girdileri (risk EWMA'ları, eğim, ayrılık
   bildirimi, hacim trendi) hepsi **yavaş** değişen sinyaller. Yavaş sinyal, 1 günle 14 günü
   ayırt edemez. Yani ufuk ailesi muhtemelen aynı sıralamayı dört kez verecek.
2. Eğer fark çıkarsa, en olası yön **kısa ufukta daha iyi**: risk EWMA'sı dünün olayına duyarlı,
   iki hafta sonrasına değil.
3. **Uzun ufukta taban oranı yükselir**, yani Brier kendiliğinden "iyileşir" gibi görünebilir.
   Bu bir yanılsamadır; o yüzden beceri skoru ve AUC'ye bakılacak. Raporda bu tuzak açıkça
   yazılacak, yoksa "14 günlük model daha iyi" diye okunur.
4. **Sentetik veride ölçülecek.** CERT'te yeniden koşu yok (r4.2 ayar verisi, r5.2/r6.2 yanmış,
   r1 saklı). Yani sonuç sentetik senaryo dağılımına bağlı ve **genellenemez** — tam da graf
   çarpanının r4.2'den r6.2'ye taşınmadığı gibi. Bu kabul edilen bir sınır.

## C-2 (yalnız karar kuralı 1 sağlanırsa)

Ufuk başına ayrı sezgisel/lojistik baş, `tahmin_{h}g_olasilik` sinyalleri ve `PRED-*` kurallarının
ufka duyarlı hâle getirilmesi. **Bu fazda tasarlanmayacak** — gerekmediği çıkarsa boşa tasarım
olur.

---

# Sapmalar — ölçümden SONRA eklendi (5 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Sonuçlar: `docs/faz-c1-sonuclar.md`.

## Sapma 1 — karamsar beklenti 1 YANLIŞ çıktı

"Fark 0,10'u geçmeyecek" yazmıştım. Dört tohumda da geçti (0,135–0,176). Gerekçem ("`p7`'nin
girdileri yavaş değişen sinyaller, 1 günle 14 günü ayırt edemez") yanlıştı — ama yanlışlığın
sebebi ilginç: ayırt eden şey model değil, **ufukların kendi öngörülebilirliği**.

## Sapma 2 — KARAR KURALI YANLIŞ ŞEYİ ÖLÇÜYORMUŞ

Ön kayıttaki kural: *"ufuklar arasında AUC farkı ≥ 0,10 ise C-2 yazılır."*

Ölçümden sonra fark edildi ki bu test, sorulan soruyu cevaplamıyor. Dört ufukta **skorlar birebir
aynı**; değişen yalnız etiketler. Dolayısıyla AUC farkı şunu ölçüyor: *1 günlük sonuçlar 14 günlük
sonuçlardan daha öngörülebilir.* Şunu ölçmüyor: *model ufka göre farklı parametre istiyor.*

Birincisi bir **bilgi sınırıdır** (doğanın gerçeği), ikincisi bir **tasarım eksikliği**. Ufuk başına
model yazmak birinciyi değiştirmez.

Doğru test şu olurdu: *ufuk h için eğitilmiş baş, h ufkunda tek `p7`'yi geçiyor mu?* — ve o test
C-2'nin kendisini gerektiriyor, C-1'de cevaplanamaz. Yani C-1 bu soruyu **cevaplayamaz biçimde**
tasarlanmış.

Kural tetiklendi, C-2 yazılacak, ama **gerekçesi değişti** ve aşağıdaki bulguya dayanıyor.

## Sapma 3 — ön kayıtta öngörülmeyen asıl bulgu: olasılık kalibre değil

Beceri skoru dört ufukta ve dört tohumda da **negatif** (−0,30 … −1,05): sabit taban oranını
tahmin etmek modelin olasılığından daha iyi. Buna karşılık sıralama gücü yüksek (AUC 0,90,
AUPRC tabanın 13 katı).

> `p7` iyi bir sıralayıcı, kötü bir olasılık.

Sebebi kodda: `sigmoid(-3.5 + Σcomp)` — tek elle konulmuş kesme noktası, tek ufka göre. Taban oranı
ufka göre iki kat değişiyor (0,031 → 0,063); aynı kesme noktası dördüne doğru olasılık veremez.

Bu, ön kayıtta hiç öngörülmemişti. C-2'nin kapsamını **daralttı**: ufuk başına ayrı MODEL değil,
tek sıralayıcı + ufuk başına KALİBRASYON. Araç zaten var ve kullanılmıyor:
`VennAbersKalibrator` (`gnn/conformal_eval.py`).

## Sapma 4 — tohum taraması ön kayıtta yoktu

Ön kayıt tek koşu öngörmüştü. Fark eşiğe yakın çıktığı için dört tohumla tekrarlandı. İki bulgu da
dayanıklı. Bu bir kapsam genişlemesi ama **ölçüt gevşetmesi değil** — tersine, sıkılaştırma.
