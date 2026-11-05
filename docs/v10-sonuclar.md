# v10 — kaynak listesi tamamlandı, eşik DEĞİŞMEDİ: sonuçlar

**Ölçüm: 5 Kasım 2026.** Ön kayıt: `docs/v10-on-kayit.md` (koddan önce yazıldı).
Dondurma `kurallar-donduruldu-v10` → `donmuş durumla aynı`. 405 test geçiyor.

> **Planlanan iki işin biri yapıldı, biri YAPILMADI.** Türetme kuralı, ön kayıtta yazdığım kendi
> doğrulama sınamasını geçemedi; ölçüt 1 gereği `EPOSTA_TABAN` değiştirilmedi.

## Ön kayıtlı ölçütler

| # | Ölçüt (ölçümden önce yazıldı) | Sonuç |
|---|---|---|
| 1 | Türetme kuralı `bytes_out` için 5 MB'ı ±3 kat içinde yeniden üretir | **KALDI** — 50 MB, 10× sapma |
| 2 | `UEBA-0023` günlük uyarı ≤ 2 | **değerlendirilmedi** (ölçüt 1 kaldı → eşik değişmedi) |
| 3 | S11 hâlâ tetiklenir | değerlendirilmedi |
| 4 | Negatif kontrol temiz | değerlendirilmedi |
| 5 | Kullanıcı yaygınlığı düşer | değerlendirilmedi |
| 6 | Başka hiçbir kural etkilenmez | **GEÇTİ** |

Ölçüt 1 kaldığı anda 2–5 düşer: eşik değişmediği için ölçülecek bir şey yok. Bu bir başarısızlık
değil, ön kaydın **tasarlandığı gibi** çalışmasıdır.

## A — varsayılan kaynak listesi tamamlandı

```
önce : ('ad', 'hr', 'proxy', 'edr', 'vpn', 'file_server', 'dlp')
sonra: ('ad', 'hr', 'proxy', 'edr', 'vpn', 'file_server', 'dlp', 'email')
```

| | önce | sonra |
|---|---|---|
| Varsayılanda devre dışı kural | `UEBA-0023` ("kaynak yok") | **hiçbiri** |
| Değerlendirilen kural | 24 / 25 | **25 / 25** |

Sözleşme teste bağlandı: `test_v10_varsayilan_hicbir_kurali_devre_disi_birakmaz`. Bir kural
varsayılanda devre dışı kalacaksa bu **bilinçli bir karar** olmalı, sessiz bir eksik olmamalı —
`UEBA-0023`'ün eşiğinin iki kez yanlış teşhis edilmesinin kökü tam buydu.

**Ölçüt 6 geçti:** `UEBA-0022` (12 tetiklenme / 11 kullanıcı), `UEBA-0024` (12 / 9) ve kuyruk
kapsaması (7/8) Faz B ile **birebir aynı**. `EPOSTA_TABAN` yalnız `eposta_dis_z`'ye giriyor;
değişmiş olsaydı başka bir şeyi yanlışlıkla bağlamışız demekti.

## B — eşik DEĞİŞMEDİ, çünkü türetme kuralı kendi sınamasını geçemedi

Ön kayıtta yazılan kural:

> taban = nüfus genelinde, kullanıcı başına günlük değerin MAD'inin **medyanı**

Ve yazılan koruma: *"Aynı kural `bytes_out` için uygulanacak... Kural o sabiti yaklaşık olarak
yeniden üretirse kural sağlamdır; üretmezse kural yanlıştır ve `EPOSTA_TABAN` değiştirilmez."*

Ölçüm (senaryo günleri hariç, 130 (sid, gün) çifti çıkarıldı):

| | değer |
|---|---|
| `bytes_out` günlük medyan | 133.285.752 |
| kullanıcı MAD'lerinin medyanı | 39.513.783 |
| MAD çeyrekleri (p25–p75) | 29.214.618 – 57.489.039 |
| **türetilen taban** | **50.000.000** |
| bilinen-iyi (`FEATURE_FLOOR["bytes_out"]`) | **5.000.000** |
| oran | **10,00×** |

**±3 kat sınırının dışında → kural reddedildi → `EPOSTA_TABAN = 50_000` olduğu gibi kaldı.**

### Kuralın neden yanlış olduğu (başarısızlığın öğrettiği)

`robust_z` tabanı `max(mad, floor)` içinde duruyor. Yani taban **yalnız kendi MAD'i tabandan küçük
olan kullanıcılarda bağlar**; normal MAD'li kullanıcıda hiç devreye girmez. Dolayısıyla tabanın
referansı "tipik MAD" **olamaz** — tipik MAD'e eşit bir taban, nüfusun yarısında bağlayıcı olur ve
rolünü aşar.

Doğru referans, MAD dağılımının **alt ucu** olmalı. Bu, başarısızlığın bize öğrettiği yapısal
bilgidir ve ön kayıt yazılırken bilinmiyordu.

### Keşif niteliğinde: 13 sabite karşı aday kurallar

`FEATURE_FLOOR`'da 13 sabit var ve hepsi aynı rolü oynuyor — yani tek referans noktası yerine bir
**doğrulama kümesi** mevcut. Yedi aday kural, MAD'i hesaplanabilen 8–10 sabite karşı denendi:

| Aday kural | Medyan oran | ±3× içinde | En kötü sapma |
|---|---|---|---|
| medyan MAD *(ön kayıtta yazılan)* | 2,00 | 7/8 | 7,9× |
| p25 MAD | 1,75 | 5/6 | 5,8× |
| p10 MAD | 1,45 | 4/5 | 4,1× |
| p05 MAD | 1,25 | 4/5 | 3,5× |
| **en küçük MAD (>0)** | **1,00** | **9/10** | **3,3×** |
| medyan MAD / 8 | 0,25 | 1/8 | 8,0× |
| medyan değer / 25 | 0,16 | 3/7 | 8,3× |

"En küçük sıfır olmayan MAD" dikkat çekici biçimde iyi uyuyor **ve** yukarıdaki yapısal gerekçeyle
tutarlı: taban, en küçük anlamlı yayılımı korumak için var.

> **Ama bu kural UYGULANMADI.** Yedi aday arasından **sonuçları gördükten sonra** seçildi; yani
> doğrulama kümesi üzerinde model seçimi yapıldı, doğrulama değil. On referans noktası ve yedi
> aday varken bir uyumun bulunması güçlü kanıt değildir. Bu bir **hipotez**, ve ileride **ayrı bir
> ön kayıtla** — tercihen CERT'in gerçek dağılımları üzerinde — sınanması gerekir.

## Şu anki durum: `UEBA-0023` hâlâ çok gevşek ve hâlâ GÖLGEDE

| | değer |
|---|---|
| Tetiklenme | 108 / 12 gün |
| Etkilenen kullanıcı | **51 / 80** (%64) |
| Günlük uyarı | ~6 (bütçe 6) |
| Negatif kontrolde | 1 tetiklenme |
| Yaşam döngüsü | **gölge modda** |

Kural yayında olsaydı bütçenin tamamını tek başına doldurabilirdi. Olmadı: gölge modda, bir kez
bile analiste gitmedi. 13.6 mezuniyet şartı (precision ≥ %25 **ve** ≤ 2 uyarı/gün **ve** ≥ 14 gün)
onu engelliyor ve engellemeye devam ediyor.

**Yani risk kontrol altında, sorun çözülmemiş.** İkisini karıştırmamak gerekiyor.

## Karar kullanıcıda: eşik bir POLİTİKA sorusu

Ölçüm şunu gösterdi: bu sabit veriden türetilemiyor — en azından tek bir sentetik nüfustan ve
post-hoc seçilmemiş bir kuralla türetilemiyor. Cevaplanması gereken soru istatistiksel değil:

> **Bir günde, normalinin ne kadar üstüne çıkan dış e-posta hacmi bir analistin zamanına değer?**

Hedef ortamda USB yasak olduğu için e-posta birincil sızıntı kanalı; yani bu eşik gerçek bir
operasyonel karardır, ayarlanacak bir sayı değil. Seçenekler, tetikleme koşuluyla birlikte
(`x > med + 5,19 × taban`):

| Taban | Tetikleme koşulu | Beklenen etki |
|---|---|---|
| 50 KB *(şu an)* | med + 0,26 MB | %64 kullanıcı — gürültü |
| 1 MB | med + 5,2 MB | orta |
| 5 MB | med + 26 MB | yalnız büyük ek yığınları |

Rakamlar sentetik nüfustan; gerçek kurumda dağılım farklı olacak. **Doğru yol:** hedef ortamın
e-posta ağ geçidinden bir aylık hacim dağılımı alıp tabanı oradan türetmek. O zamana kadar kural
gölge modda kalır ve zarar vermez.

## Ne yapılMADI

- **Eşik değiştirilmedi** (ön kayıt ölçütü 1).
- **`min MAD` kuralı uygulanmadı** — post-hoc seçim, ayrı ön kayıt gerektirir.
- **CERT'te yeniden koşu yapılmadı.** Ön kayıtta yazıldığı gibi: r4.2 ayar verisi, r5.2/r6.2
  yanmış, r1 saklı. `email` kaynağı CERT kör koşularında zaten vardı, yani A maddesi CERT'i
  etkilemiyor; `EPOSTA_TABAN` değişmediği için B de etkilemiyor. **Bu kez eksiklik yok.**
