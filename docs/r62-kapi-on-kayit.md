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

---

# Sapmalar — koşum DURDURULDU (7 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**.

## Koşu tamamlanmadan durduruldu, çünkü soru r6.2'de SORULAMIYOR

Referans varyantı (`tam`) bitti ve ölçüt 1'i okurken daha temel bir şey görüldü:

```
CERT-r6.2-S2-CMP2946   KALDI (tetiklenmedi) [kısmi pencere]
CERT-r6.2-S4-CDE1846   GEÇTİ
```

90 günlük pencerede 2 senaryo var ve kaçan tek senaryo **`KALDI (tetiklenmedi)`** — yani beklenen
kural **hiç tetiklenmedi**.

**Kanıt doğrulama kapısı yalnız `BÜTÇE DIŞI` biçimine etki eder:** "tespit tetiklendi ama kuyruğa
girmedi". Hiç tetiklenmemiş bir tespit için kapının yapacağı bir şey yoktur — **var olmayan bir
uyarıyı kuyruğa alamazsınız.**

Dolayısıyla bu pencere, kapı hipotezini ne doğrular ne çürütür. Pencereyi büyütmek de çözmez:

## Kayıtlı r6.2 kör koşusunda hiç `BÜTÇE DIŞI` YOK

`docs/r62-graf-tek-basina.md`, 360 günlük dört pencere:

```
S1 ✔   S3 ✔   S4 ✔   S5 ✘   S2 ölçülemedi
```

Tek kaçan S5 ve sebebi **ölçülmüş durumda**: `UEBA-0003` r6.2'de yapısal olarak ölü — web
`bytes_out` her olayda sıfır, çünkü `cert.py` `http.csv`'den `content` okumuyor (4.2 etik sınır;
`docs/faz-a3-sonuclar.md`).

> **r6.2'nin kaçırdığı insider, kapının YUKARI tarafında kaçıyor.** Tespit üretilmiyor; kapı
> üretilmiş tespitleri filtreliyor. İkisi farklı katman.

## Sonuç: çıkarım DOĞRULANDI, ama koşuyla değil kayıtla

Sınanmak istenen çıkarım şuydu: *"graf r6.2'de +0 verdi çünkü orada açacak kapı yoktu."*

Kayıtlı ölçümler bunu daha güçlü biçimde söylüyor: r6.2'de **açılacak kapı yok, çünkü kapıya gelen
tespit yok.** Ne graf, ne kapı, ne sıralama değişikliği, ne bütçe — tespit üretilmediği sürece
hiçbiri S5'e ulaşamaz.

**Bu bir ölçüm değil, kayıtlı ölçümlerden çıkarılan bir sonuç.** Ama argüman neredeyse totolojik:
var olmayan bir tespit kuyruğa alınamaz. Yeni bir koşu bunu değiştirmezdi; 4,5 saatlik koşu **+0**
verip aynı yere çıkacaktı — ve "+0" rakamı yanıltıcı olurdu, çünkü "kapı işe yaramadı" gibi
okunurdu. Oysa doğru cümle: **kapı bu veride sınanamaz.**

## Önemli sonuç: kapı düzeltmesi r6.2 ile DOĞRULANAMAZ

Projenin kuralı bir bileşenin varsayılan açılması için **iki farklı veride** değer üretmesini
istiyor. Kapı için:

| Veri | Kapıya bağlı kaçan insider | Kapı sınanabilir mi |
|---|---|---|
| r4.2 | **5** (`BÜTÇE DIŞI`) | ✅ ölçüldü, +5 |
| r6.2 | **0** | ❌ sınanamaz |
| r1 | bilinmiyor | **tek kalan ihtimal** |

Yani kapı düzeltmesinin ikinci veri setini **yalnız r1 verebilir** — ve ancak r1'de
`BÜTÇE DIŞI` biçiminde kaçan insider varsa. Bu, r1'i harcama kararını doğrudan etkiliyor ve
`docs/acik-bulgular.md`'ye işlendi.

## Harcanan

Referans varyantı 87 dakika hesap tüketti ve sonucu kayda geçti (`tam`: 1/2 kapsama, 2.176 vaka).
İkinci ve üçüncü varyant koşmadı. **Hiçbir kör veri harcanmadı** — r6.2 zaten yanmış durumdaydı.
