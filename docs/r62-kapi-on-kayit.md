# r6.2'de kanıt kapısı — ön kayıt

**Yazıldı: 6 Kasım 2026, koşudan ÖNCE.** Dayanak: `docs/graf-kapi-sonuclar.md`.

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Soru

r4.2'de ölçüldü: graf çarpanı ve kanıt doğrulama kapısı **birebir aynı 5 insider'ı** kurtarıyor,
etki toplanmıyor, mekanizma tek satır (`any(v > 1 for v in r.multipliers.values())`).

Buradan bir **çıkarım** yapıldı ama ölçülmedi: *graf r6.2'de +0 verdi çünkü orada açacak kapı
yoktu.* Bu koşu o çıkarımı sınıyor.

> **r6.2'de kanıt kapısını kapatmak insider kazandırıyor mu?**

| Sonuç | Anlamı |
|---|---|
| **+0** (graf gibi) | Mekanizma aynı → r6.2'nin engeli **kapı değil**, çıkarım doğrulanır |
| **+1 ya da fazlası** | Kapı, grafın yapamadığını yapıyor → graf ≠ kapı, çıkarım **çürür** |

İkisi de bilgi. Çürürse, r4.2'deki eşdeğerliğin veri setine özgü olduğunu öğreniriz.

## Neden bu koşu bir şey HARCAMIYOR

r6.2 **yanmış veri**: 29 Ekim'de bir kez kör koşuldu ve o gün yandı. Sonrasında zaten birkaç kez
ölçüm için kullanıldı (`docs/r62-v4-olcumu.md`, `docs/r62-graf-tek-basina.md`). Yeni bir kör koşu
değil, yeni bir bilgi yakmıyor.

**Kör veri yalnız r1 ve ona dokunulmuyor.**

## Koşu

| | |
|---|---|
| Veri | CERT r6.2 (logon aralığı 2010-01-02 → 2011-06-01) |
| Pencere | 90 gün, ısınma 21, bütçe 30 — **r4.2 koşusuyla aynı parametreler** |
| Bitiş | 2011-06-01 (verinin son günü) |
| Varyantlar | `tam` · `v4_graf_carpan` · `v12_dogrulama_kapali` |
| Donmuş dosya | **hiçbiri** |

Graf varyantı da koşuluyor ki karşılaştırma **aynı koşu içinde** yapılsın. Daha önceki r6.2 graf
ölçümü farklı bir araçla (4 pencere × 360 gün, `kor_kosu_r52.py`) yapılmıştı; doğrudan
kıyaslanamaz.

## Başarı eşikleri — koşudan ÖNCE

1. **`tam` referansı anlamlı olmalı:** r6.2'de 90 günlük pencerede en az 1 ölçülebilir senaryo
   bulunmalı. Bulunmazsa (senaryolar pencere dışında kalırsa) **hiçbir şey yorumlanmaz** ve pencere
   kaydırılır — sonuç değil, ölçülebilirlik sorunu olur.
2. **Karar, kurtarılan insider KİMLİĞİ üzerinden:** r4.2'de olduğu gibi sayıya değil kümeye
   bakılacak.
3. **Graf ve kapı r6.2'de de aynı kümeyi mi veriyor?** r4.2'de veriyordu. Burada da verirse
   eşdeğerlik veri setinden bağımsızdır; vermezse r4.2'ye özgüdür.
4. **Bedel ölçülür:** vaka sayısı ve precision. r4.2'de kapı +%7 vakaya mal olmuştu ve precision
   değişmemişti; r6.2'de farklı olabilir (taban oranı 55 kat düşük).

## Beklentiler — karamsar

1. **+0 bekliyorum** (çıkarım doğrulanır). Gerekçe: graf r6.2'de +0 verdi ve mekanizmanın aynı
   olduğu r4.2'de ölçüldü.
2. **Ama vaka sayısı r4.2'dekinden çok daha fazla artabilir.** r6.2'de 2.801 kullanıcı ve insider
   yoğunluğu binde 0,36 — tek sinyalli vakalar çok daha kalabalık. Kapı burada gerçekten yanlış
   alarmı kesiyor olabilir ve kapatmanın bedeli r4.2'dekinin katı çıkabilir.
3. **Ölçüt 1 en olası başarısızlık.** r6.2'nin senaryoları 360 güne yayılı; 90 günlük tek pencere
   hiç senaryo yakalamayabilir. O hâlde "ölçülemedi" raporlanacak ve pencere **bir kez**
   kaydırılacak — sonuç görülüp beğenilmediği için değil, ölçülebilirlik için. Kaydırma kararı
   senaryo sayısına bakılarak verilecek, sonuca bakılarak değil.
4. **Hangi sonuç çıkarsa çıksın varsayılan değişmeyecek.** Bu bir teşhis koşusu; iki veri de kör
   değil.
