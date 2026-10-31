# v7 ayar taraması — sonuçlar

**Ölçüm: 31 Ekim 2026, r4.2, 90 gün, bütçe 30.** Dondurma `kurallar-donduruldu-v6` → `donmuş durumla aynı`.
Yeni bileşen **yok**: sprint v6'da yeni bileşen eklemenin marjinal getirisinin sıfıra yakın olduğu ölçüldü.

## Ana tablo

| Varyant | Yakalanan | Vaka | Vaka/gün | prec@N | recall@10 (kull.) | **Vaka / insider** |
|---|---|---|---|---|---|---|
| `tam` | 22/34 | 1.939 | 21,5 | 0,045 | 0,618 | 88,1 |
| **`graf_carpan`** | **27/34** | 2.069 | 23,0 | 0,047 | **0,824** | 76,6 |
| `graf + öncelik` | 27/34 | 2.068 | 23,0 | 0,048 | 0,824 | 76,6 |
| **`graf + kapı`** | **23/34** | **398** | **4,4** | 0,116 | 0,676 | **17,3** |
| `kapı (gözlem 25)` | 20/34 | 282 | 3,1 | 0,213 | 0,588 | 14,1 |
| `kapı (gözlem 10)` | 18/34 | 214 | 2,4 | **0,238** | 0,529 | **11,9** |
| `öncelik (tek başına)` | 22/34 | 1.939 | 21,5 | 0,045 | **0,676** | 88,1 |

## Bulgu 1 — Kapı eşiği hiç önemli değilmiş

| Eşik | Yakalanan | Vaka |
|---|---|---|
| 0,1 | 18/34 | 217 |
| 0,2 | 18/34 | 216 |
| 0,3 | 18/34 | 214 |

Üçü de **aynı**. "Eşik 0,3 fazla agresif, gevşetelim" hipotezim **yanlıştı**. Sonsal olasılık
dağılımı bu aralıkta o kadar keskin ki 0,1 ile 0,3 arasında pratikte hiçbir vaka yok.

## Bulgu 2 — `min_gozlem` önemliymiş

| Gözlem eşiği | Yakalanan | Vaka |
|---|---|---|
| 10 | 18/34 | 214 |
| **25** | **20/34** | 282 |

**+2 senaryo, +68 vaka.** İkinci hipotezim doğru çıktı: kayıp, az kanıtla susturulan örüntülerden
geliyordu. Kapı kullanılacaksa `bayes_min_gozlem` varsayılanı 10 değil **25** olmalı.

## Bulgu 3 — Öncelik sıralayıcı bedelsiz bir kazanç

| | `tam` | `öncelik` |
|---|---|---|
| Vaka | 1.939 | **1.939** (birebir aynı) |
| Yakalanan senaryo | 22/34 | 22/34 |
| **recall@10 (kullanıcı)** | 0,618 | **0,676** |

Vaka sayısı **değişmeden** recall@10 yükseliyor. Tasarım sözleşmesi buydu: "sıra ham skordan
ayrılır" — fonksiyon kuyruğun **üyeliğini** değil **sırasını** değiştiriyor ve analist ilk 10'a
baktığında daha çok insider görüyor.

Senaryo kapsamasını artırmıyor (22/34) çünkü kapsama "pencere boyunca bir kez kuyruğa girdi mi"
sorusunu sorar; sıralama o soruyu değiştirmez. Ama **maliyeti sıfır** olduğu için açılmaması için
sebep yok.

Grafın üstüne eklendiğinde ek kazanç yok (27/34 → 27/34): graf zaten sıralamayı açıyor.

## Bulgu 4 — Graf ve kapı birbirini kısmen götürüyor

Ölçülmüş şekilde çalışan iki bileşen ilk kez birlikte denendi:

| | Yakalanan | Vaka |
|---|---|---|
| Graf tek başına | **27/34** | 2.069 |
| Kapı tek başına (gözlem 25) | 20/34 | 282 |
| **Birlikte** | **23/34** | **398** |

Kapı, grafın kazandırdığı 5 senaryonun **4'ünü** geri alıyor (27 → 23). Grafın yukarı çektiği
vakaları susturuyor.

Ama verimlilik tablosunda bu kombinasyon güçlü: **17,3 vaka/insider**, graf tek başınayken 76,6.
Yani dörtte bir iş yüküyle 23 insider.

## Sonuç: tek kazanan yok, bir verimlilik sınırı var

Bu tarama "hangi ayar en iyi" sorusunu cevaplamadı — çünkü **doğru cevap analist kapasitesine
bağlı**. Elimizdeki seçenekler:

| Analist kapasitesi | Yapılandırma | Yakalanan | Günlük vaka |
|---|---|---|---|
| Yüksek (~23 vaka/gün) | **graf + öncelik** | **27/34** | 23,0 |
| Orta (~4 vaka/gün) | **graf + kapı (gözlem 25)** | 23/34 | 4,4 |
| Düşük (~3 vaka/gün) | kapı (gözlem 25) | 20/34 | 3,1 |

**Graf çarpanı her üç noktada da kazandırıyor** — tek başına, kapıyla, öncelikle. 41 bayrak
içinde bu tutarlılığı gösteren tek bileşen.

## Varsayılan değişikliği önerisi — henüz yapılmadı

r4.2 **ayar verisidir**; buradan çıkan rakam yansız değildir. Varsayılanı değiştirmeden önce
**r6.2'de yalnız graf çarpanı** ölçülmeli. r6.2'deki "hepsi açık" koşusu grafı, ölçülmüş şekilde
zarar veren ADWIN'le birlikte açmıştı — grafın kazancı orada sulanmış olabilir.

Öneri (ölçüm sonrası karara bağlı):
- `graf_enabled=True`, `graf_agirligi=0.5` → varsayılan
- `priority_*_weight=0.5` → varsayılan (bedelsiz)
- `bayes_min_gozlem` 10 → **25** (kapı kullanılacaksa)
- `adwin_enabled` kalıcı olarak kapalı (ölçülmüş şekilde zararlı)
