# CERT r6.2 — v4 bileşenleri açık ölçüm (KÖR DEĞİL)

**Koşu: 29–30 Ekim 2026**, 5 sa 15 dk. HEAD `fadf6e5`, dondurma `kurallar-donduruldu-v4`
→ koşudan önce **`donmuş durumla aynı`**. Çıktı: `ztp_out_r62_v4/`.

> **Bu bir kör koşu değildir.** r6.2 kör koşusu 29 Ekim'de bir kez yapıldı (`docs/kor-kosu-r62-sonuclar.md`)
> ve o veri o koşuyla yandı. Buradaki rakamlar aynı veri ikinci kez görüldükten sonra üretildi; yansız
> genelleme tahmini değildir. Koşu kaydı bunu dosyanın içinde taşıyor:
> `"tur": "geliştirme ölçümü (v4 bileşenleri açık) — KÖR DEĞİL"`.
> Geriye kalan tek gerçek kör veri **r1**'dir ve dokunulmadı.

Açık bileşenler (`--ac`, koşu kaydındaki `v4_bilesenleri`):

```json
{"graf_enabled": true, "graf_agirligi": 0.5, "adwin_enabled": true, "bayes_kapi_esigi": 0.3,
 "belirsizlik_enabled": true, "kanit_dogrulama": "dengeli", "cok_ajanli_rapor": true}
```

İkisi de bütçe 30, aynı bölme (sha256 `6f7168f…`), aynı örneklem (`9f694b1…`), aynı model (`2beabe4…`),
aynı ön kayıt commit'i (`adf4a59`). Tek fark yedi bayrak.

## 1. Sonuç tablosu

| Alan | v3 (kör, `0ed0472`) | v4 (ölçüm, `fadf6e5`) | Değişim |
|---|---|---|---|
| **Yakalama** | **3/4 (0,750)** | **3/4 (0,750)** | **yok** |
| TP / FN | 3 / 1 | 3 / 1 | yok |
| FP | 538 | **1114** | **2,07×** |
| TN | 2258 | 1682 | −576 |
| precision (ikili) | 0,006 | **0,003** | yarıya |
| precision@1 | 0,014 | **0,003** | ⅕'ine |
| precision@10 | 0,003 | 0,001 | ⅓'üne |
| **Erkenlik medyanı** | **0 gün** | **10 gün** | **+10** |
| Vaka | 8.516 | 10.993 | +%29 |
| Kuyruğa giren (4 pencere toplamı) | 1.262 | 2.435 | 1,93× |
| Süre | 212 dk | 309 dk | 1,46× |
| Tepe bellek | 17,53 GB | 17,62 GB | ≈aynı |

Senaryo bazında yakalama **birebir aynı**: S1 ✔, S3 ✔, S4 ✔, S5 ✘, S2 ölçülemedi (değiştirilmiş
senaryo yok). v4'ün kaçırdığı insider, v3'ün kaçırdığı insider.

## 2. Tek gerçek kazanç: erkenlik

| Senaryo | v3 | v4 |
|---|---|---|
| S1 | 11 gün | 11 gün |
| S3 | 0 gün | 0 gün |
| S4 | **0 gün** | **10 gün** |
| medyan | 0 | **10** |

S4 v3'te sızıntı gününde yakalanıyordu; v4'te 10 gün önce kuyruğa girdi. Operasyonel olarak
bunun değeri var — ama **n = 3**. Bir senaryonun bir ölçümde 10 gün öne gelmesi, üç
gözlemlik bir medyanı sıfırdan ona taşır. Bunu "sistem artık 10 gün önce uyarıyor" diye
okumak istatistiksel olarak savunulamaz.

## 3. Kaybın kaynağı: graf bir çarpan

Kural tetiklemeleri yukarı fırladı:

| Kural | v3 | v4 | Kat |
|---|---|---|---|
| PRED-0012 | 297 | 1122 | 3,8× |
| UEBA-0017 | 1.772 | 5.603 | 3,2× |
| UEBA-0007 | 10 | 75 | 7,5× |
| UEBA-0001 | 3.810 | 3.955 | 1,04× |
| UEBA-0005 | 20.762 | 20.379 | 0,98× |

Graf riski skora **çarpan** olarak giriyor (`scoring.py`: `1 + 0,5 × graf_riski`). Zaten
tetiklenen kuralların skorunu büyütüyor, böylece eşiği aşan kullanıcı sayısı artıyor —
kuyruk 1,93× şişiyor. Ama `1,5 × 0 = 0`: hiçbir kural tetiklemeyen kullanıcıya graf hiçbir
şey ekleyemez. Kaçırılan insider tam olarak o durumda. **Yapısal tavan budur** ve bu ölçüm
onu doğruladı: 1.173 ek yanlış alarm, sıfır ek insider.

## 4. r4.2'deki kazanç neden burada yok

| | r4.2 (ayar verisi) | r6.2 (bu ölçüm) |
|---|---|---|
| Kapsama | 21 → **26** | 3 → **3** |
| recall@10_kullanıcı | 0,618 → **0,765** | — |
| FP / kuyruk | 112 → 221 kullanıcı | 538 → 1114 |
| precision@1 | 0,42 → **0,244** | 0,014 → **0,003** |

r4.2'de v4 hem yakalamayı artırdı hem precision'ı düşürdü. r6.2'de **yalnızca** precision'ı
düşürdü. Aradaki fark, r4.2'nin ayar verisi olması: bayrak değerleri (`graf_agirligi=0,5`,
`bayes_kapi_esigi=0,3`) orada seçildi. r6.2'de aynı değerler yakalamaya dokunmadı. Bu,
v4 kazancının **r4.2'ye aşırı uyum** olduğuna dair ilk ciddi kanıttır.

## 5. Varsayılanlar neden değişmiyor

Bu ölçümden sonra da `config.py`'de v4 bileşenlerinin tamamı **varsayılanda kapalı**.
Açmak için kanıt gerekir ve kanıt şu an ters yönde: ölçülen tek veri setinde (r6.2) açmak
yakalamayı değiştirmeden yanlış alarmı ikiye katlıyor. Dondurma manifestosu v4 bu haliyle
geçerli; bayraklar yalnızca `--ac` ile açılıyor ve açıldığı koşunun kaydına yazılıyor.

## 6. Bu ölçümün cevaplamadığı sorular

1. **Hangi bileşen?** Graf, ADWIN ve Bayes kapısı birlikte açıldı. r4.2'deki kapsama
   kazancını hangisinin ürettiği, S4'teki 10 günü hangisinin getirdiği **ölçülmedi**.
   Bileşen bazında ablasyon gerekiyor.
2. **Bayes kapısı hiç çalışmadı.** Analist etiketi yok (`bayes_elenen_vaka: 0`); kapı
   tasarım gereği etiketsiz ortamda hiçbir şey elemez. Bu ölçümde o bileşen etkisizdi.
3. **Kör genelleme.** Yukarıdaki hiçbir rakam kör değildir. r1 bu iş için saklı.
