# Bulgular — mimari ↔ uygulama denetimi

Bu belge, `docs/mimari-dokuman.md` ile `src/ztp` arasındaki denetimde çıkan bulguları,
yapılan değişikliği ve değişikliğin ölçülen etkisini kaydeder. Her bulgu bir koda,
bir kurala ve bir ölçüme bağlanır; bağlanamayan iddia bu belgeye girmez.

Ölçüm ortamı: sentetik kurum (`--synthetic`), 150 kullanıcı, 90 gün ısınma + 21 gün risk
serisi + 30 gün değerlendirme, `seed=42`, bütçe 8/gün, son gün 2026-09-16. Cevap anahtarı
`SyntheticOrg.ground_truth` (S1–S10). CERT r4.2 bu makinede indirilmemiştir (4,8 GB);
yansız rakam için 19.2'deki uyarı geçerlidir — sentetik veri regresyon içindir.

---

### Bulgu 1 — Akran oranının veto yetkisi

**Ne bekliyorduk:** Doküman 9.1/11.4 akran grubu kıyasını "bağlam düzelticisi" olarak
tanımlar: rol bağlamını hesaba katıp yanlış pozitifi düşüren bir **düzeltme** katmanı.
13.1 ise tespitlerin varlık-gün bağlamında toplanmasını, korelasyonun ödüllendirilmesini
öngörür. Beklenti, akran kıyasının bir sinyali güçlendirip zayıflatması; onu **yok
etmemesiydi**.

**Ne bulduk:** UEBA-0003 (anormal veri çıkış hacmi) ve UEBA-0007 (mesai dışı toplu dosya
erişimi) akran oranını **VE koşulu** olarak taşıyordu:

```yaml
kosullar:
  - veri_hacmi_z > 3.5            # kişisel sapma
  - veri_hacmi_akran_kati > 5.0   # akran oranı — VETO yetkisi
```

`veri_hacmi_akran_kati = bugünkü_hacim / akran_medyanı` olduğundan, ateşlenmek için
gereken **mutlak** eşik departmanın veri yoğunluğuyla birlikte yükseliyordu. Akran
medyanı 2 GB/gün olan bir finans ekibinde kural ancak 10 GB'ın üstünde tetikleniyor;
9 GB çeken ele geçirilmiş bir hesap, kişisel z ≈ 9 (uç bir sapma) olmasına rağmen
**hiç görünmüyordu**.

Ölçülen büyüklük: düzeltme sonrası koşuda UEBA-0003'ün **493 tetiklemesinin 214'ü
(%43)** akran oranı 5,0'ın altındaydı — yani eski kuralda veto ediliyordu.

Üç şey bunu ağırlaştırıyordu:

1. **Kısmi puan yok.** Skor yalnızca ateşlenen tespitlerin toplamıdır; hiçbir kural
   VE koşulunu geçemezse `raw = 0` olur ve `select_queue` kullanıcıyı tamamen eler
   (`scoring.py`). Kişisel olarak uç ama akrana göre normal görünen kullanıcı "az
   riskli" değil, **görünmez** oluyordu.
2. **Hacimde kümülatif pencere yoktu.** Doküman 2.3 "eşik altı kalma" saldırısının
   karşı önlemini "7 günlük kümülatif pencere" diye yazmıştı; kodda bu yalnızca dosya
   (`dosya_7g_poisson_p`) ve USB (`usb_7g_poisson_p`) için vardı, veri hacminde yoktu.
3. **Varlık hassasiyeti skora girmiyordu.** `sensitive_access_count` özelliği üretiliyor
   ama hiçbir UEBA kuralı okumuyordu; bordro dosyası yemekhane menüsüyle aynı ağırlıktaydı.

**Neden önemli:** Doküman 2.1 "sabırlı içeriden tehdit" ve "kötü niyetli yeni işe alım"
satırları için *"sistemin asıl hedefi bunlardır"* diyor. Delik tam olarak beyan edilen
önceliğin üstündeydi. Ayrıca akran ağırlığının varlık sebebi (ADR-007, 2.3) baseline
zehirlemeye karşı **sabit referans tutmaktır** — sinyal susturmak değil. VE koşulu,
bağlam düzelticisini sessiz bir filtreye dönüştürmüştü.

**Değişiklik:**

1. `detection/engine.py` — şiddet bloğuna `akran_olcekleyici` desteği eklendi.
   `peer_severity_factor(oran)` nötr noktası eski VE eşiği olacak biçimde kuruldu:
   `log10(oran) / log10(5.0)`, `[0.2, 2.0]` aralığına kırpılır. Oran 5× iken çarpan
   1,0; 1,3× iken 0,2; 40× iken 2,0. Akranıyla aynı davranan kullanıcı artık elenmez,
   yalnızca şiddeti — dolayısıyla kuyruktaki önceliği — düşer (13.5 sıralama tabanlıdır).
   `_names()` şiddet sinyalini, ölçekleyiciyi ve `rapor_sinyalleri` listesini de kayda
   alır, böylece rapor akran oranını ve her iki pencerenin z'sini göstermeye devam eder.
2. `rules/UEBA-0003.yaml` (sürüm 1.0 → 1.1) — koşul tek satıra indi
   (`veri_hacmi_anomali_z > 3.5`); akran oranı `akran_olcekleyici` oldu.
3. `rules/UEBA-0007.yaml` (sürüm 1.0 → 1.1) — `dosya_sayisi_akran_kati > 5.0` koşuldan
   çıkarıldı, ölçekleyiciye taşındı.
4. `profile.py` — `veri_hacmi_7g_toplam`, `veri_hacmi_7g_z` ve
   `veri_hacmi_anomali_z = max(günlük z, 7g z)` eklendi (`usb_anomali_p` ile aynı idiom).
   7 günlük ölçeğin göreli tabanı **haftalık** beklenen üzerinden uygulanır; günlük taban
   √7 ile çarpılırsa taban %10 → %3,8'e düşüyor ve ılımlı bir yükseliş z'yi patlatıyordu
   (ilk uygulamada bu hata vardı, ölçümle yakalandı ve düzeltildi).
5. `profile.py` — `kritik_varlik_erisim_sayisi` sinyali eklendi; `olcekleyici_taban_sinyali`
   ile kritik varlığa erişim olan günlerde akran indirimi uygulanmaz (çarpan tabanı 1,0).
6. Kural birim testlerine `akran_tavani_altinda_veri_yogun_departman` senaryosu eklendi
   (kişisel z 9,0 + akran oranı 4,5×). Bu senaryo **eski kuralda kalır, yenisinde geçer** —
   bulgu böylece regresyon testine dönüştü.

**Ölçüm (önce→sonra):**

| Metrik | Önce | Sonra | Δ |
|---|---|---|---|
| Vaka hacmi (30 gün) | 184 | 229 | **+45 (+%24)** |
| Günlük ortalama | 6,13 | 7,63 | +1,50 (bütçe 8 — altında) |
| Kapsama (pozitif senaryo) | 8/8 | 8/8 | 0 |
| S9 negatif kontrol | GEÇTİ | **GEÇTİ** | korundu |
| **precision@1** | 0,700 | **0,967** | **+0,267** |
| precision@3 | 0,614 | 0,678 | +0,064 |
| precision@5 | 0,468 | 0,473 | +0,005 |
| precision@10 | 0,359 | 0,328 | −0,031 |
| Doğru vaka sayısı | 66 / 184 | **75 / 229** | +9 |
| Kullanıcı bazında precision | 0,099 (81 kişi) | 0,089 (90 kişi) | −0,010 |
| Bastırma oranı (`bastirma.oran`) | 0,0 (0 olay) | 0,003 (1 olay) | izin dönüşü |
| S6 (zehirleme) erkenlik | 20 gün | 22 gün | +2 gün |
| UEBA-0003 skor payı | 0,291 | 0,414 | +0,123 |
| Test paketi | 82/82 | **82/82** | korundu |

Yorum: alarm hacmi %24 arttı ama **analist kapasitesinin (8/gün) altında kaldı**.
Kuyruğun tepesi belirgin biçimde temizlendi (precision@1 0,70 → 0,97): akran oranı
artık eleme değil sıralama yaptığı için gerçek anomaliler yukarı çıkıyor. Kuyruğun
kuyruğu seyreldi (precision@10 −0,031), bu 13.1'in bilinçli sonucudur — sessiz günlerde
bütçe düşük skorlu vakalarla dolar. Kapsama değişmedi çünkü sentetik senaryo setinde
**veri yoğun departmanda ele geçirilmiş hesap senaryosu yok**; bulgu sentetik koşuyla
değil, kural birim testiyle kanıtlanmıştır (bkz. Değişiklik 6).

**S9 regresyonu ve çözümü (kapandı):** İlk uygulamada S9 (kayıtlı izin dönüşü) negatif
kontrolü yanlış pozitif üretti. Kök sebep: `izin_kayitli` sinyali **Prediction katmanında**
üretiliyor, UEBA katmanı ondan **önce** çalışıyor (`pipeline.py`) — yani UEBA-0003'ün izin
takvimine erişimi yoktu. Eski akran vetosu, farkında olmadan izin takviminin işini yapıyordu.

Ölçüm, akran oranının bu iki durumu **ayıramayacağını** da gösterdi: S9'un izin dönüşü akran
medyanının ~4 katı, kurgulanan finans saldırısı ~4,5 katı — aynı banttalar. Yani veto ne
yanlış pozitifi seçici olarak eliyordu ne de saldırıyı; **ikisini birden susturuyordu**. Ara
bir eşik (2×, 3×) da ayırt edemezdi.

Doğru ayırt edici, doküman 9.3/17.2'nin zaten öngördüğü devamsızlık takvimidir. Uygulanan çözüm:

- `profile.py` — `izin_donusu` sinyali UEBA katmanında hesaplanır (`ctx.last_active` + `self.leaves`;
  `prediction.izin_kayitli` ile aynı mantık, yalnızca katman sırası nedeniyle burada tekrarlanır).
- `detection/engine.py` — `_suppressed()` içine `izin_donusu` bastırma etiketi eklendi
  (`servis_hesaplari` ve `yedekleme_penceresi` ile aynı kalıp).
- `UEBA-0003.yaml` / `UEBA-0007.yaml` — `bastirma` listelerine `izin_donusu` eklendi.

Bastırma tercih edildi çünkü 12.5'e göre bastırılan olay **sayılır ve raporlanır**
(`suppressed.jsonl`, `metrics.json → bastirma.oran`); sessizce yutulmaz, Prensip 5'e uyar ve
kural mantığını kirletmez. Ölçümde görünürlüğü doğrulandı: `bastirma.oran = 0,003` (1 olay).

**Kalan risk (kabul edildi):** Bu bastırma, kurbanın izinden döndüğü gün hesabını kullanan
saldırgana dar bir pencere açar. Pencere izin kaydıyla sınırlıdır, sayılır ve raporlanır; bu
pencerede erişim deseni kuralları (#4 imkânsız seyahat, #5 yeni cihaz/konum) ile aldatma
katmanı (#18–20) çalışmaya devam eder. Doküman 12.4'e eklenen sınır bu boşluğu kapsar.

---

### CERT r5.2 kör koşu (27 Ekim 2026)

Kurallar `kurallar-donduruldu-v1` ile, ayar sırasında hiç görülmemiş veride tek koşu. 70/15/15 grup bazında karşılaştırma ve sapma kaydı:
[cert-r42-r52-karsilastirma.md](cert-r42-r52-karsilastirma.md).

- Yakalama (değerlendirilebilir): **25/30 (0,83)**; r4.2'de 18/20 (0,90). Yeni senaryo türü S4: 4/4.
- precision@1 **0,20** (r4.2: 0,40); erkenlik medyanı 9 gün (r4.2: 8).
- 21 kuraldan 9'u tetiklendi (7 canlı + 2 gölge); r4.2'de 8 (6 + 2). Fark: UEBA-0003.
- r4.2'de eğitilen LR modeli r5.2'ye taşınmadı (AUC 0,84 → 0,69, sezgiselin altında). r5.2'nin kendi verisiyle
  eğitilen model AUC 0,91. Öğrenen model kurumun kendi etiketleriyle eğitilmeli.
- Sapma: ikincil LR bölmesi örneklemle aynı tohum akışından üretildiği için geçersiz çıktı. Mekanik olarak düzeltildi
  ve iki sonuç birlikte raporlandı.

---

## CERT Insider Threat Test Dataset ile doğrulama (r4.2)

Kaynak: Software Engineering Institute / CMU, *Insider Threat Test Dataset*, https://doi.org/10.1184/R1/12841247 (CC BY 4.0).
Sentetik olarak üretilmiş 1000 kullanıcılık bir kurumun logon / device / http / email / file kayıtları ve kırmızı takım
senaryolarının cevap anahtarı (`answers/insiders.csv`).

### Veri eşlemesi

| CERT dosyası | OCSF-lite | Not |
|---|---|---|
| `logon.csv` | Authentication (3002), kaynak `ad` | `DTAA/XXX0001` öneki kanonik kimliğe indirgenir |
| `device.csv` (Connect) | File (1001), kaynak `dlp`, `usb_copy` | Kullanıcı bazlı normal USB oranı vardır |
| `http.csv` | HTTP (4002), kaynak `proxy` | URL saklanmaz; **kategori** (cloud_storage, job_search, hacking_tools, …) |
| `email.csv` (r4.2+) | Email (4009), kaynak `email` | `size` → bytes_out; dış alıcı → `email_external` |
| `file.csv` (r4.2+) | File (1001), kaynak `file_server` | Taşınabilir medyaya kopya; dosya adı yerine uzantı kategorisi |
| `LDAP/*.csv` | İK/AD dizini | Aylık anlık görüntüler → işe giriş/ayrılış; departman → akran grubu |
| `psychometric.csv` | **okunmaz** | Kişilik verisi skorlamaya girmez (etik sınır / amaçla sınırlılık) |

### r4.2 koşusu

```
ztp --cert-dir cert_data/r4.2 --end 2010-11-30 --days 90 --budget 10 --tenant cert-r42 --out ./ztp_out
```

- 1000 kullanıcı, 13.261.768 olay (pencere: 14 May – 30 Kas 2010; değerlendirme 2 Eyl – 30 Kas), 134.835 varlık-gün
- Mevcut kaynaklar: ad, dlp, email, file_server, proxy (+hr). EDR/VPN yok → DQ-0010 devre dışı (kademeli işlevsellik)
- Süre: ≈ 8 dk (tek makine, Python)

#### Kapsama (cevap anahtarı, 34 insider)

| Senaryo | n | Sonuç | Tetiklenen kurallar (tipik) | Medyan erkenlik |
|---|---|---|---|---|
| 1 — mesai dışı giriş + USB + wikileaks, ayrılış | 14 | 14/14 kuyrukta | UEBA-0001, 0007, 0017, 0002; farklı-taktik çarpanı ×2.5 | 8 gün |
| 2 — iş arama siteleri + USB artışı, ayrılış | 17 | 10/11 (6 senaryo kısmi pencere) | UEBA-0017 (7g kümülatif), 0002, PRED-0012 | 20 gün |
| 3 — sysadmin keylogger, amirin makinesi | 3 | 2/3 (1 bütçe dışı) | UEBA-0005 (başkasına atanmış cihaz), 0002 (hacking_tools) | 6 gün |

"Erkenlik" = senaryo bitişi − ilk kuyruk girişi (gün).

#### Precision (cevap anahtarı etiket rolünde)

| Ölçüm | Değer |
|---|---|
| precision@1 | 0,39 |
| precision@3 | 0,22 |
| precision@5 | 0,14 |
| precision@10 (= bütçe) | 0,09 |
| Kuyruğa giren kullanıcı / insider | 263 / 27 (0,10) |

Yorum: bütçe her gün dolar; aktif insider olmayan günlerde kuyruk tek-sinyalli benign kullanıcılarla doldurulur.
Bu, sabit eşik yerine kapasite tabanlı kuyruk tasarımının bilinçli sonucudur ("sessiz günlerde kapsama"). Analist
kapasitesi 3 ise precision 0,22'ye çıkar; hangi N'in doğru olduğu ürün değil operasyon kararıdır.

### Prediction katmanı kalibrasyonu (r4.2, `--train-prediction`)

7 günlük olasılığın gerçekleşmeyle karşılaştırılması (cevap anahtarı etiket rolünde; zamansal holdout = son 33 gün):
sezgisel model AUC 0,61 / Brier 0,025 (taban 0,0084'ten kötü); öğrenen lojistik model AUC **0,86** / Brier **0,0081** /
ECE 0,0016. Ayrıntı ve yorum: `docs/mimari-dokuman.md` Ek D.3.

### Ablasyon (r4.2, 60 gün, `--ablation`)

Akran bağlamı kapatılınca kapsama 16/26 → 13/26 (en değerli bileşen); prediction ve ilişkisel kurallar kapatılınca sonuç
değişmiyor (bu veride katkıları ölçülemedi — İK sinyali yok); çarpanlar küçük pozitif katkı. Tablo: `docs/mimari-dokuman.md` Ek D.3.

### r1 koşusu (gürültü tabanı)

r1'in cevap anahtarı yoktur; 1000 benign kullanıcıda günde ≈ 7,8 vaka üretildi (bütçe 10). r1'in http hacmi aşırı
düzensizdir (bir gün 205 bin, ertesi gün 139 satır); veri kalitesi katmanı proxy'yi o günlerde askıya aldı — beklenen davranış.

### CERT'in ortaya çıkardığı tasarım düzeltmeleri

1. Paylaşımlı lab makineleri "yeni cihaz" sayılıyordu → akran cihaz kümesi, cihaz sahipliği (atanmış PC), akran
   taban-oranıyla ölçeklenen şiddet.
2. Günlük Poisson eşiğinin altında kalan USB artışı (2→5-7/gün) → **7 günlük kümülatif pencere** (eşik altı kalmaya karşı önlem).
3. İlk giriş saati normalken gece tekrar giriş → mesai dışı giriş sayısı sinyali.
4. Tatilde tüm kaynakların birlikte düşmesi → takvim etkisi; tek kaynak düşüşü → toplama bozulması.
5. Açık vaka yeni kanıt gelmeden yeniden kuyruğa alınmaz.
6. Tespit açıklamaları tespit anındaki bağlamla saklanır (bir hafta sonraki bağlamla yazılmaz).

### Sınırlar

- Kurallar r4.2 sonuçları görüldükten sonra ayarlandı → **döngüsel doğrulama riski**; yansız rakam için r5.2/r6.2'de tekrar.
- CERT'te İK sinyalleri, EDR ve coğrafi konum yoktur; PRED-0011/13/14, UEBA-0004/0006 ve DQ-0010 bu veride sınanamaz.
- http `content` alanı okunmaz; bayt hacmi yalnızca e-posta boyutundan gelir.
