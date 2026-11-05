# Faz C-1 — ufuk ölçümü: karar kuralı tetiklendi, ama yanlış şeyi ölçüyormuş

**Ölçüm: 5 Kasım 2026.** Ön kayıt: `docs/faz-c-on-kayit.md` (koddan önce yazıldı).
Araç: `scripts/ufuk_olcumu.py`. 120 kullanıcı, 20 gün, tohum 7, 2.639 tahmin satırı.
Hiçbir donmuş dosya değişmedi, dondurma v10 aynı.

## Ölçüm

Tek olasılık (`p7_sezgisel`), dört ufka karşı ayrı ayrı değerlendirildi. Skorlar **aynı**, değişen
yalnız hedef tanımı — yani fark modelden değil ufkun kendisinden geliyor.

| Ufuk | n | pozitif | taban oranı | **AUC** | AUPRC | × taban | beceri skoru | ECE |
|---|---|---|---|---|---|---|---|---|
| **1 gün** | 2.639 | 82 | 0,0311 | **0,900** | 0,406 | **13,1×** | **−0,919** | 0,116 |
| 3 gün | 2.639 | 95 | 0,0360 | 0,863 | 0,373 | 10,3× | −0,749 | 0,111 |
| 7 gün | 2.639 | 120 | 0,0455 | 0,837 | 0,330 | 7,3× | −0,509 | 0,102 |
| **14 gün** | 2.639 | 167 | 0,0633 | **0,763** | 0,289 | 4,6× | −0,304 | 0,084 |

Ön kayıttaki karar kuralı: *AUC farkı ≥ 0,10 ise C-2 yazılır.* Fark **0,137** → kural tetikleniyor.

Ve ön kayıttaki karamsar beklenti 1 ("fark 0,10'u geçmeyecek") **yanlış çıktı**. Beklenti 2
(fark çıkarsa kısa ufuk daha iyi) **doğru çıktı** ve tam monoton.

## Ama karar kuralı yanlış şeyi ölçüyormuş

AUC bir **sıralama** ölçütüdür. Dört ufukta skorlar **birebir aynı**; değişen yalnız etiketler.
Dolayısıyla bu tablo şunu ölçüyor:

> **1 günlük sonuçlar, 14 günlük sonuçlardan daha öngörülebilir.**

Şunu ölçmüyor:

> Model ufka göre farklı parametre istiyor.

İkisi ayrı şeyler. Birinci cümle bir **bilgi sınırıdır**: bugünün risk sinyali yarını iki hafta
sonrasından daha iyi biliyor — bu doğanın gerçeği, model eksikliği değil. Ufuk başına model yazmak
onu değiştirmez.

> **Ön kayıtta yazdığım karar kuralı bu ayrımı yapamıyordu.** "AUC farkı ≥ 0,10" testi, ufuk
> başına modelin gerekliliğini değil ufukların öngörülebilirliğini sınıyor. Doğru test şu olurdu:
> *ufuk h için eğitilmiş bir baş, h ufkunda tek `p7`'yi geçiyor mu?* — ve o test C-2'nin kendisini
> gerektiriyor, C-1'de cevaplanamaz.

Kural tetiklendiği için C-2 yazılacak, ama **gerekçesi kuralın söylediği şey değil**, aşağıdaki
ikinci bulgu.

## İkinci bulgu — ve asıl olan bu: olasılık KALİBRE DEĞİL

**Beceri skoru dört ufukta da NEGATİF** (−0,919 … −0,304).

Beceri skoru = `1 − Brier / Brier_taban`. Negatif olması şu demek: **sabit taban oranını tahmin
etmek, modelin olasılığından daha iyi.** ECE 0,08–0,12, yani ortalama %8–12 sapma.

Buna karşılık sıralama gücü yüksek: AUC 0,900 ve AUPRC tabanın **13,1 katı** (1 gün).

> `p7` iyi bir **sıralayıcı**, kötü bir **olasılık**.

Bu ayrım operasyonel olarak kritik, çünkü sistem sıralamayı kullanıyor (kuyruk, bütçe 13.5) ama
olasılığı **rapora yazıyor** ("%X olasılıkla 7 gün içinde"). Sıralama güvenilir, o cümle değil.

### Sebebi kodda görünüyor

```python
# prediction_model.py:87  HeuristicModel
return sigmoid(-3.5 + sum(comp.values())), comp
```

Tek bir elle konulmuş kesme noktası (`-3.5`), **tek bir ufka** (7 gün) göre. Ama taban oranı ufka
göre iki kat değişiyor (0,0311 → 0,0633). Aynı kesme noktası dört farklı taban oranına doğru
olasılık veremez — matematiksel olarak mümkün değil.

## C-2'nin yeniden tanımı

C-1'in ölçtüğü şey, ön kayıtta tasarlanan C-2'yi (ufuk başına ayrı MODEL) desteklemiyor. Desteklediği
şey farklı ve daha dar:

| Ön kayıtta planlanan C-2 | Ölçümün desteklediği C-2 |
|---|---|
| Ufuk başına ayrı sezgisel/lojistik baş | **Tek sıralayıcı, ufuk başına KALİBRASYON** |
| Gerekçe: ufuklar farklı bilgi taşıyor | Gerekçe: taban oranı ufka göre 2× değişiyor, tek kesme noktası dördüne uyamaz |
| Dört model, dört bakım yükü | Bir model, dört eşleme |

Ve araç zaten var: `VennAbersKalibrator` (PAVA izotonik, `gnn/conformal_eval.py`) — yazılmış,
test edilmiş, kullanılmıyor.

**Başarı ölçütü (C-2 ön kaydında yazılacak):** ufuk başına kalibrasyon, beceri skorunu dört ufukta
da **negatiften pozitife** çevirmeli. Çevirmezse kalibrasyon da işe yaramıyor demektir ve rapor
cümlesinden olasılık ifadesi çıkarılmalı.

## Yan bulgu — "7 gün" neden 7?

Bu projede ufuk hep 7 gündü ve **nedeni hiç sorgulanmamıştı**. Ölçüm gösteriyor ki 7 gün bir orta
nokta: 1 günde sıralama belirgin daha iyi (AUC 0,900 vs 0,837; AUPRC 13,1× vs 7,3×), 14 günde
belirgin daha kötü.

Yani **erken uyarı iddiası ufuk uzadıkça zayıflıyor** ve bu sayısal olarak ilk kez kayıtlı.
"Sistem 7 gün önceden uyarır" cümlesi, "1 gün önceden çok daha güvenilir uyarır" cümlesinden
zayıftır — ama ikisi birlikte söylenirse dürüst olur.

## Sınırlar

- **Sentetik veride ölçüldü.** CERT'te yeniden koşu yok (r4.2 ayar verisi, r5.2/r6.2 yanmış, r1
  saklı). Graf çarpanının r4.2'den r6.2'ye taşınmadığı hatırlanmalı: bu sayılar genellenemez.
- **Yalnız sezgisel model ölçüldü.** Öğrenen lojistik model bu koşuda eğitilmemişti (etiket yok),
  dolayısıyla `p7 == p7_sezgisel`. Lojistik modelin kalibrasyonu ayrı bir soru.
- **Tohum değişkenliği ölçüldü** (başta eksikti, dört tohumla kapatıldı):

| Tohum | AUC 1g | AUC 14g | **fark** | beceri 1g | beceri 14g | AUPRC 1g |
|---|---|---|---|---|---|---|
| 7 | 0,900 | 0,763 | **0,137** | −0,919 | −0,304 | 13,1× |
| 11 | 0,905 | 0,729 | **0,176** | −0,882 | −0,346 | 13,4× |
| 42 | 0,900 | 0,765 | **0,135** | −1,051 | −0,356 | 9,9× |
| 2026 | 0,907 | 0,733 | **0,174** | −0,990 | −0,378 | 11,9× |

  Dört tohumda da fark **eşiğin üstünde** (0,135–0,176) ve beceri skoru **dört ufukta, dört tohumda
  da negatif**. İki bulgu da tohuma dayanıklı; tek koşuluk tesadüf değil.
