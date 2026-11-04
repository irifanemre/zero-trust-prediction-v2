# Faz A-3 — kanal düzeyi şema kararı: sonuçlar

**Ölçüm: 31 Ekim 2026, 4 Kasım'da yeniden üretildi.** Ön kayıt: `docs/faz-a3-on-kayit.md`
(ölçümden önce yazıldı). Dondurma: `kurallar-donduruldu-v9` → `donmuş durumla aynı`.
`scripts/sema_karar_dogrula.py --kanal`, r4.2 ve r6.2, 30 günlük pencere.

> **Sonuç: fazın HEDEFİ ÇÜRÜDÜ.** Mekanizma çalışıyor ama A-2'nin bulamadığı vakayı (`UEBA-0003`
> / r6.2 / S5) **kanal düzeyinde de bulamıyor** — çünkü sorun çözünürlükte değil, sinyalin
> kendisinde. Bayrak varsayılan **kapalı** kalıyor.

## Ön kayıtlı ölçütler

Ön kayıt şöyle yazmıştı: *"Ölçüt 3 **ve** 4 birlikte geçmezse mekanizma işe yaramıyor demektir:
biri kapatmayı, diğeri kapatmamayı sınıyor."*

| # | Ölçüt (ölçümden önce yazıldı) | Sonuç |
|---|---|---|
| 1 | Bayrak kapalıyken sonuç birebir A-2 ile aynı | **GEÇTİ** |
| 2 | Bayrak açıkken sentetik veride skor/kuyruk/tetiklenme birebir aynı | **GEÇTİ** |
| 3 | r6.2'de `UEBA-0003` `sinanamaz — bytes_out@proxy` raporlanır | **KALDI** |
| 4 | r4.2'de `UEBA-0003` **canlı** kalır | **GEÇTİ** |

3 kaldı, 4 geçti → ön kayıtlı karara göre **mekanizma hedefine ulaşmadı**.

## Ölçülen: iki sürümün kanal tablosu BİREBİR AYNI

| Alan | ad | dlp | email | file_server | proxy |
|---|---|---|---|---|---|
| `action` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `app` | ✘ boş | ✘ boş | ✔ | ✘ boş | ✔ |
| `bytes_out` *(kanallar arası toplanır — karara girmez)* | ✘ boş | ✘ boş | ✔ | ✔ | **✘ boş** |
| `cmdline` | ✘ boş | ✘ boş | ✘ boş | ✘ boş | ✘ boş |
| `outcome` | ✘ sabit | ✘ sabit | ✘ sabit | ✘ sabit | ✘ sabit |
| `process` | ✘ boş | ✘ boş | ✘ boş | ✘ boş | ✘ boş |
| `resource` | ✘ boş | ✘ boş | ✘ boş | ✘ boş | ✘ boş |
| `source` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `time` | ✔ | ✔ | ✔ | ✔ | ✔ |

r4.2 ve r6.2 için **aynı tablo**. Şema kararı da aynı: her iki sürümde **2 kural** ölü
(`UEBA-0006`, `UEBA-0008`) — yani alan düzeyinin (A-2) verdiği sonucun aynısı. Kanal düzeyi
CERT'te **ek bir kural bulmuyor**.

### Tablonun asıl söylediği: `bytes_out@proxy` HER İKİ SÜRÜMDE boş

Bu, A-2'nin teşhisini düzeltiyor. A-2 "r6.2'nin `http.csv`'sinde `content` kolonu yok" demişti.
Ölçüm:

```python
# cert.py
http_cols = ["id", "date", "user", "pc", "url"]   # 'content' OKUNMAZ (4.2 etik sınır / 20.1)
...
bytes_out=(ht["content"].str.len().values if "content" in ht else 0)   # bu dal ÖLÜ
```

`content` hiçbir sürümde okunmuyor, dolayısıyla `"content" in ht` **her zaman** False. Yani:

| | r4.2 | r6.2 |
|---|---|---|
| `http.csv`'de `content` kolonu | **var** | yok |
| Ayrıştırıcı okuyor mu | **hayır** | hayır |
| Web `bytes_out` | **0** | 0 |

Sonuç aynı, sebep farklı, ve fark önemli: bu bir **r6.2 sürüm farkı değil**, her CERT koşusunda
geçerli **kalıcı bir ölçüm sınırı**. Etik sınırın (sayfa metni okunmaz) ölçülebilir bedeli budur.

## Ölçüt 3 neden kaldı: sorun çözünürlük değil, SİNYAL

`UEBA-0003`'ün okuduğu sinyal `veri_hacmi_z`. Onun kaynağı:

```python
f["bytes_out"] = g["bytes_out"].sum()          # features.py:61 — KAYNAK FİLTRESİ YOK
files = ev[ev["source"] == "file_server"]      # 68 — filtreli
f["proc_count"] = ev[ev["source"] == "edr"]... # 73 — filtreli
f["usb_count"] = ev[(ev["source"] == "dlp")... # 75 — filtreli
```

`veri_hacmi_z` **kanallar arası günlük toplamdır**. Web kanalı boşsa sinyal **zayıflar,
sıfırlanmaz** — r4.2'de `UEBA-0003` skor payının 0,68'ini üretiyor ve bu pay e-posta ile dosya
baytlarından geliyor.

Dolayısıyla `bytes_out@proxy` boş diye `UEBA-0003`'ü kapatmak **yanlış kapatmadır**. Kanal düzeyi
çözünürlük, kanala özel olmayan bir sinyalde doğru cevabı veremez.

> **Ön kayıtın kararı yanlıştı.** Ön kayıt şöyle demişti: *"kural yazarı hangi kanala baktığını
> `veri_kaynaklari`'nda beyan etmiştir; beyanı esas alıyoruz."* Ölçüm bunu çürüttü:
> `veri_kaynaklari` üretimde hangi telemetrinin **gerektiğini** beyan eder, sinyalin hangi kanalı
> **topladığını** beyan etmez. İkisini eşitlemek kategori hatasıdır.

## Uygulama sırasında mekanizma kendi kendini iki kez düzeltti

### 1. Kanal içinde TEKİLLİK anlamsızdır — ve bu neredeyse USB kuralını susturuyordu

İlk sürüm tekilliği kanal başına ölçtü. Sonuç: `source` gruplama değişkenidir ve kendi grubu
içinde tek değerlidir; `action` `dlp` kanalında her zaman `usb_copy`, `proxy`'de her zaman
`http`'tir. Profil bunları "sabit ⚠" gösterdi ve r4.2'de **5 kural** ölü ilan edildi:

| Kural | Sebep (yanlış) | Gerçek |
|---|---|---|
| UEBA-0003 | `bytes_out@proxy` boş | kanallar arası toplanıyor → canlı |
| UEBA-0005 | `source@ad` "sabit" | gruplama değişkeni → yapısal, canlı |
| **UEBA-0017** | `action@dlp`, `source@dlp` "sabit" | `dlp`'de eylem zaten tek türdür → canlı |
| UEBA-0006 | `outcome@ad` sabit | **doğru** |
| UEBA-0008 | `process`, `cmdline`, `resource` boş | **doğru** |

`UEBA-0017`, r4.2'nin **34 senaryosunun 31'inin dayandığı USB kuralıdır.** Mekanizma, sistemin en
değerli kuralını susturacaktı. Düzeltme: tekillik **alan** düzeyinden alınır, kanal yalnız
"bu kanalda hiç değer var mı" sorusunu cevaplar. Düzeltmeden sonra r4.2'de 5 → **2** ölü kural.

### 2. Kanallar arası toplanan alanlar karardan muaf

`KANALLAR_ARASI = {"bytes_out"}`. Kanal profili yine **ölçülür** ve tabloda görünür (teşhis
değerlidir), ama karara girmez. Alan **tamamen** boşsa kural yine ölür — muafiyet "hiç bakma"
demek değil.

Her iki düzeltme de testle bağlandı: `test_A3_kanal_icinde_YAPISAL_sabitlik_olu_sayilmaz`,
`test_A3_KANALLAR_ARASI_toplanan_alan_kanal_kararindan_MUAF`.

## Mekanizma neye YARIYOR (silinmedi, kapalı duruyor)

Kanal düzeyi, **kanala özel** sinyallerde doğru çalışıyor ve testle gösterildi:

```
action@dlp boş  →  usb_count üretilemez  →  UEBA-0017 SINANAMAZ
   (alan düzeyi bunu göremez: `action` diğer kanallarda dolu)
```

Bu CERT'te hiç olmuyor ama **gerçek kurulumda olur**: DLP beslemesi bir alanını kaybederse,
e-posta ağ geçidi bir alanı göndermeyi bırakırsa. Yani mekanizmanın değeri CERT'te değil, sahada.
Ölçülmediği için **varsayılan kapalı** — grafa uygulanan ölçütün aynısı: iki farklı veride değer
üretmeyen bileşen varsayılan açılmaz.

## S5-MBG3183 nasıl yakalanır: bu katmanda değil

S5, 57 saniyede 4 Dropbox yüklemesi — **saf web** sızıntısı. Yakalamak için gereken:

| Gereken | Nerede |
|---|---|
| Kanal bazlı hacim özelliği (`bytes_out@proxy`) | `features.py` — ÖZELLİK işi |
| O özelliği okuyan kural | katalog — KURAL işi |
| Web yükleme hacminin gerçekten ölçülmesi | veri kaynağı — CERT'te **mümkün değil** |

Üçüncüsü CERT'te etik sınır yüzünden kapalı, dolayısıyla S5 **CERT'te hiçbir kuralla
yakalanamaz**. Gerçek kurulumda proxy'nin kendi `bytes_sent` alanı vardır ve sayfa metni
okumadan ölçülür — yani sahada çözülebilir, bu veri setinde çözülemez.

**Doğru rapor cümlesi:** r6.2'de S5 "kaçırıldı" değil, **"bu veri setinde ölçülemez"**. Ama bunu
raporlatmak için `veri_hacmi_z`'nin kanal bazlı bir kardeşi gerekiyor — o da Faz B'nin konusu
(üreteç/özellik işi), bu katmanın değil.

## Varsayılan: KAPALI (iki bayrak da)

| Bayrak | Varsayılan | Gerekçe |
|---|---|---|
| `sema_farkindaligi` (A-2) | kapalı | Ölçüt 3 kalmıştı; 2 gerçek ölü kural buldu ama asıl vakayı göremedi |
| `sema_kanal_duzeyi` (A-3) | kapalı | Ölçüt 3 yine kaldı; CERT'te ek bir kural bulmuyor |

Bu, iki fazın değersiz olduğu anlamına gelmiyor. Elde kalan ölçülmüş bilgi:

1. **`UEBA-0006` ve `UEBA-0008` her CERT koşusunda yapısal olarak ölü** (toplam ağırlık 11).
   r4.2'nin 11 ablasyon varyantının hepsinde ve r6.2'nin üç koşusunda "bu veride desen görülmedi"
   diye raporlanmışlardı. Bu rakamları okuyan herkes 25 kuralın 25'inin sınandığını sanıyordu.
2. **Web hacmi CERT'te hiç ölçülmüyor** — r6.2'ye özgü değil, kalıcı sınır.
3. **Harita hatası sınıfı gerçek ve tekrarlayan:** bu iki fazda üç tane bulundu
   (`files_accessed`→`resource`, `kesif_genisligi_akran_kati`→`recon_process_count`,
   `veri_kaynaklari`→kanal). Üçü de "ad doğru görünüyor" diye geçmişti. Zinciri üretim koduna
   karşı denetleyen testler o yüzden var.

## Bir sonraki adım

Ön kayıttaki plan (Faz B: e-posta/webmail/baskı senaryoları) **değişmiyor**. Eklenen tek madde:
Faz B'de sentetik üreteç kanal bazlı hacim üretirse, `bytes_out@kanal` özelliği de o fazda
ölçülebilir hâle gelir. Önce ön kayıt, sonra kod.
