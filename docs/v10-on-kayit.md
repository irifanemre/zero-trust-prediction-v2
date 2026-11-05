# v10 ön kaydı — `UEBA-0023`'ün eşiği ve varsayılan kaynak listesi

**Yazıldı: 5 Kasım 2026, kod değişikliğinden ÖNCE.** Dayanak: `docs/faz-b-sonuclar.md`.

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## İki iş, tek sürüm — çünkü ayrılamazlar

Faz B iki şeyi ortaya çıkardı ve ikisi birbirine bağlı: kural varsayılan yapılandırmada devre
dışıydı (dolayısıyla eşiği hiç sınanmadı), eşiği etkinleştirince de çok gevşek olduğu görüldü.
Biri olmadan diğeri ölçülemez.

| | Ne | Dosya | Donmuş |
|---|---|---|---|
| A | Varsayılan `available_sources`'a `email` | `config.py` | **evet** |
| B | `EPOSTA_TABAN` türetme kuralıyla yeniden hesaplanır | `profile.py` | **evet** |

İkisi de donmuş → **dondurma v10**.

## A — varsayılan kaynak listesi

```
şu an : ('ad', 'hr', 'proxy', 'edr', 'vpn', 'file_server', 'dlp')
                                                        ↑ email YOK
```

`UEBA-0023`, katalogdaki 25 kuraldan varsayılan yapılandırmada devre dışı kalan **tek** kural.
Listede `dlp` ve `edr` gibi görece ileri kaynaklar varken `email`'in olmaması tutarsız.

`available_sources` bir **dağıtım gerçeğidir**: e-posta ağ geçidi olmayan kurumda `UEBA-0023`
gerçekten çalışmamalı ve çalışmayacak — her kiracı kendi listesini verir, varsayılan yalnız
şablondur. Değişen şey şablonun tutarlılığı.

## B — `EPOSTA_TABAN`: türetme kuralı, tahmin değil

`robust_z(x, med, mad, floor) = 0.6745 · (x − med) / max(mad, floor)` ve eşik `z > 3.5`.
Yani tetikleme koşulu:

```
x − med > 5,19 × max(mad, EPOSTA_TABAN)
```

`EPOSTA_TABAN`'ın rolü: kullanıcının kendi MAD'i **dejenere** olduğunda (sıfır ya da anlamsız küçük)
devreye giren **asgari ölçek**. 50 KB iken koşul `x > med + 259 KB`'a iniyor — tek bir sıradan
eke eşdeğer. 80 kullanıcının 51'inde tetiklemesinin sebebi bu.

### Sabitin tarihi: iki kez de tahminle konuldu

| Sürüm | Değer | Nereden geldi |
|---|---|---|
| v8 ilk | 5 MB | `FEATURE_FLOOR["bytes_out"]`'tan **kopyalandı** — farklı ölçek |
| v8 düzeltme | 50 KB | "e-posta web'den küçüktür" diye **100 kat** düşürüldü, doğrulanmadı |
| v10 | ? | **türetme kuralıyla** hesaplanacak |

### Türetme kuralı (ölçümden önce yazılıyor)

> `EPOSTA_TABAN` = nüfus genelinde, **kullanıcı başına günlük dış e-posta hacmi MAD'inin
> medyanı**; en yakın yuvarlak değere yuvarlanır.

Gerekçe: taban, kullanıcının kendi MAD'i yoksa onun yerine geçecek. Yerine geçtiği şeyin
**tipik büyüklüğünde** olmalı — daha küçüğü sahte alarm, daha büyüğü sağırlık üretir.

**Senaryo günleri hesaba KATILMAZ.** S11'in enjekte ettiği 12–24 MB'lık günler MAD'i şişirir ve
eşik saldırıya göre ayarlanmış olur — döngüsel. Yalnız taban günleri kullanılır.

### Kuralın kendisi doğrulanacak: bilinen-iyi sabitle sınama

Aynı kural `bytes_out` için uygulanacak. `FEATURE_FLOOR["bytes_out"] = 5e6` **çalışan** bir
sabittir (`UEBA-0003` aynı z eşiğiyle makul oranda tetikliyor). Kural o sabiti yaklaşık olarak
yeniden üretirse kural sağlamdır; üretmezse **kural yanlıştır** ve `EPOSTA_TABAN` değiştirilmez.

> Bu, eşiği sonuca göre ayarlamanın önüne geçen tek koruma: türetme kuralı, sonucunu zaten
> bildiğimiz bir yerde sınanıyor.

### z eşiği 3,5'te KALIR

`UEBA-0003` de `veri_hacmi_z > 3.5` kullanıyor; 3,5 projenin standart robust-z eşiği. Yanlış olan
sabit **taban**, z değil. z'yi oynatmak, yanlış yerdeki sorunu doğru yerde düzeltmeye çalışmaktır.

## Başarı eşikleri — ölçümden ÖNCE

1. **Türetme kuralı `bytes_out` için 5 MB'ı ±3 kat içinde yeniden üretir.** Üretmezse kural
   reddedilir, `EPOSTA_TABAN` değişmez, bulgu rapor edilir.
2. **`UEBA-0023` günlük uyarı ≤ 2** (13.6 gölge mod mezuniyet şartı; şu an ~6).
3. **S11 hâlâ tetiklenir** (şu an pencerede 4 tetiklenme).
4. **Negatif kontrol temiz** (şu an 1 tetiklenme — kirli).
5. **Kullanıcı yaygınlığı belirgin düşer** (şu an 51/80).
6. **Başka hiçbir kural etkilenmez:** `UEBA-0022`/`UEBA-0024` tetiklenmeleri ve kuyruk kapsaması
   (7/8) aynı kalır. `EPOSTA_TABAN` yalnız `eposta_dis_z`'ye giriyor, dolayısıyla değişirse
   **başka bir şeyi yanlışlıkla bağlamışız** demektir.

2, 3 ve 4 birlikte geçmeli: biri gürültüyü, biri duyarlılığı, biri temizliği sınıyor. Yalnız 2
geçerse kural sağır olmuş olabilir.

## Beklentiler — karamsar

1. **Türetme kuralı `bytes_out` sınamasını geçmeyebilir.** `bytes_out` günlük TOPLAM trafiktir
   (medyan ~120 MB), e-posta ise seyrek ve küçük; iki dağılımın MAD/medyan oranı farklı olabilir.
   Geçmezse ölçüt 1 gereği durulur — eşik tahminle değiştirilmez.
2. **≤ 2 uyarı/gün tutsa bile kural yayına alınmayacak.** 13.6 üç şart istiyor: precision ≥ %25
   **ve** ≤ 2 uyarı/gün **ve** ≥ 14 gün gölgede. Precision ancak etiketle ölçülür, sentetik
   senaryoda "precision" cevap anahtarından gelir ve zayıf kanıttır. **Kural gölge modda kalır.**
3. **CERT sayıları değişmeyebilir ya da değişebilir — ikisi de sonuç.** `email` kaynağı CERT kör
   koşularında zaten vardı, yani A maddesi CERT'i etkilemez. Ama `EPOSTA_TABAN` değişirse r4.2/r6.2'de
   `UEBA-0023` davranışı değişir. **Bu fazda CERT'te yeniden koşu yapılmayacak**: r4.2 ayar
   verisidir, r5.2 ve r6.2 yanmıştır, r1 saklı. Etkisi ancak ileride ölçülebilir ve bu **kabul
   edilen bir eksikliktir**, gizlenmiyor.
4. **En olası sessiz hata:** taban yükseltilince kural *hiç* tetiklenmez ve bu "düzeldi" gibi
   görünür. Ölçüt 3 (S11 hâlâ tetiklenmeli) tam bunun için var.

---

# Sapmalar — ölçümden SONRA eklendi (5 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Sonuçlar: `docs/v10-sonuclar.md`.

## Sapma 1 — B maddesi YAPILMADI: türetme kuralı kendi sınamasını geçemedi

Kural `bytes_out` için 50 MB üretti; bilinen-iyi sabit 5 MB, yani ±3 kat sınırının **dışında**
(10×). Ölçüt 1 "üretmezse kural yanlıştır ve `EPOSTA_TABAN` değiştirilmez" diyordu; değiştirilmedi.

Bu bir sapma değil, **ön kaydın tasarlandığı gibi çalışması**. Doğrulama sınaması tam bu amaçla
yazılmıştı: eşiği gözle ayarlamanın önüne geçmek. Sınama olmasaydı 10 kat yanlış bir kural
"türetildi" diye uygulanacaktı.

Başarısızlığın öğrettiği yapısal bilgi ön kayıt yazılırken bilinmiyordu: taban `max(mad, floor)`
içinde durduğu için **yalnız kendi MAD'i tabandan küçük olan kullanıcılarda bağlar**. Dolayısıyla
referansı "tipik MAD" olamaz — tipik MAD'e eşit bir taban nüfusun yarısında bağlayıcı olur.
Referans, MAD dağılımının **alt ucu** olmalıydı.

## Sapma 2 — ön kayıt dışı keşif: 13 sabite karşı aday kural taraması

Ön kayıt tek referans noktası (`bytes_out`) öngörmüştü. Kural kalınca `FEATURE_FLOOR`'daki **13**
sabitin hepsine karşı yedi aday kural denendi. "En küçük sıfır olmayan MAD" 9/10 sabiti ±3 kat
içinde yeniden üretiyor (medyan oran 1,00) ve yukarıdaki yapısal gerekçeyle tutarlı.

**Bu kural UYGULANMADI** ve uygulanmaması bilinçli: yedi aday arasından **sonuçlar görüldükten
sonra** seçildi, yani doğrulama kümesi üzerinde model seçimi yapıldı. On nokta ve yedi adayla bir
uyum bulmak güçlü kanıt değil. Hipotez olarak kayda geçiyor; sınanması ayrı bir ön kayıtla,
tercihen CERT'in gerçek dağılımları üzerinde yapılacak.

## Sapma 3 — ölçüt 2–5 değerlendirilmedi

Eşik değişmediği için ölçülecek bir şey kalmadı. Ölçütler "eşik değişirse şunlar sağlanmalı"
biçiminde yazılmıştı; ön koşul gerçekleşmedi. Düşen ölçütler kayda geçiyor ki ileride eşik
türetildiğinde aynı eşiklerle sınanabilsin.

## Sapma 4 — eşik sorusunun istatistiksel olmadığı anlaşıldı

Ön kayıt sabiti veriden türetmeyi planlıyordu. Ölçüm bunun — en azından tek bir sentetik nüfustan
ve post-hoc seçilmemiş bir kuralla — mümkün olmadığını gösterdi. Soru şuna indi:

> Bir günde, normalinin ne kadar üstüne çıkan dış e-posta hacmi bir analistin zamanına değer?

Bu bir **operasyonel karar**, türetilecek bir sayı değil. Hedef ortamın e-posta ağ geçidinden
alınacak bir aylık hacim dağılımı doğru girdidir. O zamana kadar kural gölge modda kalıyor:
risk kontrol altında, sorun çözülmemiş — ikisi karıştırılmamalı.
