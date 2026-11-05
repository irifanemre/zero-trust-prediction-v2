# Faz E — sürüklenme teşhisi: hipotez doğrulanamadı, ADWIN zaten neredeyse ÖLÜ

**Ölçüm: 5 Kasım 2026.** Ön kayıt: `docs/faz-e-on-kayit.md` (koddan önce yazıldı).
Araç: `scripts/suruklenme_tanisi.py`. 24 gün, tohum 7, iki nüfus büyüklüğü.
Hiçbir donmuş dosya değişmedi, yeni dedektör yazılmadı, dondurma v10 aynı.

> **Page-Hinkley ve BOCPD YAZILMADI.** Gerekçe "gerek yok" değil: ön kayıtlı test hipotezi
> **doğrulayamadı** ve ADWIN'in zararı sentetik veride **yeniden üretilemedi** — yani alternatif
> dedektörleri seçmek için de değerlendirmek için de dayanak yok.

## Ölçüt 3 önce okunmalı: ADWIN'in zararı yeniden ÜRETİLEMEDİ

| Nüfus | ADWIN kapalı | ADWIN açık | etki |
|---|---|---|---|
| 120 kullanıcı | 7/8 yakalama, 127 vaka | 7/8, 126 vaka | **+0** |
| 400 kullanıcı | 8/8 yakalama, 162 vaka | 8/8, 163 vaka | **+0** |

r4.2'de ADWIN recall@10'u 0,618 → 0,588 düşürmüştü. Sentetik veride **hiçbir etkisi yok**.

Ön kayıt bunu öngörmüştü (karamsar beklenti 3) ve sonucu da yazmıştı: *"O hâlde dürüst sonuç 'bu
veri bu soruyu ölçemiyor' olur."* Ve ön kayıt ölçüt 3 için şunu demişti: *"3 numara önce okunmalı:
zarar yeniden üretilemiyorsa hipotez testi anlamsızdır."*

Teknik olarak ölçüt 3 "zarar ya da etkisizlik" diye yazılmıştı ve etkisizlik geçiyor; ama niyeti
zararı yeniden üretmekti ve **üretilemedi**. Bu yüzden aşağıdaki hipotez testi **zayıf dayanaklı.**

## Hipotez testi: ÖLÇÜLEMEDİ — ama yön çok net

| Nüfus | | kullanıcı | kesme alan | oran |
|---|---|---|---|---|
| 120 | insider | 11 | **3** | 0,273 |
| 120 | temiz | 109 | **0** | 0,000 |
| 400 | insider | 11 | **3** | 0,273 |
| 400 | temiz | 389 | **1** | 0,003 |

Ön kayıt: *"Kesme sayısı 10'un altındaysa 'ölçülemedi' raporlanacak, oran uydurulmayacak."*
Toplam kesme 120 kullanıcıda **3**, 400 kullanıcıda **4**. → **ÖLÇÜLEMEDİ.**

Oran hesaplanmıyor, ama ham sayılar kayda geçiyor: insider'ların **%27'si** kesme aldı, temiz
kullanıcıların **%0,3'ü**. İki koşuda da aynı. 120 kullanıcıda 3 kesmenin **3'ü de**, 400
kullanıcıda 3'ün **2'si** insider penceresinin **içinde**.

> Yön hipotezle tam uyumlu, **büyüklük ön kayıtlı standardı karşılamıyor.** Hipotez
> **doğrulanmadı**; "veriyle tutarlı" demekle "doğrulandı" demek aynı şey değil.

## Ön kayıtta öngörülmeyen asıl bulgu: ADWIN neredeyse hiç tetiklenmiyor

400 kullanıcı × 24 gün = 9.600 kullanıcı-günü → **4 kesme.** Varsayılan `adwin_delta` ile ADWIN
pratikte **ölü bir bileşen**.

Bu, r4.2 sonucunu yeniden yorumlamayı gerektiriyor. ADWIN 400 kullanıcıda 4 kez tetikliyorsa,
r4.2'de recall@10'u 0,03 düşürmesi nasıl oldu? İki olasılık:

1. r4.2'nin skor ölçeği/süresi çok daha fazla kesme üretti (360 gün, 2.801 kullanıcı).
2. **Az sayıda kesme, ama tam insider'lara denk geldiği için** yeterli oldu.

İkincisi buradaki zenginleşmeyle (insider %27, temiz %0,3) tutarlı ve sayısal olarak makul:
insider'ların dörtte biri taban sıfırlaması alırsa, r4.2'nin 34 insider'ında ~9 kişi kısmen
körleşir ve bütçe yarışında birkaçını kaybetmek recall@10'u 0,618 → 0,588 yapar.

**Ama bu bir çıkarım, ölçüm değil.** Ön kayıtlı test ölçülemedi; bu açıklama veriyle tutarlı en
iyi hikâye, kanıt değil.

## Neden Page-Hinkley / BOCPD yazılmadı

| Gerekçe | |
|---|---|
| Hipotez doğrulanamadı | Alternatif dedektörün **neyi** düzeltmesi gerektiğini bilmiyoruz |
| ADWIN'in zararı sentetik veride yok | Alternatifler **burada değerlendirilemez** — fark ölçülemez |
| ADWIN varsayılanda neredeyse ölü | "Daha iyi dedektör" sorusu, ölü bir bileşeni değiştirmek demek |
| Şüphelenilen kusur kavramsal | Risk skorunu izleyip tabanı sıfırlamak — **her** dedektör aynısını yapar |

Son satır belirleyici: eğer kusur `a.ekle(results[sid].raw)` satırındaysa, Page-Hinkley de BOCPD de
aynı sinyali izler ve aynı tepkiyi verir. Dedektörü değiştirmek **girdiyi** düzeltmez.

## Doğru düzeltme (uygulanmadı, ayrı ön kayıt gerekir)

Sürüklenme, **tespit çıktısından** değil **ham davranış sinyallerinden** izlenmeli: `bytes_out`,
`logon_count`, `distinct_apps_n` gibi kullanıcı davranışı ölçütleri. O zaman "kullanıcı yeni bir
role geçti" (meşru sürüklenme) ile "kullanıcının risk skoru tırmanıyor" (tespitin kendisi)
birbirinden ayrılır.

Uygulanmadı çünkü ADWIN'in girdisini değiştirmek sürüklenme katmanının tasarımını değiştirir ve
`profile.py` donmuş kümede. Kendi ön kaydıyla yapılacak iş.

## Sınırlar

- **Hipotez doğrulanmadı.** %27 vs %0,3 zenginleşmesi dikkat çekici ama n=4 kesme. Ön kayıtlı
  eşik gevşetilmedi.
- **ADWIN'in zararı sentetik veride yok**, yani bu veri asıl soruyu ölçemiyor. CERT'te ölçmek
  gerekir ama r4.2 ayar verisi, r5.2/r6.2 yanmış, r1 saklı.
- **Tek tohum, tek delta.** `adwin_delta` daha duyarlı yapılırsa kesme sayısı artar ve oran
  ölçülebilir hâle gelebilir — ama o, ölçümün gücünü değil **ölçülen bileşeni** değiştirir ve
  ölçümü gördükten sonra yapılması uygun olmaz.
