# RB-UEBA-0023 — Dış e-posta hacminde anormal artış

**Amaç:** Kullanıcının **kurum dışına** gönderdiği e-posta hacminin kendi normalinin belirgin üstüne çıkması.

UEBA-0003'ten (genel veri çıkış hacmi) farkı **kanaldır**: o, web ve e-posta dahil tüm çıkışı tek havuzda ölçer. Yoğun web kullanan bir kullanıcıda e-posta ile sızdırma o havuza gömülür. Bu kural yalnız dış e-postayı, kişinin **kendi dış e-posta tabanına** göre ölçer.

## İlk kontroller (analist)

- **Alıcı kim:** rakip firma, kişisel adres (gmail/yahoo), yeni işveren alan adı? Daha önce yazışılmış bir adres mi?
- **Ne gönderildi:** ek sayısı (`eposta_ek_sayisi`) ve toplam hacim. 1 büyük ek ile 20 küçük ek farklı davranışlardır.
- **Zamanlama:** mesai dışı mı? Ayrılık bildirimi, performans süreci ya da yetki kaybıyla aynı haftada mı?
- **Öncesinde ne var:** son 7 günde hassas kaynaklara toplu erişim (UEBA-0007) ya da yeni paylaşım keşfi?
- **BCC alanı:** kendi kişisel adresine BCC, klasik sızdırma kalıbıdır.

## Yükseltme kriteri

Aşağıdakilerden **biri** varsa yükselt:

- Alıcı, kullanıcının kendi kişisel adresi ya da daha önce hiç yazışılmamış bir dış alan adı
- Aynı hafta içinde ayrılık bildirimi / performans süreci kaydı var
- Gönderimden önceki 7 günde hassas kaynaklara toplu erişim var
- Ek sayısı kişinin normalinin birkaç katı

## Bilinen yanlış pozitif kalıpları

- **Satış, pazarlama, tedarik rolleri** — büyük sunum ve teklif dosyaları işin parçasıdır
- **Dönemsel yoğunluk** — ay/çeyrek sonu raporlama, denetim dönemi
- **Yüklenici ve dış ekiple proje** — büyük dosya paylaşımı meşru olabilir, alan adı doğrulanmalı
- **Otomatik raporlama hesapları** — servis hesabı bastırması zaten devrede

## Telemetri sınırı

Bu kural e-posta **boyutunu** ölçer; eklerin **içeriğini okumaz** (§20.1 veri minimizasyonu). "Ne gönderildi" sorusunun cevabı bu kuraldan çıkmaz, DLP ya da e-posta ağ geçidi kaydından bakılır.

Kurumda dış/iç ayrımı alıcı alan adına göre yapılır; alan adı listesi yanlışsa kural sessizce yanlış çalışır — `available_sources` ve alan adı yapılandırması doğrulanmalıdır.

## Kapatma

Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
