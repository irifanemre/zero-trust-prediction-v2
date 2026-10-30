# Bileşen ablasyonu — r4.2

Koşu: 2026-10-30 · HEAD `68895a3252f7e1c0d9059a19cc829e9e2939dd70` · dondurma `—` → **kontrol edilmedi**
90 gün, ısınma 21, bütçe 30, 13,261,768 olay.

Her satır **aynı veri** üzerinde tek bileşen değişkenle koşuldu. `tam` referanstır.

| Varyant | Yakalanan | Δ | Vaka | Δvaka | prec@N | rec@10k | rec@30k | Erkenlik | AUPRC | ×taban | Süre |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `tam` | 22/34 | +0 | 1,939 | +0 | 0.045 | 0.618 | 0.676 | 8 | 0.064 | 6.700 | 26 dk |
| `v6_geri_bildirim` | 18/34 | -4 | 214 | -1725 | 0.238 | 0.529 | 0.529 | 8 | 0.168 | 66.800 | 7 dk |
| `v6_geri_bildirim_kapisiz` | 22/34 | +0 | 1,939 | +0 | 0.045 | 0.647 | 0.676 | 8 | 0.148 | 40.800 | 7 dk |
| `v6_gurultulu_etiket` | 18/34 | -4 | 217 | -1722 | 0.235 | 0.529 | 0.529 | 8 | 0.133 | 28.300 | 6 dk |

## Varyantlar

- `tam` — tüm bileşenler açık (referans)
- `v6_geri_bildirim` — v6-A döngü: analist etiketi → Bayes kapısı + Venn-Abers + periyodik yeniden eğitim  
  `{'geri_bildirim_dongusu': True, 'analist_gecikme_gun': 2, 'bayes_kapi_esigi': 0.3, 'bayes_min_gozlem': 10, 'belirsizlik_enabled': True, 'pred_yeniden_egitim_gun': 14, 'pred_min_yeni_etiket': 25}`
- `v6_geri_bildirim_kapisiz` — v6-A döngü ama Bayes kapısı KAPALI — etkinin kapıdan mı başka yerden mi geldiğini ayırır  
  `{'geri_bildirim_dongusu': True, 'analist_gecikme_gun': 2, 'belirsizlik_enabled': True, 'pred_yeniden_egitim_gun': 14, 'pred_min_yeni_etiket': 25}`
- `v6_gurultulu_etiket` — v6-A döngü, analistin %15'i yanılıyor — gürültülü etikete dayanıklılık  
  `{'geri_bildirim_dongusu': True, 'analist_gecikme_gun': 2, 'analist_hata_orani': 0.15, 'bayes_kapi_esigi': 0.3, 'bayes_min_gozlem': 10, 'belirsizlik_enabled': True}`

## Bileşen etkinliği

| Varyant | Graf kenar | ADWIN kesim | Bayes elenen | Anomali uyum | Anomali skorlanan |
|---|---|---|---|---|---|
| `tam` | 0 | 0 | 0 | — | — |
| `v6_geri_bildirim` | 0 | 0 | 1725 | — | — |
| `v6_geri_bildirim_kapisiz` | 0 | 0 | 0 | — | — |
| `v6_gurultulu_etiket` | 0 | 0 | 1722 | — | — |

**Okuma:** Δ pozitifse bileşen yakalamayı artırıyor. Δvaka bedelini verir — yakalama artmadan vaka
artıyorsa bileşen yalnız yanlış alarm üretmiştir. AUPRC tek başına okunmaz, `×taban` şans seviyesinin
kaç katı olduğunu söyler.
