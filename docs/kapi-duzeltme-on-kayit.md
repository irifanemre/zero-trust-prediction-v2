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
