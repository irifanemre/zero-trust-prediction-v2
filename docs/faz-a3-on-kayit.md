# Faz A-3 ön kaydı — şema kararı ALAN düzeyinden KANAL düzeyine

**Yazıldı: 31 Ekim 2026, ölçümden ÖNCE.** Dayanak: `docs/faz-a2-sonuclar.md` (ölçüt 3 KALDI).

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Problem

Faz A-2 şema kararını karar yoluna bağladı ve iki gerçek ölü kural buldu (`UEBA-0006`,
`UEBA-0008`). Ama **asıl aradığı vakayı göremedi.** Ölçülen çelişki:

```
⚠ http.csv: `content` kolonu yok → `bytes_out` (web yükleme hacmi — yoksa UEBA-0003 web tarafında ÖLÜ)
| `bytes_out` | kullanilabilir | 0.0367 | 6590 |
```

İki satır birbiriyle çelişiyor ve karar ikincisine bakıyor. `bytes_out` **üç kanaldan** beslenir:

| Kanal (`source`) | Ham kaynak | r6.2 | r4.2 |
|---|---|---|---|
| `proxy` (web) | `http.csv:content` | **YOK → her olayda 0** | var |
| `email` | `email.csv:size` | var | var |
| `file_server` | `file.csv:content` | var | var |

Alan **toplamda** dolu, **web kanalında** ölü. `UEBA-0003`'ün kaynağı `proxy`'dir ve S5-MBG3183
(57 saniyede 4 Dropbox yüklemesi) bir web olayıdır — hâlâ `KALDI (tetiklenmedi)` raporlanıyor,
oysa doğrusu `ÖLÇÜLEMEDİ`.

**Mekanizmanın çözünürlüğü alan düzeyinde; sorun kanal düzeyinde.**

## Yaklaşım: yeni harita YOK, var olan iki bilgi birleştirilecek

Kuralın hangi kanala baktığı kataloğda **zaten yazılı**: `veri_kaynaklari`. `UEBA-0003` için
`[proxy]`. Alanın hangi kanalda dolu olduğu da ölçülebilir: `events.groupby("source")[alan]`.

```
bytes_out@proxy        → ölü      (doluluk 0,0000)
bytes_out@email        → canlı
bytes_out@file_server  → canlı
→ UEBA-0003 (kaynak: proxy) SINANAMAZ
→ UEBA-0023 (kaynak: email) canlı
```

Yani A-2'nin zinciri bir halka uzuyor:

```
kural → veri_kaynaklari → (alan × kaynak) → ham olay alanı
```

## Değişecekler

| # | Ne | Dosya |
|---|---|---|
| 1 | `AlanDurumu` kaynak bazında: `alanlar_kaynak[(alan, kaynak)]` | `schema_profiler.py` (**donmuş**) |
| 2 | `turev_uretilebilir(turev, kaynak=None)` — kaynak verilirse o kanala bakar | `schema_profiler.py` |
| 3 | Kural mevcudiyeti kuralın `veri_kaynaklari`'nı kullanır | `availability.py` (**donmuş**) |
| 4 | Bayrak `sema_kanal_duzeyi` (ayrı bayrak, `sema_farkindaligi` gerektirir) | `config.py` (**donmuş**) |

Donmuş küme değişiyor → **dondurma v9**.

### Neden ayrı bayrak

`sema_farkindaligi` A-2'de ölçüldü ve ne yaptığı biliniyor. Kanal düzeyi onun üstüne gelen,
**daha agresif** bir kapatmadır: bir kuralı, alan toplamda dolu olsa bile kapatabilir. İkisini tek
bayrağa koymak, A-2'nin ölçülmüş davranışını ölçülmemiş bir davranışla karıştırır.

## Aşırı kapatma riski — bu fazın asıl tehlikesi

A-2'nin riski düşüktü: alan tamamen boşsa kural gerçekten çalışamaz. A-3'ün riski yüksek:

1. **Çok kaynaklı kural.** `veri_kaynaklari` birden fazlaysa, kural kaynakların **hepsinde** mi
   ölü olmalı, **birinde** ölü olması yetmeli mi? → Karar: **hepsinde** ölü olmalı. A-2'nin
   "kısmen ölü kural çalışmaya devam eder" kuralının aynısı.
2. **Sinyal birden fazla kanalı toplayabilir.** `veri_hacmi_z` tek bir günün `bytes_out`
   toplamıdır — web + email + file. Web ölüyse sinyal **zayıflar**, sıfırlanmaz. Bu, "kural ölü"
   demek için yeterli mi? → Karar: kuralın `veri_kaynaklari`'nda yazılı kanallar ölüyse ölüdür.
   Kural yazarı hangi kanala baktığını orada beyan etmiştir; beyanı esas alıyoruz.
3. **`SOURCE_ALIAS`.** Katalogdaki kaynak adı (`ad_oturum`, `dosya_sunucu`) olay tablosundaki
   `source` değilidir; motor `SOURCE_ALIAS` ile çevirir. Aynı çeviri burada da kullanılacak,
   yoksa her kural "kaynağı bilinmiyor" olur.

## Başarı eşikleri — ölçümden ÖNCE

1. **Bayrak kapalıyken** sonuç birebir A-2 ile aynı (skor, kuyruk, kural tetiklenme).
2. **Bayrak açıkken sentetik veride** skor, kuyruk ve kural tetiklenme **birebir aynı**; değişen
   yalnız rapor. A-2'deki sözleşmenin aynısı: mekanizma RAPORU değiştirir, SKORU değiştirmez.
3. **Bayrak açıkken r6.2'de** `UEBA-0003` `sinanamaz — şema: bytes_out@proxy` raporlanır.
4. **Bayrak açıkken r4.2'de** `UEBA-0003` **canlı** kalır (r4.2'de `http.csv:content` vardır).
   Bu, mekanizmanın körü körüne kapatmadığının testidir — 3 ile birlikte okunmalı.

Ölçüt 3 **ve** 4 birlikte geçmezse mekanizma işe yaramıyor demektir: biri kapatmayı, diğeri
kapatmamayı sınıyor.

## Beklentiler — karamsar

1. **Hiçbir insider kazanılmayacak.** Hiç. Bu faz tek bir tespit eklemiyor.
2. r6.2'nin yakalaması `3/4` iken `3/3 ölçülebilir + 1 ölçülemeyen` olarak raporlanacak. **Pay
   aynı, payda küçülüyor** — oran 0,75'ten 1,00'a çıkacak ve bu bir **iyileşme değildir**, aynı
   gerçeğin dürüst ifadesidir. Raporda bu cümle açıkça yazılacak, yoksa sayı şişirme gibi okunur.
3. r4.2'de hiçbir şey değişmeyecek.
4. En olası başarısızlık: `veri_kaynaklari` beyanları kuralın gerçekte okuduğu kanallarla
   uyuşmuyor olabilir. O hâlde ölçüt 4 kalır ve **mekanizma değil katalog** düzeltilir — ama
   düzeltme ayrı bir commit ve ayrı bir gerekçeyle, bu ölçümün içinde değil.

## Bu fazdan sonra ne YAPILMAYACAK

Kanal düzeyi çözünürlük `bytes_out@proxy` gibi **alan × kaynak** çiftinde durur. Daha ince
kırılımlar (ör. `bytes_out@proxy@dropbox.com`) **yapılmayacak**: o noktada şema profili, kuralın
kendisini yeniden yazmaya başlar ve mekanizmanın ölçtüğü şey ("veri var mı") ile kuralın ölçtüğü
şey ("davranış anormal mi") birbirine karışır.
