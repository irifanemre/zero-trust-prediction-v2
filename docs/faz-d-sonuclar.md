# Faz D — dinamik kapasite: kazanç var ama sebebi öngörü değil, İSRAF

**Ölçüm: 5 Kasım 2026.** Ön kayıt: `docs/faz-d-on-kayit.md` (koddan önce yazıldı).
Araç: `scripts/kapasite_dagitimi.py`. 120 kullanıcı, 24 gün, tohum 7.
Hiçbir donmuş dosya değişmedi, boru hattına hiçbir şey bağlanmadı, dondurma v10 aynı.

## Ölçüm — aynı toplam kapasite (144 vaka), beş dağıtım planı

| Plan | insider-günü | farklı insider | toplam vaka | taban farkı | günlük bütçe |
|---|---|---|---|---|---|
| **düzgün (taban)** | **72** | 8 | 144 | — | [6] |
| hafta içi ağırlıklı | 64 | 9 | 144 | **−8** | [2, 7, 13] |
| **kuyruk oranlı** | **75** | **10** | 144 | **+3** | [1, 3, 4, 6, 7, 8, 9, 11] |
| tepe skor oranlı | 69 | 8 | 144 | −3 | [1 … 20] |
| HİLELİ (yarını bilen) | 72 | 8 | 144 | **+0** | [6] |

| # | Ölçüt (ölçümden önce yazıldı) | Sonuç |
|---|---|---|
| 1 | Uygulanabilir plan tabanı ≥1 insider-günü geçer | **GEÇTİ** — +3, ve +2 farklı insider |
| 2 | Hileli plan tabanı ≥2 geçer (üst sınır) | **KALDI** — +0 |
| 3 | Toplam kapasite eşit (±%2) | **GEÇTİ** — hepsi tam 144 |

## Ölçüt 2 neden kaldı: hileli plan DEJENERE çıktı, üst sınır ölçülemedi

Hileli plan "o gün insider varsa tavana çık" diyordu. Ölçüm gösterdi ki **11 insider'ın senaryo
pencereleri 24 günün neredeyse tamamını kaplıyor**: 195 fırsat günü / 24 gün ≈ her gün ~8 insider
pencerede. Dolayısıyla "insider var mı" her gün **evet** ve hileli planın ağırlıkları hepsi eşit
oldu — günlük bütçesi `[6]`, yani düzgün planın aynısı.

> **Üst sınır ölçülemedi.** Ölçüt 2'nin kalması dağıtımın değersiz olduğunu göstermiyor; **ölçüm
> tasarımımın kusurlu** olduğunu gösteriyor. "Hangi günde insider var" sorusu bu veride bilgi
> taşımıyor çünkü cevap her zaman evet.

Ön kayıttaki karamsar beklenti 1 tam bunu söylüyordu: *"insider günlerce kuyrukta kalıyor; bir günü
kaçırmak senaryoyu kaçırmak demek değil."* Doğru çıktı — ama sonucu, hileli planı anlamsız kılacak
kadar güçlü çıktı. Daha iyi bir üst sınır planı "o gün insider kuyruğun KAÇINCI sırasında" bilgisini
kullanmalıydı.

## Ölçüt 1 geçti — ama mekanizma öngörü değil, kullanılmayan kapasite

Kuyruk oranlı plan neden kazandı? Çünkü **düzgün dağıtım kapasitenin %18'ini çöpe atıyor.**

```
kuyruk uzunlukları (24 gün): 3,3,3,4,4,4,4,4,5,5,5,5,5,5,5,6,6,6,7,7,8,8,8,10
bütçe 6/gün  → 144 slot, 26'sı boşa  (%18)
bütçe 10/gün → 240 slot, 110'u boşa  (%46)
```

Sistem 120 kullanıcı için günde **3–10** aday üretiyor (medyan 5). Düzgün 6/gün planı, kuyruğun 3
olduğu günlerde 3 slotu boşa harcıyor; kuyruğun 10 olduğu günlerde 4 adayı dışarıda bırakıyor.
Kuyruk oranlı plan o 26 slotu yoğun günlere taşıyor → **+3 insider-günü, +2 farklı insider.**

> Kazanç tehdidi **öngörmekten** değil, kapasiteyi **israf etmemekten** geliyor.

Bu, "dinamik SOC kapasitesi" fikrinin brief'te hayal edildiği hâli değil. Uygulanabilir karşılığı
çok daha basit: **kullanılmayan bütçe ertesi güne devretsin** (backlog carry-over). Gelecek bilgisi
gerektirmiyor, model gerektirmiyor, tahmin gerektirmiyor.

### Neden hafta içi ağırlıklı plan ZARAR verdi (−8)

Ön kayıttaki karamsar beklenti 3 doğru çıktı. Plan hafta sonu bütçesini 2'ye düşürüyor; sentetik
senaryolarda mesai dışı/hafta sonu sızıntı var ve o günler kesiliyor. "Analistler hafta içi
çalışıyor" gerçeği, "tehdit hafta içi oluyor" varsayımını gerektirmiyor.

### Neden tepe skor oranlı plan zarar verdi (−3)

Günlük bütçesi [1 … 20] arasında savruluyor. Tek yüksek skorlu gün 20 slot alıyor ama kuyruğu
belki 8 uzunluğunda — 12 slot çöpe. Yani bu plan israfı **azaltmıyor, artırıyor**.

## Asıl bulgu: bu ölçekte darboğaz analist değil, SEÇİCİLİK

| | değer |
|---|---|
| Kullanıcı | 120 |
| Günlük aday (kuyruk) | 3–10, medyan 5 |
| Bütçe 30 ile kuyruk | **hâlâ 3–10** — bütçe hiç bağlayıcı değil |
| precision@1 | **0,958** |
| precision@10 | 0,577 |

Sistem bütçeyi doldurmuyor. Yani "analist kapasitesi yetmiyor" sorunu bu ölçekte **yok**; sorun
dedektörün ne kadar aday ürettiği. Dinamik kapasiteye yatırım yapmak, dolu olmayan bir kovayı
daha verimli taşımaya çalışmak olur.

Bu gerçek kurulumda değişebilir: 120 kullanıcı yerine 10.000 kullanıcıda kuyruk bütçeyi aşar ve
dağıtım soruları anlam kazanır. **Ölçüm bu ölçek için geçerli, genellenemez.**

## Öneri: devretme (uygulanmadı, ayrı ön kayıt gerekir)

Ölçülen kazanç küçük ama bedava: +3 insider-günü, +2 farklı insider, **aynı analist saatiyle**.
Uygulanabilir biçimi şu: kullanılmayan günlük bütçe bir sonraki güne devreder, tavan ile sınırlı.

Uygulanmadı çünkü kuyruk ve bütçe mantığı sistemin çekirdeği (13.5) ve değiştirilmesi her kapsama
rakamını etkiler. Kendi ön kaydıyla yapılacak iş.

## Sınırlar

- **Tek tohum, tek ölçek (120 kullanıcı).** Kuyruk/bütçe ilişkisi ölçeğe çok duyarlı ve bu ölçümün
  ana bulgusu (bütçe bağlayıcı değil) büyük kurulumda tersine döner.
- **Hileli plan dejenere.** Dağıtımın teorik üst sınırı **ölçülemedi**; o yüzden "dağıtımda kazanç
  yok" denemez, yalnız "denediğim planlardan biri israfı azaltarak +3 kazandırdı" denebilir.
- **Sentetik veri.** CERT'te koşu yok (r4.2 ayar verisi, r5.2/r6.2 yanmış, r1 saklı).
