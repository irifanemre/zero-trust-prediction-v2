# Faz B ön kaydı — kanal senaryoları: üreteç sözlüğü ve USB dışı sızıntı

**Yazıldı: 5 Kasım 2026, kod değişikliğinden ÖNCE.** Dayanak: aşağıdaki ölçüm (`scripts/kanal_senaryo_olcumu.py`).

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Neden bu faz: hedef ortamda USB YASAK

Kullanıcının kurulum ortamında USB kullanımı yasak. Yani r4.2'nin 34 senaryosunun **31'i** o
ortamda karşılığı olmayan bir kanalı ölçüyor. Değeri olan kanallar şunlar: **dış e-posta, kişisel
webmail, bulut yükleme.** Bu üç kanalın kuralları (`UEBA-0022/0023/0024`) v6-D ve v8'de yazıldı,
üçü de **gölge modda** doğdu ve **hiçbir veride doğrulanamadı**.

## Ölçülen durum — referans (kod değişikliğinden önce)

80 kullanıcı, 12 gün, tohum 7, bütçe 6:

| Kanal sinyali | Toplam | Sıfır olmayan kullanıcı-günü | Yorum |
|---|---|---|---|
| `ext_email_bytes` | **0** | **0** | üreteçte `email` kaynağı HİÇ YOK |
| `ext_email_count` | **0** | **0** | aynı |
| `cloud_app_count` | 9 | **3** | yalnız S1'in enjekte ettiği `personal_cloud` |
| `sensitive_app_count` | 9 | 3 | aynı — normal kullanıcıda **taban sıfır** |
| `webmail_count` | **7.714** | **3.954** | her bölümün normal iş uygulaması |

| Kural | Tetiklenme | Gerçekte ne ölçüyor |
|---|---|---|
| `UEBA-0022` bulut | 3 | S1 enjeksiyonu, **sıfır tabana** karşı → "hayatında ilk kez", sıçrama değil |
| `UEBA-0023` dış e-posta | **0** | **hiç sınanmadı** |
| `UEBA-0024` kişisel webmail | **6** | **KURUMSAL e-posta trafiği** — yapısal yanlış pozitif |

Mevcut kapsama: **7/8** pozitif senaryo (S7 kısmi pencere yüzünden kaçıyor), negatif kontrol temiz.

### Asıl arıza: iki sözlük birbiriyle konuşmuyor

```
üreteç app sözcükleri : bank_portal, cloud_console, crm, docs_wiki, efatura, erp, excel_online,
                        git, hris, intranet, jira, job_portal, linkedin, pkg_registry, slides,
                        ssh_gw, ticketing, webmail, wms
tespit SENSITIVE_APPS : cloud_storage, file_transfer, hacking_tools, job_search, paste_site,
                        personal_cloud, webdav

KESİŞİM: BOŞ   (tek ortak sözcük: `webmail`)
```

Kesişim boş olduğu için sentetik veride hassas kategori sinyali **yalnız senaryo enjeksiyonundan**
gelir; normal davranış tabanı yoktur. Ve tek ortak sözcük olan `webmail`, **iki sözlükte zıt
anlama geliyor**:

| | `webmail` ne demek |
|---|---|
| CERT (`URL_CATEGORIES`) | gmail, yahoo, hotmail, outlook.com → **kişisel**, ağ geçidini atlama |
| `features.py:95` | kuralın niyeti: kişisel webmail |
| Sentetik üreteç | **her bölümün normal iş uygulaması** (7.714 olay, trafiğin %5,2'si) |

`UEBA-0024`'ün 6 tetiklenmesi buradan geliyor. Kural hatalı değil, **üreteç yanlış kelimeyi
kullanıyor** — ve bu, kuralın gerçek niyetinin hiçbir zaman sınanamadığı anlamına da geliyor.

## Yaklaşım: sözlük sözleşmesi tespit katmanının

Tespit katmanının sözlüğü **birincil doğrulama kaynağıyla (CERT) aynıdır**; dolayısıyla sözleşme
odur ve **üreteç ona uyacak**. Tersi (tespit katmanını üretece uydurmak) CERT'le uyumu bozar.

## Değişecekler

| # | Ne | Dosya | Donmuş? |
|---|---|---|---|
| 1 | İş webmail'i `corp_mail` olur; `webmail` yalnız **kişisel** anlamına gelir | `data/synthetic.py` | hayır |
| 2 | `email` kaynağı eklenir: `email_internal` tabanı + `email_external` hacim/ek | `data/synthetic.py` | hayır |
| 3 | Normal kullanıcılara **gerçek bulut tabanı** (seyrek ama sıfır değil) | `data/synthetic.py` | hayır |
| 4 | S11 dış e-posta sızıntısı · S12 webmail ağ geçidi atlama · S13 bulut sıçraması | `data/synthetic.py` | hayır |
| 5 | Ölçüm aracı | `scripts/kanal_senaryo_olcumu.py` | hayır |

**Kısıt: hiçbir donmuş dosya değişmeyecek.** `features.py`, `schema.py`, kurallar ve eşikler
aynı kalır — çünkü üreteç zaten o sözlükte var olan kelimeleri kullanmaya başlıyor, yeni kelime
icat etmiyor. Faz B donmuş bir dosyaya dokunmak zorunda kalırsa **tasarım yanlış demektir** ve
durup yeniden düşünülecek. Dondurma sürümü **değişmeyecek** (v9 kalacak).

### Kapsam DIŞI: `linkedin` / `job_portal` → `job_search` çakışması

Üreteç `linkedin` ve `job_portal` yayıyor; CERT bunları `job_search` kategorisine düşürüyor, yani
**ayrılık niyeti** sinyali sayıyor. Üreteçte ise bunlar Satış ve İK bölümlerinin **normal iş
araçları**.

Bu bilerek düzeltilmiyor: "satışçının LinkedIn kullanması ayrılık sinyali midir" bir **kural
tasarımı** sorusudur, üreteç sorunu değil. Sözlüğü körü körüne eşitlemek, sinyalin meşru olduğu
tam o iki bölümde sistematik yanlış pozitif üretirdi. Kayda geçiyor, ayrı ele alınacak.

## Başarı eşikleri — ölçümden ÖNCE

1. **Mevcut kapsama bozulmaz:** ≥ 7/8 pozitif senaryo, negatif kontrol (S9) temiz kalır.
2. **`UEBA-0023` ilk kez sınanır:** S11'de tetiklenir (şu an 0 tetiklenme — *herhangi* bir
   tetiklenme yeni bilgidir).
3. **`UEBA-0024`'ün yapısal yanlış pozitifi SIFIRA iner:** S12'de tetiklenir, kurumsal e-posta
   trafiğinde tetiklenmez (şu an 6).
4. **`UEBA-0022` gerçek tabana karşı sınanır:** S13'te tetiklenir ve `cloud_app_count`'un sıfır
   olmayan kullanıcı-günü **3'ten belirgin biçimde yükselir** (yani taban artık var).
5. **Eşik denetimi:** `eposta_dis_z`, `tests/test_esik_ulasilabilirlik.py::BILINEN` listesinden
   **çıkar** (şu an "üreteç dış e-posta üretmiyor" gerekçesiyle orada).
6. **Üç yeni senaryo negatif kontrolde tetiklenmez.**

3 ve 6 birbirinin frenidir: 3 kapatmayı, 6 aşırı tetiklememeyi sınıyor. **5 numara en sert
ölçüttür**, çünkü otomatik denetim listesinden bir maddenin düşmesi gerekiyor.

## Beklentiler — karamsar

1. **CERT'te hiçbir şey değişmeyecek.** Üreteç yalnız sentetik veriyi etkiler; r4.2/r6.2 sayıları
   bu fazdan hiç etkilenmez. Bu fazın kazancı **sınanabilirlik**, performans değil.
2. **Bulut tabanı eklemek mevcut kapsamayı DÜŞÜREBİLİR.** S1 şu an `personal_cloud`'un "hayatında
   ilk kez" olmasına dayanıyor; herkeste seyrek bir bulut tabanı olursa S1'in sinyali zayıflar.
   Ölçüt 1 tam bunu kollamak için var. Düşerse taban kaldırılmayacak — **gerçeğe yakın olan taban
   olandır**; bunun yerine S1'in kaçtığı rapor edilecek.
3. **Kuralın kendisi için yazılmış senaryoda tetiklenmesi ZAYIF kanıttır.** Sınavı da cevap
   anahtarını da ben yazıyorum. Bu fazın gerçek kazancı iki tanedir ve ikisi de dolaylı:
   (a) `UEBA-0024`'ün yapısal yanlış pozitif kaynağı kalkar,
   (b) üç kural **ulaşılabilir** hâle gelir, yani ileride bir değişiklik onları sessizce
   bozarsa eşik denetimi bunu yakalar. Şu an bozulsalar kimse fark etmez.
4. **En olası başarısızlık:** `UEBA-0023`'ün eşiği (`eposta_dis_z > 3.5`, taban 50 KB) sentetik
   e-posta hacim dağılımına uymaz ve S11'de tetiklenmez. O hâlde **eşik DEĞİŞTİRİLMEYECEK** —
   v8'de bir kez bu yapıldı (5 MB → 50 KB) ve ölçümden sonra eşik oynatmak sapma olarak kayda
   geçti. Bu kez eşik sabit kalır, senaryonun hacmi gerçekçi bir aralıkta tutulur ve tetiklenmezse
   **tetiklenmedi diye raporlanır**.

## Bu fazdan sonra ne YAPILMAYACAK

Üreteci CERT'e benzetme yarışına girilmeyecek. Sentetik verinin işi **kuralın ulaşılabilir
olduğunu göstermek**, gerçek kurumu temsil etmek değil — `scripts/esik_ulasilabilirlik.py`'nin
notunda yazdığı gibi bu denetim bir **alt sınırdır**. Kanal kurallarının gerçek değeri ancak
hedef ortamın kendi telemetrisinde ölçülebilir.
