# Faz A-2 — şema farkındalığını karar yoluna bağlamak: ön kayıt

**Yazım: 31 Ekim 2026, uygulamadan ÖNCE.**

## Problem

Faz A-1 (şema profilleyici) **rapor ediyor** ama hiçbir kararı değiştirmiyor. Sistem hâlâ
"sinyal üretilemiyor" ile "desen görülmedi" arasında ayrım yapmıyor.

Bedeli ölçüldü: r6.2'de `UEBA-0003` (ağırlık 8) **yapısal olarak ölüydü** ve kural sağlığı raporu
onu `sinanmadi — bu veride desen görülmedi` diye gösterdi. O cümle teknik olarak doğru,
operasyonel olarak yanlış: desen görülmedi değil, **bakılamadı**.

Aynı sorun kapsama raporunda da var. r6.2'nin S5 senaryosu `UEBA-0002` + `UEBA-0003` bekliyor.
`UEBA-0003` ölü olduğu için S5 **yarı ölçülebilir** bir senaryo; rapor ise onu diğer kaçanlarla
aynı kefeye koyup `KALDI (tetiklenmedi)` diyor. "3/4" rakamı bu yüzden olduğundan emin görünüyor.

## Değişiklik

| # | Ne | Dosya |
|---|---|---|
| 1 | Sinyal → türev özellik → ham alan zinciri | `availability.py` (yeni) |
| 2 | Kuralın gerektirdiği sinyaller koşuldan çıkarılır | `availability.py` |
| 3 | Şemadan ölü kural değerlendirilmez, **sayılır** | `detection/engine.py` (**donmuş**) |
| 4 | Kural sağlığı: `sinanamaz — şema` ayrı durum | `metrics.py` |
| 5 | Kapsama: beklenen kuralların hepsi ölüyse `ÖLÇÜLEMEDİ` | `metrics.py` |
| 6 | Bayrak `sema_farkindaligi` | `config.py` (**donmuş**) |

Motor ve yapılandırma donmuş kümede → **dondurma v8** yazılacak.

## Bayrak

`sema_farkindaligi: bool = False` — varsayılan **kapalı**. Kapalıyken davranış birebir eskisi;
sözleşme testiyle bağlanacak.

## Başarı eşikleri — ölçümden ÖNCE

Bu faz **yakalama artırmayı hedeflemiyor**; raporun dürüstlüğünü artırıyor. Eşikler buna göre:

1. **Bayrak kapalıyken** r4.2 sonucu referansla **birebir** aynı (kapsama, vaka, precision, recall).
2. **Bayrak açıkken r4.2'de** kapsama **değişmez** (22/34). r4.2'de ölü sinyal yok, dolayısıyla
   açmanın hiçbir etkisi olmamalı — bu, mekanizmanın yanlış pozitif üretmediğinin testidir.
3. **Bayrak açıkken r6.2'de** `UEBA-0003` `sinanamaz — şema` olarak raporlanır ve S5
   `ÖLÇÜLEMEDİ` ya da kısmi işaretlenir.

Üçüncü şart sağlanmazsa mekanizma işe yaramıyor demektir.

## Beklentiler — karamsar

1. r4.2'de **hiçbir şey değişmeyecek** (orada ölü sinyal yok).
2. r6.2'de yakalama rakamı **düşmeyecek** ama `3/4` ifadesi `3/4 (1 senaryo kısmi ölçülebilir)`
   hâline gelecek — yani rakam aynı, **anlamı** netleşecek.
3. Bu faz hiçbir insider kazandırmayacak. Kazancı **ölçümün güvenilirliği**.

Üçüncü beklenti bilinçli: bir fazın değeri her zaman yakalama artışı olmak zorunda değildir.
Yanlış bir rakama güvenmek, düşük bir rakamı bilmekten daha pahalıdır.

---

# Sapmalar — ölçümden SONRA eklendi (31 Ekim 2026)

Ön kayıt metni yukarıda **değiştirilmedi**. Ölçüm sırasında planın dışına çıkılan her nokta burada.
Sonuçlar: `docs/faz-a2-sonuclar.md`.

## Sapma 1 — ölçüt 1 ve 2 sentetik veride ölçüldü, r4.2'de değil

Plan "r4.2'de birebir aynı" diyordu. Ölçüm, r4.2'nin **şema durumunu** sentetik veride yeniden
üreterek yapıldı (`outcome` sabit, `process`/`cmdline` boş) ve iki koşu bire bir karşılaştırıldı:
risk skorları, kuyruk ve kural tetiklenme sayıları birebir aynı.

**Gerekçe:** r4.2'de tam ablasyon 11 varyant × ~40 dk. Sentetik koşu aynı sözleşmeyi (skor
değişmez, rapor değişir) dakikalar içinde ve **sürekli** sınar — testin içinde, bir kerelik koşuda
değil. **Zayıflığı:** r4.2'nin kendi sayıları (22/34, 1.939 vaka) bu fazda yeniden ölçülmedi;
dayanak, dondurma kontrolü + bayrak kapalıyken kod yolunun hiç çalışmaması.

## Sapma 2 — ölçüt 2 bir YANLIŞ POZİTİF buldu ve harita düzeltildi

Ölçüt 2 ilk koşuda **kaldı**: bir kullanıcının skoru 1,26 ↔ 189,08 oynadı. Sebep mekanizmanın
kendi haritasındaki iki hatalı bağımlılıktı:

| Sinyal/özellik | Yanlış | Doğru |
|---|---|---|
| `kesif_genisligi_akran_kati` | `recon_process_count` | `distinct_resources` (`profile.py:607`) |
| `files_accessed` | `resource` | `source` (`features.py:69`) |

Harita düzeltildi, ölçüt 2 geçti. Düzeltme **ölçüm görüldükten sonra** yapıldı — ama düzeltmenin
dayanağı üretim kodudur, etiket ya da sonuç değil: `profile.py:607` ve `features.py:69` ne
kullanıyorsa harita onu yazıyor. Yine de sıra bu: önce ölçüm kaldı, sonra kod değişti. Kayda
geçiyor. Aynı hatanın tekrarına karşı `test_turev_zinciri_uretim_koduyla_tutarli` eklendi.

## Sapma 3 — ÖLÇÜT 3 KALDI, mekanizma düzeltilmedi

r6.2'de `UEBA-0003` ölü **raporlanmadı**: `bytes_out` üç kanaldan beslenir ve r6.2'de yalnız web
kanalında boştur (`email.csv:size` ve `file.csv:content` dolu), dolayısıyla alan düzeyinde
"kullanılabilir" görünüyor. Mekanizmanın çözünürlüğü **alan** düzeyinde, sorun **kanal** düzeyinde.

Ön kayıt "üçüncü şart sağlanmazsa mekanizma işe yaramıyor demektir" diyordu. Düzeltme:
mekanizma **kısmen** çalışıyor — iki gerçek ölü kural buldu (`UEBA-0006`, `UEBA-0008`; toplam
ağırlık 11) ama asıl aradığı vakayı göremedi.

**Bu sapmada mekanizma ölçüm görüldükten sonra genişletilMEDİ.** Kanal düzeyi çözünürlük ayrı bir
faz (A-3) ve ayrı bir ön kayıtla yapılacak. Bayrak varsayılan **kapalı** kalıyor.

## Sapma 4 — doğrulama 30 günlük pencereyle yapıldı

Şema kararı veri setinin şemasından çıkar, koşu sonucundan değil; harita motor kurulurken, tek gün
işlenmeden hesaplanır. Bu yüzden 30 günlük pencere 360 günlükle **aynı şema kararını** verir ve
17 GB'lık `http.csv`'yi bir kez taramak yeterlidir.

**Pencereye bağlı olan tek şey senaryo sayımıdır:** r4.2'de 2, r6.2'de 1 senaryo pencereye düştü.
`ölçülebilir 2 · ÖLÇÜLEMEZ 0` satırları bu küçük örneklem içindir ve **kapsama oranı iddiası
değildir**.
