# r6.2'de yalnız graf çarpanı — sonuçlar

**Koşu: 31 Ekim 2026, 4 sa 44 dk.** r6.2, 4 pencere, 360 gün, bütçe 30, 2801 kullanıcı.
Dondurma `kurallar-donduruldu-v6` → `donmuş durumla aynı`. Yapılandırma: `--ayar graf`
(yalnız `graf_enabled=True, graf_agirligi=0.5`).

> **Kör değil.** r6.2 bir kez kör koşuldu (29 Ekim) ve o veri yandı.

## Hipotez ve sonuç

**Hipotez:** r6.2'deki "hepsi açık" ölçümü grafı, zarar verdiği ölçülmüş ADWIN'le **birlikte**
açmıştı ve sonuç +0 insider / +1.173 yanlış alarmdı. Graf tek başına açılırsa r4.2'deki gibi
(+5 insider) kazandırabilir.

**Sonuç: HİPOTEZ ÇÜRÜDÜ.**

| Ölçüt | Taban (hepsi kapalı) | Hepsi açık | **Yalnız graf** |
|---|---|---|---|
| **Yakalama** | **3/4** | **3/4** | **3/4** |
| TP / FN | 3 / 1 | 3 / 1 | 3 / 1 |
| **Yanlış pozitif** | **538** | 1.114 | **1.295** |
| precision | 0,006 | 0,003 | **0,002** |
| precision@1 | 0,014 | 0,003 | **0,014** |
| precision@3 | 0,007 | 0,001 | 0,006 |
| **Erkenlik medyanı** | **0 gün** | **10 gün** | **10 gün** |
| Vaka | 8.516 | 10.993 | 9.722 |

Senaryo bazında üç koşu da **birebir aynı**: S1 ✔, S3 ✔, S4 ✔, S5 ✘, S2 ölçülemedi.

## Üç bulgu

### 1. Grafın r4.2'deki kazancı r6.2'ye TAŞINMIYOR

r4.2'de graf çarpanı 22/34 → **27/34** veriyordu; recall@10 0,618 → 0,824. r6.2'de **tek bir ek
insider bile** getirmiyor ve yanlış pozitifi 538'den **1.295'e** çıkarıyor.

Bu, projedeki en net **aşırı uyum kanıtıdır**. 41 bayraktan tutarlı değer ürettiğini düşündüğüm
tek bileşen, ikinci veri setinde değer üretmiyor.

### 2. Graf tek başına, hepsi açıkken'den DAHA ÇOK yanlış alarm üretiyor

538 → 1.295 (yalnız graf) vs 538 → 1.114 (hepsi açık). Yani ADWIN ve diğer bileşenler r6.2'de
yanlış alarmı bir miktar **azaltıyormuş**. r4.2'de ADWIN zararlıydı; r6.2'de etkisi ters yönde.

Bu, bileşen etkilerinin **veri setine bağlı olduğunun** ve r4.2'de ölçülen bir etkinin başka
veride tersine dönebileceğinin doğrudan kanıtıdır.

### 3. Erkenlik kazancı grafa ait — ve bu tek olumlu bulgu

| Senaryo | Taban | Yalnız graf |
|---|---|---|
| S1 | 11 gün | 11 gün |
| S3 | 0 gün | 0 gün |
| **S4** | **0 gün** | **10 gün** |
| medyan | 0 | **10** |

v4 ölçümünde erkenliğin 0'dan 10'a çıktığını görmüş ama **hangi bileşenden geldiğini
bilmiyorduk**. Artık biliyoruz: graf. S4, sızıntı gününde değil 10 gün önce kuyruğa giriyor.

Ama **n = 3**. Tek bir senaryonun öne gelmesi üç gözlemlik medyanı sıfırdan ona taşır. Bu,
"sistem 10 gün önce uyarır" demek değildir.

Ayrıca **precision@1 korunuyor** (0,014, tabanla aynı) oysa hepsi açıkken 0,003'e düşüyordu.
Kuyruğun tepesini bozan şey graf değil, diğer bileşenlermiş.

## Ne yapılacak: varsayılan DEĞİŞMİYOR

Bu koşunun amacı "graf varsayılan açık olsun mu" sorusunu cevaplamaktı. **Cevap hayır.**

| Gerekçe | |
|---|---|
| r4.2'de +5 insider | r6.2'de **+0** |
| r4.2'de +130 vaka maliyeti | r6.2'de **+1.206 vaka, +757 yanlış pozitif** |
| Tek olumlu: erkenlik | n=3, tek senaryodan |

Bir bileşenin varsayılan açılması için **iki farklı veride** değer üretmesi gerekir. Graf bunu
sağlamadı.

## RQ3'ün cevabı

Brief'in araştırma sorularından biri şuydu:

> **RQ3:** r4.2'deki iyileştirmeler r5.2 ve r6.2'ye genelleniyor mu?

**Hayır.** Ölçülen tek bileşen için cevap net: r4.2'de +5, r6.2'de +0 ve ciddi yanlış alarm
maliyeti. Bu, "CERT r4.2'de iyi sonuç aldık" cümlesinin neden tek başına anlamsız olduğunun
sayısal gösterimidir.

## S5 neden hâlâ kaçıyor — artık otomatik tespit ediliyor

S5-MBG3183 üç koşuda da kaçtı. Sebebi 30 Ekim'de elle bulundu: r6.2'nin `http.csv` dosyasında
`content` kolonu yok, `bytes_out` her web olayında sıfır, dolayısıyla `UEBA-0003` **yapısal olarak
ölü**.

Bu artık elle bulunmuyor: **şema profilleyici** (31 Ekim) aynı eksiği ilk koşuda raporluyor.

```
r6.2  uyarı=1  http.csv: `content` kolonu yok → `bytes_out`
      (web yükleme hacmi — yoksa UEBA-0003 web tarafında ÖLÜ)
```
