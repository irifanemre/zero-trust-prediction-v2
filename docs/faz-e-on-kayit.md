# Faz E ön kaydı — sürüklenme tespiti: önce ADWIN'in neden zarar verdiğini anla

**Yazıldı: 5 Kasım 2026, kod değişikliğinden ÖNCE.**

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Brief ne istiyor, neden doğrudan yapılmıyor

Brief "ADWIN dışı sürüklenme (Page-Hinkley, BOCPD)" diyor. Doğrudan okunuşu: iki yeni dedektör
eklemek.

Ama ADWIN zaten ölçüldü ve **zarar verdiği** bulundu: r4.2'de recall@10 0,618 → **0,588**
(`docs/r62-v4-olcumu.md`). Sebebi hiç araştırılmadı. İki yeni dedektör eklemek, sebebi
bilinmeyen bir başarısızlığı iki kez daha denemek olur.

## Hipotez — kodu okuyarak kuruldu, ölçülmedi

```python
# pipeline.py:538
if self.cfg.adwin_enabled:
    a = self.adwin.get(sid) or Adwin(delta=...)
    if a.ekle(results[sid].raw) is not None:      # ← RİSK SKORU besleniyor
        self.profile.adwin_cut[sid] = day          # ← taban o günden başlıyor
```

ADWIN'e beslenen şey **risk skorunun kendisi**. Sürüklenme bulduğunda yaptığı şey, kişisel taban
çizgisini o güne sıfırlamak.

> **Hipotez: ADWIN insider'ın kendi tırmanışını "sürüklenme" sanıyor ve tabanı sıfırlayarak o
> tırmanışı YENİ NORMAL yapıyor — yani tespiti kendi eliyle siliyor.**

Bu bir ayar sorunu değil, **kavramsal ters çevirme** olurdu: sürüklenme dedektörü, tespit
çıktısıyla besleniyor ve tepkisi onu normalleştirmek.

Doğruysa Page-Hinkley ve BOCPD **aynı şeyi** yapar, çünkü aynı yanlış sinyali izlerler. Yani
hipotez doğruysa Faz E'nin brief'teki hâli **çürür**.

## Ölçüm (bu faz)

| # | Ne | Dosya | Donmuş |
|---|---|---|---|
| 1 | ADWIN kesme günleri toplanır, insider pencereleriyle karşılaştırılır | `scripts/suruklenme_tanisi.py` (yeni) | hayır |
| 2 | Kesmelerin insider penceresine düşme oranı vs şans beklentisi | aynı | hayır |
| 3 | ADWIN açık/kapalı yakalama farkı (aynı tohum, aynı veri) | aynı | hayır |

**Hiçbir donmuş dosya değişmeyecek, yeni dedektör yazılmayacak, dondurma değişmeyecek.**

## Başarı eşikleri — ölçümden ÖNCE

Bu bir **teşhis** ölçümü. "Geçti/kaldı" yerine hipotezin doğrulanıp doğrulanmadığı:

1. **Hipotez DOĞRULANIR** eğer insider'lardaki kesme oranı, insider olmayanlardakinin **≥ 2 katı**
   ise. O hâlde sürüklenme sinyali insider tırmanışıyla karışıyor demektir ve **Page-Hinkley /
   BOCPD yazılmayacak** — aynı sinyali izleyecekleri için aynı hatayı yapacaklar.
2. **Hipotez ÇÜRÜR** eğer oran benzer ise (< 2 kat). O hâlde ADWIN'in zararı başka bir sebepten
   ve alternatif dedektörleri denemek **gerekçeli** olur.
3. **Doğruluk kontrolü:** ADWIN açıkken yakalama, kapalıyken yakalamadan **düşük ya da eşit**
   olmalı — r4.2'de ölçülen zarar sentetik veride de görünmeli. Görünmezse sentetik veri bu
   soruyu ölçemiyor demektir ve 1–2 yorumlanmaz.

3 numara önce okunmalı: zarar yeniden üretilemiyorsa hipotez testi anlamsızdır.

## Beklentiler — karamsar

1. **Hipotez doğrulanacak.** Kod yolu bunu güçlü biçimde ima ediyor: risk skoru yükselir →
   ADWIN kayma görür → taban sıfırlanır → sapma kaybolur.
2. **Ama oran 2 katı geçmeyebilir**, çünkü ADWIN `delta` varsayılanıyla muhafazakâr olabilir ve
   çok az kesme üretebilir. Az kesme → gürültülü oran → sonuç belirsiz. Kesme sayısı 10'un
   altındaysa "ölçülemedi" raporlanacak, oran uydurulmayacak.
3. **Sentetik veride zarar görünmeyebilir** (ölçüt 3). Sentetik senaryolar r4.2'den daha keskin;
   taban sıfırlansa bile sapma yeterince büyük kalabilir. O hâlde dürüst sonuç "bu veri bu soruyu
   ölçemiyor" olur.
4. Hipotez doğrulansa bile **ADWIN'i düzeltmek bu fazın işi değil.** Doğru düzeltme (sürüklenmeyi
   risk skoru yerine ham davranış sinyallerinden izlemek) bir tasarım değişikliği ve kendi ön
   kaydını gerektirir.

---

# Sapmalar — ölçümden SONRA eklendi (5 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Sonuçlar: `docs/faz-e-sonuclar.md`.

## Sapma 1 — hipotez testi ÖLÇÜLEMEDİ (ön kayıtta öngörülmüştü)

Toplam kesme 120 kullanıcıda 3, 400 kullanıcıda 4 — eşik 10. Ön kayıt "kesme sayısı 10'un
altındaysa 'ölçülemedi' raporlanacak, oran uydurulmayacak" diyordu; uydurulmadı. Karamsar
beklenti 2 doğru çıktı.

Yön hipotezle tam uyumlu (insider %27, temiz %0,3; iki koşuda da aynı) ama bu "doğrulandı" demek
değil. Veriyle tutarlı olmak ile doğrulanmak aynı şey değil.

## Sapma 2 — ÖLÇÜT 3'ün niyeti karşılanmadı

Ölçüt 3 "ADWIN açıkken yakalama düşük ya da eşit olmalı" diye yazılmıştı ve teknik olarak geçti
(+0 etki). Ama **niyeti** r4.2'de ölçülen zararı yeniden üretmekti ve üretilemedi. Ön kayıt zaten
şunu demişti: *"zarar yeniden üretilemiyorsa hipotez testi anlamsızdır."*

Ölçütü "düşük ya da eşit" diye yazmak hataydı; "belirgin düşük" olmalıydı. Eşitlik hem
"ADWIN zararsız" hem "bu veri ölçemiyor" ile uyumlu ve ikisini ayırmıyor. Kayda geçiyor.

## Sapma 3 — nüfus 120'den 400'e çıkarıldı

Ön kayıt tek koşu öngörmüştü. 3 kesme eşiğin altında kalınca nüfus 400'e çıkarıldı; bu, ölçümün
**istatistiksel gücünü** artırır ve **ölçülen bileşeni değiştirmez** (delta aynı). Kesme 4'e
çıktı, hâlâ eşiğin altında.

`adwin_delta`'yı duyarlı yapmak kesme sayısını artırırdı ama o, ölçülen bileşeni değiştirir ve
ölçümü gördükten sonra yapılması uygun olmaz. Yapılmadı.

## Sapma 4 — ön kayıtta öngörülmeyen bulgu: ADWIN neredeyse ölü

9.600 kullanıcı-gününde 4 kesme. Varsayılan `adwin_delta` ile ADWIN pratikte işlevsiz bir bileşen
ve bu ön kayıtta hiç sorulmamıştı.

Bulgu r4.2 sonucunu yeniden yorumlamayı gerektiriyor: 400 kullanıcıda 4 kez tetikleyen bir bileşen
recall@10'u nasıl 0,03 düşürdü? En tutarlı açıklama, az sayıda kesmenin **tam insider'lara denk
gelmesi** — buradaki zenginleşmeyle (%27 vs %0,3) uyumlu ve r4.2'nin 34 insider'ında ~9 kişilik
kısmi körleşmeye karşılık geliyor. **Ama bu bir çıkarım, ölçüm değil.**
