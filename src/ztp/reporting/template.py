"""Deterministik analist raporu (Bölüm 18) ve tespit açıklamaları; LLM erişilemediğinde tek nokta arıza olmaz (15.3)."""

from __future__ import annotations

from typing import List

from ztp.detection.engine import Hit
from ztp.reporting.sanitize import strip_unsafe


class TemplateReporter:
    @staticmethod
    def render(case: dict) -> str:
        w = 96
        raw: List[str] = []
        L = raw
        L.append("┌" + "─" * w + "┐")
        L.append(
            f"│ VAKA {case['case_id']:<28} Risk: {case['risk']:>3}/100  {'▲' if case['delta_7g'] >= 0 else '▼'} (7 gün: {case['delta_7g']:+d})".ljust(
                w + 1
            )
            + "│"
        )
        L.append(
            f"│ Kullanıcı: {case['kullanici']}  |  Departman: {case['departman']}  |  Müşteri: {case['musteri']}  |  Gün: {case['gun']}".ljust(
                w + 1
            )
            + "│"
        )
        L.append(
            f"│ Yüzdelik: %{case['yuzdelik'] * 100:.1f}  |  Ham: {case['ham_skor']:.1f}  |  Yapısal: {case['yapisal_skor']:.2f}  |  7g tahmin: %{case['tahmin_7g']['olasilik'] * 100:.0f}  |  Kritik: {'EVET' if case['kritik'] else 'hayır'}  |  Güven: {(case.get('guven') or {}).get('seviye', '—')}".ljust(
                w + 1
            )
            + "│"
        )
        L.append("├" + "─" * w + "┤")
        L.append("│ SKOR GEREKÇESİ".ljust(w + 1) + "│")
        for h in case["tespitler"]:
            L.append(
                f"│  • [{h['kural']}] {h['ad']}: {h['aciklama']} (+{h['katki']:.1f} puan) [olay {', '.join(h['kanit'][:3]) or '—'}]"
                + (f" → {h['runbook']}" if h.get("runbook") else "")
                + "│"
            )
        if case.get("karsit_olgu"):
            L.append("│  KANIT AĞIRLIĞI (bu kanıt olmasaydı ham skor):".ljust(w + 1) + "│")
            for k in case["karsit_olgu"][:4]:
                carp = f" [çarpan kaybı: {', '.join(k['kaybolan_carpanlar'])}]" if k["kaybolan_carpanlar"] else ""
                L.append(
                    f"│    {k['kural']}: {case['ham_skor']:.1f} → {k['ham_olmadan']:.1f} (−%{k['ham_dusus_yuzde']}), "
                    f"risk {case['risk']} → {k['risk_olmadan']}{carp}".ljust(w + 1)
                    + "│"
                )
        guv = case.get("guven") or {}
        if guv.get("nedenler"):
            L.append(f"│  ⚠ Güven {guv.get('seviye')}: {'; '.join(guv['nedenler'])}".ljust(w + 1) + "│")
        if case["carpanlar"]:
            L.append("│  Çarpanlar: " + ", ".join(f"{k} ×{v}" for k, v in case["carpanlar"].items()).ljust(w - 13) + "│")
        ex = case["baglam"]
        L.append(
            f"│  Baseline: akran grubu {ex.get('akran_grubu')} | ağırlık {ex.get('agirlik')} | hesap yaşı {ex.get('hesap_yasi')} gün".ljust(
                w + 1
            )
            + "│"
        )
        if ex.get("tuzak_varliklar"):
            L.append(
                f"│  ⚠ TUZAK ETKİLEŞİMİ (deterministik kanıt, bütçeden bağımsız): {', '.join(ex['tuzak_varliklar'])}".ljust(w + 1)
                + "│"
            )
        if ex.get("zehirleme"):
            L.append(f"│  ⚠ Zehirleme şüphesi: {ex['zehirleme']}".ljust(w + 1) + "│")
        if ex.get("if_katki"):
            L.append(f"│  IF (destek/gölge) katkı — özellik, robust-z: {ex['if_katki']}".ljust(w + 1) + "│")
        L.append("├" + "─" * w + "┤")
        L.append("│ İLİŞKİ HARİTASI".ljust(w + 1) + "│")
        gf = case["graf"]
        for d in gf["cihazlar"][:3]:
            L.append(f"│  {case['kullanici']} ──kullandı──▶ {d}".ljust(w + 1) + "│")
        for s in gf["paylasilan_cihazlar"][:3]:
            L.append(
                f"│  {s['cihaz']} ──ayrıca kullanıldı──▶ {s['diger_kullanici']} ({s['gun_once']} gün önce){' [RİSKLİ]' if s['riskli'] else ''}".ljust(
                    w + 1
                )
                + "│"
            )
        for p in gf["kritik_yollar"][:3]:
            L.append(f"│  yol: {' → '.join(p)}".ljust(w + 1) + "│")
        for c in gf["ortak_noktalar"][:2]:
            L.append(f"│  ortak kaynak: {c['kaynak']} ← {', '.join(c['riskli_kullanicilar'])}".ljust(w + 1) + "│")
        for t in gf["teknikler"][:4]:
            L.append(
                f"│  Eşleşen teknik: {t['teknik']} ({t['ad']}) → {t['taktik']}{'; gruplar: ' + ', '.join(t['gruplar']) if t['gruplar'] else ''}".ljust(
                    w + 1
                )
                + "│"
            )
        L.append(f"│  Etki alanı: {gf['etki_alani']} kaynak (3 adım)".ljust(w + 1) + "│")
        L.append("├" + "─" * w + "┤")
        L.append("│ ZAMAN ÇİZELGESİ".ljust(w + 1) + "│")
        for t in case["zaman_cizelgesi"]:
            L.append(f"│  {t}".ljust(w + 1) + "│")
        if case.get("attack_baglami"):
            L.append("├" + "─" * w + "┤")
            L.append("│ ATT&CK BAĞLAMI (bilgi tabanı; skorlamaya girmez)".ljust(w + 1) + "│")
            for p in case["attack_baglami"][:4]:
                L.append(f"│  {p['teknik']} {p['ad']} — {p['ozet']} Önlem: {p['onlem']}".ljust(w + 1) + "│")
        L.append("├" + "─" * w + "┤")
        L.append("│ OTOMATİK ÖZET (her ifade olay kimliğine bağlı)".ljust(w + 1) + "│")
        for line in _wrap(case["ozet"], w - 3):
            L.append(f"│  {line}".ljust(w + 1) + "│")
        L.append(f"│  [özet kaynağı: {case['ozet_kaynagi']}]".ljust(w + 1) + "│")
        sec = case.get("guvenlik") or {}
        if sec.get("injection_suphesi"):
            L.append(
                f"│  ⚠ GÜVENLİK: kanıt metinlerinde talimat benzeri içerik {sec.get('bayraklar')} — redakte edildi, LLM'e verilmedi".ljust(
                    w + 1
                )
                + "│"
            )
        L.append("├" + "─" * w + "┤")
        r = case["mudahale"]
        L.append(
            f"│ KADEMELİ MÜDAHALE: {r['seviye']} → {r['aksiyon']} (kullanıcı etkisi: {r['kullanici_etkisi']})".ljust(w + 1) + "│"
        )
        L.append(
            "│ Otomatik engelleme YOK — erişim kısıtlama yalnızca doğrulanmış olay + insan kararıyla (7.3).".ljust(w + 1) + "│"
        )
        L.append(
            "│ [ ✓ GERÇEK TEHDİT ]  [ ✗ YANLIŞ ALARM (sebep zorunlu) ]  [ ¿ BELİRSİZ ]   → etiket deposuna yazılır".ljust(w + 1)
            + "│"
        )
        L.append(
            f"│   --label {case['case_id']} --decision gercek_pozitif|yanlis_pozitif|belirsiz --reason ... --analyst ...".ljust(
                w + 1
            )
            + "│"
        )
        L.append("└" + "─" * w + "┘")
        # kutu satırları: uzun satırlar kesilmez, sarılır (analist bilgi kaybetmesin)
        out = []
        for line in raw:
            line = strip_unsafe(line)  # log kaynaklı adlardaki ANSI/kontrol karakterleri raporu/terminali manipüle edemez
            if line.startswith(("┌", "├", "└")):
                out.append(line)
                continue
            body = line[1:].rstrip("│").rstrip()
            indent = len(body) - len(body.lstrip(" "))
            chunks = _wrap(body.strip(), w - 2 - indent) if len(body) > w - 1 else [body.strip()]
            for i, ch in enumerate(chunks):
                out.append("│" + (" " * indent + (ch if i == 0 else "  " + ch)).ljust(w) + "│")
        return "\n".join(out)


def _wrap(text: str, width: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > width:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def deterministic_summary(case: dict) -> str:
    """15.3 Yedeklilik: LLM yoksa/hatalıysa deterministik şablon özet — her cümle olay kimliğine bağlı."""
    parts = []
    for h in case["tespitler"][:5]:
        ev = ", ".join(h["kanit"][:3]) or "seri"
        parts.append(f"{h['ad']}: {h['aciklama']} [olay {ev}].")
    if case["baglam"].get("rejim_degisimi"):
        parts.append(
            f"Kullanıcının {case['baglam']['rejim_degisimi']} [{', '.join(case['kanit_serileri'].get('rejim', ['seri']))}]."
        )
    if case["graf"]["paylasilan_cihazlar"]:
        s = case["graf"]["paylasilan_cihazlar"][0]
        parts.append(
            f"Kullanılan {s['cihaz']} cihazı {s['gun_once']} gün önce {s['diger_kullanici']} tarafından da kullanıldı [graf]."
        )
    return " ".join(parts) if parts else "Tespit yok."


def describe_hit(h: Hit, ex: dict) -> str:
    s = h.sinyaller
    r = h.rule_id
    if r == "UEBA-0003":
        return f"normal {ex.get('normal_hacim_mb')} MB/gün → bugün {ex.get('bugun_hacim_mb')} MB (robust z {s.get('veri_hacmi_z', 0):.1f}, akranın {s.get('veri_hacmi_akran_kati', 0):.0f}×)"
    if r == "UEBA-0001":
        if s.get("mesai_disi_giris_sayisi", 0) >= 1 and s.get("mesai_disi_giris_poisson_p", 1) < 0.01:
            return f"mesai dışı {s['mesai_disi_giris_sayisi']} giriş (kişisel/akran beklentisi çok düşük, p={s['mesai_disi_giris_poisson_p']:.1e}); ilk giriş {ex.get('giris_saati')}"
        return f"giriş saati {ex.get('giris_saati')} (normal {ex.get('normal_giris', 'akran profili')}; dairesel sapma {s.get('saat_sapmasi_z', 0):.1f}σ)"
    if r == "UEBA-0002":
        return f"kişi ve akran grubu için ilk kez görülen uygulama: {', '.join(ex.get('yeni_uygulamalar', []))}"
    if r == "UEBA-0004":
        return f"ardışık girişler arası gerekli hız {s.get('seyahat_hizi_kmh', 0):.0f} km/s"
    if r == "UEBA-0005":
        own = ex.get("baskasinin_cihazi") or {}
        return (
            f"yeni cihaz {ex.get('yeni_cihazlar', [])} / yeni ülke {ex.get('yeni_ulkeler', [])}"
            + (f"; başkasına atanmış: {list(own)}" if own else "")
            + (f" ({ex['cihaz_akran_orani']})" if ex.get("cihaz_akran_orani") else "")
        )
    if r == "UEBA-0006":
        return f"{s.get('basarisiz_giris_sayisi')} başarısız giriş (Poisson p={s.get('basarisiz_giris_poisson_p', 0):.1e})"
    if r == "UEBA-0007":
        return f"{ex.get('bugun_dosya')} dosya erişimi (normal {ex.get('normal_dosya')}; p={s.get('dosya_sayisi_poisson_p', 0):.1e}), mesai dışı oranı %{100 * s.get('mesai_disi_dosya_orani', 0):.0f}"
    if r == "UEBA-0008":
        return f"hesap {s.get('hesap_yasi_gun')} günlük; kaynak çeşitliliği akranın {s.get('kesif_genisligi_akran_kati', 0):.1f}×, keşif süreci {s.get('kesif_sureci_sayisi')}"
    if r == "UEBA-0009":
        return f"7 günlük profil akran grubundan {s.get('akran_yapisal_mesafe', 0):.1f} robust-birim uzakta"
    if r == "DQ-0010":
        return f"cihaz {ex.get('sessiz_cihaz')} EDR akışı kesildi; kullanıcı AD'de aktif (görünürlük yok ≠ olay yok)"
    if r == "PRED-0011":
        return ex.get("yetki_artisi", "yetki artışı sonrası kaynak çeşitliliği kaydı")
    if r == "PRED-0012":
        return f"7 günlük risk serisi {ex.get('risk_serisi_7g')} — eğim {s.get('risk_egim_7g', 0):.2f} MAD/gün"
    if r == "PRED-0013":
        return f"{ex.get('sessizlik', '')}; dönüş aktivitesi z={s.get('donus_aktivite_z', 0):.1f}"
    if r == "PRED-0014":
        return f"ayrılık bildirimi var; 14g hacim eğimi {s.get('hacim_trend_14g', 0):.2f}, bulut uygulaması {ex.get('bulut_uygulama', 'yok')}"
    if r == "REL-0015":
        return f"paylaşılan cihaz {s.get('paylasilan_cihaz_sayisi')} adet; kritik varlığa {s.get('kritik_varliga_yol_sayisi')} zaman-sıralı yol"
    if r == "REL-0016":
        return f"{s.get('ortak_kaynak_riskli_kume')} ortak kaynak diğer riskli kullanıcılarla paylaşılıyor"
    if r == "UEBA-0017":
        why = (
            "kişisel geçmişte ilk kez"
            if s.get("usb_ilk_kez")
            else (
                f"günlük Poisson p={s.get('usb_poisson_p', 1):.1e}"
                if s.get("usb_poisson_p", 1) < 0.001
                else f"7 günlük kümülatif {ex.get('usb_7g')} p={s.get('usb_7g_poisson_p', 1):.1e}"
            )
        )
        return f"taşınabilir medya bugün {s.get('usb_sayisi')} kez ({why})"
    if r == "UEBA-IF01":
        return f"IF anomali yüzdeliği %{100 * s.get('if_anomali_pct', 0):.1f}; en çok katkı: {ex.get('if_katki')}"
    if r.startswith("HONEY-"):
        kind = {"HONEY-0018": "hesap", "HONEY-0019": "kaynak", "HONEY-0020": "cihaz"}.get(r, "")
        toks = [t.split(":", 1)[1] for t in (ex.get("tuzak_varliklar") or []) if t.startswith(kind + ":")]
        return f"tuzak {kind} etkileşimi (meşru kullanımı yok; baseline uygulanmaz): {', '.join(toks) or '—'}"
    return ", ".join(f"{k}={v}" for k, v in s.items() if v is not None)
