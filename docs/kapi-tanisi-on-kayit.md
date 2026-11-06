# Kuyruk kapısı teşhisi — ön kayıt

**Yazıldı: 6 Kasım 2026, koşudan ÖNCE.** Dayanak: `docs/v11-r42-sonuclar.md`.

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Soru

v11 ölçümü gösterdi ki r4.2'de **bütçe 30'dan 100'e çıkınca hiçbir şey değişmiyor** (1.939 vaka,
23 insider, düz eğri). Yani `BÜTÇE DIŞI` diye raporlanan 5 senaryoyu tutan şey **bütçe değil**.

`select_queue` kuyruğa girişi **üç kapıyla** sınırlıyor:

| # | Kapı | Kod | Bayrak var mı |
|---|---|---|---|
| 1 | Son 7 günde kuyruğa girmiş ve yeni tespiti olmayan tekrar sunulmaz | `eligible()`, `scoring.py:189` | **yok** (sabit 7 gün) |
| 2 | Kanıt doğrulama — tek zayıf sinyal kuyruğa girmez | `corroborated()`, `scoring.py:139` | `kuyruk_dogrulama` |
| 3 | Günlük bütçe | `alarm_budget_per_day` | var |

v11 3'ü eledi. **Bu koşu 2'yi sınıyor.**

## Teşhis — bu kez veriden, etiketten değil

v11 koşusunun çıktısından (`ablasyon.json`, `tam` varyantı) çıkarılan ham gözlemler:

1. **Kaçan 12 senaryonun HEPSİ S2.** r4.2'nin S2 sınıfı USB tabanlı veri hırsızlığıdır.
2. **5 `BÜTÇE DIŞI`'nın 4'ü `[kısmi pencere]`** — senaryonun bir kısmı 90 günlük değerlendirme
   penceresinin dışında. Tam pencereli olan **tek** vaka: `CERT-r4.2-S2-IUB0565`.
3. `corroborated()` şu altı koşuldan **biri** sağlanırsa geçiyor: kritik · yüzdelik ≥ 0,998 ·
   anomali (kapalı) · herhangi bir çarpan > 1 · **≥ 2 farklı kural** · **≥ 3 farklı günde tekrar**.
4. Daha önce ölçüldü (`tests/test_esik_ulasilabilirlik.py::BILINEN`): `UEBA-0017`'nin iki Poisson
   kolu da ulaşılamaz; kural pratikte **yalnız `usb_ilk_kez == 1`** ile tetikleniyor — yani
   "hayatında ilk kez USB", tanımı gereği **tek gün**.

**Hipotez:** S2 insider'ları tek kuralı (`UEBA-0017`) tek günde tetikliyor. Bu, `corroborated()`'ın
hem "≥ 2 farklı kural" hem "≥ 3 farklı gün" koşulunu birden düşürüyor; çarpan ve kritik de yoksa
kapı 2 onları eliyor ve kuyruğa hiç giremiyorlar.

Doğruysa, kaçırılan insider'ların gerçek sebebi **kanıt doğrulama kapısı** — bütçe değil, sıralama
değil, tespit eksikliği değil.

## Koşu

| | |
|---|---|
| Veri | CERT r4.2, 90 gün, bütçe 30 (v11 koşusuyla aynı) |
| Varyantlar | `tam` (referans, önbellekte) ve **`v12_dogrulama_kapali`** (`kuyruk_dogrulama=False`) |
| Donmuş dosya | **hiçbiri** — `kuyruk_dogrulama` zaten var olan bir bayrak |
| Dondurma | v11 değişmeyecek |

Kapı 1 bu koşuda **sınanmıyor**: bayrağı yok, eklemek `scoring.py`'yi (donmuş) değiştirmek demek.
Kapı 2 açıklamazsa kapı 1 ayrı bir ön kayıtla ele alınacak.

## Başarı eşikleri — koşudan ÖNCE

1. **Referans aynı:** `tam` yine 22/34 ve 1.939 vaka. Değilse diğerleri okunmaz.
2. **Hipotez DOĞRULANIR** eğer kapı kapalıyken `BÜTÇE DIŞI` sayısı **5'ten azalırsa**. Kaç tanesi
   geri geldiği, kapının maliyetinin ölçüsüdür.
3. **Hipotez ÇÜRÜR** eğer `BÜTÇE DIŞI` 5'te kalırsa. O hâlde sebep kapı 1 ya da kısmi penceredir
   ve bu koşu onu eler.
4. **Bedel ölçülür:** kapı kapalıyken vaka sayısı ve precision@N raporlanır. Kapı tam da yanlış
   alarmı kesmek için var; kaldırmanın bedeli **ölçülmeden** hiçbir öneri yapılmayacak.

## Beklentiler — karamsar

1. **Kapı kapalıyken vaka sayısı çok artacak** — belki iki katı. `corroborated()` tek sinyalli
   vakaların hepsini eliyor ve onlar kalabalık. Yani ölçüt 2 geçse bile **bu bir çözüm değil**,
   yalnız sebebin teşhisi.
2. **Kazanç 5'in tamamı olmayacak.** Dördü kısmi pencereli; senaryonun bir kısmı zaten
   değerlendirme dışında, dolayısıyla kapı açılsa bile bazısı gelmeyebilir.
3. **En olası sonuç: kısmi doğrulama** — birkaçı gelir, birkaçı gelmez. O hâlde sebep tek değil
   ve bunu söylemek, tek sebep uydurmaktan dürüsttür.
4. **Bu koşu bir ÇÖZÜM üretmeyecek.** Teşhis koşusudur. `kuyruk_dogrulama` varsayılan açık
   kalacak; kapatmak için önce bedelinin kabul edilebilir olduğu gösterilmeli ve bu ayrı iştir.

## Koşudan sonra ne YAPILMAYACAK

- `kuyruk_tekrar_gun` (3) ya da `kuyruk_kacis_yuzdelik` (0,998) **ayarlanmayacak**. Sonucu
  gördükten sonra bu sabitleri oynatmak, eşiği sonuca göre ayarlamaktır — bu projede iki kez
  yapıldı, ikisi de sapma olarak kayda geçti.
- **Varsayılan değiştirilmeyecek.**
