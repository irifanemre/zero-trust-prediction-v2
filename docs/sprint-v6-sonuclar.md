# Sprint v6 — sonuçlar

**Ölçüm: 30 Ekim 2026, r4.2, 90 gün, bütçe 30.** Ön kayıt: `docs/sprint-v6-on-kayit.md`.
Dondurma: `kurallar-donduruldu-v6` (36 dosya, 23 kural).

> **Üç katmanın üçü de ön kayıttaki eşiğini geçemedi. Üçü de varsayılanda kapalı kalıyor.**

## Karne

| Katman | Ön kayıttaki eşik | Ölçülen | |
|---|---|---|---|
| **A** geri bildirim döngüsü | kapsamayı değiştirmez (±1) | 22/34 → **18/34** | ✘ |
| **B** saldırı yolu tahmini | top-1 ≥ 2× taban | **1,33×** (0,579 vs 0,436) | ✘ |
| **C** öğrenen graf gömme | > 27/34 | **22/34** | ✘ |

Ön kayıtta **karamsar** yazılan beklentiler tuttu. Beklenti 4 ("C, 27/34'ü geçemez") aynen
gerçekleşti; beklenti 3 ve 5 de bu sonuçlarla tutarlı. Karamsar beklentinin tutması iyi haber
değildir — ağır modellerin bu veride değer üretmediğinin kanıtıdır.

## Tam tablo

| Ölçüt | `tam` | A (döngü) | B (yol) | C (öğrenen graf) | *karşılaştırma:* graf çarpanı |
|---|---|---|---|---|---|
| Yakalanan | 22/34 | **18/34** | 22/34 | 22/34 | **27/34** |
| Vaka | 1.939 | **214** | 1.939 | 1.967 | 2.069 |
| precision@N | 0,045 | **0,238** | 0,045 | 0,044 | 0,047 |
| precision@1 | 0,420 | 0,537 | 0,420 | 0,438 | 0,422 |
| recall@10 (kull.) | 0,618 | 0,529 | 0,618 | 0,618 | **0,824** |
| Erkenlik medyanı | 8 | 8 | 8 | 8 | 8 |

## İki sözleşme testi geçti

Kod doğru çalışıyor; başarısız olan fikirler, uygulama değil.

| Sözleşme | Sonuç |
|---|---|
| B, ağırlık 0 iken kuyruğu değiştirmemeli | **Birebir aynı** ✔ |
| C, sinyal üretirken ağırlık 0 iken skoru değiştirmemeli | **Birebir aynı** ✔ |

Bu iki kontrol önemlidir: yeni bir bileşenin "sessiz" hâlinin gerçekten sessiz olduğunu gösterir.
Aksi hâlde kapalı bir bayrak bile sonuçları kaydırabilirdi.

## Katman katman

### A — Geri bildirim döngüsü

Etkisinin **tamamı Bayes kapısından** geliyor. Kapı kapalıyken döngü (etiket üretimi + Venn-Abers +
periyodik yeniden eğitim) kuyruğun **içeriğini hiç değiştirmiyor** — `prediction_weight = 0`
olduğu için modelin olasılığı skora zaten girmiyor.

Ama **sırayı** değiştiriyor: recall@10 0,618 → **0,647**. Analistin "yanlış pozitif" etiketi,
v1'den beri kodda duran `×0,2` çarpanını canlandırıyor. Döngünün bedelsiz tek kazancı budur.

Kapının kendisi sert bir takas: vaka −%89, precision 5,3×, **−4 senaryo**. Gürültülü etikete
(analistin %15'i yanılıyor) **dayanıklı** çıktı — bu beklenmedik ve olumlu bir sonuç.

Ayrıntı: `docs/v6a-geri-bildirim-olcumu.md`.

### B — Saldırı yolu tahmini

| | |
|---|---|
| Sonraki adım top-1 | 0,579 |
| Taban ("her zaman en sık taktiği söyle") | 0,436 |
| **Oran** | **1,33×** — eşik 2× |
| top-3 | 0,982 vs taban 0,980 → **1,0×** |

top-3'ün doygun çıkması, ön kayıttaki **sapma 1**'in gerekçesini doğruladı: 9 taktiklik bir
sözlükte top-3 tabanı zaten 0,98; o metrikle hiçbir model ayırt edilemez.

Model çalışıyor ve mantıklı tahminler üretiyor, ama 1,33× bir analiste gösterilecek güveni
vermiyor. **Transformer kolu ayrıca ölçülmedi** — n-gram tabanı eşiği geçemediği için, onu geçmesi
beklenen ağır modelin ölçülmesi anlamsız.

### C — Öğrenen graf gömme

| | |
|---|---|
| Eğitim | 8 kez, 15.036 kenar, 923 kullanıcı, 947 hedef |
| Kayıp | 0,070 (model öğreniyor) |
| Skorlanan | 71.510 kullanıcı-gün |
| **Kapsama** | **22/34** — eşik > 27 |

Model teknik olarak çalışıyor (kayıp düşüyor, oyuncak veride bölüm ayrımını öğreniyor) ama
r4.2'de **tek bir ek senaryo bile** getirmiyor; yalnız 28 vaka ekliyor.

Eşiğin 27 olarak konması belirleyici oldu: taban 22 alınsaydı "değer üretmedi" yerine "nötr"
denebilirdi. Basit graf çarpanı tek başına 27 veriyorken, öğrenilmiş gömme 22'de kalıyor.

## Sonuç: 41 bayraktan 1'i işe yarıyor

Tüm ablasyonların birleşik tablosu:

| Bileşen | Kapsama | Maliyet |
|---|---|---|
| **Graf çarpanı** | **+5** (recall@10 0,618→0,824) | +130 vaka |
| Bayes kapısı | −4 | vaka −%89, precision 5,3× |
| ECOD kanalı | +0 | +71 vaka |
| Toplamsal graf · Öğrenen graf | +0 | +28 |
| Saldırı yolu · Belirsizlik | +0 | 0 |
| Isolation Forest | +0 | +172 |
| **ADWIN** | **+0, recall −0,03** | +79 |

**Ölçülmüş şekilde değer üreten tek bileşen graf çarpanıdır.**

## Sıradaki iş — ekleme değil, ayar

Yeni bileşen eklemenin marjinal getirisi ölçülmüş şekilde sıfıra yakın. Sıradaki üç iş, var
olanı ayarlamak:

1. **Bayes kapısı eşik taraması** (0,3 → 0,1 / 0,2) ve `bayes_min_gozlem` 10 → 25.
   Kaybedilen 4 senaryonun ince kanıtla susturulanlardan olması muhtemel.
2. **Graf çarpanı + Bayes kapısı birlikte.** Ölçülmüş şekilde çalışan iki bileşen bunlar ve
   **hiç birlikte denenmediler**.
3. **`priority()` fonksiyonunu ölçmek.** Darboğazın sıralama olduğu ölçüldü (kaçan 12'nin 5'i
   tespit edilmiş ama bütçeyi kaçırmış); tam bu iş için yazılmış fonksiyonun dört ağırlığı da 0
   ve hiç ölçülmedi.

Ve bundan bağımsız olarak: **CERT sizin tehdit modelinizi temsil etmiyor** (34 senaryonun 31'i
USB'ye bağımlı). Eksik kanallara (e-posta, bulut senkronizasyonu, yazdırma) kural yazmak,
yukarıdaki üç ayardan daha büyük bir kazanç olabilir — ama CERT'te ölçülemez.
