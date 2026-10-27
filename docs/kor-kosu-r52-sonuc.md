# CERT r5.2 kör koşu — sonuç raporu

Plan: [kor-kosu-plani.md](kor-kosu-plani.md) (ön kayıt; §10 koşu öncesi ekler). Koşu 27 Ekim 2026'da bir kez yapıldı.
Kurallar, eşikler, ağırlıklar ve metrik tanımları koşudan sonra değiştirilmedi.

## Kayıt

| | |
|---|---|
| Kural sürümü | `kurallar-donduruldu-v1`; koşudan hemen önce `python -m ztp.freeze --check …` → `donmuş durumla aynı` |
| HEAD | `7df7bce` (etiket `kor-kosu-r5.2-hazir`) |
| Komut | `python scripts/kor_kosu_r52.py --cert-dir C:/data/cert_r5.2/r5.2 --out C:/data/ztp_out/kor_r52` |
| Pencereler | 2010-06-08 – 2010-09-05 · 2010-09-06 – 2010-12-04 · 2010-12-05 – 2011-03-04 · 2011-03-05 – 2011-06-02 (her biri `--days 90 --warmup 21`, bütçe 10/gün). Atlanan: 2010-03-10 – 2010-06-07 |
| Örneklem | f = 0,55 tek oranlı katmanlı (§10): **1102 kullanıcı, 56 insider, oran %5,08** (nüfus 2000 / 99 / %4,95) |
| Birincil LR | `configs/models/kor-r52-birincil-lr.json`, sha256 `433ffbf9…`, C = 0,001, eşik 0,1173 |
| Süre, bellek | 4 × ~28 dk; tepe 11,5–11,6 GB (tahmin 12,0 GB) |
| Çıktılar | `C:\data\ztp_out\kor_r52\` (`sonuclar.json`, `ozet.md`, `pencere_*.json/.npz`, `sapma_ikincil_lr.json`) |

## Sonuçlar ve r4.2 ile karşılaştırma

r4.2 sütunu kurallar o veride ayarlandığı için **üst sınırdır**. r4.2 tüm kurumda (1000 kullanıcı) tek 90 günlük
pencere; r5.2 örneklemde (1102 kullanıcı) 360 gün.

| Metrik | r4.2 (ayarlanmış) | r5.2 (kör) |
|---|---|---|
| Yakalama, değerlendirilebilir (GEÇTİ / n) | 18/20 (0,90) | **25/30 (0,83)** |
| Kısmi pencereli (GEÇTİ / n) | 8/14 | 13/26 |
| precision@1 · @3 · @5 · @10 (varlık-gün) | 0,40 · 0,22 · 0,15 · 0,09 | **0,20 · 0,12 · 0,10 · 0,08** |
| Kullanıcı bazında TP · FN · FP · TN | 18 · 2 · 251 · 715 | 25 · 5 · 459 · 587 |
| Kullanıcı bazında precision · recall | 0,067 · 0,90 | 0,052 · 0,83 |
| Erkenlik medyanı (GEÇTİ, gün) | 8 | 9 |
| Vaka hacmi | 10/gün (bütçe dolu) | 3545 vaka / 360 gün (~9,8/gün) |

**Senaryo türüne göre (değerlendirilebilir):**

| Tür | r4.2 | r5.2 | r5.2 erkenlik medyanı | r5.2 kaçırılanlar |
|---|---|---|---|---|
| S1 — mesai dışı + USB + wikileaks, ayrılış | 13/13 | 13/15 | 9 gün | 2 BÜTÇE DIŞI (beklenen kurallar tetiklendi, kuyruğa girmedi) |
| S2 — iş arama + USB artışı | 3/4 | **2/5** | 53 gün | 1 BÜTÇE DIŞI, 2 KALDI (tetiklenmedi) |
| S3 — sysadmin keylogger | 2/3 | 6/6 | 1 gün | — |
| S4 — başkasının makinesinden giriş + e-posta ile sızdırma (**ayar sırasında hiç görülmedi**) | — | **4/4** | 44,5 gün | — (kısmi pencerelilerde 12/13) |

**Kuyruğa girişte yer alan kurallar** (değerlendirilebilir insider sayısı, r5.2): UEBA-0017 19 · UEBA-0001 14 ·
UEBA-0005 10 · UEBA-0002 8 · UEBA-0007 7 · PRED-0012 5.

### Kural sağlığı — 21 kuraldan kaçı sınandı

Değerlendirme günlerinde tetiklenme sayıları. Gölge moddaki kurallar kuyruğa girmez, ayrı kaydedilir.

| Kural | r4.2 canlı | r5.2 canlı | Not |
|---|---|---|---|
| UEBA-0001 mesai dışı | 386 | 1663 | |
| UEBA-0002 ilk kez görülen uygulama | 218 | 892 | |
| UEBA-0003 anormal veri çıkışı | 0 | **24** | r5.2'de ilk kez tetiklendi; hiçbir insider'ın kuyruk girişinde yer almadı |
| UEBA-0005 yeni cihaz | 2050 | 9495 | S3/S4'ün ana kuralı |
| UEBA-0007 mesai dışı toplu dosya | 11 | 13 | |
| UEBA-0017 taşınabilir medya | 213 | 744 | en çok insider yakalayan kural |
| PRED-0012 risk yörüngesi | 25 | 80 | |
| UEBA-0009 akrandan sapma (gölge) | 1875 | 5626 | gölge mod |
| UEBA-IF01 Isolation Forest (gölge) | 933 | 4080 | gölge mod |
| DQ-0010 | — | — | devre dışı: EDR kaynağı yok |
| HONEY-0018/19/20, PRED-0011/13/14, REL-0015/16, UEBA-0004/0006/0008 | 0 | 0 | |

**r4.2: 8/21 (6 canlı + 2 gölge). r5.2: 9/21 (7 canlı + 2 gölge).** Fark yalnız UEBA-0003. Tetiklenmeyen 12 kuralın
10'u CERT'te bulunmayan kaynaklara (İK olayları, başarısız giriş, IP/konum, EDR, tuzak) bağlı. REL-0015/16 için kaynak
var (paylaşımlı makineler) ama r5.2'de de tetiklenmedi. Daha önce konuşulan "9/21" r4.2 için bu tanımla 8'dir.

### Lojistik regresyon (7 günlük olasılık)

| | n (pozitif) | AUC | ECE | Brier / taban | F1 |
|---|---|---|---|---|---|
| **Birincil:** r4.2'de eğitilmiş model, r5.2'ye bir kez | 258.966 (1915) | **0,687** | 0,036 | 0,0223 / 0,0073 | 0,040 (r4.2 eşiği) |
| Sezgisel model, aynı satırlar | 258.966 (1915) | 0,714 | 0,065 | 0,0230 / 0,0073 | — |
| İkincil (düzeltilmiş bölme, aşağıya bkz.): r5.2 içinde eğitim, test | 10.914 (54) | 0,907 | 0,002 | 0,0050 / 0,0049 | 0,055 |
| İkincil, sezgisel | 10.914 (54) | 0,846 | 0,069 | 0,0208 / 0,0049 | — |

r4.2'de eğitilen model başka bir kuruma **taşınmadı**. AUC 0,84'ten 0,69'a düştü, sezgisel modelin de altında kaldı.
Brier tabanın üç katı; olasılıklar kalibre değil. Aynı özelliklerle r5.2'nin kendi verisinde eğitilen model ise
AUC 0,91 ve iyi kalibrasyon veriyor. Yorum: öğrenen modelin kurumun kendi etiketiyle eğitilmesi gerekir (mimari 14.5).

## Önceden yazılan beklentilerle (§5) karşılaştırma

- *Yakalama ve precision@1'in r4.2'den düşük çıkması:* **gerçekleşti.** Yakalama 0,90 → 0,83, precision@1 0,40 → 0,20.
- *UEBA-0003 kör kalabilir, S4 REVİZYON GEREKLİ çıkabilir:* **kısmen.** UEBA-0003 24 kez tetiklendi ama hiçbir insider'ı
  yakalamadı. S4 yine de 4/4 GEÇTİ, çünkü beklenen kurallardan UEBA-0005 tetiklendi.
- *S1/S2'de URL kategorileri belirleyici olacak:* S1 13/15 yüksek kaldı. S2 2/5'e düştü; S2 kaçırmalarının ikisinde hiçbir
  kural tetiklenmedi.

## Sapma: ikincil LR bölmesi (koşu sonrası fark edildi)

**Hata.** `cert-r5.2-kullanici-bolmesi.json` (2000 kullanıcı) ve `cert-r5.2-orneklem.json` aynı tohumla (42) ve aynı
`RandomState` akışıyla üretildi. Katman içi permütasyonlar örtüştüğü için örneklemin 1102 kullanıcısının **1098'i eğitim
parçasına** düştü; doğrulama ve test parçalarında 2'şer kullanıcı kaldı. Ön kayıtlı ikincil sonuç bu yüzden **geçersiz**:
test n = 0, tamamlayıcı protokolde test 137 satır / 2 kullanıcı (AUC 0,645). Parça bazlı precision@k da (doğrulama/test
= 1,0) aynı nedenle anlamsız; yukarıdaki precision değerleri "tümü" satırıdır ve bölmeden bağımsızdır.

**Etki alanı.** Bölme yalnız ikincil LR'de ve parça bazlı precision@k'da kullanılır. Yakalama, precision (tümü),
confusion, erkenlik, kural sağlığı ve birincil LR etkilenmez.

**Düzeltme.** Bölme aynı yöntemle (`make_user_split`, 70/15/15, tohum 42) yalnız örneklemin kullanıcıları üzerinde
yeniden üretildi (`configs/splits/cert-r5.2-orneklem-bolmesi.json`: 771/166/165 kullanıcı, insider 39/9/8). İkincil
protokol kaydedilmiş tahmin satırlarıyla yeniden hesaplandı; boru hattı yeniden koşulmadı
(`scripts/kor_kosu_r52_sapma.py` → `sapma_ikincil_lr.json`). Düzeltilmiş bölme sonuç görüldükten sonra üretildiği için
ön kayıtlı değildir. Ama mekanik bir işlemdir: seçim, ayar ya da alternatif deneme yoktur, ilk denemede kullanılan
sonuçtur. Düzeltilmiş ikincil sonuç: C = 0,1 (doğrulama log-loss), test AUC 0,907, ECE 0,0017, F1 0,055. Tamamlayıcı
(tüm günler): C = 0,01, test AUC 0,840.

## Sınırlar

- **Örneklem:** Kullanıcıların %55'i. Akran grupları küçüldü (en az grup boyutu 8 korunuyor). Bütçe 10/gün 1102
  kullanıcıya uygulandı; tüm kurumda (2000) kişi başı bütçe daha düşük olurdu.
- **İnsider yoğunluğu:** %5. Gerçek bir kuruma göre çok yüksek; precision iyimser.
- **Senaryo bilgisi:** S1–S3 tanımları r4.2'den biliniyordu. Yalnız S4 tamamen yeni.
- **Tek sentetik üretici:** r4.2 ve r5.2 aynı üreticiden (CMU SEI) çıkıyor. Kör koşu, kuralların bu üreticinin başka bir
  kurumuna genellenmesini ölçer; gerçek bir kuruma genellenmesini ölçmez.
- **Kaynak kapsamı:** 21 kuralın 12'si bu veride sınanamadı (yukarıdaki tablo).
