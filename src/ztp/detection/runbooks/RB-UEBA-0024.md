# RB-UEBA-0024 — Kişisel webmail kullanımında ani artış

**Amaç:** Kullanıcının kişisel webmail sitelerine (Gmail, Yahoo, Outlook.com, Hotmail…) erişiminin kendi normalinin belirgin üstüne çıkması.

**Neden önemli:** Kurumsal e-posta ağ geçidi denetleniyorsa, kişisel webmail o denetimi atlamanın **en basit yoludur**. USB kapatılmış bir ortamda birincil sızıntı kanallarından biri hâline gelir.

## İlk kontroller (analist)

- **Yükleme mi okuma mı:** telemetri ayırıyorsa yönü doğrula. Sabah gelen kutusuna bakmak ile dosya yüklemek aynı şey değildir.
- **Hangi site, hangi sıklık:** tek oturumda arka arkaya mı, güne yayılmış mı?
- **Aynı dönemde ne var:** dosya sunucusunda toplu erişim, bulut depolama kullanımı (UEBA-0022), dış e-posta artışı (UEBA-0023)?
- **Bağlam:** ayrılık bildirimi, yetki kaybı, performans süreci?
- **Cihaz:** kurumsal cihazdan mı, kişisel/BYOD'dan mı?

## Yükseltme kriteri

Aşağıdakilerden **biri** varsa yükselt:

- Aynı hafta içinde hassas kaynaklara toplu erişim var
- Ayrılık bildirimi ya da yetki kaybı kaydı var
- Kurumsal politika kişisel webmail'i yasaklıyorsa — bu durumda anomali değil, **doğrudan politika ihlalidir** ve kuralın ağırlığı/kritiklik ayarı gözden geçirilmelidir
- Artış, bulut depolama ya da dış e-posta artışıyla **aynı pencerede**

## Bilinen yanlış pozitif kalıpları

- **Öğle arası kişisel kullanım** — birçok kurumda serbesttir; eşik 3 olay bunu zaten büyük ölçüde eler
- **İş başvurusu dönemi** — iş arama tek başına suç değildir; yalnız veri hareketiyle birlikte anlamlıdır
- **İK, işe alım rolleri** — dış adayla yazışma işin parçası olabilir
- **Ortak cihaz / kiosk** — kimlik çözümlemesi yanlış kişiye yazıyor olabilir; `baskasinin_cihazi_sayisi` sinyaline bakın

## Politika notu

Kurumda kişisel webmail **yasaksa** bu kural istatistiksel bir anomali kuralı olmaktan çıkar; her olay bir ihlaldir. O ortamda ağırlığın yükseltilmesi ve `kritik` işaretlenmesi — tuzak (honeytoken) kurallarıyla aynı mantık — değerlendirilmelidir. Bu, yapılandırma kararıdır ve ölçülmeden değiştirilmez.

## Kapatma

Karar (`gercek_pozitif` / `yanlis_pozitif` + sebep / `belirsiz`) etiket deposuna yazılır; `bilinen_istisna` ise son kullanma tarihli bastırma önerisi üretilir.
