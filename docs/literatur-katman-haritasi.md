# Literatür taraması → eklenebilecek katmanlar

**Tarama: 30 Ekim 2026.** Insider threat tespiti, log anomali tespiti, akış öğrenmesi, uyarı
triyajı ve zero trust literatürü tarandı; her bulgu sistemin **ölçülmüş** eksiklerine eşlendi.

## Taramanın sınırı (önce bu)

Tam metni okunan: **bir** kaynak — [heterojen graf GNN taraması, arXiv 2510.26307](https://arxiv.org/html/2510.26307v3)
(ilk 100k karakter; açık sorunlar bölümü kesik). Diğer kaynaklar **arama özetleri** üzerinden
değerlendirildi. Aşağıdaki rakamların bir kısmı hakem süzgecinden geçmemiş ön baskılardan
geliyor ve öyle işaretlendi. Bir katmanı uygulamaya almadan önce ilgili makalenin tam metni
okunmalıdır.

## Neyi çözmeye çalışıyoruz

Listenin sırası modanın değil **ölçülmüş arızanın** sırası. r6.2 ölçümünden (`docs/r62-v4-olcumu.md`):

| # | Ölçülmüş arıza | Kanıt |
|---|---|---|
| **A1** | Kaçan insider hiçbir kural tetiklemiyor; graf **çarpan** olduğu için ulaşamıyor (`1,5 × 0 = 0`) | S5 hem v3 hem v4'te kaçtı |
| **A2** | Kuyruk şişiyor, yakalama artmıyor | FP 538 → 1114, TP 3 → 3 |
| **A3** | 30'luk bütçe neredeyse her gün doluyor | 30,5 vaka/gün |
| **A4** | precision@1 = 0,003 — sıralama düz | 2801 kullanıcıda 1 insider |
| **A5** | Analist etiketi yok → Bayes kapısı, aktif öğrenme, precision ölçümü çalışmıyor | `bayes_elenen_vaka: 0` |
| **A6** | Erkenlik n=3 — istatistik yapılamıyor | medyan 0 → 10 gün, tek senaryodan |
| **A7** | v4 kazancı r4.2'ye aşırı uyum olabilir | r4.2 +5 insider, r6.2 +0 |

---

## Grup 1 — Yapısal boşluğu kapatanlar (A1: en yüksek değer)

Hepsi aynı fikrin varyantı: **kural tetiklenmese de skor üretebilen paralel bir kanal.**
Mevcut mimaride her şey kurallardan türüyor; çarpan tabanı sıfır olana dokunamıyor.

| # | Katman | Ne yapar | Kaynak | Emek |
|---|---|---|---|---|
| 1.1 | **Toplamsal graf skoru** | `scoring.py`'de `1 + w·graf` yerine `skor + w·graf`. Tek satırlık değişiklik, tabanı sıfır olanı kurtarır. | — (kendi ölçümümüzün doğrudan sonucu) | **saat** |
| 1.2 | **Otokodlayıcı / VAE yeniden kurma hatası** | Kullanıcı-gün özellik vektörünü sıkıştırıp geri kurar; hata = anomali. Kurala bağlı değil. CERT r4.2'de en etkili tek model olarak raporlanıyor; AE, Isolation Forest'ı özellikle **çok düşük FPR**'de geçiyor. | [Lin & Dalhousie, TNSM 2021](https://web.cs.dal.ca/~lcd/pubs/TNSM2021.pdf), [CNS 2020](https://web.cs.dal.ca/~lcd/pubs/CNS20.pdf), [arXiv 2109.02568](https://arxiv.org/pdf/2109.02568) | gün |
| 1.3 | **Isolation Forest / ECOD / COPOD** | Ağaç tabanlı ve dağılım tabanlı klasik anomali tespiti. Hızlı, parametresiz, yorumlanabilir. Referans taban olarak zorunlu. | [MDPI 13/1/259](https://www.mdpi.com/2076-3417/13/1/259) | **saat** |
| 1.4 | **Denetimsiz topluluk + oylama** | 4 denetimsiz yöntemin oylaması. **%0,1 soruşturma bütçesinde insider'ların %60'ı**, %5 bütçede tamamı. Bizim bütçemiz 30/2801 = %1,07 — tam bu eğrinin üzerinde. | [TNSM 2021](https://web.cs.dal.ca/~lcd/pubs/TNSM2021.pdf) | gün |
| 1.5 | **Deep SVDD / Deep SAD** | Normali bir hiperkürenin içine sıkıştırır; **Deep SAD** birkaç etiketli anomaliyi de kullanabilir (bizde 34 insider var → tam uygun). | [arXiv 1906.02694](https://arxiv.org/pdf/1906.02694) | gün |
| 1.6 | **DevNet (sapma ağları)** | Az-örnekli anomali tespiti + açıklanabilirlik. Etiketli anomali sayısı çok azken tasarlandı. | [arXiv 2108.00462](https://arxiv.org/pdf/2108.00462) | gün |
| 1.7 | **PU öğrenme (pozitif-etiketsiz)** | "İnsider değil" diye bilinen kullanıcı yok — hepsi *etiketsiz*. Mevcut lojistik regresyon bunları negatif sayıyor; bu **yanlış** ve taban oranını bozuyor. PU öğrenme tam bu durum için. Insider threat'e uygulanmış hazır çalışma bulamadım; [yazılım açığı tespitinde](https://arxiv.org/pdf/2308.10523) var. | — (boşluk) | hafta |

> **1.1 + 1.3 birlikte bir günlük iş** ve A1'i doğrudan sınar. Bu listenin en yüksek getiri/emek
> oranı burada. 1.2 ve 1.4 bir sonraki adım.

## Grup 2 — Sıralama ve precision (A2, A3, A4)

Daha çok sinyal değil, **daha iyi sıralama** gerekiyor. v4 bunu yanlış taraftan denedi.

| # | Katman | Ne yapar | Kaynak | Emek |
|---|---|---|---|---|
| 2.1 | **Uç değer teorisi ile eşik (SPOT / DSPOT)** | Sabit eşik yerine akıştan Genelleştirilmiş Pareto dağılımı uydurup kuyruk olasılığından eşik üretir. Her kullanıcı için ayrı. Bizim MAD/robust-z eşiklerimizin yerine geçebilir. | [Siffer ve ark., KDD 2017](https://docs.rs/crate/libspot-rs/latest) | gün |
| 2.2 | **Sıralama öğrenmesi (LambdaMART / learning-to-rank)** | Triyajı sınıflandırma değil **sıralama** problemi olarak kurar. Bütçe 30'sa önemli olan ilk 30'un sıralaması, mutlak skor değil. | [Sandia ALAT](https://www.osti.gov/servlets/purl/1365098), [TEQ](https://www.researchgate.net/publication/308188870_Learning_to_rank_for_alert_triage) | hafta |
| 2.3 | **Sınıf-koşullu (Mondrian) konformal** | Mevcut Venn-Abers **marjinal** kapsama veriyor; aşırı dengesizlikte azınlık sınıfı örtülmüyor. 1:345 dengesizlikte standart konformal anomali kapsamasını %52,9'a düşürüyor, sınıf-koşullu %90,6'da tutuyor. Bizim oranımız 1:2800. | [MAKE 8/7/190](https://doi.org/10.3390/make8070190), [arXiv 2607.27143](https://arxiv.org/pdf/2607.27143) (ön baskı) | gün |
| 2.4 | **Seçici konformal risk kontrolü (SCRC) + çekimserlik** | İki aşama: hangi vakalar hakkında karar verileceğini seç, sonra kalanlar için risk kontrollü küme üret. Bütçe dolduğunda "karar vermiyorum" demenin ilkeli hâli. | [arXiv 2512.12844](https://arxiv.org/html/2512.12844v2), [arXiv 2606.08517](https://arxiv.org/pdf/2606.08517) | hafta |
| 2.5 | **Maliyet duyarlı öğrenme / odak kaybı** | Bir kaçan insider ile bir yanlış alarmın maliyeti eşit değil; lojistik regresyon öyle davranıyor. Sınıf ağırlığı tek satır. | [arXiv 2607.27143](https://arxiv.org/pdf/2607.27143) | **saat** |
| 2.6 | **AUPRC'ye geçiş** | Dengesiz veride AUROC yanıltıcı; literatür AUPRC öneriyor. Bizde AUC 0,775 raporlanıyor — AUPRC yok. | [arXiv 2510.26307](https://arxiv.org/html/2510.26307v3) | **saat** |
| 2.7 | **Çoklu-örnek öğrenme (MIL)** | Kullanıcı-gün'ü *torba*, olayları *örnek* say: "bu günde en az bir kötücül olay var". Etiket granülaritemizle tam örtüşüyor. | [MINNS, arXiv 2108.00462 içinde](https://arxiv.org/pdf/2108.00462) | hafta |

## Grup 3 — Etiket ekonomisi (A5: bu olmadan yarı sistem ölü)

Bayes kapısı, precision ölçümü ve aktif öğrenme **hepsi** analist etiketine bağlı ve
etiket yok. Bu bir kod eksiği değil, **süreç** eksiği.

| # | Katman | Ne yapar | Kaynak | Emek |
|---|---|---|---|---|
| 3.1 | **Cevap anahtarından sentetik etiket beslemesi** | CERT cevap anahtarı var. Analist davranışını taklit eden bir simülatör (kapanan vaka = FP, yükseltilen = TP) Bayes kapısını ve aktif öğrenmeyi **ölçülebilir** hâle getirir. Sandia tam bu eşlemeyi kullanıyor. | [Sandia ALAT](https://www.osti.gov/servlets/purl/1115032) | gün |
| 3.2 | **Tetiklemeli aktif öğrenme (PACT)** | Donmuş bir ön eleyicinin üstüne, belirsizlik + yüksek-skor karışımıyla örnek seçen uyarlanabilir tetikleyici. Yanlış pozitif yükünde %43 ve %21 azalma, **3,8–5,2× daha az analist sorgusu**. (Ön baskı — doğrulanmadı.) | [arXiv 2605.22324](https://arxiv.org/pdf/2605.22324) | hafta |
| 3.3 | **Belirsizlik örneklemesi** | `belirsizlik_enabled` zaten var ama etiket toplamaya bağlanmamış. Venn-Abers aralığı geniş olan vakaları analiste öncelikli sor. | [ALAT](https://www.osti.gov/servlets/purl/1365098) | gün |
| 3.4 | **Aldatma / honeytoken etiket kaynağı** | `deception.py` var (`HoneytokenRegistry`). Honeytoken'a dokunmak **neredeyse kesin pozitif** etiket üretir — tahmin değil. Mevcut modül puanlamaya bağlı değil; etiket üretecine çevrilebilir. | [IntechOpen UEBA](https://www.intechopen.com/chapters/1208835) | gün |

## Grup 4 — Temsil öğrenme (ağır; A1 ve A4'e dolaylı)

Bunlar en çok konuşulan ama **bizim için en riskli** grup: 9.500 satırlık deterministik,
donmuş, denetlenebilir bir sisteme eğitimli sinir ağı sokmak dondurma protokolünü
ve yorumlanabilirliği zorlar.

| # | Katman | Ne yapar | Kaynak | Emek |
|---|---|---|---|---|
| 4.1 | **LSTM / GRU davranış dizisi modeli** | Kullanıcının olay dizisini sırayla modeller; bizim özellik çıkarımı sırayı düzleştiriyor. Tuor ve ark. **günlük 250 vaka bütçesinde %90 recall** (bizim bütçe 30). | [AICS 2017](https://fw.cs.wwu.edu/~hutchib2/papers/aics17_insiderthreat.pdf), [OSTI 1572682](https://www.osti.gov/biblio/1572682) | hafta |
| 4.2 | **LogBERT / LAnoBERT (maskeli log modeli)** | Log dizisini BERT'le kendi kendine denetimli öğrenir: maskeli anahtar tahmini + hiperküre küçültme. Etiket gerektirmez. | [arXiv 2103.04475](https://arxiv.org/pdf/2103.04475), LAnoBERT (Appl. Soft Comp. 146, 2023) | hafta+ |
| 4.3 | **Gerçek GNN (GAT / GraphSAGE / HGT)** | Bizim `TemporalGraphBaseline` **öğrenmiyor** — elle yazılmış graf istatistikleri. Literatürdeki kazanç öğrenilmiş düğüm gömmelerinden geliyor. | [arXiv 2510.26307](https://arxiv.org/html/2510.26307v3) (DOMINANT, ALARM, StrGNN, TADDY, OCGNN, AddGraph…) | hafta+ |
| 4.4 | **ATHITD — zamansal heterojen graf dizisi** | Zaman pencereleri üzerinden heterojen graf dizisi + hedef düğümün kısa dönem evrimine dikkat. Bizim kurduğumuz grafın öğrenen hâli. | Comput. & Security 157 (2025) 104587 | hafta+ |
| 4.5 | **DTGI — dengesizliğe dayanıklı sürekli-zaman graf** | Sürekli zamanlı dinamik heterojen graf ağı, **aşırı dengesizlik** için tasarlandı. | [JCIS 65(1)](https://www.tandfonline.com/doi/abs/10.1080/08874417.2023.2267510) | hafta+ |
| 4.6 | **GCN + Bi-LSTM (açık/örtük graf)** | Graf yapısı ve zaman dizisini birlikte modelliyor; CERT'te sınanmış. | [arXiv 2512.18483](https://arxiv.org/html/2512.18483v1) | hafta+ |
| 4.7 | **R-GNN — RiskScore güdümlü graf öğrenme** | Bizim mimarimize **en yakın** çalışma: denetim loglarından bilgi grafı + bir risk skorunu graf öğrenmeye rehber sinyal olarak veriyor. Bizde `graph/knowledge.py` ve risk skoru ikisi de var. | [ETASR 17187](https://etasr.com/index.php/ETASR/article/view/17187) | hafta |
| 4.8 | **Karşıtsal / kendi kendine denetimli hedefler** | GraphCAD, HeCo, Anomal-E, TS-IDS, GLocalKD. Etiket olmadan temsil öğrenir — A5'i baypas eder. | [arXiv 2510.26307](https://arxiv.org/html/2510.26307v3) | hafta+ |
| 4.9 | **Tahmin tabanlı tespit (GDN, OCAN)** | Bir sonraki adımı tahmin et, sapmayı ölç. OCAN: LSTM-AE + GAN ayırıcı. | [arXiv 2510.26307](https://arxiv.org/html/2510.26307v3) | hafta+ |
| 4.10 | **Metrik öğrenme / siyam ağları** | Akran karşılaştırmasını elle yazılmış benzerlik yerine öğrenilmiş mesafeyle yapar. `peers.py` buna hazır. | [arXiv 2308.10055](https://arxiv.org/pdf/2308.10055) | hafta |

## Grup 5 — LLM katmanı (mevcut `reporting/` üzerine)

| # | Katman | Ne yapar | Kaynak | Emek |
|---|---|---|---|---|
| 5.1 | **Kademeli LLM hattı** | Ucuz davranışsal filtre → yalnızca en riskli alt küme LLM'e. CERT v6 e-posta derlemiyle **~100× LLM yükü azalması** raporlanıyor. Bizim mimarimiz (bütçe 30) tam bu şekil. (Hakemsiz bildiri.) | Agents4Science 2025 | gün |
| 5.2 | **Davranışı doğal dile çevirip LLM ince ayarı** | Kullanıcı davranışını doğal dil olarak temsil edip bilgi kaybını azaltıyor; karşıtsal davranış-örüntü görevi + **davranış düzeyinde denetim izi**. | [COLING 2025](https://aclanthology.org/2025.coling-main.574/) | hafta+ |
| 5.3 | **Çok ajanlı denetim (Audit-LLM / CORTEX / AACT)** | Bizde `multi_agent.py` var (Investigator/Verifier/Reporter). Literatürdeki fark: ajanlar **araç çağırıyor** ve analist eylemini taklit ediyor. | [arXiv 2510.00311](https://arxiv.org/pdf/2510.00311) | hafta |
| 5.4 | **Sıfır-örnekli yapılandırılmış risk göstergeleri** | LLM'i tespit için değil, **gösterge çıkarımı** için kullan — sonra deterministik motora ver. Donmuş sistemle uyumlu. | [arXiv 2608.16508](https://arxiv.org/pdf/2608.16508) (ön baskı) | gün |
| 5.5 | **Chimera / OrgForge-IT — sentetik senaryo üretimi** | Çok ajanlı LLM ile insider senaryosu simülasyonu. **A6'yı (n=3) doğrudan çözer**: senaryo sayısını artırır. Doğrulanabilir sentetik ölçüt. | [arXiv 2508.07745](https://arxiv.org/pdf/2508.07745), [arXiv 2603.22499](https://arxiv.org/pdf/2603.22499) | hafta |

## Grup 6 — Akış / işletim altyapısı

| # | Katman | Ne yapar | Kaynak | Emek |
|---|---|---|---|---|
| 6.1 | **River (çevrimiçi öğrenme)** | ADWIN'i elle yazdık; River'da ADWIN + DDM + Page-Hinkley + Hoeffding ağacı + çevrimiçi anomali hazır. Kendi ADWIN'imizdeki kova sırası hatası tam bu yüzden çıktı. | [River, JMLR 2021](https://arxiv.org/pdf/2012.04740) | gün |
| 6.2 | **Page-Hinkley / CUSUM / SPRT** | ADWIN'e ek kayma dedektörleri. Farklı kayma biçimlerini yakalar (ani vs. kademeli). | [River](https://arxiv.org/pdf/2012.04740) | gün |
| 6.3 | **Bayes çevrimiçi değişim noktası (BOCPD)** | `stats.py`'deki `changepoint_mean_shift` yerine olasılıksal, çoklu-değişim-noktalı sürüm. | — | gün |
| 6.4 | **OCSF tam uyum** | Kod "OCSF-lite" diyor. Tam OCSF şeması gerçek SIEM/EDR beslemelerine takılabilirliği verir. | [NIST SP 800-207](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf) bağlamı | hafta |
| 6.5 | **Sigma / YARA-L kural ihracı** | 22 kuralımız kendi DSL'imizde (`detection/expr.py`). Sigma'ya çevrilirse başka SIEM'lerde koşar. | — | hafta |
| 6.6 | **Graf veritabanı (Neo4j / TigerGraph)** | 51M kenarı bellekte tutuyoruz (17,6 GB tepe). Graf DB'ye taşımak bellek tavanını kaldırır. | — | hafta |
| 6.7 | **Federatif / kişiselleştirilmiş öğrenme** | Veri kurumdan çıkmadan model eğitimi. Insider threat için kişiselleştirilmiş federatif öğrenme çalışması var. | [Sci. Reports s41598-025-04029-w](https://www.nature.com/articles/s41598-025-04029-w) | hafta+ |
| 6.8 | **Risk uyarlamalı erişim denetimi (RAdAC)** | Zero trust'ın eksik yarısı: skoru **uygulamaya** bağlamak. SP 800-207 oturum başına dinamik politika istiyor ama **formül vermiyor**; bizim skor tam o boşluğa oturuyor. `response.py` kademeli yanıtı var, erişim kararı yok. | [NIST SP 800-207](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf) | hafta |

## Grup 7 — Bilimsel yöntem (A6, A7: en çok ihmal edilen)

Bu grupta **yeni teknoloji yok**, ama listenin en değerli kısmı burası olabilir.

| # | Katman | Ne yapar | Emek |
|---|---|---|---|
| 7.1 | **Bileşen bazında ablasyon** | `ablation.py` var ama v4 bileşenleri için koşulmadı. Graf / ADWIN / Bayes tek tek. A7'yi doğrudan sınar. | **3 koşu ≈ 3 saat** |
| 7.2 | **r5.2'de v4 ölçümü** | r5.2'de **99 insider** var (r6.2'de 5). A6'nın (n=3) tek gerçek çözümü. r5.2 zaten yanmış, maliyeti yok. | koşu |
| 7.3 | **AUPRC + bütçe-recall eğrisi** | Tek sayı yerine eğri: bütçe 1'den 100'e recall nasıl değişiyor. TNSM 2021'in raporlama biçimi; doğrudan karşılaştırılabilir hâle getirir. | gün |
| 7.4 | **Çapraz-sürüm genelleme matrisi** | r4.2'de ayarla → r5.2/r6.2/r1'de ölç. Aşırı uyumun tek dürüst testi. | koşu |
| 7.5 | **Düşmanca değerlendirme (mimicry)** | Eylem budama ve gürültü üretme ile kaçınma; klasik makine öğrenmesi çözümlerinin bu taktiklere açık olduğu gösterilmiş. Donmuş kurallar **özellikle** kırılgan: kural metni biliniyorsa kaçınma kolay. | [Sensors/PMC7181010](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7181010/), [Wagner mimicry](https://people.eecs.berkeley.edu/~daw/papers/mimicry.pdf), [CNS 2020](https://web.cs.dal.ca/~lcd/pubs/CNS20.pdf) | hafta |
| 7.6 | **r1'de kör koşu** | Kalan tek kör veri. Yukarıdakilerin hiçbiri eklenmeden **önce** mi sonra mı koşulacağına karar verilmeli — ikisi birden olmaz. | koşu |

---

## Grup 8 — Eklenmemesi gerekenler

Dürüstlük gereği: literatürde popüler ama bu sistemde **reddedilmeli**.

| Katman | Neden hayır |
|---|---|
| **Psikometrik / OCEAN kişilik özellikleri** | CERT'te `psychometric.csv` var ve `data/cert.py:224` onu **bilinçli olarak okumuyor** (§4.2 etik sınır / §20.1 amaçla sınırlılık). Literatürde sadece Big Five ile sınıflandırma yapan çalışmalar var ve doğruluk raporluyorlar — ama bu, çalışanı davranışı değil **kişiliği** için işaretlemek demektir. Kendi belgelenmiş sınırımızı ihlal eder. Teknik olarak mümkün, ilkesel olarak hayır. |
| **E-posta duygu analizi / psikodilbilim** | Aynı sınır. `http.csv`'de `content` (sayfa metni) ve `file.csv`'de içerik **okunmuyor**, yalnızca uzunluğu hacim vekili olarak alınıyor (`cert.py:414`). İçeriği okumaya başlamak veri minimizasyonundan vazgeçmektir. |
| **Doğruluk (accuracy) metriği** | 1:2800 dengesizlikte "hiç kimse insider değil" cevabı %99,96 doğruluk verir. Literatür bunu en yaygın ama en yanıltıcı metrik olarak işaretliyor. Raporlarımıza girmemeli. |
| **Derin sinir ağı tek başına sınıflandırıcı olarak** | 88 sınıflandırıcılık bir çalışmada CERT'te rastgele orman en iyi, derin sinir ağları **en alttaki %10'da**. Ağır model ≠ iyi sonuç. | 
| **Sürekli kimlik doğrulama / tuş vuruşu dinamiği** | CERT'te veri yok; eklenirse ölçülemez. Gerçek kurum dağıtımı için anlamlı, bu araştırma için değil. |

---

## Önerilen sıra

```
1. 1.1 toplamsal graf skoru  +  1.3 Isolation Forest        → 1 gün,  A1'i sınar
2. 7.1 bileşen ablasyonu     +  7.2 r5.2'de ölçüm           → 1 gün,  A7 ve A6
3. 2.5 maliyet duyarlı       +  2.6 AUPRC  +  7.3 bütçe eğrisi → 1 gün, A4
4. 1.2 otokodlayıcı          +  1.4 topluluk oylaması       → 1 hafta, A1/A2
5. 3.1 sentetik etiket       +  3.3 belirsizlik örneklemesi  → 1 hafta, A5
6. 2.1 SPOT  +  2.3 Mondrian konformal                      → 1 hafta, A3
7. 7.5 düşmanca değerlendirme                               → 1 hafta
8. (karar) 7.6 r1'de kör koşu — hangi noktada?
```

İlk üç adım **üç gün** ve A1, A4, A6, A7'yi birlikte sınıyor. Grup 4'ün tamamı bundan sonra
gelir; öncesinde girmesi, ölçülmemiş bir tabanın üstüne ağır model koymak olur — v4'te tam
bunu yaptık ve r6.2'de bedelini gördük.

## Kaynaklar

Tarama kaynakları, grup sırasına göre: [arXiv 2510.26307 (HGNN taraması)](https://arxiv.org/html/2510.26307v3) ·
[TNSM 2021 (denetimsiz topluluk)](https://web.cs.dal.ca/~lcd/pubs/TNSM2021.pdf) ·
[CNS 2020 (düşmanca)](https://web.cs.dal.ca/~lcd/pubs/CNS20.pdf) ·
[arXiv 2005.12433 (derin öğrenme taraması)](https://arxiv.org/pdf/2005.12433) ·
[arXiv 2109.02568 (AE/VAE)](https://arxiv.org/pdf/2109.02568) ·
[arXiv 1901.10948 (88 sınıflandırıcı)](https://arxiv.org/pdf/1901.10948) ·
[arXiv 1906.02694 (Deep SAD)](https://arxiv.org/pdf/1906.02694) ·
[arXiv 2108.00462 (DevNet)](https://arxiv.org/pdf/2108.00462) ·
[arXiv 2308.10523 (PU öğrenme)](https://arxiv.org/pdf/2308.10523) ·
[arXiv 2103.04475 (LogBERT)](https://arxiv.org/pdf/2103.04475) ·
[arXiv 2012.04740 (River)](https://arxiv.org/pdf/2012.04740) ·
[libspot / SPOT-DSPOT](https://docs.rs/crate/libspot-rs/latest) ·
[MAKE 8/7/190 (sınıf-koşullu konformal)](https://doi.org/10.3390/make8070190) ·
[arXiv 2512.12844 (SCRC)](https://arxiv.org/html/2512.12844v2) ·
[arXiv 2606.08517 (uyarlanabilir SCRC)](https://arxiv.org/pdf/2606.08517) ·
[arXiv 2607.27143 (maliyet duyarlı konformal)](https://arxiv.org/pdf/2607.27143) ·
[arXiv 2503.19146 (risk tabanlı eşik)](https://arxiv.org/pdf/2503.19146) ·
[Sandia ALAT — aktif öğrenme](https://www.osti.gov/servlets/purl/1115032) ·
[Sandia — sıralama öğrenmesi](https://www.osti.gov/servlets/purl/1365098) ·
[TEQ](https://www.researchgate.net/publication/308188870_Learning_to_rank_for_alert_triage) ·
[arXiv 2605.22324 (PACT)](https://arxiv.org/pdf/2605.22324) ·
[arXiv 2510.00311 (CORTEX)](https://arxiv.org/pdf/2510.00311) ·
[COLING 2025 (LLM ince ayar)](https://aclanthology.org/2025.coling-main.574/) ·
[arXiv 2508.07745 (Chimera)](https://arxiv.org/pdf/2508.07745) ·
[arXiv 2603.22499 (OrgForge-IT)](https://arxiv.org/pdf/2603.22499) ·
[arXiv 2608.16508 (sıfır-örnekli göstergeler)](https://arxiv.org/pdf/2608.16508) ·
[ETASR 17187 (R-GNN)](https://etasr.com/index.php/ETASR/article/view/17187) ·
[JCIS 65(1) (DTGI)](https://www.tandfonline.com/doi/abs/10.1080/08874417.2023.2267510) ·
[arXiv 2512.18483 (GCN+Bi-LSTM)](https://arxiv.org/html/2512.18483v1) ·
[Springer (bi-hiyerarşik graf)](https://link.springer.com/chapter/10.1007/978-981-96-5318-8_31) ·
[GraphCH, IEEE TQ 2024](https://www.computer.org/csdl/journal/tq/2024/05/10399790/1TJtM6VfEv6) ·
[AICS 2017 (LSTM, bütçeli recall)](https://fw.cs.wwu.edu/~hutchib2/papers/aics17_insiderthreat.pdf) ·
[OSTI 1572682](https://www.osti.gov/biblio/1572682) ·
[arXiv 2308.10055 (karşıtsal)](https://arxiv.org/pdf/2308.10055) ·
[Sci. Reports (federatif)](https://www.nature.com/articles/s41598-025-04029-w) ·
[MDPI 13/1/259](https://www.mdpi.com/2076-3417/13/1/259) ·
[ACM 3798089 (insan faktörleri)](https://dl.acm.org/doi/10.1145/3798089) ·
[Springer (psikometriden risk)](https://link.springer.com/chapter/10.1007/978-3-031-80020-7_10) ·
[PMC7181010 (maskeleme kaçınma)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7181010/) ·
[Wagner — mimicry](https://people.eecs.berkeley.edu/~daw/papers/mimicry.pdf) ·
[NIST SP 800-207](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf) ·
[IntechOpen (UEBA)](https://www.intechopen.com/chapters/1208835)
