# Faz D ön kaydı — dinamik SOC kapasitesi: aynı toplam, farklı dağıtım

**Yazıldı: 5 Kasım 2026, kod değişikliğinden ÖNCE.**

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Soru doğru kurulmalı

Brief "dinamik SOC kapasitesi" diyor. Yanlış okunuşu: *bütçeyi artırmak*. Bütçeyi artırmak elbette
yakalamayı artırır ve bunu ölçmeye gerek yok — `butce_recall_egrisi()` zaten ölçüyor.

Doğru soru şu:

> **Toplam analist kapasitesi SABİTken**, onu günlere düzgün dağıtmak yerine duruma göre
> dağıtmak yakalamayı artırır mı?

Çünkü bir SOC'un haftalık adam-saati sabittir. Dinamik kapasite, kapasite **yaratmaz**; var olanı
yeniden dağıtır. Kazanç ancak tehditler zamanda kümeleniyorsa vardır.

## Yaklaşım: çevrimdışı yeniden oynatma, boru hattına dokunmadan

`metrics.queue_by_day` her günün **risk sıralı** kuyruğunu tutuyor. Yüksek bütçeyle (30) tek koşu
yapılır, sonra kayıtlı kuyruklar üzerinde farklı dağıtım planları **çevrimdışı** oynatılır. Her
planın günlük tavanı ≤ 30 ve **toplam kapasitesi hedefle aynı** (ör. ortalama 6/gün).

| # | Ne | Dosya | Donmuş |
|---|---|---|---|
| 1 | Kayıtlı kuyruklar üzerinde dağıtım planı karşılaştırması | `scripts/kapasite_dagitimi.py` (yeni) | hayır |

**Hiçbir donmuş dosya değişmeyecek, boru hattına hiçbir şey bağlanmayacak, dondurma değişmeyecek.**

### Karşılaştırılacak planlar (hepsi aynı toplam kapasite)

| Plan | Tanım | Gerekçe |
|---|---|---|
| **düzgün** | her gün k | taban — şu anki davranış |
| hafta içi ağırlıklı | hafta içi ×1,4, hafta sonu ×0,3 | analistler hafta içi çalışıyor |
| kuyruk oranlı | o günün kuyruk uzunluğuna oransal | "yoğun günde çok bak" |
| tepe skor oranlı | o günün en yüksek risk skoruna oransal | "tehlikeli günde çok bak" |
| **yarınki bilgiyle (hile)** | o gün gerçekten insider varsa tavan, yoksa taban | **ÜST SINIR** — uygulanamaz |

Son plan bilerek hileli: gelecek bilgisi kullanıyor, dolayısıyla uygulanabilir değil. Varlık
sebebi, dağıtımın teorik en iyi hâlini vermek — gerçekleşebilir planlar ona ne kadar yaklaşıyor?

## Başarı eşikleri — ölçümden ÖNCE

1. **Uygulanabilir bir plan, düzgün dağıtımı en az 1 insider-günü farkla geçer.** Geçmezse
   dinamik kapasite bu veride değer üretmiyor demektir ve **uygulanmayacak**.
2. **Hileli plan düzgünü belirgin geçer** (≥ 2 insider-günü). Geçmezse dağıtımın kendisinde
   kazanç yok — yani ölçüm, planların yetersizliğini değil **sorunun yapısını** gösteriyor ve
   ölçüt 1'in kalması beklenen sonuçtur.
3. **Toplam kapasite her planda eşit** (±%2). Eşit değilse karşılaştırma geçersizdir — bu bir
   doğruluk kontrolü.

2 ve 1 birlikte okunmalı: hileli plan kazanamıyorsa ölçüt 1'in kalması bir başarısızlık değil,
**doğru cevap**.

## Beklentiler — karamsar

1. **Hileli plan bile az kazandıracak.** Gerekçe: sentetik senaryolar kademeli sızıntı üretiyor,
   yani insider günlerce kuyrukta kalıyor. Bir günü kaçırmak senaryoyu kaçırmak demek değil;
   dolayısıyla günlük dağıtımın oynaması kapsamayı pek değiştirmez.
2. **Uygulanabilir planlar hiç kazandırmayacak.** "Kuyruk uzunluğu" ve "tepe skor" sinyalleri,
   o gün gerçekten insider olup olmadığıyla zayıf ilişkili — eğer güçlü ilişkili olsalardı zaten
   sıralama onları öne alıyor olurdu.
3. **Hafta içi ağırlıklı plan ZARAR verebilir.** Sentetik üreteçte hafta sonu aktivitesi düşük
   (`WEEKDAY_FACTOR` 0,35) ama *mesai dışı* sızıntı senaryoları var; hafta sonu bütçeyi kısmak
   onları kaçırabilir.
4. **Bu faz da yakalama artırmayacak.** Beş bileşen üst üste eşiğini geçemedi; bunun geçmesi için
   özel bir sebep yok. Değeri, "dinamik kapasite" fikrinin **ölçülmüş** olarak elenmesi ya da
   dar bir koşulda değerli bulunması.

---

# Sapmalar — ölçümden SONRA eklendi (5 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Sonuçlar: `docs/faz-d-sonuclar.md`.

## Sapma 1 — HİLELİ PLAN DEJENERE ÇIKTI, üst sınır ölçülemedi

Ölçüt 2 hileli planı "üst sınır" olarak kurmuştu: o gün insider varsa tavana çık. Ölçüm gösterdi ki
11 insider'ın pencereleri 24 günün neredeyse tamamını kaplıyor (195 fırsat günü / 24 gün ≈ her gün
~8 insider). Yani "insider var mı" her gün evet, ağırlıklar eşit, plan düzgün planın aynısı oldu
(`[6]`) ve farkı +0.

**Ölçüt 2'nin kalması dağıtım hakkında bilgi vermiyor; ölçüm tasarımımın kusurlu olduğunu
gösteriyor.** Daha iyi bir üst sınır planı "insider kuyruğun kaçıncı sırasında" bilgisini
kullanmalıydı. Düzeltilmedi: ölçümü gördükten sonra üst sınır planını değiştirmek, üst sınırı
sonuca göre ayarlamak olur. Kayda geçiyor.

## Sapma 2 — ölçüt 1 geçti ama mekanizma ön kayıtta öngörülenden farklı

Ön kayıt dinamik kapasitenin "tehditler zamanda kümeleniyorsa" kazandıracağını varsayıyordu. Kazanç
oradan gelmedi: düzgün dağıtım kapasitenin **%18'ini kullanmıyor** (144 slotun 26'sı boş, çünkü
kuyruk medyanı 5 ve bütçe 6). Kuyruk oranlı plan o boş slotları yoğun günlere taşıyor.

Yani kazanç **öngörüden değil israfı önlemekten** geliyor ve uygulanabilir karşılığı çok daha basit:
kullanılmayan bütçe ertesi güne devretsin. Gelecek bilgisi, model, tahmin gerektirmiyor.

## Sapma 3 — ön kayıtta sorulmayan asıl soru: bütçe bu ölçekte BAĞLAYICI DEĞİL

Koşu bütçe 30 ile yapıldı ve kuyruk **hâlâ 3–10** uzunluğunda kaldı. Yani 120 kullanıcıda sistem
bütçeyi hiç doldurmuyor; "analist kapasitesi yetmiyor" sorunu bu ölçekte yok.

Bu, Faz D'nin varsayımını temelden sorguluyor ve ön kayıtta hiç sorulmamıştı. Gerçek kurulumda
(10.000 kullanıcı) tersine dönmesi beklenir, dolayısıyla ölçüm **bu ölçek için geçerli,
genellenemez**.

## Sapma 4 — karamsar beklenti 3 doğru çıktı, ve ölçülü biçimde

"Hafta içi ağırlıklı plan ZARAR verebilir" yazmıştım: −8 insider-günü ile en kötü plan oldu.
Sebep de yazdığı gibi — hafta sonu bütçesi 2'ye düşüyor ve mesai dışı sızıntı senaryoları o günlerde.
"Analistler hafta içi çalışıyor" gerçeği, "tehdit hafta içi oluyor" varsayımını gerektirmiyor.
