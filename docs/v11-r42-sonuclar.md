# v11'in r4.2'de ölçümü — +0 insider, +126 vaka. Ve "BÜTÇE DIŞI" etiketi yanıltıcıymış

**Ölçüm: 6 Kasım 2026, 2 varyant × 90 gün, bütçe 30.** Ön kayıt: `docs/v11-r42-on-kayit.md`
(koşudan önce yazıldı). Dondurma `kurallar-donduruldu-v11` koşu başında doğrulandı.

> **Devretme r4.2'de hiçbir şey kazandırmadı** ve ön kayıttaki karamsar beklenti 1 doğru çıktı.
> Ama asıl bulgu ölçütlerin içinde değil: **o 5 insider bütçe yüzünden kaçmıyormuş.**

## Ön kayıtlı ölçütler

| # | Ölçüt (koşudan önce yazıldı) | Sonuç |
|---|---|---|
| 1 | `tam` referansı yeniden üretilir: 22/34, 1.939 vaka | **GEÇTİ** — birebir |
| 2 | Kapsama düşmez (≥ 22/34) | **GEÇTİ** — 22/34 |
| 3 | Kapasite yaratılmaz (vaka ≤ 30 × 90 = 2.700) | **GEÇTİ** — 2.065 |
| 4 | `BÜTÇE DIŞI` sayısı 5'ten azalır | **KALDI** — 5 → 5 |

| | `tam` | `v11_butce_devretme` |
|---|---|---|
| Kapsama | 22/34 | **22/34** |
| Vaka | 1.939 | **2.065** (+126) |
| precision@N | 0,045 | 0,044 |
| recall@10 / @30 | 0,618 / 0,676 | 0,618 / 0,676 |
| Erkenlik medyanı | 8 gün | 8 gün |

**Durumu değişen senaryo: 0.** Kaçma biçimleri iki varyantta da aynı: 22 GEÇTİ · 6 KALDI ·
**5 BÜTÇE DIŞI** · 1 REVİZYON GEREKLİ.

Yani devretme 126 ek vaka açtı ve **hiçbiri insider değildi**. Saf maliyet.

## Asıl bulgu — ve bu bir DÜZELTME

Bütçe eğrisi (`tam` varyantı):

| Bütçe | İncelenen vaka | Yakalanan insider | recall (kullanıcı) |
|---|---|---|---|
| 20 | 1.289 | 22 | 0,647 |
| **30** | 1.896 | **23** | **0,676** |
| 50 | 1.939 | **23** | 0,676 |
| 75 | 1.939 | **23** | 0,676 |
| **100** | **1.939** | **23** | **0,676** |

**Bütçe 30'dan 100'e çıkınca hiçbir şey değişmiyor.** Vaka sayısı 1.939'da doyuyor, yakalanan
insider 23'te kalıyor. Yani sistem bütçeyi **doldurmuyor** — üç katı bütçe verilse de aynı
insider'lar yakalanıyor.

> **Sonuç: o 5 insider bütçe yüzünden kaçmıyor.** Bütçeyi üçe katlamak onları getirmiyor.

### Etiketin adı yanlış, açıklaması doğru

```python
# metrics.py
if expected & all_fired and not hit_exp:
    sonuc = "BÜTÇE DIŞI (beklenen tespit tetiklendi, kuyruğa girmedi)"
```

Parantez içi **doğru**: "tetiklendi, kuyruğa girmedi". Ama etiketin adı bunu **bütçeye**
atfediyor. Oysa `select_queue` kuyruğa girişi üç şeyle sınırlıyor ve bütçe yalnız üçüncüsü:

| # | Kapı | Ne yapar |
|---|---|---|
| 1 | `eligible()` | Son 7 günde kuyruğa girmiş ve o günden beri **yeni tespiti olmayan** kullanıcı tekrar sunulmaz (vaka zaten açık) |
| 2 | `kuyruk_dogrulama` | **Kanıt çeşitliliği** yoksa eleniyor — tek kaynaklı tespit kuyruğa girmiyor |
| 3 | `alarm_budget_per_day` | Bütçe kesmesi |

Eğri 30–100 arasında düz olduğu için **3 numara bağlayıcı değil**. Geriye 1 ve 2 kalıyor.

### Bu, benim daha önceki okumamı düzeltiyor

Bu oturumda sana *"kaçan 12 insider'ın 5'i tespit edilmişti ve **bütçe yarışında** kaybedildi"*
demiştim ve v11'i tam o teşhise dayanarak önermiştim. **Teşhis etiketin adından okunmuştu,
veriden değil.** Ölçüm onu çürüttü: bütçe o kapı değil.

Devretme yanlış kapıyı zorladı; o yüzden 126 ek vaka açıp sıfır insider getirdi.

## Varsayılan: KAPALI (zaten öyleydi, şimdi gerekçesi iki veriden)

| Veri | Sonuç |
|---|---|
| Sentetik (120 kullanıcı, bütçe 6) | kapsama 7/8 → **8/8**, +1 insider-günü |
| **CERT r4.2** (2.801 kullanıcı, bütçe 30) | kapsama 22/34 → **22/34**, **+0**, +126 vaka |

Ön kayıttaki karamsar beklenti 1 ve 4 birlikte doğru çıktı: *"kuyruk sürekli doluysa kullanılmayan
kapasite yoktur ve devretme hiçbir şey yapmaz... bu bileşenin değeri küçük kurulumlara özgü
olabilir."*

Gerçek fark daha ince: r4.2'de kuyruk **dolu değil** (bütçe 30'da 1.896, sınırsızda 1.939 vaka) —
ama boş kalan kapasiteyi doldurduğunda da **sıradaki adaylar insider değil**. Küçük sentetik
kurulumda sıradaki aday insider olabiliyordu; 2.801 kullanıcılık r4.2'de olmuyor.

Bu, grafın r4.2 → r6.2 çürümesiyle **aynı sınıf** bir sonuç: bir veride değer üreten mekanizma,
başka veride üretmiyor. Devretme bu sefer **ters yönde** — küçük veride kazandı, büyük veride
kazanmadı.

## Sıradaki soru (bu fazın dışında)

Eğer o 5 insider'ı tutan şey bütçe değilse, **1 numara mı 2 numara mı?** İkisi de tek koşuyla
ölçülebilir ve koşu artık ucuz (veri önbellekte, varyant başına ~7 dk):

- `kuyruk_dogrulama=False` → kanıt çeşitliliği kapısı kalkar
- `queue_cooldown` benzeri bir varyant → 7 günlük tekrar sunma kısıtı kalkar

Hangisi o 5'i getiriyorsa, kaçırılan insider'ların **gerçek** sebebi odur. Bu, bütçeyle uğraşmaktan
çok daha değerli bir yön — ama kendi ön kaydıyla.

## Sınırlar

- **r4.2 kör değil** — ayar verisi. Burada +0 çıkması, kör veride de +0 çıkacağı anlamına gelmez
  (tersi de). Ama varsayılanı açmamak için zaten yeterli.
- **Tek bütçe değeri (30).** Daha düşük bütçede (ör. 10) devretmenin etkisi farklı olabilir; eğri
  10–30 arasında dik (21 → 23 insider), yani orada bütçe bağlayıcı. Ölçülmedi.
