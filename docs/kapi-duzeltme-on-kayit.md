# Kanıt kapısında tek-seferlik kanıt — ön kayıt

**Yazıldı: 7 Kasım 2026, kod değişikliğinden ÖNCE.** Dayanak: `docs/graf-kapi-sonuclar.md`,
`docs/r62-kapi-on-kayit.md`.

> Bu metin ölçümden sonra **değiştirilmeyecek**. Plandan sapılan her nokta sonuna *Sapmalar*
> başlığıyla eklenecek.

## Teşhis özeti

r4.2'de kaçan 12 insider'ın **5'i** kanıt doğrulama kapısında kalıyor (ölçüldü: kapı kapatılınca
5/5 geri geliyor, graf çarpanı da **birebir aynı 5'i** kurtarıyor, etki toplanmıyor).

Kapının geçme koşulları (`scoring.py:148`):

| # | Koşul |
|---|---|
| 1 | `r.critical` |
| 2 | `r.percentile >= 0.998` |
| 3 | denetimsiz anomali (varsayılan kapalı) |
| 4 | `any(v > 1 for v in r.multipliers.values())` |
| 5 | `len({h.rule_id for h in r.hits}) >= 2` — **2+ farklı kural** |
| 6 | `len({h.day for h in r.hits}) >= 3` — **3+ farklı günde tekrar** |

## Mantıksal kusur — sonuçtan bağımsız

`UEBA-0017`'nin koşulu:

```yaml
- usb_sayisi >= 1
- usb_ilk_kez == 1 or usb_poisson_p < 0.001 or usb_7g_poisson_p < 0.001
```

Ve `usb_ilk_kez`'in tanımı (`profile.py:425`):

```python
s["usb_ilk_kez"] = int(k_usb > 0 and profil_gun >= 30 and float(ctx.p_sum.get(sid, 0.0)) == 0.0)
```

**"Hayatında ilk kez USB" tanımı gereği kullanıcı başına BİR KEZ doğru olabilir.** Geçmiş toplamı
sıfır olma şartı, ikinci kez sağlanamaz.

Ayrıca iki Poisson kolu da **ulaşılamaz** olarak ölçülmüş durumda
(`tests/test_esik_ulasilabilirlik.py::BILINEN`: gözlenen en küçük p 0,0047 ve 0,034; eşik 0,001).
Yani `UEBA-0017` pratikte **yalnız tek-seferlik kol** üzerinden tetikleniyor.

> **Kusur:** Kapının 6. koşulu, tetiklenmesi **tanımı gereği tekrarlanamayan** bir kuraldan
> 3 günlük tekrar istiyor. Bu bir mantıksal çelişki ve r4.2'de 5 insider'ı bloke ettiği
> **ölçülmüş olmasından bağımsız** olarak kusurdur.

## Düzeltme — ve seçilMEYEN alternatif

| Seçenek | Ne yapar | Neden seçilmedi / seçildi |
|---|---|---|
| **A — kapı tek-seferlik kanıtı kabul eder** | 7. koşul: hit'in sinyalleri arasında tanımı gereği tek-seferlik bir sinyal 1 ise geçer | **SEÇİLDİ** — yeni sayısal eşik gerektirmiyor, mantıksal kusuru düzeltiyor |
| B — `UEBA-0017`'nin ulaşılamaz eşikleri düzeltilir | Poisson kolları ulaşılabilir olur, insider birden fazla gün tetikler, kapıyı doğal yoldan geçer | **Daha iyi uzun vadeli düzeltme** ama **yeni bir eşik türetmeyi** gerektiriyor; v10'da türetme kuralı kendi sınamasını geçemedi. Bu fazda yapılmıyor. |
| C — `kuyruk_tekrar_gun` 3→2 ya da `kuyruk_kacis_yuzdelik` gevşetilir | — | **Reddedildi**: sonucu gördükten sonra sabit oynatmak. Bu projede iki kez yapıldı, ikisi de sapma. |

### A'nın dürüst zayıflığı — şimdiden yazılıyor

"Tanımı gereği tek-seferlik" sinyal kümesi bugün **tek üyeli**: `usb_ilk_kez`. Diğer "yeni_*"
sinyalleri (`yeni_cihaz_sayisi`, `yeni_hassas_uygulama`) tekrarlanabilir — gelecek ay başka bir
cihaz da "yeni" olur.

> **Yani düzeltme, ölçümde önemli çıkan tek kurala denk geliyor ve bu şüphe uyandırır.**
> Savunması: ölçüt tek-seferliliğin **tanımından** çıkarılıyor (geçmiş toplamı sıfır şartı), sonuca
> bakılarak değil; ve kümenin tek üyeli olması bir sınır olarak raporlanacak. Genelliği
> **kanıtlanmış değil.**

## Değişecekler

| # | Ne | Dosya | Donmuş |
|---|---|---|---|
| 1 | `TEK_SEFERLIK_SINYAL = {"usb_ilk_kez"}` + 7. koşul | `scoring.py` | **evet** |
| 2 | Bayrak `tek_seferlik_kanit` | `config.py` | **evet** |

İkisi de donmuş → **dondurma v12**. Bayrak varsayılan **kapalı**.
Kural dosyaları, eşikler, ağırlıklar **değişmeyecek**.

## Başarı eşikleri — ölçümden ÖNCE

1. **Bayrak kapalıyken r4.2 birebir aynı** (22/34, 1.939 vaka). Doğruluk kontrolü.
2. **Bayrak açıkken kapsama artar** ve kurtarılan küme, `v12_dogrulama_kapali`'nin kurtardığı beş
   senaryoyla **aynı** olmalı. Farklı bir küme çıkarsa düzeltme başka bir şey yapıyor demektir.
3. **Bedel, kapıyı tamamen kapatmaktan BELİRGİN AZ olmalı.** Kapı kapalı +129 vakaya mal oluyordu;
   hedefli düzeltme çok daha az olmalı (ör. < +40). Değilse hedefli olmamış.
4. **precision@N düşmez.**

2 ve 3 birlikte belirleyici: 2 düzeltmenin **doğru şeyi** yaptığını, 3 **dar** yaptığını sınıyor.
3 sağlanmazsa düzeltme kapıyı gevşetmekten farklı değildir ve değeri yoktur.

## Beklentiler — karamsar

1. **Kapsama 27/34 olacak, aynı 5 senaryo.** Mekanizma anlaşıldığı için sürpriz beklenmiyor.
2. **Bedel çok düşük olacak** (+10'un altı). Gerekçe: `usb_ilk_kez == 1` olan kullanıcı-gün sayısı
   az — "hayatında ilk kez" olayı kullanıcı başına bir kez. Ama tam bu yüzden **yanlış pozitifi
   de** düşük olmalı, yani 3. ölçüt rahat geçmeli.
3. **r6.2'de doğrulanamayacak.** Ölçüldü: r6.2'de kapıya bağlı kaçan insider **yok**
   (`docs/r62-kapi-on-kayit.md`). Yani ikinci veri setini yalnız r1 verebilir ve **varsayılan bu
   fazda açılmayacak** — hangi sonuç çıkarsa çıksın.
4. **En olası sessiz hata:** bayrak açıkken *beklenenden fazla* senaryo gelmesi. O hâlde düzeltme
   dar değil ve ölçüt 2 bunu yakalar.

---

# Sapmalar — ölçümden SONRA eklendi (7 Kasım 2026)

Ön kayıt metni yukarıda **değiştirilmedi**.

## ÖLÇÜT 2 TAMAMEN KALDI — düzeltme hiçbir şey yapmadı, ve KOD GERİ ALINDI

| Varyant | Kapsama | Vaka | precision@N |
|---|---|---|---|
| `tam` | 22/34 | 1.939 | 0,045 |
| `v12_dogrulama_kapali` | **27/34** | 2.068 | 0,045 |
| **`v12_tek_seferlik_kanit`** | **22/34** | **1.939** | 0,045 |

Hedefli düzeltme r4.2'de **birebir referansla aynı** sonucu verdi: 0 senaryo kurtardı, 0 ek vaka
açtı. Yani kod yolu **hiç tetiklenmedi**.

Sentetik veride de ölçüldü: **+0 yakalama, +5 vaka.** Orada tetikleniyor (5 ek vaka) ama hiçbir
senaryo kurtarmıyor.

> **İki veride de saf maliyet, sıfır fayda.** Kod `git revert` ile geri alındı, dondurma **v11'de
> kaldı**. Ön kayıt ve bu sapma kaydı duruyor — öğrenilen şey kodda değil burada.

## Hatanın zinciri — ve üçüncü kez aynı sınıf

Ön kayıt şu önermeye dayanıyordu: *"`UEBA-0017` pratikte yalnız tek-seferlik kol üzerinden
tetikleniyor."* Kaynağı `tests/test_esik_ulasilabilirlik.py::BILINEN` yorumu:

```
# UEBA-0017'nin iki Poisson koşulu da SENTETİK VERİDE ulaşılamaz (gözlenen en küçük p sırasıyla
# 0,0047 ve 0,034; eşik 0,001). Kural PRATİKTE YALNIZ `usb_ilk_kez == 1` ile tetikleniyor —
# ... Bu, r4.2'de kaçan 7 S2 senaryosunun MUHTEMEL sebebidir
```

Üç cümle, üç farklı kesinlik düzeyi:

| Cümle | Dayanak |
|---|---|
| "sentetik veride ulaşılamaz" | **ölçülmüş**, kapsamı açık |
| "pratikte yalnız … ile tetikleniyor" | **kapsam düşmüş** genelleme |
| "r4.2'de kaçanların muhtemel sebebi" | açıkça **tahmin** |

İkinci cümleyi okudum ve ölçülmüş bilgi gibi kullandım. Ölçüm onu çürüttü: r4.2'de o 5 insider'ın
tetikleyen hit'lerinde `usb_ilk_kez` **yok** — yoksa düzeltme çalışırdı. Gerçek veride Poisson
kolları **ulaşılabilir**.

> Bu, bu oturumda **üçüncü kez** aynı hata sınıfı: *bir metnin ifadesini ölçüm sanmak.* Önceki
> ikisi "BÜTÇE DIŞI" etiketinin adı ve grafın "sıralamayı germesi" açıklamasıydı. Üçü de ön kayıtlı
> ölçütle yakalandı; ölçüt 2 tam bunun için yazılmıştı
> (*"farklı bir küme çıkarsa düzeltme başka bir şey yapıyor demektir"*).

Yorum düzeltildi: ikinci cümlenin kapsamı geri konuldu.

## Ölçüt 1, 3 ve 4 geçti — ama anlamsız

- Ölçüt 1 (kapalıyken birebir aynı): geçti.
- Ölçüt 3 (bedel kapıdan az): +0 vs +129 — teknik olarak geçti, ama **sıfır fayda için sıfır
  bedel** övünülecek bir şey değil.
- Ölçüt 4 (precision düşmez): geçti, çünkü hiçbir şey değişmedi.

Üçünün de geçmesi düzeltmenin işe yaradığını göstermiyor. **Tek anlamlı ölçüt 2'ydi ve kaldı.**

## Şimdi bilinen: o 5 insider NEDEN kapıda kalıyor

Elenen açıklamalar:

| Açıklama | Durum |
|---|---|
| Bütçe yetmiyor | **yanlış** — bütçe 30→100 eğrisi düz |
| Tespit edilemiyor | **yanlış** — `BÜTÇE DIŞI` = beklenen kural tetiklendi |
| Tek-seferlik kanıt çelişkisi | **yanlış** — hedefli düzeltme hiç tetiklenmedi |

Geriye **jenerik sebep** kalıyor: o 5 insider gerçekten *tek kural, tek gün, 0,998 yüzdeliğin
altında, çarpansız* görünüyor — yani kapının **tam olarak elemek için var olduğu** profile sahip.

> **Sonuç: dar bir düzeltme yok.** Onları geçirmenin tek yolu kapıyı **genel olarak** gevşetmek
> (+129 vaka) ve o da iki veride doğrulanamıyor — r6.2'de kapıya bağlı kaçan insider yok.

Bu, kapı dizisinin dürüst kapanışı: **sebep bulundu, çözümü yok.**
