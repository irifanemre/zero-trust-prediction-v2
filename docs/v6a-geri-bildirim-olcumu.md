# v6-A geri bildirim döngüsü — ölçüm sonuçları

**Koşu: 30 Ekim 2026, r4.2, 90 gün, bütçe 30, 13,3M olay.** Dondurma v5 doğrulandı.
Ön kayıt: `docs/sprint-v6-on-kayit.md` (ölçümden önce yazıldı).

> **Kör değil.** r4.2 kuralların ayarlandığı veridir, üst sınırı gösterir.

## Sonuç tablosu

| Ölçüt | `tam` | **döngü** | döngü, kapı kapalı | döngü, %15 gürültülü etiket |
|---|---|---|---|---|
| **Yakalanan senaryo** | **22/34** | **18/34** | **22/34** | **18/34** |
| Vaka | 1.939 | **214** | 1.939 | 217 |
| Kuyruğa giren kullanıcı | 122 | 99 | 122 | 101 |
| **precision@N** | 0,045 | **0,238** | 0,045 | 0,235 |
| precision@1 | 0,420 | **0,537** | 0,443 | 0,529 |
| precision@10 | 0,108 | **0,300** | 0,113 | 0,295 |
| recall@10 (kullanıcı) | 0,618 | 0,529 | **0,647** | 0,529 |
| recall@30 (kullanıcı) | 0,676 | 0,529 | 0,676 | 0,529 |
| Erkenlik medyanı | 8 gün | 8 gün | 8 gün | 8 gün |
| Bayes kapısının elediği | 0 | **1.725** | 0 | 1.722 |
| Süre | 26 dk | 7 dk | 7,8 dk | 6,6 dk |

### Kaçma biçimleri

| | `tam` | döngü | kapı kapalı | gürültülü |
|---|---|---|---|---|
| GEÇTİ | 22 | 18 | 22 | 18 |
| BÜTÇE DIŞI | 5 | **9** | 5 | 9 |
| KALDI (tetiklenmedi) | 6 | 7 | 6 | 7 |
| REVİZYON GEREKLİ | 1 | 0 | 1 | 0 |

## Bulgu 1 — Döngünün etkisi Bayes kapısından ibaret

`döngü, kapı kapalı` varyantı `tam` ile **aynı kuyruğu** üretiyor: 1.939 vaka, 22/34 kapsama.
Yani etiket üretmek, Venn-Abers aralığı hesaplamak ve modeli periyodik yeniden eğitmek —
üçü birlikte — kuyruğun **içeriğini değiştirmiyor**.

Bunun sebebi yapısal ve baştan görülebilirdi: `prediction_weight = 0`. Öğrenen modelin
olasılığı skora hiç girmiyor. Ağırlığı sıfır olan bir modeli yeniden eğitmek, tanımı gereği
kuyruğa etki edemez. **Periyodik kalibrasyon iddiası bu yapılandırmada sınanamadı.**

### Ama sıra değişiyor

Kuyruk aynı olsa da **sırası** değişiyor: precision@1 0,420 → 0,443, recall@10 0,618 → **0,647**.
Sebebi v1'den beri kodda duran ama etiketsiz ortamda hiç çalışmamış bir mekanizma:

```
fp_pattern_match → mult["daha_once_normal"] = 0.2
```

Analist bir deseni "yanlış pozitif" işaretlediğinde aynı desen 90 gün içinde tekrar gelirse
skoru beşte bire düşüyor. Etiket aktığı an bu mekanizma canlanıyor ve sıralamayı iyileştiriyor —
**vaka sayısını hiç değiştirmeden.** Döngünün bedelsiz tek kazancı budur.

## Bulgu 2 — Bayes kapısı sert bir takas

Kapı 1.939 vakanın **1.725'ini** eliyor:

| | Kazanç | Bedel |
|---|---|---|
| Vaka hacmi | 1.939 → 214 (**−%89**) | — |
| precision@N | 0,045 → 0,238 (**5,3×**) | — |
| precision@10 | 0,108 → 0,300 (2,8×) | — |
| Yakalanan senaryo | — | 22 → **18** (−4) |
| recall@30 (kullanıcı) | — | 0,676 → 0,529 |

Analist günde ~21 vaka yerine ~2,4 vaka görüyor ve bunların **%24'ü gerçek** (önceden %4,5).
Buna karşılık 4 senaryo kaçıyor: bütçe dışı kalanlar 5'ten 9'a çıkıyor.

Yani kapı, **kuyruğa girebilecek gerçek tespitleri de susturuyor**. Eşik 0,3'te fazla agresif.

## Bulgu 3 — Gürültülü etikete dayanıklı

Analistin **%15'i yanılırsa** ne olur? Neredeyse hiçbir şey:

| | Temiz etiket | %15 hatalı |
|---|---|---|
| Yakalama | 18/34 | 18/34 |
| Vaka | 214 | 217 |
| precision@N | 0,238 | 0,235 |
| Bayes elediği | 1.725 | 1.722 |

Beklenmedik derecede sağlam. Sebep: Beta-binom sonsalı bir örüntü için **biriken** doğru/yanlış
sayımlarına bakıyor; tek tek hatalar ortalamada sönüyor. Gerçek bir SOC'ta etiketler temiz
gelmeyeceği için bu, döngünün dağıtılabilirliği açısından önemli bir sonuçtur.

## Ön kayıt: beklentiler tuttu mu?

| # | Beklenti | Sonuç | |
|---|---|---|---|
| 1 | A, vaka hacmini en az %10 düşürür | **−%89** | ✔ |
| 2 | A, kapsamayı değiştirmez (±1 senaryo) | **−4 senaryo** | ✘ |
| — | Başarı eşiği: "Bayes kapısı sıfırdan farklı eleme yapar **ve** precision@N düşmeden vaka hacmi azalır" | 1.725 eleme, precision 5,3× | ✔ (harfiyen) |

### Sapma 2 — eşiğin kendisi eksikti

**30 Ekim, ölçümden SONRA fark edildi.** Başarı eşiği "precision düşmeden vaka azalır" diyordu
ve harfiyen tuttu. Ama eşik **kapsama kaybını hesaba katmıyordu**: 4 senaryo kaybederek precision
yükseltmek de o cümleyi sağlar.

Eşik bu koşu için değiştirilmiyor — sonuç yukarıda olduğu gibi raporlanıyor. Sonraki ölçümlerde
kuyruk kısan her bileşen için eşik şu olacak: **"precision artar VE kapsama ±1 içinde kalır"**.
Bu, ön kayıt yazarken öğrenilen bir derstir: "bir şey düşmeden" biçimindeki eşikler, düşmesi
istenmeyen her şeyi tek tek saymadığı sürece eksiktir.

## Ne yapılacak

1. **Kapı eşiği taranmalı.** 0,3 fazla agresif. 0,1 ve 0,2 ile koşup kapsama–precision eğrisi
   çıkarılmalı; amaç kapsamayı 22'de tutup vakayı mümkün olduğunca kısmak.
2. **`bayes_min_gozlem` yükseltilmeli.** Şu an 10. Daha yüksek bir eşik, az gözlemle susturulan
   örüntüleri korur — kaybedilen 4 senaryonun oradan gelmiş olması muhtemel.
3. **`prediction_weight` açılmadan periyodik eğitim ölçülemez.** İkisi birlikte bir varyant olmalı.
4. **AUPRC karşılaştırması geçersiz.** `tam` için 0,064, döngü için 0,168 görünüyor ama
   hedef değişkeni farklı: etiketsizken cevap anahtarı, etiketliyken analist etiketi kullanılıyor.
   Elma-armut; bu rakam **iyileşme olarak okunmamalı**.
