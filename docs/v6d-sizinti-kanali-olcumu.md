# v6-D sızıntı kanalı ayrımı — ölçüm sonuçları

**Koşu: 30 Ekim 2026, r4.2, 90 gün, bütçe 30.** Ön kayıt: `docs/sprint-v6-on-kayit.md` katman D.

> **Karar: UEBA-0022 GÖLGEDE KALIYOR.** Sprintin iki güvenlik şartı geçti, projenin kendi
> gölge-mod mezuniyet şartı (precision ≥ %25) geçilmedi.

## Ön kayıttaki şartlar

| # | Şart | Sonuç | |
|---|---|---|---|
| 1 | ~~r6.2'de S5 yakalanır~~ | **Sapma 3 ile geçersiz** — eşik o vaka görüldükten sonra gevşetildi | — |
| 2 | r4.2'de kapsama düşmez | 22/34 → **22/34** | ✔ |
| 3 | Vaka hacmi artışı ≤ %15 | 1.939 → 1.960 (**+%1,08**) | ✔ |

## Tam tablo

| Ölçüt | `tam` | `v6d_sizinti_kanali` |
|---|---|---|
| Yakalanan senaryo | 22/34 | **22/34** |
| **Değişen senaryo** | — | **0** |
| Vaka | 1.939 | 1.960 (+%1,08) |
| Kuyruğa giren kullanıcı | 122 | 137 |
| precision@N | 0,045 | 0,047 |
| precision@1 | **0,420** | **0,375** ▼ |
| precision@10 | 0,108 | 0,112 |
| recall@10 (kullanıcı) | 0,618 | 0,618 |
| recall@30 (kullanıcı) | 0,676 | 0,676 |
| Erkenlik medyanı | 8 gün | 8 gün |

## Kuralın kendi sağlığı

| | |
|---|---|
| Tetiklenme | **143** (90 günde, 1,59/gün) |
| Katıldığı gerçek vaka | 12 |
| Katıldığı yanlış vaka | 64 |
| **Kural precision'ı** | **%15,8** |
| Sistem ortalaması (precision@N) | %4,7 |
| Skora katkı payı | %10,8 |
| Doğrulama durumu | `dogrulandi` |

Kural, tetiklendiği vakalarda sistem ortalamasının **3,4 katı** kaliteli. Ama **hiçbir yeni senaryo
yakalamadı** — dokunduğu 12 gerçek vaka zaten başka kurallarla yakalanıyordu.

## Gölge mod mezuniyeti (13.6)

Projenin sprint öncesinden beri yürürlükte olan standardı:

| Şart | Eşik | Ölçülen | |
|---|---|---|---|
| En az gün | 14 | 90 | ✔ |
| Günlük ortalama uyarı | ≤ 2,0 | 1,59 | ✔ |
| **Precision** | **≥ 0,25** | **0,158** | **✘** |

Üçünden biri sağlanmadı → **kural gölgede kalır.** Bu benim yargım değil, projenin kendi
yazılı standardı; sprintin şartlarıyla çakıştığında daha katı olan geçerlidir.

## Neden r4.2 bu kuralı ölçemez

r4.2 bu kuralın **maliyetini** ölçebilir, **faydasını** ölçemez. İki sebep:

1. **r4.2'nin 34 senaryosunun 31'i USB'ye bağımlı.** Bu kuralın hedeflediği senaryo sınıfı
   (bulut yükleme) r4.2'de neredeyse yok.
2. **r4.2'nin `http.csv` dosyasında `content` kolonu VAR.** Yani orada `UEBA-0003` (veri hacmi)
   normal çalışıyor ve bu kuralın doldurduğu boşluk r4.2'de **mevcut değil**. Boşluk yalnız
   r6.2 gibi hacim bilgisi olmayan veride ortaya çıkıyor.

Dolayısıyla "r4.2'de bir şey yakalamadı" bulgusu kuralın işe yaramadığını **göstermez**; yalnız
r4.2'nin bu soruyu cevaplayamadığını gösterir.

## Elimizde ne kaldı

| Kanıt | Durum |
|---|---|
| Maskelemenin varlığı | **Ölçüldü** — havuzda p=0,347, ayrı sayaçta p=0,0134 (26 kat) |
| Kuralın maliyeti | **Ölçüldü** — +%1,08 vaka, kapsama değişmedi |
| Kuralın sinyal kalitesi | **Ölçüldü** — ortalamanın 3,4 katı |
| **Kuralın faydası** | **Ölçülemedi** — tek test vakası sapma 3 ile yandı, r4.2 bu sınıfı içermiyor |

Faydanın yansız sınavı **r1**'dir — dokunulmamış tek veri.

## Yan bulgu: UEBA-0003 r6.2'de yapısal olarak ölü

Teşhis sırasında çıktı ve kuraldan bağımsız olarak önemli:

**r6.2'nin `http.csv` dosyasında `content` kolonu yoktur.** Ayrıştırıcı `bytes_out`'u içerik
uzunluğundan türettiği için r6.2'de **her web olayının `bytes_out` değeri sıfırdır**. Yani
`UEBA-0003` (anormal veri çıkış hacmi, ağırlık 8 — en ağır iki UEBA kuralından biri) r6.2'de
**hiç tetiklenemez**.

Bu, r6.2 kör koşusunun sonuçlarını okurken bilinmesi gereken bir sınırdır: o koşuda web
sızdırması hacim üzerinden **ölçülmemiştir**. r6.2'de `bytes_out`'a katkı veren kaynaklar
yalnızca e-posta (`size` alanı gerçektir) ve taşınabilir medyaya dosya kopyalarıdır.
