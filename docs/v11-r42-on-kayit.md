# v11'in r4.2'de ölçümü — ön kayıt

**Yazıldı: 6 Kasım 2026, koşudan ÖNCE.** Dayanak: `docs/v11-sonuclar.md`, `docs/v6a-geri-bildirim-olcumu.md`.

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Soru

r4.2'de kaçan 12 insider'ın dağılımı (`tam` varyantı, `docs/v6a-geri-bildirim-olcumu.md`):

| Kaçma biçimi | sayı |
|---|---|
| GEÇTİ | 22 |
| **BÜTÇE DIŞI** — tespit edildi, kuyruğa girmedi | **5** |
| KALDI — hiç tetiklenmedi | 6 |
| REVİZYON GEREKLİ | 1 |

Devretme (`butce_devretme`) tam bu başarısızlık biçimini hedefliyor: kullanılmayan kapasiteyi
biriktirip yoğun güne taşıyor. Sentetik veride S5'i böyle kazandı (`BÜTÇE DIŞI` → `GEÇTİ`).

> **Soru: r4.2'deki 5 "bütçe dışı" senaryonun kaçı geri geliyor?**

## Neden r4.2'de ölçmek meşru, ve neyi KANITLAMAZ

r4.2 **ayar verisidir** — zaten yakıldı, ablasyon için kullanılıyor. Orada ölçmek yeni bir ihlal
değil. Ama kör de değil:

> **r4.2'de +2 çıksa bile varsayılan AÇILMAYACAK.** Graf çarpanı tam bunu yaptı: r4.2'de +5
> insider, r6.2'de +0 (`docs/r62-graf-tek-basina.md`). Bir bileşenin varsayılan açılması için
> **kör** veride değer üretmesi gerekir ve elimizde yalnız r1 var, o da saklı.

Bu ölçümün amacı varsayılanı değiştirmek değil: **mekanizmanın gerçek veride çalışıp
çalışmadığını** görmek. Çalışmazsa r1'i harcamaya hiç değmez.

## Koşu

| | |
|---|---|
| Veri | CERT r4.2, 90 gün, bütçe 30 |
| Varyantlar | `tam` (referans) ve `v11_butce_devretme` |
| Yapılandırma farkı | yalnız `butce_devretme=True` |
| Dondurma | `kurallar-donduruldu-v11` doğrulanacak |

Ablasyon betiğine tek varyant eklenecek (`ablation.py`, donmuş değil). Başka hiçbir dosya
değişmeyecek.

## Başarı eşikleri — koşudan ÖNCE

1. **Referans yeniden üretilir:** `tam` varyantı 22/34 kapsama ve 1.939 vaka vermeli
   (`docs/v6a-geri-bildirim-olcumu.md`). Vermezse koşu ortamı değişmiş demektir ve 2–4
   yorumlanmaz. **Bu ölçüt önce okunacak.**
2. **Kapsama düşmez:** devretme açıkken ≥ 22/34.
3. **Kapasite yaratılmaz:** toplam vaka ≤ bütçe × gün × pencere. Devretme bütçeyi kaydırır,
   artırmaz.
4. **Kazanç ölçülür:** `BÜTÇE DIŞI` sayısı 5'ten azalır. Azalmazsa mekanizma gerçek veride
   çalışmıyor demektir.

1 ve 3 doğruluk kontrolleri; 2 ve 4 fayda ölçütleri. **1 kalırsa diğerleri okunmaz.**

## Beklentiler — karamsar

1. **Kazanç sentetikten az olacak, muhtemelen 0–2 senaryo.** Gerekçe: r4.2'de bütçe 30 ve
   kuyruk muhtemelen **sürekli dolu** — sentetik veride (120 kullanıcı, kuyruk 3–10, bütçe 6)
   kapasitenin %18'i boşa gidiyordu, ama r4.2'de 2.801 kullanıcı var. Kuyruk hep doluysa
   **kullanılmayan kapasite yoktur ve devretme hiçbir şey yapmaz.**
2. Bu, v11 ön kaydındaki karamsar beklenti 4'ün tam olarak sınanmasıdır: *"10.000 kullanıcıda
   kuyruk sürekli bütçeyi aşar, devretme hiçbir şey yapmaz."* r4.2 o senaryonun gerçek örneği.
3. **+0 çıkarsa bu bir başarısızlık DEĞİL**, aradığımız cevaptır: devretmenin değeri küçük
   kurulumlara özgüdür ve bu ölçüm onu gösterir. O hâlde bileşen kapalı kalır ve r1'de
   denenmez.
4. Kapsama **düşmemeli**; düşerse uygulama hatası vardır (devretme yalnız ek kapasite verir,
   sıralamayı değiştirmez).

## Koşudan sonra ne YAPILMAYACAK

- Sonuç iyi çıksa bile **varsayılan açılmayacak** (kör veri yok).
- `butce_devir_tavani` ayarlanmayacak. Sonucu gördükten sonra tavan oynatmak, eşiği sonuca göre
  ayarlamaktır — bu projede iki kez yapıldı ve ikisi de sapma olarak kayda geçti.
