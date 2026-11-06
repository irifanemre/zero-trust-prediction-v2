# Kuyruk kapısı teşhisi — hipotez DOĞRULANDI, ve grafın ne yaptığı değişti

**Ölçüm: 6 Kasım 2026, 2 varyant × 90 gün, bütçe 30.** Ön kayıt: `docs/kapi-tanisi-on-kayit.md`
(koşudan önce yazıldı). Dondurma `kurallar-donduruldu-v11` koşu başında doğrulandı.
Donmuş dosya değişmedi.

> **Kaçan 5 insider'ın hepsi geri geldi** ve bedeli beklediğimin çok altında çıktı. Ama asıl
> bulgu bu değil: ölçüm, **graf çarpanının r4.2'de ne yaptığına dair açıklamayı değiştiriyor.**

## Sonuç

| | `tam` | `v12_dogrulama_kapali` |
|---|---|---|
| **Kapsama** | 22/34 | **27/34** (+5) |
| `BÜTÇE DIŞI` | 5 | **0** |
| Vaka | 1.939 | **2.068** (+129, **×1,07**) |
| **precision@N** | 0,045 | **0,045** (değişmedi) |
| precision@1 | 0,420 | 0,411 |

| # | Ölçüt (koşudan önce yazıldı) | Sonuç |
|---|---|---|
| 1 | `tam` referansı aynı (22/34, 1.939) | **GEÇTİ** |
| 2 | `BÜTÇE DIŞI` 5'ten azalır → hipotez doğrulanır | **GEÇTİ** — 5 → **0** |
| 4 | Bedel ölçülür | **+129 vaka, precision DEĞİŞMEDİ** |

Geri gelen beş senaryo, hepsi S2 (USB): `DIB0285`, `EGD0132`, `IUB0565`, `PSF0133`, `XHW0498`.
Dördü kısmi pencereliydi ve ön kayıt "bazısı gelmeyebilir" demişti — **hepsi geldi.**

## İki karamsar beklenti de yanlış çıktı

| Beklenti | Gerçek |
|---|---|
| "Vaka sayısı çok artacak, belki iki katı" | **×1,07** — %7 |
| "Kazanç 5'in tamamı olmayacak" | **5/5 geldi** |

Kapının kestiği şey sanıldığı kadar kalabalık değilmiş. Ve kritik olan: **precision@N hiç
değişmedi** (0,045 → 0,045). Yani kapı, yanlış alarmı **oransal olarak** azaltmıyormuş; hem
insider'ları hem gürültüyü aynı oranda kesiyormuş.

## Asıl bulgu — graf çarpanının açıklaması değişiyor

| Varyant | Kapsama | Vaka |
|---|---|---|
| `tam` | 22/34 | 1.939 |
| **`v4_graf_carpan`** (30 Ekim) | **27/34** | **2.069** |
| **`v12_dogrulama_kapali`** (6 Kasım) | **27/34** | **2.068** |

**Bir vaka fark.** İki tamamen farklı mekanizma, aynı kapsamayı ve neredeyse aynı vaka sayısını
veriyor. Tesadüf olması zor.

Açıklama `corroborated()` içinde:

```python
return (
    r.critical
    or r.percentile >= self.cfg.kuyruk_kacis_yuzdelik
    or (...anomali...)
    or any(v > 1 for v in r.multipliers.values())   # ← graf çarpanı BURAYA giriyor
    or len({h.rule_id for h in r.hits}) >= 2
    or len({h.day for h in r.hits}) >= self.cfg.kuyruk_tekrar_gun
)
```

Graf çarpanı açıldığında `multipliers` içine 1'den büyük bir değer koyuyor — ve bu, kanıt
doğrulama kapısını **tek başına açıyor.**

> **Hipotez: grafın r4.2'deki +5'i, sıralamayı "germesinden" değil, KAPIYI AÇMASINDAN geliyor.**

Bu doğruysa, projenin en çok analiz edilmiş iki sonucu da yeniden okunmalı:

| Eski açıklama | Yeni hipotez |
|---|---|
| "Çarpan sıralamayı gerer, toplamsal sıkıştırır; o yüzden çarpan +5 verdi, toplamsal +0" | Çarpan kapıyı açar, toplamsal terim `multipliers`'a girmez — o yüzden açmaz |
| "Grafın +5'i r6.2'ye taşınmadı → aşırı uyum" | r6.2'de kaçanlar **kapı yüzünden** kaçmıyor olabilir; graf orada açacak bir kapı bulamadı |

İkincisi önemli: "aşırı uyum" teşhisi doğru olabilir ama **mekanizma** farklıysa, çıkarılacak ders
de farklı. "Graf aşırı uydu" ile "graf r4.2'de bir kapıyı açıyordu, r6.2'de o kapı zaten engel
değildi" aynı şey değil.

**Bu bir hipotez, ölçüm değil.** Doğrudan sınaması ucuz ve kesin: graf çarpanı **ve** doğrulama
kapısı **birlikte** açılırsa —

- Eğer ikisi **aynı** 5 insider'ı kurtarıyorsa sonuç yine **27/34** olur (etki toplanmaz)
- Eğer **farklı** insider'lar kurtarıyorlarsa 27'nin üstüne çıkar

Tek koşu, ~7 dk (veri önbellekte). Kendi ön kaydıyla yapılmalı.

## Varsayılan DEĞİŞMİYOR — ve sebebi önemli

+5 insider, +%7 vaka, precision sabit. Bu, bu arkın gördüğü **en iyi takas**. Yine de kapı açılmıyor:

> **Graf çarpanı da r4.2'de tam olarak böyle görünüyordu** — 27/34, 2.069 vaka — ve r6.2'de
> **+0 insider / +757 yanlış pozitif** verdi. Aynı rakamları veren bir mekanizmaya bu kez farklı
> davranmak için hiçbir sebep yok.

Kapı ancak **kör veride** değer ürettiği gösterilirse açılır. Elimizde yalnız r1 var ve saklı.

## İki senaryo yer değiştirdi (kayda geçiyor)

| Senaryo | Önce | Sonra |
|---|---|---|
| `MOS0047` | REVİZYON GEREKLİ | **KALDI** (kötüleşti) |
| `RHL0992` | KALDI | REVİZYON GEREKLİ |

Kapı kaldırılınca kuyruk bileşimi değişiyor; bazı vakalar yer değiştiriyor. Net etki sıfır ama
"yalnız kazanç var" demek yanlış olur.

## Bunun operasyonel anlamı

Kaçırılan insider'lar hakkında üç farklı teşhis vardı ve ölçüm ikisini eledi:

| Teşhis | Durum |
|---|---|
| ~~Tespit edilemiyor~~ | **Yanlış** — tespit ediliyorlar (`BÜTÇE DIŞI` = beklenen kural tetiklendi) |
| ~~Bütçe yetmiyor~~ | **Yanlış** — bütçe 30→100 eğrisi düz (`docs/v11-r42-sonuclar.md`) |
| **Tek kanıtlı oldukları için gösterilmiyorlar** | **Ölçüldü ve doğrulandı** |

Yani sorun kural yazmakta ya da analist kapasitesinde değil: **sistem onları görüyor, "tek sinyal
yeterli kanıt değil" diyerek susturuyor.**

Bu, USB senaryosunun doğasıyla da tutarlı: `UEBA-0017` pratikte yalnız `usb_ilk_kez == 1` ile
tetikleniyor (iki Poisson kolu ulaşılamaz, `tests/test_esik_ulasilabilirlik.py::BILINEN`) ve
"hayatında ilk kez USB" tanımı gereği **tek gün, tek kural**. Kapının iki koşulunu da düşürüyor.

## Sınırlar

- **r4.2 kör değil** — ayar verisi. Graf çarpanı burada aynı rakamları verip kör veride çöktü.
- **Tek bütçe (30), tek koşu.**
- **Kapı 1 sınanmadı** (7 günlük tekrar sunma kısıtı). Bayrağı yok; `scoring.py` donmuş.
  Kapı 2 beş senaryonun beşini de açıkladığı için şu an gerek de yok.
- **Çözüm önerilmiyor.** Kapıyı kaldırmak bir seçenek değil; `corroborated()`'ın "tek güçlü
  sinyal" koşullarının **USB için** genişletilmesi ayrı bir tasarım işi ve ayrı ön kayıt ister.
