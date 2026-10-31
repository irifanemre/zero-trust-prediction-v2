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
