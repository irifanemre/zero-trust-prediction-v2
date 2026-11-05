# v11 — kullanılmayan bütçenin devretmesi: beş ölçütün hepsi geçti

**Ölçüm: 5 Kasım 2026.** Ön kayıt: `docs/v11-on-kayit.md` (koddan önce yazıldı).
Dondurma `kurallar-donduruldu-v11` → `donmuş durumla aynı`. 407 test geçiyor (yavaş dahil).

> **Bu oturumda eşiğini geçen İLK bileşen.** Yine de varsayılan kapalı — gerekçe aşağıda.

## Ölçüm — 120 kullanıcı, 24 gün, bütçe 6

| | devretme KAPALI | devretme AÇIK |
|---|---|---|
| **Yakalanan senaryo** | 7 / 8 | **8 / 8** |
| İnsider-günü | 74 | **75** |
| Toplam vaka | 127 | 130 |
| En yoğun gün | 8 | 10 |

| # | Ölçüt (ölçümden önce yazıldı) | Sonuç |
|---|---|---|
| 1 | Bayrak kapalıyken sonuç birebir v10 | **GEÇTİ** — 7 yakalama / 127 vaka, Faz E koşusuyla aynı |
| 2 | Kapasite yaratmaz: vaka ≤ bütçe × gün | **GEÇTİ** — 130 ≤ 144 |
| 3 | Yakalama düşmez | **GEÇTİ** — 7 → **8** (arttı) |
| 4 | Günlük tavan aşılmaz | **GEÇTİ** — 10 ≤ 12 |
| 5 | İnsider-günü ≥ +1 | **GEÇTİ** — +1 |

## Kazanılan senaryo: S5, ve neden tam olarak bu

Devretme kapalıyken S5 şöyle raporlanıyordu:

```
BÜTÇE DIŞI (beklenen tespit tetiklendi, kuyruğa girmedi)   S5_log_sessizligi
```

Yani `DQ-0010` **tetiklenmişti** ama o günün bütçesi dolu olduğu için kuyruğa girememişti. Devir
bakiyesi o güne bir slot taşıdı ve senaryo yakalandı.

> Kazanç yeni bir tespitten değil, **zaten üretilmiş bir tespitin kaybedilmemesinden** geliyor.
> Sistem o insider'ı görmüştü; kuyruk onu dışarıda bırakıyordu.

Bu, Faz D'nin bulgusunu doğruluyor: boşa giden kapasite gerçek bir kayıp ve geri alınabilir.

## Faz D'nin +3'ü yerine +1 — ön kayıt bunu öngörmüştü

Karamsar beklenti 1: *"Kazanç Faz D'nin +3'ünden AZ olacak. Faz D kuyruk uzunluğunu o gün bilerek
dağıttı; devretme ancak geçmişte biriken bakiyeyi kullanabilir."* **Doğru çıktı: +1.**

| | Faz D (çevrimdışı) | v11 (gerçek) |
|---|---|---|
| Bilgi | o günün kuyruk uzunluğu | yalnız geçmişte biriken bakiye |
| İnsider-günü kazancı | +3 | **+1** |
| Uygulanabilir mi | hayır | **evet** |

Fark, ileriye bakmanın bedeli. Faz D'nin +3'ü bir üst sınırdı; gerçekleşebilir olanın üçte biri.

Buna karşılık **senaryo kazancı** (7 → 8) Faz D'nin ölçmediği bir şey: Faz D insider-günü sayıyordu,
senaryo yakalaması değil. Bir insider-günü, doğru senaryoya denk gelirse tam bir senaryo kazandırır.

## Varsayılan neden KAPALI

Beş ölçütün hepsi geçmesine rağmen bayrak kapalı. Gerekçe bu projenin kendi kuralı:

> Bir bileşenin varsayılan açılması için **iki farklı veride** değer üretmesi gerekir.
> (`docs/r62-graf-tek-basina.md` — graf çarpanı r4.2'de +5 insider verip r6.2'de +0 verdikten
> sonra konan kural.)

Devretme **tek veride** (sentetik) ölçüldü. CERT'te ölçülmedi: r4.2 ayar verisi, r5.2/r6.2 yanmış,
r1 saklı. Graf çarpanı tam bu noktada çürüdü ve aynı hataya düşülmeyecek.

Ayrıca ön kayıttaki karamsar beklenti 4 uyarıyordu: *"10.000 kullanıcıda kuyruk sürekli bütçeyi
aşar, kullanılmayan kapasite hiç olmaz ve devretme hiçbir şey yapmaz."* Yani bu bileşenin değeri
**küçük kurulumlara özgü** olabilir ve sentetik ölçüm bunu söyleyemez.

## Devir tavanı: beklenti 2 doğrulandı

Karamsar beklenti 2: *"Devir bakiyesi çoğu zaman tavana takılacak... tavan kazancın büyük kısmını
da kesiyor olabilir."*

Ölçüm: kuyruk medyanı 5, bütçe 6 → günde ~1 slot birikiyor, tavan 6 → bakiye ~6 günde doluyor ve
sonrası çöpe gidiyor. 24 günde 26 boş slotun ancak bir kısmı kullanılabiliyor.

Tavan **kaldırılmadı** ve kaldırılmayacak: sınırsız devir, uzun sessizlikten sonra tek günde
kuyruğu patlatır. Sözleşme testle bağlandı (`test_v11_devretme_kapasite_YARATMAZ`): iki sessiz
günden sonra bakiye 6 olsa bile yoğun günde alınan **tam 6** (bütçe 3 + tavan 3), fazlası değil.

## Sınırlar

- **Tek veri, tek tohum, tek ölçek.** Yukarıdaki iki gerekçe.
- **Kazanç küçük:** +1 insider-günü, +1 senaryo. Ama maliyeti **sıfır** — ek analist saati yok,
  model yok, tahmin yok, gelecek bilgisi yok.
- **Ölçüt 1 ayrı koşuyla doğrulandı**, aynı süreçte yan yana değil. Bayrak kapalıyken kod yolu
  hiç çalışmıyor (`getattr(self.cfg, "butce_devretme", False)`) ve sayılar Faz E'nin aynı
  yapılandırmalı koşusuyla birebir eşleşti (7 yakalama, 127 vaka).
