# v11 ön kaydı — kullanılmayan bütçenin devretmesi

**Yazıldı: 5 Kasım 2026, kod değişikliğinden ÖNCE.** Dayanak: `docs/faz-d-sonuclar.md`.

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Faz D ne ölçtü

Düzgün dağıtım analist kapasitesinin **%18'ini kullanmıyor**:

```
kuyruk uzunlukları (120 kullanıcı, 24 gün): 3,3,3,4,4,4,4,4,5,5,5,5,5,5,5,6,6,6,7,7,8,8,8,10
bütçe 6/gün → 144 slot, 26'sı boşa (%18)
```

Kuyruğun 3 olduğu günde 3 slot çöpe gidiyor; kuyruğun 10 olduğu günde 4 aday dışarıda kalıyor.
Çevrimdışı oynatmada kuyruk oranlı dağıtım **+3 insider-günü ve +2 farklı insider** kazandırdı,
aynı toplam kapasiteyle.

Faz D bunu *dinamik kapasite* diye ölçtü ama mekanizma öngörü değil **israf**. Uygulanabilir
karşılığı çok daha basit ve gelecek bilgisi gerektirmiyor: **kullanılmayan bütçe devreder.**

## Değişecek

| # | Ne | Dosya | Donmuş |
|---|---|---|---|
| 1 | Kullanılmayan günlük bütçe bir sonraki güne devreder | `scoring.py` (`select_queue`) | **evet** |
| 2 | Bayrak `butce_devretme` + tavan `butce_devir_tavani` | `config.py` | **evet** |

İkisi de donmuş → **dondurma v11**. Bayrak varsayılan **kapalı**.

### Tasarım

```
devir_bakiyesi = 0
her gün:
    gunluk_tavan = butce + min(devir_bakiyesi, butce_devir_tavani)
    alinan = min(len(kuyruk), gunluk_tavan)
    devir_bakiyesi = max(0, devir_bakiyesi + butce - alinan)
```

Üç kısıt, hepsi bilinçli:

1. **Tavan var** (`butce_devir_tavani`, varsayılan = günlük bütçe). Sınırsız devir, uzun sessiz
   dönemden sonra tek günde 100 vaka açabilir — analist kuyruğu patlar. Devir **bir günlük** ek
   kapasiteyle sınırlı.
2. **Devir ileriye bakmaz.** Yalnız geçmişte kullanılmayan kapasite devreder; "yarın yoğun olacak"
   tahmini yok. Gelecek bilgisi gerektiren hiçbir şey yok.
3. **Kritik istisna bozulmaz.** 13.5'teki kritik vakalar (tuzak gibi deterministik kanıt) bütçeden
   bağımsız kuyruğa giriyor; devir o yolu değiştirmez.

## Başarı eşikleri — ölçümden ÖNCE

1. **Bayrak kapalıyken sonuç birebir v10** (kapsama, kuyruk, vaka sayısı). Doğruluk kontrolü.
2. **Bayrak açıkken toplam vaka sayısı artar ama ORTALAMA bütçeyi aşmaz**: toplam vaka ≤
   `bütçe × gün`. Devir kapasite yaratmamalı, yalnız kaydırmalı. Aşarsa uygulama hatalıdır.
3. **Yakalama düşmez.** Kapsama ve insider-günü, kapalı hâlden az olamaz.
4. **Günlük tavan aşılmaz**: hiçbir gün `bütçe + butce_devir_tavani`'nı geçmez.
5. **Kazanç Faz D'nin ölçtüğü yönde**: insider-günü ≥ +1. Faz D çevrimdışı oynatmada +3 bulmuştu;
   devretme o kazancın bir kısmını yakalamalı. +0 çıkarsa mekanizma Faz D'nin bulduğu şeyi
   yakalamıyor demektir.

2 ve 4 doğruluk kontrolleri, 3 ve 5 fayda ölçütleri. **2 ya da 4 kalırsa uygulama hatalıdır ve
bayrak açılmaz**, 5 kalırsa mekanizma işe yaramıyor demektir.

## Beklentiler — karamsar

1. **Kazanç Faz D'nin +3'ünden AZ olacak.** Faz D kuyruk uzunluğunu *o gün* bilerek dağıttı;
   devretme ancak *geçmişte* biriken bakiyeyi kullanabilir. Yani yoğun gün bakiyeden önce gelirse
   kazanç yok.
2. **Devir bakiyesi çoğu zaman tavana takılacak.** Kuyruk medyanı 5, bütçe 6 → günde ~1 slot
   birikiyor; tavan 6 ise bakiye 6 günde doluyor ve sonrası çöpe gidiyor. Yani tavan, kazancın
   büyük kısmını da kesiyor olabilir — ölçülecek.
3. **Bu ölçekte kazanç küçük kalacak.** Faz D'nin asıl bulgusu şuydu: 120 kullanıcıda bütçe
   bağlayıcı değil, kuyruk 3–10. Devir ancak kuyruğun bütçeyi aştığı günlerde işe yarar ve o
   günler az.
4. **Gerçek kurulumda tersine dönebilir.** 10.000 kullanıcıda kuyruk sürekli bütçeyi aşar, yani
   kullanılmayan kapasite hiç olmaz ve devretme **hiçbir şey yapmaz**. Yani bu bileşenin değeri
   küçük kurulumlara özgü olabilir — ölçüm bunu söyleyemez, çünkü o ölçek sentetik olarak
   üretilmedi.

---

# Sapmalar — ölçümden SONRA eklendi (5 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Sonuçlar: `docs/v11-sonuclar.md`.

## Sapma yok — beş ölçütün hepsi geçti

Bu, oturumun sapma listesi boş olan ilk fazı. Ölçütler yazıldığı gibi sınandı ve geçti:
kapalıyken birebir aynı, kapasite yaratmıyor, yakalama düşmedi (arttı), günlük tavan aşılmadı,
insider-günü +1.

## Kayda geçen iki nokta (sapma değil, doğrulama)

**Karamsar beklenti 1 doğru çıktı.** "Kazanç Faz D'nin +3'ünden az olacak" yazılmıştı: +1 geldi.
Fark ileriye bakmanın bedeli — Faz D o günün kuyruk uzunluğunu bilerek dağıtmıştı, devretme yalnız
geçmişte biriken bakiyeyi kullanıyor. Faz D'nin +3'ü bir üst sınırdı ve gerçekleşebilir olan
üçte biri.

**Karamsar beklenti 2 doğru çıktı.** "Devir bakiyesi çoğu zaman tavana takılacak" yazılmıştı:
kuyruk medyanı 5, bütçe 6 → günde ~1 slot birikiyor, tavan 6 → bakiye ~6 günde doluyor, sonrası
çöpe gidiyor. Tavan kaldırılmadı; sınırsız devir uzun sessizlikten sonra kuyruğu patlatır ve bu
sözleşme testle bağlandı.

## Ön kayıtta yazılmayan ama ölçümde çıkan: kazanılan senaryo S5

Devretme kapalıyken S5 `BÜTÇE DIŞI (beklenen tespit tetiklendi, kuyruğa girmedi)` raporlanıyordu —
yani `DQ-0010` tetiklenmiş ama bütçe dolu olduğu için kuyruğa girememiş. Devir o güne bir slot
taşıdı.

Kazanç **yeni bir tespitten değil, zaten üretilmiş bir tespitin kaybedilmemesinden** geliyor.
Ön kayıt insider-günü ölçütü koymuştu (ölçüt 5) ama senaryo kazancını öngörmemişti; Faz D de
insider-günü sayıyordu, senaryo yakalaması değil.

## Varsayılan KAPALI kalıyor — ön kayıtta yazılmayan karar

Beş ölçüt de geçti ama bayrak açılmadı, çünkü projenin kendi kuralı iki farklı veride değer
üretmeyi şart koşuyor (`docs/r62-graf-tek-basina.md`). Devretme yalnız sentetik veride ölçüldü.
Graf çarpanı tam bu noktada çürümüştü: r4.2'de +5, r6.2'de +0.
