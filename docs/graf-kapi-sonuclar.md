# Graf çarpanı kapıyı açıyormuş — hipotez DOĞRULANDI, iki yerleşik açıklama düşüyor

**Ölçüm: 6 Kasım 2026, 4 varyant × 90 gün, bütçe 30, tek koşu.** Ön kayıt:
`docs/graf-kapi-on-kayit.md` (koşudan önce yazıldı). Dondurma `kurallar-donduruldu-v11`
koşu başında doğrulandı. Donmuş dosya değişmedi.

> Sonuç, olabileceği kadar temiz çıktı: **üç mekanizma da birebir aynı 5 senaryoyu kurtarıyor ve
> etki toplanmıyor.**

## Ölçüm

| Varyant | Kapsama | Vaka | precision@N |
|---|---|---|---|
| `tam` | 22/34 | 1.939 | 0,045 |
| `v4_graf_carpan` | **27/34** | 2.069 | 0,047 |
| `v12_dogrulama_kapali` | **27/34** | 2.068 | 0,045 |
| **`v12_graf_arti_kapi`** | **27/34** | 2.069 | 0,047 |

Kurtarılan senaryolar — **üçünde de aynı küme**, hiçbirinde kayıp yok:

```
CERT-r4.2-S2-DIB0285   CERT-r4.2-S2-EGD0132   CERT-r4.2-S2-IUB0565
CERT-r4.2-S2-PSF0133   CERT-r4.2-S2-XHW0498
```

| | |
|---|---|
| graf ∩ kapı | **5** |
| graf ∪ kapı | **5** |
| graf + kapı birlikte | **5** |

Birleşim = kesişim = birlikte açılan. **Etki toplanmıyor.** Ön kayıttaki karar kuralı: *"27/34'te
kalırsa ve küme aynıysa hipotez doğrulanır."* Her iki şart da sağlandı.

| # | Ölçüt (koşudan önce yazıldı) | Sonuç |
|---|---|---|
| 1 | `tam` referansı aynı (22/34, 1.939) | **GEÇTİ** |
| 2 | Kurtarılan insider **kimliği** karşılaştırılır, sayısı değil | **GEÇTİ** — küme birebir aynı |
| 3 | 27/34 **ve** aynı küme → hipotez doğrulanır | **DOĞRULANDI** |

Karamsar beklenti 2 ("graf+kapı vaka sayısı ikisinden de yüksek çıkacak") da **yanlış** çıktı:
2.069, grafın tek başına verdiğiyle aynı.

## Mekanizma — tek satır

```python
# scoring.py:152, corroborated()
or any(v > 1 for v in r.multipliers.values())
```

Graf çarpanı `multipliers` sözlüğüne 1'den büyük bir değer koyuyor ve bu, kanıt doğrulama kapısını
**tek başına** açıyor. Kapı zaten açıkken grafın ekleyecek bir şeyi kalmıyor — bu yüzden ikisi
birlikte de 5.

> **Grafın r4.2'deki +5'i ilişkisel zekâdan gelmiyor. Bir eşik kapısını açmasından geliyor.**

## Düşen birinci açıklama: "çarpan gerer, toplamsal sıkıştırır"

Proje şunu kaydetmişti: *çarpan sıralama farklarını **gerer**, toplamsal terim **sıkıştırır**; o
yüzden `v4_graf_carpan` +5 verdi, `v5_graf_toplamsal` +0 verdi.* Bu bir **sıralama** açıklamasıydı.

Gerçek sebep koddan görünüyor:

```python
contrib["GRAF-TOPLAMSAL"] = add     # toplamsal terim contrib'e girer
...
any(v > 1 for v in r.multipliers.values())   # kapı YALNIZ multipliers'a bakar
```

Toplamsal terim `multipliers`'a **hiç girmiyor**, dolayısıyla kapıyı **açamaz**. Fark germe/sıkıştırma
değil; biri kapıyı açıyor, diğeri açamıyor. Aynı sonuç, tamamen farklı mekanizma.

## Düşen ikinci açıklama: "graf r4.2'ye aşırı uydu"

`docs/r62-graf-tek-basina.md` şunu yazmıştı: *"r4.2'de +5, r6.2'de +0 → projedeki en net aşırı
uyum kanıtı."*

Sonuç hâlâ doğru (graf r6.2'de değer üretmedi) ama **teşhis değişiyor**:

| Eski okuma | Yeni okuma |
|---|---|
| Graf, r4.2'nin özelliklerine aşırı uydu | Graf, r4.2'de **bir kapıyı açıyordu**; r6.2'de o kapı zaten engel değildi |

Fark pratik: "aşırı uyum" dersi *"grafı atma zamanı"* der. Yeni okuma *"r6.2'de kaçanların engeli
başkaydı, onu bul"* der. İkincisi sınanabilir bir yön, birincisi bir kapanış.

**Bu bir çıkarım, r6.2'de ölçülmedi.** Doğrulaması için r6.2'de `v12_dogrulama_kapali` koşulmalı:
kapı orada da +0 veriyorsa, r6.2'nin engeli gerçekten başka bir yerde.

## Pratik sonuç: 5 insider için graf katmanına gerek yok

| | Graf çarpanı | Kanıt kapısını gevşetmek |
|---|---|---|
| Kazanç (r4.2) | +5 | **+5, aynı kişiler** |
| Vaka maliyeti | +130 | **+129** |
| Gerekli altyapı | graf oluşturma, yayılım, akran yapısı | **tek koşul değişikliği** |
| Açıklanabilirlik | "graf riski 0,7" | **"tek ama güçlü sinyal"** |
| Katman süresi | ek `graf_olusturma` + `graf_sinyalleri` | **sıfır** |

Aynı sonucu veren iki yoldan **basit olanı** tercih edilir. Graf katmanı bu kazanç için
gereksiz karmaşıklık.

## Yine de varsayılan DEĞİŞMİYOR

+5 insider, +%7 vaka, precision sabit — arkın en iyi takası, ve artık **mekanizması da anlaşıldı**.
Buna rağmen kapı açılmıyor:

> Graf çarpanı r4.2'de **tam bu rakamları** verdi ve r6.2'de **+0 insider / +757 yanlış pozitif**
> verdi. Şimdi biliyoruz ki r6.2'de başarısız olan şey **kapıyı açmaktı**. Kapıyı doğrudan
> gevşetmenin r6.2'de farklı davranacağına inanmak için hiçbir sebep yok — tersine, aynı
> mekanizma olduğu ölçüldü.

Kapı ancak **kör veride** değer ürettiği gösterilirse gevşetilir. Ve artık bunun **ucuz bir ön
testi** var: r6.2'de `v12_dogrulama_kapali` koşmak (r6.2 yanmış veri, yeni bilgi yakmaz).

## Sıradaki adım — ucuz ve belirleyici

r6.2'de kapı varyantını koş:

| Sonuç | Anlamı |
|---|---|
| **+0** (graf gibi) | Mekanizma aynı, r6.2'nin engeli başka yerde → **kapı teorisi r6.2'yi açıklıyor** |
| **+1 veya daha fazla** | Kapı grafın yapamadığını yapıyor → graf ≠ kapı, hipotez r6.2'de tutmuyor |

Her iki sonuç da bilgi. r6.2 zaten yanmış veri olduğu için bu koşu **hiçbir şey harcamıyor**.

## Sınırlar

- **r4.2 ayar verisi.** Bu ölçüm mekanizmayı açıklıyor, genellenebilirliği göstermiyor.
- **Kapı 1 (7 günlük tekrar sunma kısıtı) hâlâ sınanmadı.** Kapı 2 beş senaryonun beşini de
  açıkladığı için gerek kalmadı, ama başka veride tabloyu değiştirebilir.
- **Çözüm önerilmiyor.** Doğru düzeltme kapıyı kaldırmak değil, `corroborated()`'ın "tek güçlü
  sinyal" koşullarını USB gibi tek-günlük-tek-kural desenlerini kapsayacak şekilde genişletmek —
  ayrı tasarım, ayrı ön kayıt.
