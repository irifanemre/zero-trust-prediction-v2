# Belgeler

Beş belge var. Hepsinin ayrı bir işi var; hangisini ne zaman okuyacağın aşağıda.

## Okuma sırası

**Sistemin ne yaptığını anlamak için** → `mimari-dokuman.md`
**Gerçekten çalışıp çalışmadığını görmek için** → `cert-r42-r52-karsilastirma.md`
**Rakamlara neden güvenilebileceğini denetlemek için** → ön kayıt belgeleri (aşağıda)

| Belge | Satır | Ne işe yarar |
|---|---|---|
| [`mimari-dokuman.md`](mimari-dokuman.md) | 2140 | Mimarinin tamamı (sürüm 1.2). Tasarım kararları, tespit katmanları, skorlama, graf, LLM güvenliği. Tek başına okunabilir. |
| [`bulgular.md`](bulgular.md) | 235 | Mimari belgesiyle `src/ztp` arasındaki denetimin bulguları: belgede yazan ile kodda olan nerede ayrışıyor. |
| [`cert-r42-r52-karsilastirma.md`](cert-r42-r52-karsilastirma.md) | 96 | Aynı kurallar iki ayrı CERT kurumunda, 70/15/15 bölmeyle. Sonuç rakamları burada. |
| [`kor-kosu-r52-plani.md`](kor-kosu-r52-plani.md) | 197 | **Ön kayıt** — r5.2 koşusundan önce yazıldı. |
| [`kor-kosu-r62-plani.md`](kor-kosu-r62-plani.md) | 222 | **Ön kayıt** — r6.2 koşusundan önce yazıldı. |

## Ön kayıt belgeleri neden var

Bir tespit sistemini kendi ayarlandığı veriyle sınamak hiçbir şey kanıtlamaz. Bu yüzden her yeni CERT veri seti
**kör koşu** olarak işlenir:

1. Kurallar, eşikler ve ağırlıklar bir **dondurma manifestine** yazılır (`configs/freeze/`). Manifest 34 dosyanın
   karmasını tutar; koşudan hemen önce `python -m ztp.freeze --check` ile doğrulanır.
2. Veri **görülmeden** bir ön kayıt belgesi yazılır: hangi pencereler, hangi bütçe, hangi metrikler ve — en önemlisi —
   **sonucun ne çıkmasını beklediğim**.
3. Koşu **bir kez** yapılır. Sonucu görüp kural ya da eşik değiştirip yeniden koşmak yasaktır; böyle bir değişiklik
   yeni bir dondurma sürümü ve **yeni bir veri seti** gerektirir.
4. Plandan sapılırsa sapma, gerekçesiyle birlikte ayrı başlık olarak yazılır — silinmez.

Beklentileri önceden yazmanın anlamı şu: tutmayan beklenti sonucun kendisidir, kuralları veriye uydurmak için
gerekçe değil.

## Kronoloji git'ten doğrulanabilir

İddia "kurallar veri görülmeden donduruldu"dur. Commit karmaları taşınamaz, dolayısıyla sıra denetlenebilir:

| Olay | Commit | Tarih |
|---|---|---|
| Kurallar donduruldu (v1) | `3f86b23` | 8 Ekim 2026, 20:05 |
| r5.2 ön kaydı yazıldı | `7792965` | 8 Ekim 2026, 20:27 |
| r5.2 kör koşu sonuçları | `d64c958` | 27 Ekim 2026, 14:53 |
| r6.2 ön kaydı yazıldı | `21bc41c` | 28 Ekim 2026 |

Dondurma ve ön kayıt, r5.2 sonuçlarından **19 gün önce**dir.

Doğrulamak için:

```bash
git log --format='%h %ad %s' --date=iso -- docs/kor-kosu-r52-plani.md configs/freeze/
```
