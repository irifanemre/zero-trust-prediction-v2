# Faz B — kanal senaryoları: sonuçlar

**Ölçüm: 5 Kasım 2026.** Ön kayıt: `docs/faz-b-on-kayit.md` (koddan önce yazıldı).
Araç: `scripts/kanal_senaryo_olcumu.py`. 403 test geçiyor. **Dondurma v9 değişmedi** —
ön kayıttaki "hiçbir donmuş dosyaya dokunulmayacak" kısıtı tutuldu.

> **Altı ölçütten beşi geçti.** Üç kanal kuralı ilk kez sınandı. Ama asıl bulgu ölçütlerin
> içinde değil: `UEBA-0023`'ün eşiği **hiç doğrulanmamıştı** ve şimdi 80 kullanıcının 51'inde
> tetikliyor. Gölge modun neden var olduğu ilk kez somut olarak görüldü.

## Ön kayıtlı ölçütler

| # | Ölçüt (ölçümden önce yazıldı) | Sonuç |
|---|---|---|
| 1 | Mevcut kapsama ≥ 7/8, negatif kontrol temiz | **GEÇTİ** — kuyrukta 7/8, S9 temiz |
| 2 | `UEBA-0023` S11'de tetiklenir (şu an 0) | **GEÇTİ** — pencerede 4 tetiklenme |
| 3 | `UEBA-0024`'ün kurumsal yanlış pozitifi sıfırlanır, S12'de tetiklenir | **GEÇTİ** |
| 4 | `UEBA-0022` gerçek tabana karşı sınanır | **GEÇTİ** — taban 3 → 278 kullanıcı-günü |
| 5 | `eposta_dis_z`, `BILINEN` ulaşılamazlık listesinden çıkar | **GEÇTİ** |
| 6 | Üç yeni senaryo negatif kontrolde tetiklenmez | **KALDI** — `UEBA-0023` bir kez tetikledi |

## Önce / sonra

| Kanal sinyali | Önce | Sonra |
|---|---|---|
| `ext_email_bytes` | **0** (kaynak yok) | 2,48 GB / 4.460 kullanıcı-günü |
| `ext_email_count` | **0** | 11.058 |
| `cloud_app_count` | 9 olay / **3** kullanıcı-günü | 563 olay / **278** kullanıcı-günü |
| `webmail_count` | 7.714 / 3.954 (**kurumsal** e-posta) | 557 / 266 (**kişisel** webmail) |
| Tanınan app sözcüğü | 1 (`personal_cloud`) | 2 (`personal_cloud`, `file_transfer`) |
| Kaynak sayısı | 6 | 7 (`email` eklendi) |

| Kural | Önce | Sonra | Senaryosunda |
|---|---|---|---|
| `UEBA-0022` bulut | 3 tetiklenme (sıfır tabana karşı) | 12 / 11 kullanıcı | **S13 ✔** 1 tetiklenme |
| `UEBA-0023` dış e-posta | **0 — hiç sınanmadı** | **108 / 51 kullanıcı** | **S11 ✔** 4 tetiklenme |
| `UEBA-0024` webmail | 6 (hepsi kurumsal trafik) | 12 / 9 kullanıcı | **S12 ✔** 3 tetiklenme |

## Bulgu 1 — `UEBA-0023`'ün eşiği hiç doğrulanmamıştı (dört katmanlı hata)

Ön kayıt "en olası başarısızlık eşiğin sentetik hacim dağılımına uymaması" demişti. Yanlıştı.
Gerçek zincir:

| Adım | Ne oldu |
|---|---|
| 1 | v8'de `UEBA-0023` yazıldı, dış e-posta hacim tabanı **5 MB** |
| 2 | Ölçümde **0 tetiklenme** görüldü |
| 3 | Sebep "eşik çok yüksek" diye teşhis edildi, taban **50 KB**'a çekildi (100 kat) |
| 4 | Kural **yine tetiklenmedi** — çünkü iki bağımsız yapısal sebep üst üste binmişti |
| 5 | Faz B ikisini de kaldırdı; 50 KB tabanı **80 kullanıcının 51'inde** tetikliyor |

İki yapısal sebep:

1. **Sentetik üreteçte `email` kaynağı yoktu** — biliniyordu, `BILINEN` listesine yazılmıştı.
2. **Varsayılan `available_sources` `email` İÇERMİYOR.** Bu bilinmiyordu. `UEBA-0023`, varsayılan
   yapılandırmayı kullanan **her koşuda** "kaynak yok" diye devre dışıydı — sinyali ne kadar güçlü
   olursa olsun hiç değerlendirilmiyordu. Katalogdaki 25 kuraldan **devre dışı kalan tek kural.**

```
varsayılan available_sources: ('ad', 'hr', 'proxy', 'edr', 'vpn', 'file_server', 'dlp')
                                                                              ↑ email YOK
UEBA-0023.veri_kaynaklari: [eposta] → SOURCE_ALIAS → email → kaynak yok (11.1)
```

CERT kör koşuları etkilenmedi, çünkü `kor_kosu_r52.py` kaynak listesini **veriden türetiyor**
(`set(data.events["source"].unique()) | {"hr"}`). Yani kural CERT'te değerlendirildi, sentetik
veride ve varsayılan yapılandırmalı her testte değerlendirilmedi.

> **Sonuç: v8'in eşik değişikliği güvenilmez.** Tetiklenemeyen bir kural için yapıldı, hiç
> doğrulanmadı ve şimdi çok gevşek olduğu ölçülüyor. Ön kayıt "eşik DEĞİŞTİRİLMEYECEK" diyordu;
> değiştirilmedi. Yeniden türetilmesi gerekiyor ve bu **ayrı bir ön kayıtla** yapılacak.

### Tekrarlayan hata sınıfının DÖRDÜNCÜ örneği

Önceki üçü: `UEBA-0003` (web hacmi hiç okunmuyor), `UEBA-0022` (seyrek sayaçta `p < 0.001`),
`UEBA-0023`'ün ilk tabanı (5 MB, yanlış ölçekten). Dördüncüsü farklı ve daha sinsi: **iki sebep
üst üste binince, birini çözmek sonucu değiştirmiyor** ve kişi yanlış teşhise daha da ikna oluyor.

`scripts/esik_ulasilabilirlik.py` birinci sebebi yakalıyordu. İkinciyi yakalayamadı çünkü sinyal
aralığına bakıyor, kuralın **değerlendirilip değerlendirilmediğine** bakmıyor. Bu, Faz A-2'nin
`sinanamaz` ayrımının eşik denetiminde karşılığı olmadığı anlamına geliyor — kayda geçiyor.

## Bulgu 2 — gölge mod ilk kez somut olarak işe yaradı

`UEBA-0023` günde ~6 uyarı, kullanıcıların %64'ünde tetikliyor. Bütçe 6/gün. Yani kural yayında
olsaydı **kuyruğun tamamını tek başına doldurabilirdi** ve gerçek tespitleri dışarı iterdi.

Hiçbiri olmadı: kural gölge modda doğdu, bir kez bile analiste gitmedi, precision'ı ölçüldü ve
ölçüm onu yayına almamayı söylüyor. 13.6'daki mezuniyet şartı (precision ≥ %25 **ve** ≤ 2 uyarı/gün
**ve** ≥ 14 gün) tam bunun için yazılmıştı; ilk kez bir kuralı gerçekten engelledi.

## Bulgu 3 — `webmail` çakışması: aynı kelime, zıt anlam

| | `webmail` ne demekti |
|---|---|
| CERT `URL_CATEGORIES` | gmail, yahoo, hotmail, outlook.com → **kişisel**, ağ geçidini atlama |
| `features.py:95` kuralın niyeti | kişisel webmail |
| Sentetik üreteç (önce) | **her bölümün normal iş uygulaması** — 7.714 olay, trafiğin %5,2'si |

`UEBA-0024`'ün önceki 6 tetiklenmesinin tamamı kurumsal e-posta trafiğindeydi: kural hatalı değil,
üreteç yanlış kelimeyi kullanıyordu. Kurumsal e-posta `corp_mail` oldu — tespit katmanı onu
tanımıyor ve **tanımaması doğru**.

Sonrasında `UEBA-0024` 12 kez / 9 kullanıcıda tetikliyor. Sayı arttı ama **anlamı değişti**: artık
gerçek bir kişisel-webmail tabanı üzerindeki sıçramaları gösteriyor, yanlış sınıflandırılmış iş
trafiğini değil. 9/80 kullanıcı hâlâ yüksek; gölge modda kalması doğru.

## Bulgu 4 — "ilk kez" ile "sıçrama" farkı ölçüldü

Önce `cloud_app_count` 80 kullanıcının 12 gününde **3 kullanıcı-günü** doluydu ve üçü de S1
enjeksiyonuydu. Yani `UEBA-0022` "hayatında ilk kez bulut" sinyalini ölçüyordu — ölçmesi kolay
ama bir kurumda işe yaramayan sinyal. Taban eklendikten sonra 278 kullanıcı-günü dolu ve kural
**kendi tabanına göre sıçramayı** ölçmek zorunda.

Ön kayıt bunun mevcut kapsamayı düşürebileceğini yazmıştı (S1 `personal_cloud`'un yeniliğine
dayanıyor). **Düşmedi:** S1 hâlâ GEÇTİ. Yani S1'in sinyali tek bir kanala bağlı değilmiş.

## Değişenler

| # | Ne | Dosya | Donmuş? |
|---|---|---|---|
| 1 | İş webmail'i `corp_mail`; `webmail` artık yalnız kişisel | `data/synthetic.py` | hayır |
| 2 | `email` kaynağı: `email_internal` tabanı + `email_external` hacmi | `data/synthetic.py` | hayır |
| 3 | `TABAN_KANAL_OLASILIK` — seyrek ama sıfır olmayan kanal tabanı | `data/synthetic.py` | hayır |
| 4 | S11 dış e-posta · S12 webmail atlama · S13 bulut sıçraması | `data/synthetic.py` | hayır |
| 5 | `GÖLGEDE` kapsama durumu (**ön kayıt dışı**, aşağıda sapma 2) | `metrics.py` | hayır |
| 6 | Ölçüm aracı + gölge atfı | `scripts/kanal_senaryo_olcumu.py` | hayır |
| 7 | `eposta_dis_z` `BILINEN` listesinden çıktı | `tests/test_esik_ulasilabilirlik.py` | hayır |

**Dondurma v9 değişmedi.** `features.py`, `schema.py`, kurallar, eşikler aynı — üreteç yeni kelime
icat etmedi, sözlükte zaten var olanları kullanmaya başladı.

## Ne YAPILMADI ve neden

- **`UEBA-0023`'ün eşiği değiştirilmedi.** Ön kayıt yasaklıyordu. Ölçümü gördükten sonra eşik
  oynatmak, v8'de bir kez yapılan ve sapma olarak kayda geçen hatanın aynısı olurdu.
- **Varsayılan `available_sources`'a `email` eklenmedi.** `config.py` donmuş ve bu bir **dağıtım
  kararı**: e-posta ağ geçidi olmayan bir kurumda `UEBA-0023` gerçekten çalışmamalı. Ama varsayılan
  listede `dlp` ve `edr` varken `email`'in olmaması tutarsız görünüyor. **Karar kullanıcıda**,
  ayrı ön kayıtla.
- **`ext_email_attachments` üretilmedi.** `attachments` kolonu `EVENT_COLUMNS`'ta yok, `schema.py`
  donmuş. Maliyeti ölçüldü: hiçbir yayındaki kural `eposta_ek_sayisi` okumuyor → kayıp sıfır.
- **`linkedin`/`job_portal` → `job_search` çakışması düzeltilmedi.** Ön kayıtta kapsam dışıydı:
  "satışçının LinkedIn kullanması ayrılık sinyali midir" bir kural tasarımı sorusu.

## Bunun ne OLMADIĞI

Üç kural artık **sınanabilir**, ama hâlâ **doğrulanmış değil**. Ön kayıtta yazdığı gibi: kuralın
kendisi için yazılmış senaryoda tetiklenmesi zayıf kanıttır — sınavı da cevap anahtarını da aynı
kişi yazıyor. Kazanç dolaylı ve iki tane:

1. `UEBA-0024`'ün yapısal yanlış pozitif kaynağı kalktı.
2. Üç kural artık **ulaşılabilir**, yani ileride bir değişiklik onları sessizce bozarsa eşik
   denetimi yakalar. Önce bozulsalar kimse fark etmezdi — `UEBA-0023`'te tam bu oldu.

**CERT sayıları bu fazdan hiç etkilenmedi** (üreteç yalnız sentetik veriyi etkiler). r4.2/r6.2
sonuçları aynı; yakalama artmadı, artması da beklenmiyordu.

## Sırada

`UEBA-0023`'ün eşiğinin yeniden türetilmesi artık **ölçülebilir** bir iş ve ayrı ön kayıt
gerektiriyor. Varsayılan kaynak listesi kararı kullanıcıda. Faz C (çok ufuklu öngörü) bekliyor.
