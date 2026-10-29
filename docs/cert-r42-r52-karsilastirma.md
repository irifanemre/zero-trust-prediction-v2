# CERT r4.2 ve r5.2 karşılaştırması (70/15/15)

Aynı kurallar (`kurallar-donduruldu-v1`) iki ayrı CERT kurumunda, kullanıcı bazlı 70/15/15 eğitim / doğrulama / test
bölmesiyle ölçüldü. Kurallar r5.2'yi hiç görmeden yakalama oranını korudu (%90 → %83). 90 günlük pencere başına yanlış
alarm oranı iki veride de yaklaşık %25. İlk vakanın isabeti (precision@1) yarıya düştü. Öğrenen model kendi kurumunda
iyi çalışıyor ama başka kuruma taşınmıyor.

## Koşulların farkı

İki ölçüm aynı koşullarda üretilmedi. Tablolar bu farklarla birlikte okunmalı.

| | r4.2 | r5.2 |
|---|---|---|
| Kurallar bu veriyi gördü mü? | **Evet.** Kurallar r4.2'nin tamamına bakılarak ayarlandı; doğrulama ve test grubu yalnız öğrenen model için görülmemiş | **Hayır.** Üç grup da kurallar için görülmemiş |
| Kullanıcı | 1000 (tüm kurum) | 1102 (2000 kişilik kurumdan %55 katmanlı örneklem; bellek sınırı) |
| Değerlendirme dönemi | 1 pencere, 90 gün (2 Eyl – 30 Kas 2010) | 4 pencere, 360 gün (8 Haz 2010 – 2 Haz 2011) |
| Insider (eğitim / doğrulama / test) | 36 / 8 / 8 | 39 / 9 / 8 |
| Senaryo türleri | S1–S3 | S1–S4 (S4 ayar sırasında hiç görülmedi) |
| Bölme dosyası | `configs/splits/cert-r4.2-kullanici-bolmesi.json` | `configs/splits/cert-r5.2-orneklem-bolmesi.json` |

Boru hattı her iki veride tüm kurumda (r5.2'de tüm örneklemde) bir kez koşuldu. Akran grupları ve günlük bütçe kurum
geneli olduğu için alt kümede koşmak sistemi değiştirirdi. Metrikler sonradan gruplara ayrılarak hesaplandı.

## Kural sistemi: 70/15/15 sonuçları

| Metrik | r4.2 Eğitim | r4.2 Doğrulama | r4.2 Test | r5.2 Eğitim | r5.2 Doğrulama | r5.2 Test |
|---|---|---|---|---|---|---|
| Kullanıcı | 700 | 150 | 150 | 771 | 166 | 165 |
| Yakalama, değerlendirilebilir (GEÇTİ / n) | 14/16 | 2/2 | 2/2 | 18/21 | 3/4 | 4/5 |
| Kısmi pencereli (GEÇTİ / n) | 6/10 | 1/2 | 1/2 | 8/18 | 3/5 | 2/3 |
| precision@1 | 0,37 | 0,12 | 0,07 | 0,15 | 0,15 | 0,07 |
| precision@10 | 0,11 | 0,07 | 0,04 | 0,07 | 0,13 | 0,06 |
| Yanlış alarm alan normal kullanıcı, 90 günde | %24 | %32 | %29 | %25 | %18 | %26 |
| Erkenlik medyanı (gün) | 8 | 6 | 7 | 9 | 9 | 5 |

**Tümü:** r4.2 18/20 yakalama (%90), precision@1 0,40, yanlış alarm %26. r5.2 25/30 yakalama (%83), precision@1 0,20,
yanlış alarm %24 (90 günlük pencere ortalaması; bir yıl boyunca en az bir kez kuyruğa giren normal kullanıcı %44).

Okurken iki noktaya dikkat:

- **Doğrulama ve test grupları çok küçük.** r4.2'de 2'şer, r5.2'de 4–5 değerlendirilebilir insider var. Bir kişi oranı
  20–50 puan oynatır; bu gruplarda yalnız büyük farklar anlamlı.
- **Grup bazında precision@k, "analist yalnız o grubun kullanıcılarını görseydi" sorusudur.** Küçük grupta günün ilk
  vakası daha zayıf adaylardan gelir, bu yüzden değer "Tümü"nden düşük çıkar.

r5.2'de kaçırılan 5 değerlendirilebilir insider'dan 3'ünde beklenen kural tetiklendi ama günlük 10 vakalık bütçeye
giremedi. Kalan 2'si iş arama senaryosuydu (S2) ve hiçbir kural tetiklenmedi.

## Öğrenen model (7 günlük olasılık)

Kural sisteminden ayrı ölçülür. Model eğitim grubunda eğitilir, C doğrulamada seçilir, test grubuna bir kez bakılır.

| | r4.2 test | r5.2 test |
|---|---|---|
| Ana protokol (7 günlük embargo): AUC · ECE · F1 | 0,83 · 0,0015 · 0,00 (29 pozitif satır) | 0,91 · 0,0017 · 0,06 (54 pozitif satır) |
| Tamamlayıcı (tüm günler): AUC · ECE · F1 | 0,84 · 0,0014 · 0,08 | 0,84 · 0,0017 · 0,06 |
| Sezgisel model, tamamlayıcı test AUC | 0,52 | 0,69 |
| **Kurumlar arası:** r4.2'de eğitilen model r5.2'nin tamamında | — | AUC 0,69 · ECE 0,036; sezgiselin (0,71) altında |

Öğrenen model her iki kurumda kendi verisiyle eğitilince sezgisel modelden iyi ve kalibre. Başka bir kurumda eğitilmiş
model ise taşınmadı. Mimarinin öngördüğü gibi (14.5) model kurumun kendi etiketleriyle eğitilmeli. Varsayılan olarak
risk skoruna eklenmediği için (`prediction_weight: 0`) kural sonuçları bu modelden etkilenmez.

## Kural sağlığı

Değerlendirme günlerinde tetiklenen kurallar: **r4.2'de 21'in 8'i, r5.2'de 9'u.** Her ikisinde de 6 kural canlı
tetiklendi: UEBA-0001/0002/0005/0007/0017 ve PRED-0012. Gölge modda ikisi tetiklendi: UEBA-0009 ve UEBA-IF01. r5.2'de
UEBA-0003 da tetiklendi (24 kez) ama hiçbir insider'ı yakalamadı. CERT'te sızdırma normal e-posta boyutları içinde,
az az yapılıyor.

Tetiklenmeyen 12 kuralın 10'u CERT'te bulunmayan kaynaklara bağlı: İK olayları, başarısız giriş, IP/konum, EDR, tuzak.
REL-0015 ve REL-0016 için kritik varlık listesi ve kaynak erişim kayıtları gerekir; CERT'te ikisi de yok.

## Kayıt ve sapma

- **r5.2 kör koşu.** r5.2 önce ön kayıtlı tek bir kör koşuyla ölçüldü (27 Ekim 2026, HEAD `7df7bce`, etiket
  commit `998469d`). Plan: `docs/kor-kosu-r52-plani.md`, ön kayıt commit'i `7792965` (8 Ekim 2026). Kural ve metrik değerleri o
  koşudan sonra değiştirilmedi; bu belgedeki r5.2 sayıları o koşunun çıktılarıdır.
- **Örneklem.** 2000 kullanıcının tamamı makinenin belleğine sığmadı (tahmini 21,8 GB). Plan gereği tek oranlı katmanlı
  örneklem alındı: f = 0,55, tohum 42, 1102 kullanıcı, 56 insider. Insider oranı korundu (%5,08; nüfusta %4,95).
- **Bölme hatası (düzeltildi).** İlk r5.2 bölmesi örneklemle aynı rastgele sayı akışından üretildiği için örneklemin
  1102 kullanıcısının 1098'i eğitim grubuna düştü. Bölme aynı yöntemle (70/15/15, tohum 42) örneklem üzerinde yeniden
  üretildi ve sonuçlar kayıtlı çıktılardan yeniden hesaplandı. Boru hattı yeniden koşulmadı
  (`scripts/kor_kosu_r52_sapma.py`).
- **Yeniden kurulan değerler.** r5.2'nin grup bazında precision@k değerleri vaka dosyalarındaki günlük sıralamadan
  yeniden kuruldu. Tümü için kayıtlı değerle fark ±0,01'dir (0,197'ye karşı 0,203).
- **Çıktılar** repo dışında tutulur: r4.2 `C:\data\ztp_out\cert_eval\`, r5.2 `C:\data\ztp_out\kor_r52\`.

## Sınırlar

- **Tek sentetik üretici.** Her iki veri seti de aynı programla üretildi (CMU SEI). Bu karşılaştırma sistemin bu
  üreticinin iki farklı kurumunda tutarlı olduğunu gösterir; gerçek bir kurumda nasıl çalışacağını göstermez.
- **Insider yoğunluğu** (%5) gerçek kurumlara göre çok yüksek; precision iyimser.
- **r5.2 örneklemi** akran gruplarını küçülttü. Bütçe 10/gün, 1102 kullanıcıya uygulandı; tüm kurumda kişi başı bütçe
  daha düşük olurdu.
- **Senaryo bilgisi.** S1–S3 tanımları r4.2'den biliniyordu. Yalnız S4 tamamen yeniydi.
