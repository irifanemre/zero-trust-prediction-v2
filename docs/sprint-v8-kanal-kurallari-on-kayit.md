# Sprint v8 — eksik kanal kuralları: ön kayıt

**Yazım: 31 Ekim 2026, ölçümden ÖNCE.** Bu belge koşudan sonra değiştirilmez; sapmalar ayrıca kaydedilir.

## Neden

USB kapalı bir ortamda veri sızdırma yok olmaz, **kanal değiştirir**. Kural kümesi kanal bazında
dengesiz: AD/oturum 5 kural, proxy 3, dosya sunucusu 4 ortak, DLP 1 (USB) — **e-posta 0 kural**,
**yazdırma 0 kural**, bulut senkronizasyonu dolaylı.

İki somut boşluk ölçüldü:

### Boşluk 1 — E-posta için tek bir sinyal yok

E-posta olayları ayrıştırılıyor (`email_external` / `email_internal`, gerçek `size` alanıyla) ama
`features.py` içinde **sıfır** e-posta işlemesi var. E-posta baytları genel `bytes_out` havuzuna
karışıyor ve web trafiğiyle **aynı baz çizgisini** paylaşıyor.

Bu, v6-D'de ölçülen maskelemenin birebir aynısı, farklı kanalda: yoğun web kullanan bir
kullanıcının dış e-posta ile veri çıkarması, kendi web tabanına gömülür.

Ayrıca `attachments` kolonu CSV'den **okunuyor ama hiç kullanılmıyor** — ek sayısı, hacimden
bağımsız bir sinyaldir (20 küçük ek, 1 büyük ekten farklı bir davranıştır).

### Boşluk 2 — `webmail` tanınıyor ama hiçbir yerde sayılmıyor

`URL_CATEGORIES` içinde `webmail` kategorisi var (gmail, yahoo, hotmail, outlook) ama bu kategori
ne `SENSITIVE_APPS` ne `CLOUD_APPS` kümesinde. Yani kişisel webmail'e yükleme **tanınıyor ve
görmezden geliniyor**. Kurumsal e-posta ağ geçidinin denetlediği bir ortamda kişisel webmail,
denetimi atlamanın en basit yoludur.

## Değişiklik

| # | Ne |
|---|---|
| 1 | `features.py`: `eposta_dis_bayt`, `eposta_dis_sayi`, `eposta_ek_sayisi`, `webmail_count` |
| 2 | `profile.py`: `eposta_dis_z` (kendi dış e-posta tabanına göre), `webmail_7g_toplam`, `webmail_7g_p` |
| 3 | `data/cert.py`: `attachments` alanı olay tablosuna taşınır |
| 4 | **`UEBA-0023`** — dış e-posta hacminde anormal artış |
| 5 | **`UEBA-0024`** — kişisel webmail kullanımında ani artış |

Her ikisi de **gölge modda** doğar (13.6).

## Eşikler — ölçümden ÖNCE sabitlendi

### UEBA-0023 (dış e-posta hacmi)

```
eposta_dis_z > 3.5
```

`UEBA-0003`'ün (genel veri hacmi) birebir aynı eşiği ve aynı ölçeği (2,0). Gerekçe: aynı tür
sinyal (hacim z-skoru), aynı istatistik (robust-z), dolayısıyla farklı bir eşik seçmek için
sebep yok. **Ağırlık 6** — `UEBA-0003`'ün 8'inden düşük, çünkü tek kanalı ölçüyor; `UEBA-0021`'in
4'ünden yüksek, çünkü hacim niyetten daha doğrudan kanıttır.

### UEBA-0024 (kişisel webmail)

```
webmail_7g_toplam >= 3
webmail_7g_p < 0.02
```

`UEBA-0022`'nin birebir aynı kalıbı ve aynı sabitleri. Gerekçe: webmail de **seyrek bir sızıntı
kanalı**dır ve v6-D'de ölçülen asimetri (seyrek sayaçta 0,001 yapısal olarak sert) burada da
geçerlidir. **Ağırlık 6** — `UEBA-0022` ile aynı.

Taban zemini `max(mu, 0.02)` — yine `UEBA-0022` ile aynı.

**Bu değerler hiçbir sonuç görülmeden yazıldı.** Sonradan değiştirmek sapma kaydına girer.

## Başarı eşikleri

Her kural için, yayına çıkması için **üçü birden**:

1. r4.2'de kapsama **düşmez** (22/34 ya da üstü)
2. Vaka hacmi artışı **%15'i geçmez**
3. Projenin gölge-mod standardı (13.6): precision **≥ %25**, günlük ortalama **≤ 2** uyarı

Üçüncü şart v6-D'de `UEBA-0022`'yi gölgede bıraktı (precision %15,8). Aynı çıta burada da
geçerlidir ve gevşetilmeyecektir.

## Beklentiler — karamsar yazıldı

1. **`UEBA-0023` r4.2'de kapsamayı artırmaz.** r4.2'nin 34 senaryosunun 31'i USB'ye bağımlı;
   e-posta sızdırması senaryo kümesinde yok denecek kadar az.
2. **`UEBA-0024` de artırmaz**, aynı sebeple.
3. **İkisi de gölge-mod precision eşiğini (%25) geçemez** — `UEBA-0022` geçemedi, bunlar da
   benzer seyreklikte kanallar.

Beklentiler tutarsa sonuç şudur: **bu kuralların değeri CERT'te ölçülemez.** Değerleri, USB'nin
kapalı olduğu ve e-posta/webmail'in birincil kanal olduğu bir ortamda ortaya çıkar — ve bunu
ölçmenin tek yolu kendi üretecimize o senaryoları eklemektir.

Bu, kuralları yazmamak için sebep değildir: olmayan kanala kural yazmamak, kanal açıldığında
**kör kalmak** demektir. Ama "ölçtük, işe yarıyor" denemeyeceği baştan kayda geçirilir.
