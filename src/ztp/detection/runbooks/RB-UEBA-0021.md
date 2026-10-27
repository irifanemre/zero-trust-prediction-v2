# RB-UEBA-0021 — Hassas kategori kullanımında artış

**Amaç:** Kişinin zaten kullandığı hassas bir kategoride (iş arama, bulut depolama, saldırı aracı) 7 günlük kullanımın kendi normalinin belirgin üstüne çıkması. "İlk kez" kuralı (UEBA-0002) bu kişide sessiz kalır.

## İlk kontroller (analist)
- Hangi kategori: iş arama mı, bulut depolama mı
- Aynı dönemde USB, e-posta ile dışarı gönderim ya da mesai dışı erişim var mı
- İK kaydında ayrılık bildirimi, performans süreci ya da rol değişikliği var mı

## Yükseltme kriteri
Artışla aynı hafta veri çıkışı (USB, bulut, dış e-posta) varsa ya da ayrılık bildirimi kaydı varsa → yükselt.

## Bilinen yanlış pozitif kalıpları
- İK, işe alım ve satış rolleri (iş ilanı siteleri işin parçası)
- Onaylı bulut depolama geçişleri
- Tek başına iş arama: suç değildir, yalnız diğer sinyallerle birlikte anlamlıdır

## Kapatma
Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
