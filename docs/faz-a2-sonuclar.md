# Faz A-2 — şema farkındalığı karar yoluna bağlandı: sonuçlar

**Ölçüm: 31 Ekim 2026.** Ön kayıt: `docs/faz-a2-on-kayit.md` (ölçümden önce yazıldı).
Dondurma: `kurallar-donduruldu-v8` → `donmuş durumla aynı`. 376 test geçiyor.

> Fazın amacı yakalama artırmak değildi: **"desen görülmedi" ile "bakılamadı" ayrımını** karar
> yoluna bağlamaktı. Üç ön kayıtlı ölçütten **ikisi geçti, biri KALDI.**

## Ön kayıtlı ölçütler ve sonuçları

| # | Ölçüt (ölçümden önce yazıldı) | Sonuç |
|---|---|---|
| 1 | Bayrak kapalıyken r4.2 sonucu birebir aynı | **GEÇTİ** |
| 2 | Bayrak açıkken yakalama değişmez — mekanizma yanlış pozitif üretmez | **GEÇTİ** (bir yanlış pozitif yakalayıp düzelttikten sonra) |
| 3 | r6.2'de `UEBA-0003` `sinanamaz — şema` raporlanır, S5 `ÖLÇÜLEMEDİ` işaretlenir | **KALDI** |

### Ölçüt 1 ve 2 nasıl ölçüldü

Sentetik veride r4.2'nin gerçek durumu yeniden üretildi: `outcome` sabitlendi, `process`/`cmdline`
boşaltıldı. Aynı sakat veriyle iki koşu, tek fark bayrak
(`tests/test_availability.py::test_mekanizma_RAPORU_degistirir_SKORU_degistirmez`):

| Ölçüt | Bayrak kapalı | Bayrak açık |
|---|---|---|
| Günlük risk skorları | — | **birebir aynı** |
| Kuyruk (gün × kullanıcı) | — | **birebir aynı** |
| Kural tetiklenme sayıları | — | **birebir aynı** |
| `UEBA-0006` raporu | `sinanmadi — bu veride desen görülmedi` | **`sinanamaz — şema: outcome`** |
| `UEBA-0008` raporu | `sinanmadi — bu veride desen görülmedi` | **`sinanamaz — şema: process, cmdline`** |

Sözleşme: **mekanizma RAPORU değiştirir, SKORU değiştirmez.**

## Ölçüt 2 bir yanlış pozitif yakaladı — ve o yanlış pozitif benim haritamdaydı

İlk koşuda skorlar aynı ÇIKMADI: bir kullanıcının altı günü farklıydı ve bir gün
**1,26 → 189,08** oynadı. Sebep:

```
"kesif_genisligi_akran_kati": "recon_process_count"   # YANLIŞ
"kesif_genisligi_akran_kati": "distinct_resources"    # DOĞRU (profile.py:607)
```

Adı "keşif" diyor ama sinyal süreç sayısına değil **erişilen tekil kaynak sayısına** bakıyor.
Sentetik veride `process` boş, `resource` dolu: `UEBA-0008`'in bir kolu canlıydı ve kural meşru
şekilde 6 kez tetikleniyordu. Yanlış harita onu susturdu, PRED-0012 9 → 4 tetiklenmeye düştü.

İkinci bir harita hatası aynı denetimde çıktı:

```
"files_accessed": ("resource",)   # YANLIŞ — features.py:69 dosya OLAYLARINI sayar
"files_accessed": ("source",)     # DOĞRU
```

CERT dosya adı saklamaz (20.1 veri minimizasyonu) ama dosya olayı vardır ve sayılır. Yanlış
zincir, r4.2'de `UEBA-0007`'nin dosya sinyallerini "şemadan ölü" gösteriyordu.

> **Bulgu:** Bu fazın yakalamak için yazıldığı hata sınıfının — *başka ölçekten/kaynaktan alınan
> bir bağımlılık varsayımı* — iki örneği fazın kendi haritasında vardı. Sinyal adı, bağımlılığının
> kanıtı değildir. Zinciri koda karşı denetleyen test o yüzden eklendi
> (`test_turev_zinciri_uretim_koduyla_tutarli`).

## Gerçek veride ilk koşu: iki kural, her iki CERT sürümünde de yapısal olarak ölü

`scripts/sema_karar_dogrula.py` ile r4.2 ve r6.2 (30 günlük pencere; şema kararı pencereden
bağımsızdır, koşu sonucundan değil şemadan çıkar):

| Kural | Ağırlık | Eksik alan | Neden |
|---|---|---|---|
| **UEBA-0006** Başarısız giriş yığını | 5 | `outcome` **sabit** | CERT `logon.csv` yalnız Logon/Logoff tutar; başarısız giriş kaydı YOK → `failed_logon_count` her gün 0 |
| **UEBA-0008** Hesap yaşı × keşif | 6 | `process`, `cmdline`, `resource` **boş** | CERT'te süreç telemetrisi yok; dosya adı saklanmaz |

Bu iki kural **r4.2'nin 11 ablasyon varyantının hepsinde** ve r6.2'nin üç koşusunda
`sinanmadi — bu veride desen görülmedi` diye raporlandı. İkisi de aslında **hiç bakılamamıştı**.
Mekanizma bunu ilk koşusunda, elle arama yapılmadan buldu.

Toplam ağırlık 11 — kataloğun 25 kuralından ikisi, ölçülen her sonucun dışında kalıyordu.

## Ölçüt 3 neden KALDI — ve bu neden önemli

Beklenti: r6.2'de `UEBA-0003` (ağırlık 8) ölü raporlanacak, çünkü r6.2'nin `http.csv`'sinde
`content` kolonu yok ve web olaylarında `bytes_out = 0`.

Ölçülen:

```
⚠ http.csv: `content` kolonu yok → `bytes_out` (web yükleme hacmi — yoksa UEBA-0003 web tarafında ÖLÜ)
...
| `bytes_out` | kullanilabilir | 0.0367 | 6590 |
```

İki satır **birbiriyle çelişiyor** ve karar ikincisine bakıyor. Sebep: `bytes_out` üç kanaldan
beslenir — `http.csv:content` (r6.2'de YOK), `email.csv:size` (VAR), `file.csv:content` (VAR).
Alan **toplamda** dolu, **web kanalında** ölü.

| Kanal | r6.2'de `bytes_out` |
|---|---|
| proxy (web) | **her olayda 0 — ölü** |
| email | gerçek boyut |
| file | gerçek boyut |

`UEBA-0003` bu yüzden ölü sayılmadı; S5-MBG3183 (57 saniyede 4 Dropbox yüklemesi) bir **web**
olayıdır ve hâlâ `KALDI (tetiklenmedi)` diye raporlanıyor.

**Mekanizmanın çözünürlüğü alan düzeyinde; sorun kanal düzeyinde.** Alan "var mı" sorusuna doğru
cevap veriyor ama sorulması gereken soru "**bu kanalda** var mı".

Ham başlık uyarısı doğruyu söylüyordu; onu karara bağlayan yol yok. Faz A-1'in bıraktığı boşluğun
aynısı, bir seviye aşağıda tekrar ediyor.

### Ölçüm penceresinin sınırı

Doğrulama 30 günlük pencereyle yapıldı: r4.2'de 2, r6.2'de 1 senaryo pencereye düştü. Senaryo
ölçülebilirliği sayıları (`ölçülebilir 2 · kısmi 0 · ÖLÇÜLEMEZ 0`) bu küçük örneklem içindir ve
**kapsama oranı iddiası değildir**. Şema kararı pencereden bağımsızdır; senaryo sayımı değildir.

## Ne değişti (kod)

| # | Ne | Dosya |
|---|---|---|
| 1 | Sinyal → türev özellik → ham alan zinciri (38 sinyal) | `availability.py` (**yeni, donmuş**) |
| 2 | Kuralın gerektirdiği sinyaller koşuldan AST ile çıkarılır | `availability.py` |
| 3 | Şemadan ölü kural değerlendirilmez, `sema_olu`'ya **sayılır** | `detection/engine.py` (**donmuş**) |
| 4 | Kural sağlığı: `sinanamaz` ayrı durum, `disabled`'dan ayrı | `metrics.py` |
| 5 | Kapsama: beklenenlerin hepsi ölüyse `ÖLÇÜLEMEDİ`, paydadan düşer | `metrics.py` |
| 6 | Bayrak `sema_farkindaligi` (varsayılan **kapalı**) | `config.py` (**donmuş**) |
| 7 | `devices` / `logon_hour` türev zincirleri | `schema_profiler.py` (**donmuş**) |
| 8 | Gerçek CERT sürümünde şema kararı doğrulaması | `scripts/sema_karar_dogrula.py` (yeni) |

Aşırı kapatmaya karşı iki koruma, ikisi de test altında:

- **Kısmen ölü kural çalışmaya devam eder.** `or`'lu kuralda bir kol ölse diğeri tetikleyebilir
  (`UEBA-0017` deseni: iki Poisson kolu ulaşılamaz ama `usb_ilk_kez` tetikliyor).
- **Haritada olmayan sinyal hakkında karar verilmez.** Risk serisinden türeyen, graf, denetimsiz
  kanal, tuzak, dizin/İK ve coğrafi sinyaller bilerek haritada yok.

## Varsayılan: KAPALI

Ölçüt 3 kaldığı için bayrak varsayılan açılmıyor. Gerekçe, bulunan iki ölü kuralın değersiz
olması değil — tersine, bulgu gerçek. Gerekçe şu: mekanizma **asıl aradığı vakayı** (r6.2 / S5 /
`UEBA-0003`) hâlâ göremiyor, dolayısıyla "şema farkındalığı açık" demek yanlış bir güven verir.

Varsayılanı değiştirmek için kanal düzeyinde çözünürlük gerekir → **Faz A-3**.

## Faz A-3 için kayıt (ön kayıt ayrıca yazılacak)

Alan düzeyinden **(alan × kaynak)** düzeyine geçiş:

```
bytes_out@proxy  → ölü       (http.csv'de content yok)
bytes_out@email  → canlı
bytes_out@file   → canlı
```

Kuralın hangi kanala baktığı `veri_kaynaklari` alanında zaten yazılı — `UEBA-0003`'ün kaynağı
`proxy`. Yani eşleştirme için yeni bir harita gerekmiyor, var olan iki bilgi birleştirilecek.

Beklenti (şimdiden yazılıyor): bu da **hiçbir insider kazandırmayacak**. r6.2'nin S5'i
`ÖLÇÜLEMEDİ` olacak, yani 3/4 yakalama **3/3 ölçülebilir + 1 ölçülemeyen** olarak raporlanacak.
Yakalama artmaz; rakam dürüstleşir.
