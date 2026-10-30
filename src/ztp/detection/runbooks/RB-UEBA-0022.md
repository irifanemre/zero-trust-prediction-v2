# RB-UEBA-0022 — Sızıntı kanalı kullanımında ani artış

**Amaç:** Kişinin **sızıntı kanallarındaki** (bulut depolama, dosya transferi, paste sitesi, kişisel bulut, WebDAV) 7 günlük kullanımının kendi normalinin belirgin üstüne çıkması.

UEBA-0021'den farkı **sayacın kapsamıdır**: o, iş arama ve saldırı araçlarını da içeren havuzu sayar. İş aramayı yoğun yapan bir kullanıcıda gerçek yükleme o havuza gömülür. Bu kural yalnız kanalı sayar ve kişinin **kendi kanal tabanına** göre ölçer.

## İlk kontroller (analist)

- **Hangi kanal, hangi hedef:** dropbox / wetransfer / pastebin / kişisel OneDrive? Kurumun onaylı bir aracı mı?
- **Ne yüklendi:** URL yolunda dosya uzantısı var mı (`.zip`, `.7z`, `.tar`, `.sql`, `.csv`)? Arşiv uzantısı toplu veri demektir.
- **Yükleme mi indirme mi:** telemetri ayırıyorsa yönü doğrula. İndirme bu kuralın konusu değildir.
- **Aynı dönemde ne var:** mesai dışı erişim, toplu dosya okuma (UEBA-0007), dış e-posta ile gönderim, ayrılık bildirimi.
- **Olay yoğunluğu:** dakikalar içinde arka arkaya mı? Birkaç dosyanın tek oturumda yüklenmesi, günlere yayılmış kullanımdan farklıdır.

## Yükseltme kriteri

Aşağıdakilerden **biri** varsa yükselt:

- Yükleme, kurumun onaylı bulut aracı **dışında** bir hedefe yapılmış
- Aynı hafta içinde ayrılık bildirimi, performans süreci ya da yetki kaybı kaydı var
- Yüklemeden önceki 7 gün içinde hassas kaynaklara toplu erişim (UEBA-0007) var
- URL yolunda arşiv uzantısı var

## Bilinen yanlış pozitif kalıpları

- **Onaylı bulut geçişi** — kurum dosya paylaşımını buluta taşıyorsa toplu bir artış beklenir; bastırma kuralı (son kullanma tarihli) uygundur
- **Geliştirici / veri bilimci rolleri** — paste sitesi ve dosya transferi işin parçası olabilir
- **Yüklenici ve dış ekiple çalışma** — büyük dosya paylaşımı meşru olabilir, hedef alan adı doğrulanmalı
- **Tek seferlik kişisel kullanım** — eşik 3 olaydır; tek tıklama zaten tetiklemez

## Telemetri sınırı — analistin bilmesi gereken

Bu kural **olay sayısını** ölçer, **bayt hacmini değil**. Bazı proxy kayıtlarında (ör. CERT r6.2) yükleme boyutu hiç bulunmaz; o durumda UEBA-0003 (anormal veri çıkış hacmi) **hiç tetiklenemez** ve bu kural tek sinyal olarak kalır. Hacim bilgisi varsa iki kural birlikte değerlendirilmelidir.

## Kapatma

Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
