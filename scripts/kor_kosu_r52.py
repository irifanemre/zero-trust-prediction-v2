#!/usr/bin/env python3
"""CERT r5.2 kör koşusu (ön kayıt planı: `docs/kor-kosu-r52-plani.md`) — tek koşu, kurallar `kurallar-donduruldu-v1`.

Dönem D1'den geriye 90 günlük pencerelere bölünür; her pencere `cert_eval.py` ile aynı ayarlarla (--days 90 --warmup 21,
bütçe 10) kendi 111 günlük tarihçesiyle koşulur ve bellek pencereden sonra boşaltılır. Her senaryo, bitiş tarihini içeren
pencerede ölçülür. Metrik tanımları `src/ztp/evaluation.py` ile aynıdır; pencereler arası birleştirme sayaçları toplar.

Kullanım:
    python scripts/kor_kosu_r52.py --cert-dir C:/data/cert_r5.2/r5.2 --out C:/data/ztp_out/kor_r52
    python scripts/kor_kosu_r52.py ... --devam      # teknik hatadan sonra: biten pencereler yeniden koşulmaz
Çıktı: <out>/sonuclar.json, <out>/ozet.md, <out>/pencere_<i>.json (+ .npz tahmin satırları).
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kor_kosu_hazirlik import PeakMemory, logon_bounds, sha256_file, windows_from_bounds  # noqa: E402

# v4 bileşenleri (revizeler.txt / revizeler2.txt). --ac ile açılır; AÇIKKEN KOŞU KÖR SAYILMAZ, çünkü bu
# bileşenlerin ayarları r4.2 ölçümü görülerek seçildi. Çıktıda `tur` alanı bunu kayda geçirir.
HEPSI_ACIK = dict(
    graf_enabled=True,
    graf_agirligi=0.5,
    adwin_enabled=True,
    bayes_kapi_esigi=0.3,
    belirsizlik_enabled=True,
    kanit_dogrulama="dengeli",
    cok_ajanli_rapor=True,
)

from ztp.config import TenantConfig  # noqa: E402
from ztp.data.cert import load_cert_dataset  # noqa: E402
from ztp.detection.catalog import load_catalog  # noqa: E402
from ztp.evaluation import PARTS, f1_at, lr_protocol, scenario_table  # noqa: E402
from ztp.metrics import MetricsCollector  # noqa: E402
from ztp.pipeline import ZeroTrustPredictionPipeline  # noqa: E402
from ztp.prediction_model import PREDICTION_FEATURES, LogisticModel, calibration_report, rows_to_matrix  # noqa: E402
from ztp.schema import DAY  # noqa: E402

LOG = logging.getLogger("kor_kosu_r52")
REPO = Path(__file__).resolve().parents[1]
FREEZE = REPO / "configs" / "freeze" / "kurallar-donduruldu-v1.json"
PLAN = REPO / "docs" / "kor-kosu-r52-plani.md"
MODEL = REPO / "configs" / "models" / "kor-r52-birincil-lr.json"
SPLIT = REPO / "configs" / "splits" / "cert-r5.2-kullanici-bolmesi.json"
SAMPLE = REPO / "configs" / "splits" / "cert-r5.2-orneklem.json"  # plan §3.2 (f, katmanlı, tohum 42)
WARMUP, DAYS, BUDGET, KS = 21, 90, 10, (1, 3, 5, 10)  # BUDGET varsayılanı; --budget ile ezilir (r6.2: 30)
BUTCELER = (1, 2, 3, 5, 10, 15, 20, 30, 50, 75, 100)  # bütçe–recall eğrisinin eksen noktaları


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


def freeze_check(manifest: Path = FREEZE) -> str:
    r = subprocess.run(
        [sys.executable, "-m", "ztp.freeze", "--check", str(manifest)], cwd=REPO, capture_output=True, text=True, encoding="utf-8"
    )
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or "donmuş durumla aynı" not in out:
        sys.exit(f"Dondurma kontrolü başarısız — koşu başlamaz:\n{out}")
    return out


# ------------------------------------------------------------------------------------------------------- pencere
def run_window(i: int, w: dict, args: argparse.Namespace, out: Path) -> dict:
    mem = PeakMemory()
    t0 = time.perf_counter()
    start, end = pd.Timestamp(w["baslangic"]), pd.Timestamp(w["bitis"])
    ek = HEPSI_ACIK if getattr(args, "ac", False) else {}
    cfg = TenantConfig(tenant_id=f"cert-r{args.surum}-p{i}", alarm_budget_per_day=args.budget, **ek)
    start_hist = end - (cfg.long_window_days + WARMUP + DAYS) * DAY
    data = load_cert_dataset(args.cert_dir, start_hist, end, answers_dir=args.answers_dir, only_users=args.users)
    cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
    load = dict(olay=len(data.events), kullanici=len(data.directory), cevap_anahtari=len(data.ground_truth))
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), out / "pencereler")
    pipe.run(start, end, WARMUP)
    m = pipe.metrics
    gt = [g for g in m.gt if not g.get("negatif")]
    rows = scenario_table(m)  # gt ile aynı sırada (CERT'te negatif kontrol yok)
    scen = []
    for g, r in zip(gt, rows):
        r = dict(r, olay_tarihi=g["olay_tarihi"], baslangic_tarihi=g["baslangic_tarihi"])
        r["bu_pencerede"] = start <= pd.Timestamp(g["olay_tarihi"]) <= end
        scen.append(r)
    # precision@k sayaçları (evaluation.part_metrics ile aynı tanım; parça bazında da)
    windows = defaultdict(list)
    for g in gt:
        windows[g["sid"]].append(MetricsCollector._window(g))
    split = json.loads(Path(args.split).read_text(encoding="utf-8"))["atama"]
    at_k = {p: {k: [0, 0] for k in KS} for p in (*PARTS, "tumu")}
    for day, ranked in m.queue_by_day.items():
        for p in (*PARTS, "tumu"):
            sel = [s for s in ranked if p == "tumu" or split.get(s) == p]
            for k in KS:
                for sid in sel[:k]:
                    hit = any(a <= day <= b for a, b in windows.get(sid, []))
                    at_k[p][k][0 if hit else 1] += 1
    # tahmin satırları: yalnız bu pencerenin değerlendirme günleri (ısınma günleri önceki pencerede zaten var)
    pr = [r for r in pipe.pred.rows if start <= pd.Timestamp(r["gun"]) <= end]
    y = np.asarray(m.outcomes(pr), dtype=int)
    np.savez_compressed(
        out / f"pencere_{i}.npz",
        X=rows_to_matrix(pr),
        y=y,
        heur=np.array([r["p7_sezgisel"] for r in pr], dtype=float),
        sid=np.array([r["sid"] for r in pr]),
        gun=np.array([r["gun"] for r in pr]),
    )
    res = dict(
        pencere=i,
        **w,
        yukleme=load,
        senaryolar=scen,
        kuyruga_giren=sorted(s for s, al in m.alerts_by_sid.items() if al),
        kullanicilar=sorted(data.directory["sid"].astype(str)),
        at_k={p: {str(k): v for k, v in d.items()} for p, d in at_k.items()},
        # bütçe–recall eğrisi: ham sayaçlar (pencereler toplanabilsin diye oran DEĞİL). Tek sayı yerine eğri,
        # çünkü "recall@30" bütçeyi 100'e çıkarınca ne kazanıldığını söylemiyor (literatür §7.3).
        butce_egrisi=_butce_sayaclari(m, windows),
        kural_tetikleme=dict(sorted(m.rule_hits.items())),
        # gölge moddaki kurallar kuyruğa girmez, ayrı kaydedilir; ısınma günleri hariç
        golge_mod=dict(
            sorted(Counter(sh["kural"] for sh in pipe.engine.shadow_log if start <= pd.Timestamp(sh["gun"]) <= end).items())
        ),
        vaka_hacmi=dict(toplam=sum(len(v) for v in m.queue_by_day.values()), gun=len(m.queue_by_day)),
        tahmin_satiri=len(pr),
        tepe_bellek_gb=mem.gb(),
        sure_sn=round(time.perf_counter() - t0),
    )
    (out / f"pencere_{i}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    del pipe, data, pr
    gc.collect()
    return res


def _butce_sayaclari(m, windows: dict) -> dict:
    """Pencere başına bütçe–recall HAM sayaçları: oranlar pencereler birleştirilirken hesaplanır.

    Oran kaydetmek yanlış olur: dört pencerenin recall'ı ortalanamaz, çünkü fırsat sayıları farklıdır.
    Burada her bütçe için (yakalanan insider-gün, fırsat, incelenen vaka, yakalanan kullanıcılar) tutulur;
    `aggregate` bunları toplar ve kullanıcı kümelerini BİRLEŞTİRİR (bir insider pencere 2'de yakalanmış olabilir).
    """
    gunler = sorted(m.queue_by_day)
    firsat = {sid: [d for d in gunler if any(a <= d <= b for a, b in ar)] for sid, ar in windows.items()}
    toplam_firsat = sum(len(v) for v in firsat.values())
    olculebilir = sorted(sid for sid, v in firsat.items() if v)
    out: dict = {}
    for k in BUTCELER:
        gun_sayisi, yakalanan, incelenen = 0, set(), 0
        for d in gunler:
            ilk_k = m.queue_by_day[d][:k]
            incelenen += len(ilk_k)
            for sid in olculebilir:
                if d in firsat[sid] and sid in ilk_k:
                    gun_sayisi += 1
                    yakalanan.add(sid)
        out[str(k)] = dict(yakalanan_gun=gun_sayisi, incelenen=incelenen, yakalananlar=sorted(yakalanan))
    out["payda"] = dict(firsat=toplam_firsat, olculebilir=olculebilir, ort_aktif=round(
        float(np.mean([d["aktif_kullanici"] for d in m.daily])) if m.daily else 0.0, 1
    ))
    return out


# ------------------------------------------------------------------------------------------------------ birleştirme
def ratio(a: int, b: int):
    return round(a / b, 3) if b else None


def _butce_birlestir(wins: list) -> dict:
    """Pencerelerin ham bütçe sayaçlarını birleştirir: günler toplanır, insider kümeleri BİRLEŞTİRİLİR."""
    varsa = [w["butce_egrisi"] for w in wins if w.get("butce_egrisi")]
    if not varsa:
        return {}
    firsat = sum(e["payda"]["firsat"] for e in varsa)
    olculebilir = sorted(set().union(*(set(e["payda"]["olculebilir"]) for e in varsa)))
    aktif = round(sum(e["payda"]["ort_aktif"] for e in varsa) / len(varsa), 1)
    satirlar = []
    for k in BUTCELER:
        anahtar = str(k)
        gun = sum(e[anahtar]["yakalanan_gun"] for e in varsa)
        incelenen = sum(e[anahtar]["incelenen"] for e in varsa)
        yakalanan = set().union(*(set(e[anahtar]["yakalananlar"]) for e in varsa))
        satirlar.append(
            dict(
                butce=k,
                butce_orani=round(k / aktif, 5) if aktif else None,
                incelenen_vaka=incelenen,
                recall_gun=ratio(gun, firsat),
                recall_kullanici=ratio(len(yakalanan), len(olculebilir)),
                yakalanan_insider=len(yakalanan),
                vaka_basina_insider=None,
            )
        )
    for onceki, simdi in zip(satirlar, satirlar[1:]):
        d_ins = simdi["yakalanan_insider"] - onceki["yakalanan_insider"]
        d_vaka = simdi["incelenen_vaka"] - onceki["incelenen_vaka"]
        simdi["vaka_basina_insider"] = round(d_vaka / d_ins, 1) if d_ins > 0 else None
    return dict(
        payda=dict(insider_gun=firsat, insider_kullanici=len(olculebilir), ort_aktif_kullanici=aktif),
        egri=satirlar,
        not_="Bütçe o günkü kuyruk uzunluğunu aşarsa kuyruk neyse o alınır; düzleşme sıranın değil kuyruğun sınırı olabilir.",
    )


def aggregate(wins: list, answers_dir: str, all_windows: list, release: str, users=None) -> dict:
    """Her senaryo bitiş tarihini içeren pencerede ölçülür; hiçbir pencereye düşmeyen senaryo 'ölçülmedi' sayılır."""
    ins = pd.read_csv(Path(answers_dir) / "insiders.csv")
    ins = ins[ins["dataset"].astype(str) == release]
    if users is not None:  # örneklemde olmayan insider ölçülmez ve matrise girmez
        ins = ins[ins["user"].isin(set(users))]
    measured = {r["senaryo"]: dict(r, pencere=w["pencere"]) for w in wins for r in w["senaryolar"] if r["bu_pencerede"]}
    scen, unmeasured = [], []
    for r in ins.itertuples(index=False):
        key = f"CERT-r{release}-S{r.scenario}-{r.user}"
        if key in measured:
            scen.append(measured[key])
        else:
            e = pd.to_datetime(r.end, format="mixed", errors="coerce")
            unmeasured.append(
                dict(
                    senaryo=key,
                    sid=r.user,
                    bitis=str(e.date()) if pd.notna(e) else None,
                    neden="tarih okunamadı" if pd.isna(e) else "bitiş tarihi koşulan pencerelerin dışında (atlanan dönem)",
                )
            )
    ev = [r for r in scen if not r["kismi"]]
    pa = [r for r in scen if r["kismi"]]

    def block(rs: list) -> dict:
        return dict(
            senaryo=len(rs),
            gecti=sum(r["gecti"] for r in rs),
            yakalama=ratio(sum(r["gecti"] for r in rs), len(rs)),
            pencerede_kuyrukta=sum(r["pencerede_kuyrukta"] for r in rs),
            kuyruga_girdi_orani=ratio(sum(r["pencerede_kuyrukta"] for r in rs), len(rs)),
            sonuclar=dict(Counter(r["sonuc"].split(" [")[0] for r in rs)),
        )

    by_type = {
        t: dict(degerlendirilebilir=block([r for r in ev if r["katman"] == t]), kismi=block([r for r in pa if r["katman"] == t]))
        for t in sorted({r["katman"] for r in scen})
    }
    early = [r["erkenlik_gun"] for r in ev if r["gecti"] and r["erkenlik_gun"] is not None]
    early_t = {
        t: median(v)
        if (v := [r["erkenlik_gun"] for r in ev if r["gecti"] and r["katman"] == t and r["erkenlik_gun"] is not None])
        else None
        for t in by_type
    }
    # precision@k: pencerelerin sayaçları toplanır
    at_k = {}
    for p in (*PARTS, "tumu"):
        at_k[p] = {}
        for k in KS:
            t = sum(w["at_k"][p][str(k)][0] for w in wins)
            f = sum(w["at_k"][p][str(k)][1] for w in wins)
            at_k[p][f"precision@{k}"] = ratio(t, t + f)
    # kullanıcı bazında confusion (r4.2 tanımı; kısmi/ölçülmeyen senaryosu olan insider matrise girmez)
    users = sorted(set().union(*(w["kullanicilar"] for w in wins)))
    queued = set().union(*(w["kuyruga_giren"] for w in wins))
    positives = {r["sid"] for r in ev}
    tp_set = {r["sid"] for r in ev if r["pencerede_kuyrukta"]}
    excluded = set(ins["user"]) - positives
    cm = dict(tp=0, fn=0, fp=0, tn=0)
    for u in users:
        if u in excluded:
            continue
        if u in positives:
            cm["tp" if u in tp_set else "fn"] += 1
        else:
            cm["fp" if u in queued else "tn"] += 1
    cm.update(
        matris_disi_insider=len(excluded & set(users)),
        precision=ratio(cm["tp"], cm["tp"] + cm["fp"]),
        recall=ratio(cm["tp"], cm["tp"] + cm["fn"]),
    )
    rules, shadow = Counter(), Counter()
    for w in wins:
        rules.update(w["kural_tetikleme"])
        shadow.update(w.get("golge_mod", {}))
    return dict(
        pencereler=[
            {
                k: w[k]
                for k in (
                    "pencere",
                    "baslangic",
                    "bitis",
                    "tarihce_baslangic",
                    "yukleme",
                    "vaka_hacmi",
                    "tahmin_satiri",
                    "tepe_bellek_gb",
                    "sure_sn",
                )
            }
            for w in wins
        ],
        atlanan_pencereler=all_windows,
        yakalama=dict(degerlendirilebilir=block(ev), kismi_pencereli=block(pa), senaryo_turu=by_type, olculmeyen=unmeasured),
        precision_at_k=at_k,
        butce_recall_egrisi=_butce_birlestir(wins),
        confusion=cm,
        erkenlik=dict(medyan=median(early) if early else None, senaryo_turu=early_t, n=len(early)),
        kural_tetikleme=dict(sorted(rules.items())),
        golge_mod=dict(sorted(shadow.items())),
        vaka_hacmi=dict(toplam=sum(w["vaka_hacmi"]["toplam"] for w in wins), gun=sum(w["vaka_hacmi"]["gun"] for w in wins)),
        senaryolar=sorted(scen, key=lambda r: (r["katman"], r["sid"])),
    )


def logistic(wins: list, out: Path, split_path: str) -> dict:
    parts = [np.load(out / f"pencere_{w['pencere']}.npz", allow_pickle=False) for w in wins]
    X = np.concatenate([p["X"] for p in parts])
    y = np.concatenate([p["y"] for p in parts])
    heur = np.concatenate([p["heur"] for p in parts])
    sid = np.concatenate([p["sid"] for p in parts])
    gun = np.concatenate([p["gun"] for p in parts])
    doc = json.loads(MODEL.read_text(encoding="utf-8"))
    model = LogisticModel.from_dict(doc["model"])
    p = model.predict_many(X)
    prim = calibration_report(p, y)
    prim.pop("guvenilirlik", None)
    prim["f1_r42_esiginde"] = round(f1_at(p, y, doc["esik"]), 3)
    prim["esik"] = doc["esik"]
    heur_rep = calibration_report(heur, y)
    heur_rep.pop("guvenilirlik", None)
    rows = [
        dict(gun=g, sid=s, ozellikler=dict(zip(PREDICTION_FEATURES, map(float, x))), p7_sezgisel=float(h))
        for g, s, x, h in zip(gun, sid, X, heur)
    ]
    second = lr_protocol(rows, y.tolist(), json.loads(Path(split_path).read_text(encoding="utf-8")))
    return dict(birincil=dict(model_sha256=sha256_file(MODEL), C=doc["C"], **prim), birincil_sezgisel=heur_rep, ikincil=second)


# ------------------------------------------------------------------------------------------------------------ özet
def fmt(v) -> str:
    if v is None:
        return "—"
    return f"{v:.3f}".replace(".", ",") if isinstance(v, float) else str(v)


def write_summary(res: dict, out: Path) -> None:
    (out / "sonuclar.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = [
        f"# CERT {res['kayit']['surum']} {res['kayit'].get('tur', 'kör koşu')} — özet"
        + (" (SINAMA)" if res["kayit"]["sinama"] else ""),
        "",
        f"- HEAD: `{res['kayit']['head']}`  plan: `{res['kayit']['plan_commit']}`",
        f"- Dondurma: {res['kayit']['freeze']}",
        "",
    ]
    a = res.get("sonuc")
    if a:
        md += [
            "## Pencereler",
            "",
            "| # | Dönem | Olay | Kullanıcı | Vaka | Tepe bellek | Süre |",
            "|---|---|---|---|---|---|---|",
        ]
        md += [
            f"| {w['pencere']} | {w['baslangic']} – {w['bitis']} | {w['yukleme']['olay']:,} | {w['yukleme']['kullanici']} | "
            f"{w['vaka_hacmi']['toplam']} | {w['tepe_bellek_gb']} GB | {w['sure_sn'] // 60} dk |"
            for w in a["pencereler"]
        ]
        y = a["yakalama"]
        md += ["", "## Yakalama", "", "| Tür | Değ. senaryo | GEÇTİ | Kuyruğa girdi | Kısmi (geçti/n) |", "|---|---|---|---|---|"]
        for t, b in y["senaryo_turu"].items():
            e, k = b["degerlendirilebilir"], b["kismi"]
            md.append(
                f"| {t} | {e['senaryo']} | {e['gecti']} ({fmt(e['yakalama'])}) | {e['pencerede_kuyrukta']} | {k['gecti']}/{k['senaryo']} |"
            )
        e, k = y["degerlendirilebilir"], y["kismi_pencereli"]
        md += [
            f"| **Tümü** | {e['senaryo']} | {e['gecti']} ({fmt(e['yakalama'])}) | {e['pencerede_kuyrukta']} | {k['gecti']}/{k['senaryo']} |",
            "",
            f"Ölçülmeyen senaryo: {len(y['olculmeyen'])}",
            "",
        ]
        pk, cm = a["precision_at_k"]["tumu"], a["confusion"]
        md += [
            "## Precision ve confusion",
            "",
            " ".join(f"{k}: {fmt(v)}" for k, v in pk.items()),
            "",
            f"TP {cm['tp']} · FN {cm['fn']} · FP {cm['fp']} · TN {cm['tn']} · precision {fmt(cm['precision'])} · "
            f"recall {fmt(cm['recall'])} (matris dışı insider {cm['matris_disi_insider']})",
            "",
            f"Erkenlik medyanı: {a['erkenlik']['medyan']} gün ({a['erkenlik']['senaryo_turu']})",
            "",
        ]
        if (egri := a.get("butce_recall_egrisi")) and egri.get("egri"):
            p = egri["payda"]
            md += [
                "## Bütçe–recall eğrisi",
                "",
                f"Payda: {p['insider_kullanici']} ölçülebilir insider, {p['insider_gun']} insider-gün fırsatı, "
                f"ortalama {p['ort_aktif_kullanici']} aktif kullanıcı/gün.",
                "",
                "| Bütçe | Bütçe oranı | İncelenen vaka | recall (gün) | recall (kullanıcı) | Yakalanan | +1 insider için ek vaka |",
                "|---|---|---|---|---|---|---|",
            ]
            for r in egri["egri"]:
                md.append(
                    f"| {r['butce']} | {fmt(r['butce_orani'])} | {r['incelenen_vaka']:,} | {fmt(r['recall_gun'])} | "
                    f"{fmt(r['recall_kullanici'])} | {r['yakalanan_insider']} | {fmt(r['vaka_basina_insider'])} |"
                )
            md += ["", egri["not_"], ""]
        md += [
            "## Kural tetikleme",
            "",
            "| Kural | Canlı | Gölge mod |",
            "|---|---|---|",
        ]
        for r in sorted(set(a["kural_tetikleme"]) | set(a["golge_mod"])):
            md.append(f"| {r} | {a['kural_tetikleme'].get(r, 0)} | {a['golge_mod'].get(r, 0)} |")
    if "lojistik" in res:
        lr = res["lojistik"]
        md += [
            "",
            "## Lojistik regresyon",
            "",
            f"- birincil: {json.dumps(lr['birincil'], ensure_ascii=False)}",
            f"- sezgisel: {json.dumps(lr['birincil_sezgisel'], ensure_ascii=False)}",
            f"- ikincil seçilen C: {lr['ikincil'].get('secilen_C')}, test: {json.dumps(lr['ikincil'].get('test'), ensure_ascii=False)}",
        ]
    (out / "ozet.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cert-dir", required=True)
    ap.add_argument("--answers-dir")
    ap.add_argument("--out", default="./ztp_out/kor_r52")
    ap.add_argument("--split", default=str(SPLIT))
    ap.add_argument(
        "--orneklem", help="kullanıcı örneklemi dosyası (r5.2 için varsayılan: configs/splits/cert-r5.2-orneklem.json)"
    )
    ap.add_argument("--devam", action="store_true", help="teknik hatadan sonra biten pencereleri atla")
    ap.add_argument("--dondurma", default=str(FREEZE), help="kural dondurma manifesti (v2 geliştirme koşusu için v2)")
    ap.add_argument("--tur", default="kör koşu", help="koşu türü etiketi (ör. 'geliştirme koşusu (70/15/15)')")
    ap.add_argument("--budget", type=int, default=BUDGET, help="alarm bütçesi (r5.2: 10, r6.2: 30)")
    ap.add_argument("--plan", default=str(PLAN), help="ön kayıt planı (commit karması kayda geçer)")
    ap.add_argument("--ac", action="store_true", help="v4 bileşenlerini aç (koşu KÖR sayılmaz)")
    ap.add_argument("--sinama", action="store_true", help="sürücü sınaması (r4.2): yalnız son pencere, temiz ağaç şartı yok")
    args = ap.parse_args()
    args.answers_dir = args.answers_dir or str(Path(args.cert_dir).parent / "answers")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(out / "kor_kosu.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    t0 = time.perf_counter()
    release = Path(args.cert_dir).name.lstrip("r")
    args.surum = release.replace(".", "")
    sample_path = Path(args.orneklem) if args.orneklem else (SAMPLE if release == "5.2" else None)
    sample = json.loads(sample_path.read_text(encoding="utf-8")) if sample_path else None
    args.users = sample["kullanicilar"] if sample else None
    if not args.sinama and git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("Çalışma ağacında commit edilmemiş değişiklik var — kör koşu commit edilmiş durumdan koşulur.")
    res = dict(
        kayit=dict(
            freeze=freeze_check(Path(args.dondurma)),
            dondurma=Path(args.dondurma).name,
            tur=args.tur,
            v4_bilesenleri=HEPSI_ACIK if args.ac else None,
            head=git("rev-parse", "HEAD"),
            etiketler=git("tag", "--points-at", "HEAD").split(),
            plan_commit=git("log", "-1", "--format=%H", "--", str(Path(args.plan).resolve().relative_to(REPO))),
            model_sha256=sha256_file(MODEL),
            bolme_sha256=sha256_file(Path(args.split)),
            orneklem=dict(dosya=sample_path.name, sha256=sha256_file(sample_path), **sample["meta"]) if sample else None,
            surum=f"r{release}",
            sinama=args.sinama,
            komut=" ".join([Path(sys.executable).name, *sys.argv]),
            baslangic=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    )
    d0, d1 = logon_bounds(Path(args.cert_dir))
    keep, skipped = windows_from_bounds(d0, d1)
    keep = keep[::-1]  # zaman sırasıyla
    if args.sinama:
        keep = keep[-1:]
    res["kayit"].update(
        D0=str(d0.date()),
        D1=str(d1.date()),
        pencere_komutu=f"--days {DAYS} --warmup {WARMUP} --budget {args.budget} --no-variants",
    )
    write_summary(res, out)
    LOG.info("Kör koşu: D0=%s D1=%s, %d pencere, atlanan %s", d0.date(), d1.date(), len(keep), skipped)
    wins = []
    for i, w in enumerate(keep, 1):
        p = out / f"pencere_{i}.json"
        if args.devam and p.exists() and (out / f"pencere_{i}.npz").exists():
            wins.append(json.loads(p.read_text(encoding="utf-8")))
            LOG.info("Pencere %d dosyadan (--devam)", i)
            continue
        LOG.info("Pencere %d/%d: %s – %s", i, len(keep), w["baslangic"], w["bitis"])
        wins.append(run_window(i, w, args, out))
        res["sonuc"] = aggregate(wins, args.answers_dir, skipped, release, args.users)
        write_summary(res, out)
        LOG.info("Pencere %d bitti (%.0f sn toplam)", i, time.perf_counter() - t0)
    res["lojistik"] = logistic(wins, out, args.split)
    res["kayit"]["bitis"] = time.strftime("%Y-%m-%d %H:%M:%S")
    res["kayit"]["sure_sn"] = round(time.perf_counter() - t0)
    write_summary(res, out)
    LOG.info("Bitti (%.0f sn). Özet: %s", time.perf_counter() - t0, out / "ozet.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
