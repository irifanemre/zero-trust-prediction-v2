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

---

# Sapmalar — ölçümden SONRA eklendi (6 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Sonuçlar: `docs/v11-r42-sonuclar.md`.

## Sapma 1 — ÖLÇÜT 4 KALDI, karamsar beklenti 1 doğru çıktı

`BÜTÇE DIŞI` 5 → 5, durumu değişen senaryo 0. Devretme 126 ek vaka açtı ve hiçbiri insider
değildi. Ön kayıt "kazanç 0–2 senaryo, muhtemelen 0" demişti; 0 geldi.

## Sapma 2 — ön kayıtın DAYANDIĞI TEŞHİS ÇÜRÜDÜ

Ön kayıt şu cümleyle başlıyordu: *"r4.2'de kaçan 12 insider'ın 5'i tespit edilmişti ve bütçe
yarışında kaybedildi. Devretme tam bu başarısızlık biçimini hedefliyor."*

**Bu teşhis yanlıştı ve kaynağı bir etiketin ADIYDI, veri değil.** Bütçe eğrisi gösteriyor ki
bütçe 30'dan 100'e çıkarıldığında:

| bütçe | vaka | yakalanan insider |
|---|---|---|
| 30 | 1.896 | 23 |
| 100 | 1.939 | **23** |

Eğri düz. Üç katı bütçe o 5 insider'ı getirmiyor, yani **bütçe o kapı değil**.

`metrics.py`'deki etiket `"BÜTÇE DIŞI (beklenen tespit tetiklendi, kuyruğa girmedi)"`. Parantez
içi doğru, etiketin **adı** yanıltıcı: kuyruğa girişi üç kapı sınırlıyor (7 günlük tekrar sunma
kısıtı, kanıt çeşitliliği doğrulaması, bütçe) ve ölçüm üçüncüsünü eliyor.

Yani bu faz **doğru mekanizmayı yanlış kapıya uyguladı**. Ön kaydı yazarken teşhisi veriden
doğrulamadım; etiketin adını okudum. Kayda geçiyor.

## Sapma 3 — ön kayıtın açıklaması da tam isabet değildi

Karamsar beklenti 1 "r4.2'de kuyruk muhtemelen SÜREKLİ DOLU, kullanılmayan kapasite yoktur"
diyordu. Yarısı doğru: sonuç (+0) doğru tahmin edildi ama **sebep** farklı. Kuyruk dolu değil —
bütçe 30'da 1.896 vaka, sınırsızda 1.939. Boş kapasite **var** ve devretme onu kullandı (+126
vaka). Sıradaki adaylar insider değildi.

Küçük sentetik kurulumda sıradaki aday insider olabiliyordu (S5 böyle kazanılmıştı); 2.801
kullanıcılık r4.2'de olmuyor.

## Yapılmayanlar (ön kayıtta söz verildiği gibi)

- **Varsayılan açılmadı** — zaten açılmayacaktı, şimdi gerekçesi iki veriden.
- **`butce_devir_tavani` ayarlanmadı.** Ön kayıt yasaklıyordu: "sonucu gördükten sonra tavan
  oynatmak, eşiği sonuca göre ayarlamaktır."
- **Kanıt çeşitliliği / tekrar sunma kapıları ölçülmedi.** Bu ölçümün ortaya çıkardığı yeni soru;
  kendi ön kaydıyla yapılacak.
