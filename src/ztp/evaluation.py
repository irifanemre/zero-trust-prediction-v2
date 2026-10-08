"""19.2 yansız ölçüm — CERT değerlendirmesinin aşırı uyuma (overfitting) karşı yeniden kurulumu.

- Kullanıcı bazlı, tabakalı 70/15/15 eğitim/doğrulama/test bölmesi: sabit tohum, dosyaya kaydedilir; nüfus parmak iziyle
  başka makinede aynı bölmenin çıktığı doğrulanır.
- Boru hattı TÜM kurumda bir kez koşulur (akran grupları, yüzdelik havuzu ve alarm bütçesi kurum genelidir — alt kümede
  koşmak sistemi değiştirirdi); metrikler parça parça hesaplanır.
- Lojistik model yalnızca eğitim parçasında eğitilir; C doğrulamada log-loss ile seçilir; test parçasına en sonda bir kez
  bakılır. Eğitim ile doğrulama/test arasında zamansal embargo vardır (etiket ufku 7 gün).

Sınır: kural katmanı eğitilmez ama r4.2'nin TAMAMI görülerek elle ayarlanmıştır. Kullanıcı bölmesi öğrenen modelin
sızıntısını giderir; kural katmanı için test parçasını "görülmemiş" yapmaz (yansız rakam r5.2/r6.2 ister).
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ztp.config import TenantConfig
from ztp.data.dataset import Dataset
from ztp.metrics import MetricsCollector
from ztp.prediction_model import LogisticModel, calibration_report, rows_to_matrix
from ztp.schema import DAY

LOG = logging.getLogger(__name__)

PARTS = ("egitim", "dogrulama", "test")
DEFAULT_FRACS = (0.70, 0.15, 0.15)
DEFAULT_C_GRID = (0.001, 0.01, 0.1, 1.0, 10.0, 100.0)
BENIGN = "benign"
SPLIT_VERSION = 1


# ------------------------------------------------------------------------------------------------------------ bölme
def scenario_stratum(senaryo: str) -> str:
    """Senaryo kimliğinden katman: CERT `CERT-r4.2-S1-AAM0658` → S1; sentetik `S2_ele_gecirilmis_hesap` → S2."""
    m = re.search(r"-S(\d+)-", senaryo)
    return f"S{m.group(1)}" if m else senaryo.split("_", 1)[0]


def insider_strata(ground_truth: Sequence[dict]) -> Dict[str, str]:
    """Pozitif senaryosu olan kullanıcı → senaryo katmanı (negatif kontroller insider sayılmaz)."""
    out: Dict[str, str] = {}
    for g in ground_truth:
        if not g.get("negatif"):
            out.setdefault(g["sid"], scenario_stratum(g["senaryo"]))
    return out


def allocate(n: int, fracs: Sequence[float]) -> List[int]:
    """En büyük kalan yöntemi: toplam korunur, her parça oranına en yakın tam sayıyı alır (eşitlikte önce eğitim)."""
    raw = [n * f for f in fracs]
    base = [int(math.floor(x)) for x in raw]
    order = sorted(range(len(fracs)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[: n - sum(base)]:
        base[i] += 1
    return base


def controlled_allocate(sizes: Dict[str, int], fracs: Sequence[float], rng: np.random.RandomState) -> Dict[str, List[int]]:
    """Kontrollü yuvarlama: önce TOPLAM kota (en büyük kalan) sabitlenir, sonra katman×parça hücrelerine kotayı aşmadan
    dağıtılır. Katman katman bağımsız yuvarlamak küçük katmanlarda birikimli hata üretir (tek kişilik katman hep eğitime
    düşer; 14/17/3'lük CERT katmanları 34 insider'ı 24/5/5 yerine 24/6/4 böler). Eşitlikler katman adıyla değil tohumlu
    sırayla bozulur — hangi senaryo türünün teste düşeceğini alfabe belirlemesin."""
    keys = sorted(sizes)
    total = allocate(sum(sizes.values()), fracs)
    tie = {keys[j]: i for i, j in enumerate(rng.permutation(len(keys)))}
    raw = {k: [sizes[k] * f for f in fracs] for k in keys}
    out = {k: [int(math.floor(x)) for x in raw[k]] for k in keys}
    left_s = {k: sizes[k] - sum(out[k]) for k in keys}
    left_p = [total[p] - sum(out[k][p] for k in keys) for p in range(len(fracs))]
    cells = sorted(
        ((raw[k][p] - out[k][p], k, p) for k in keys for p in range(len(fracs))), key=lambda c: (-c[0], tie[c[1]], c[2])
    )
    for _, k, p in cells:
        if left_s[k] > 0 and left_p[p] > 0:
            out[k][p] += 1
            left_s[k] -= 1
            left_p[p] -= 1
    for k in keys:  # açgözlü adımın yerleştiremediği birim kalırsa: kotası boş ilk parça (toplam kota yine korunur)
        while left_s[k] > 0:
            p = next(i for i in range(len(fracs)) if left_p[i] > 0)
            out[k][p] += 1
            left_s[k] -= 1
            left_p[p] -= 1
    return out


def population_fingerprint(users: Sequence[str], strata: Dict[str, str]) -> str:
    h = hashlib.sha256()
    for u in sorted(users):
        h.update(f"{u}\t{strata.get(u, BENIGN)}\n".encode())
    return h.hexdigest()


def split_summary(assign: Dict[str, str], strata: Dict[str, str]) -> dict:
    out = {}
    for part in PARTS:
        members = [u for u, p in assign.items() if p == part]
        ins = [u for u in members if u in strata]
        out[part] = dict(
            kullanici=len(members),
            insider=len(ins),
            katmanlar=dict(sorted(Counter(strata[u] for u in ins).items())),
        )
    return out


def make_user_split(
    users: Sequence[str],
    ground_truth: Sequence[dict],
    seed: int = 42,
    fracs: Sequence[float] = DEFAULT_FRACS,
    source: str = "",
) -> dict:
    """Kullanıcı bazlı tabakalı bölme. Katmanlar: insider senaryo türü (S1, S2, …) + benign. Insider'ların toplamı
    parçalara kesin orantıyla (kontrollü yuvarlama), her senaryo türü mümkün olduğunca orantılı dağılır; benign'ler
    en büyük kalanla. Katman içindeki üyeler tohumlu karıştırılır. Sıralı nüfus + `RandomState(seed)` platformdan
    bağımsız aynı sonucu verir."""
    if len(fracs) != len(PARTS) or abs(sum(fracs) - 1.0) > 1e-9:
        raise ValueError("oranlar üç parça olmalı ve toplamı 1 olmalı")
    strata = insider_strata(ground_truth)
    pop = sorted(set(users) | set(strata))
    groups: Dict[str, List[str]] = defaultdict(list)
    for u in pop:
        groups[strata.get(u, BENIGN)].append(u)
    rng = np.random.RandomState(seed)
    insider_sizes = {k: len(v) for k, v in groups.items() if k != BENIGN}
    counts = controlled_allocate(insider_sizes, fracs, rng) if insider_sizes else {}
    counts[BENIGN] = allocate(len(groups.get(BENIGN, [])), fracs)
    assign: Dict[str, str] = {}
    for key in sorted(groups):
        members = [groups[key][i] for i in rng.permutation(len(groups[key]))]
        start = 0
        for part, count in zip(PARTS, counts[key]):
            for u in members[start : start + count]:
                assign[u] = part
            start += count
    meta = dict(
        surum=SPLIT_VERSION,
        kaynak=source,
        tohum=seed,
        oranlar=dict(zip(PARTS, fracs)),
        yontem="kullanıcı bazlı; insider toplamı kontrollü yuvarlamayla kesin orantılı, senaryo türleri (S1/S2/…) "
        "kotayı aşmadan orantılı, benign en büyük kalan; katman içi tohumlu karıştırma",
        parmak_izi=population_fingerprint(pop, strata),
        ozet=split_summary(assign, strata),
    )
    return dict(meta=meta, atama=dict(sorted(assign.items())))


def save_split(split: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(split, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_or_create_split(
    path: Path,
    users: Sequence[str],
    ground_truth: Sequence[dict],
    seed: int = 42,
    fracs: Sequence[float] = DEFAULT_FRACS,
    source: str = "",
) -> Tuple[dict, bool]:
    """Dosya varsa onu kullanır ve nüfusla uyuştuğunu doğrular (başka makinede aynı bölme); yoksa üretip kaydeder.
    Uyuşmazlık açık hata verir — sessizce yeni bölme üretmek önceki sonuçlarla kıyası bozardı (Prensip 5)."""
    strata = insider_strata(ground_truth)
    pop = sorted(set(users) | set(strata))
    fp = population_fingerprint(pop, strata)
    if path.exists():
        split = json.loads(path.read_text(encoding="utf-8"))
        if split["meta"]["parmak_izi"] != fp:
            raise ValueError(
                f"Bölme dosyası bu veriyle uyuşmuyor ({path}): kullanıcı ya da insider kümesi farklı. "
                "Aynı sürüm, --end/--days/--warmup ile koşun ya da dosyayı bilerek silip yeniden üretin."
            )
        return split, False
    split = make_user_split(pop, ground_truth, seed, fracs, source)
    save_split(split, path)
    return split, True


# ------------------------------------------------------------------------------------------- parça bazlı metrikler
def _windows(metrics: MetricsCollector) -> Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]]:
    w: Dict[str, List[Tuple[pd.Timestamp, pd.Timestamp]]] = defaultdict(list)
    for g in metrics.gt:
        if not g.get("negatif"):
            w[g["sid"]].append(metrics._window(g))
    return w


def is_partial(metrics: MetricsCollector, g: dict) -> bool:
    """`coverage()` ile aynı ölçüt: senaryo penceresinin bir kısmı değerlendirme dönemi dışında."""
    w0, w1 = metrics._window(g)
    er = metrics.eval_range
    return bool(er) and (w0 + 7 * DAY < er[0] or w1 - 7 * DAY > er[1])


def scenario_table(metrics: MetricsCollector) -> List[dict]:
    """Her pozitif senaryo: coverage sonucu ('26' tanımı: pencerede kuyruk + beklenen kural) ve kullanıcı bazında
    pencerede kuyrukta olup olmadığı ('27' tanımı: herhangi bir kuralla)."""
    windows = _windows(metrics)
    rows = []
    for g, c in zip(metrics.gt, metrics.coverage()):
        if g.get("negatif"):
            continue
        sid = g["sid"]
        queued = any(a <= d <= b for d, _ in metrics.alerts_by_sid.get(sid, []) for a, b in windows.get(sid, []))
        rows.append(
            dict(
                sid=sid,
                senaryo=g["senaryo"],
                katman=scenario_stratum(g["senaryo"]),
                kismi=is_partial(metrics, g),
                sonuc=c["sonuc"],
                gecti=c["sonuc"].startswith("GEÇTİ"),
                pencerede_kuyrukta=queued,
                kuyruk_kurallari=c.get("gercek_sonuc"),
                beklenen=c.get("beklenen_tespit"),
                ilk_uyari=c.get("ilk_uyari"),
                erkenlik_gun=c.get("erkenlik_gun"),
            )
        )
    return rows


def count_reconciliation(metrics: MetricsCollector) -> dict:
    """'26' (coverage GEÇTİ) ile '27' (kullanıcı bazında pencerede kuyrukta) arasındaki farkı insider insider açıklar."""
    rows = scenario_table(metrics)
    gecti = {r["sid"] for r in rows if r["gecti"]}
    kuyruk = {r["sid"] for r in rows if r["pencerede_kuyrukta"]}
    by_sid = {r["sid"]: r for r in rows}

    def brief(sid: str) -> dict:
        r = by_sid[sid]
        return {k: r[k] for k in ("sid", "senaryo", "kismi", "sonuc", "kuyruk_kurallari", "beklenen")}

    return dict(
        coverage_gecti=len(gecti),
        coverage_gecti_degerlendirilebilir=sum(1 for r in rows if r["gecti"] and not r["kismi"]),
        coverage_gecti_kismi=sum(1 for r in rows if r["gecti"] and r["kismi"]),
        kullanici_bazinda_pencerede_kuyrukta=len(kuyruk),
        yalnizca_kuyrukta=[brief(s) for s in sorted(kuyruk - gecti)],
        yalnizca_gecti=[brief(s) for s in sorted(gecti - kuyruk)],
    )


def _ratio(a: int, b: int) -> Optional[float]:
    return round(a / b, 3) if b else None


def part_metrics(metrics: MetricsCollector, split: dict, ks: Sequence[int] = (1, 3, 5, 10)) -> Dict[str, dict]:
    """Her parça (+ 'tumu') için yakalama, precision@k ve kullanıcı bazında confusion matrix.

    - Yakalama: değerlendirilebilir ve kısmi pencereli senaryolar AYRI (kısmi = senaryonun bir kısmı dönem dışında).
    - precision@k: analist yalnız o parçanın kullanıcılarını görseydi — günlük sıralı kuyruğun parçaya düşen ilk k'sı.
    - Confusion matrix (kullanıcı bazında): pozitif = değerlendirilebilir insider; TP = kendi penceresinde (±7g) kuyruğa
      girmiş; FN = girmemiş; FP = insider olmayıp dönemde en az bir kez kuyruğa girmiş; TN = hiç girmemiş.
      Yalnız kısmi pencereli senaryosu olan insider'lar matrise girmez (sayısı ayrıca verilir)."""
    assign = split["atama"]
    rows = scenario_table(metrics)
    windows = _windows(metrics)
    queued_any = {s for s, al in metrics.alerts_by_sid.items() if al}
    out: Dict[str, dict] = {}
    for part in (*PARTS, "tumu"):

        def in_part(s: str, p: str = part) -> bool:
            return p == "tumu" or assign.get(s) == p

        sc = [r for r in rows if in_part(r["sid"])]
        ev = [r for r in sc if not r["kismi"]]
        pa = [r for r in sc if r["kismi"]]
        at_k = {}
        for k in ks:
            t = f = 0
            for day, ranked in metrics.queue_by_day.items():
                for sid in [s for s in ranked if in_part(s)][:k]:
                    hit = any(a <= day <= b for a, b in windows.get(sid, []))
                    t += hit
                    f += not hit
            at_k[f"precision@{k}"] = _ratio(t, t + f)
        users = [u for u in assign if in_part(u)]
        positives = {r["sid"] for r in ev}
        partial_only = {r["sid"] for r in pa} - positives
        in_window = {r["sid"] for r in sc if r["pencerede_kuyrukta"]}
        tp = fn = fp = tn = 0
        for u in users:
            if u in partial_only:
                continue
            if u in positives:
                tp += u in in_window
                fn += u not in in_window
            else:
                fp += u in queued_any
                tn += u not in queued_any
        out[part] = dict(
            kullanici=len(users),
            degerlendirilebilir=dict(
                senaryo=len(ev),
                gecti=sum(r["gecti"] for r in ev),
                yakalama=_ratio(sum(r["gecti"] for r in ev), len(ev)),
                pencerede_kuyrukta=sum(r["pencerede_kuyrukta"] for r in ev),
            ),
            kismi_pencereli=dict(
                senaryo=len(pa),
                gecti=sum(r["gecti"] for r in pa),
                pencerede_kuyrukta=sum(r["pencerede_kuyrukta"] for r in pa),
            ),
            **at_k,
            confusion=dict(
                tp=tp,
                fn=fn,
                fp=fp,
                tn=tn,
                matris_disi_kismi_insider=len(partial_only & set(users)),
                precision=_ratio(tp, tp + fp),
                recall=_ratio(tp, tp + fn),
            ),
        )
    return out


# ---------------------------------------------------------------------------------------- lojistik regresyon (14.5)
def log_loss(p: np.ndarray, y: np.ndarray, eps: float = 1e-12) -> float:
    p = np.clip(np.asarray(p, dtype=float), eps, 1 - eps)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def f1_best(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """Olası tüm eşiklerde en iyi F1 ve eşiği (p ≥ eşik → pozitif). Eşik doğrulamada seçilir, testte sabit kullanılır."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=int)
    if len(p) == 0 or y.sum() == 0:
        return 0.0, 1.0
    idx = np.argsort(-p, kind="mergesort")
    ps, ys = p[idx], y[idx]
    tp, fp = np.cumsum(ys), np.cumsum(1 - ys)
    last = np.r_[ps[1:] != ps[:-1], True]
    tp, fp, th = tp[last], fp[last], ps[last]
    f1 = 2 * tp / (2 * tp + fp + (ys.sum() - tp))
    i = int(np.argmax(f1))
    return float(f1[i]), float(th[i])


def f1_at(p: np.ndarray, y: np.ndarray, threshold: float) -> float:
    pred, y = np.asarray(p) >= threshold, np.asarray(y, dtype=int)
    tp, fp, fn = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum())
    return 2 * tp / (2 * tp + fp + fn) if (tp + fp + fn) else 0.0


def _brief_cal(rep: dict) -> dict:
    return {k: rep.get(k) for k in ("n", "pozitif", "taban_orani", "auc", "brier", "brier_taban", "brier_beceri", "ece")}


def _select_and_test(
    X: np.ndarray,
    y: np.ndarray,
    heur: np.ndarray,
    tr: np.ndarray,
    va: np.ndarray,
    te: np.ndarray,
    c_grid: Sequence[float],
) -> dict:
    """C'yi doğrulama log-loss'uyla seçer (her C için F1 de), sonra testi seçilmiş model ve doğrulama eşiğiyle BİR kez ölçer.
    Doğrulamada pozitif yoksa seçim anlamsızdır (log-loss en düşük olasılığı ödüllendirir) — rapor bunu bayraklar."""
    out: dict = {}
    grid, best = [], None
    for c in c_grid:
        try:
            model = LogisticModel.fit(X[tr], y[tr], C=c)
        except ValueError as exc:
            grid.append(dict(C=c, hata=str(exc)))
            continue
        pv = model.predict_many(X[va])
        ll = log_loss(pv, y[va])
        f1, th = f1_best(pv, y[va])
        cal = calibration_report(pv, y[va])
        grid.append(
            dict(
                C=c,
                dogrulama_logloss=round(ll, 5),
                dogrulama_f1=round(f1, 3),
                f1_esigi=round(th, 4),
                dogrulama_auc=cal.get("auc"),
                dogrulama_brier=cal.get("brier"),
            )
        )
        if best is None or ll < best[0]:
            best = (ll, c, model, th)
    out["c_izgarasi"] = grid
    if best is None:
        out["neden"] = "hiçbir C değeri için model kurulamadı (eğitim parçasında yetersiz pozitif)"
        return out
    _, c_sel, model, th = best
    out["secilen_C"] = c_sel
    out["secim_olcutu"] = "doğrulama log-loss (en küçük)"
    if int(y[va].sum()) == 0:
        out["secim_gecersiz"] = "doğrulama parçasında pozitif yok — C seçimi ve F1 eşiği anlamsız"
    pt = model.predict_many(X[te])
    test = _brief_cal(calibration_report(pt, y[te]))
    test["f1_dogrulama_esiginde"] = round(f1_at(pt, y[te], th), 3)
    test["esik"] = round(th, 4)
    out["test"] = test
    out["test_sezgisel"] = _brief_cal(calibration_report(heur[te], y[te]))
    return out


def lr_protocol(
    rows: Sequence[dict],
    y: Sequence[int],
    split: dict,
    c_grid: Sequence[float] = DEFAULT_C_GRID,
    embargo_days: int = 7,
    holdout_frac: float = 0.3,
) -> dict:
    """Eğitim: eğitim parçasının kullanıcıları, kesimden (günlerin son `holdout_frac`'ı) ÖNCEKİ günler.
    Doğrulama/test: kendi kullanıcıları, kesim + `embargo_days` SONRASI (etiket ufku 7 gün: eğitim etiketlerinin baktığı
    günler değerlendirme dönemine taşmaz). C, doğrulama log-loss'uyla seçilir; F1 her C için raporlanır (en iyi eşikte).
    Test bir kez, seçilmiş modelle ve doğrulamada seçilen eşikle ölçülür. Kıyas için aynı koşuda eski protokol
    (tüm kullanıcılar, zamansal holdout, embargo yok, C=1) da hesaplanır."""
    assign = split["atama"]
    X = rows_to_matrix(rows)
    yv = np.asarray(y, dtype=int)
    dv = pd.to_datetime(pd.Series([r["gun"] for r in rows])).values
    days = np.unique(dv)
    n_hold = max(1, int(round(len(days) * holdout_frac)))
    cut = pd.Timestamp(days[-n_hold])
    emb = cut + embargo_days * DAY
    part = np.array([assign.get(r["sid"], "") for r in rows])
    masks = dict(
        egitim=(part == "egitim") & (dv < cut.to_datetime64()),
        dogrulama=(part == "dogrulama") & (dv >= emb.to_datetime64()),
        test=(part == "test") & (dv >= emb.to_datetime64()),
    )
    sids = np.array([r["sid"] for r in rows])
    report: dict = dict(
        bolme=dict(
            kesim=str(cut.date()),
            embargo_bitis=str(emb.date()),
            embargo_gun=embargo_days,
            **{k: dict(satir=int(m.sum()), pozitif=int(yv[m].sum()), kullanici=int(len(set(sids[m])))) for k, m in masks.items()},
        )
    )
    heur = np.array([r["p7_sezgisel"] for r in rows], dtype=float)
    report.update(_select_and_test(X, yv, heur, masks["egitim"], masks["dogrulama"], masks["test"], c_grid))
    # ---- tamamlayıcı (sonuç görülmeden sabitlendi): kullanıcı ayrık, TÜM günler. Etiketler kişiye özel olduğundan
    # ayrık kullanıcılar arasında etiket sızıntısı yoktur; embargo yalnız ortak zaman bağlamına (kurum geneli yüzdelik
    # havuzu, dönemsellik) karşıdır. Ana protokolde doğrulama/test pozitifleri tükenirse ölçülebilirlik için yan yana.
    all_masks = {k: part == k for k in PARTS}
    comp = dict(
        bolme={
            k: dict(satir=int(m.sum()), pozitif=int(yv[m].sum()), kullanici=int(len(set(sids[m])))) for k, m in all_masks.items()
        },
        **_select_and_test(X, yv, heur, all_masks["egitim"], all_masks["dogrulama"], all_masks["test"], c_grid),
    )
    report["tamamlayici_tum_gunler"] = comp
    # ---- aynı koşuda eski protokol: tüm kullanıcılar, zamansal holdout, embargo yok, C=1
    old_tr, old_ho = dv < cut.to_datetime64(), dv >= cut.to_datetime64()
    try:
        old = LogisticModel.fit(X[old_tr], yv[old_tr], C=1.0)
        report["eski_protokol_bu_kosu"] = _brief_cal(calibration_report(old.predict_many(X[old_ho]), yv[old_ho]))
    except ValueError as exc:
        report["eski_protokol_bu_kosu"] = dict(hata=str(exc))
    return report


# ------------------------------------------------------------------------------------------- eşik hassasiyeti (19.5)
UEBA_0003_CONDITION = "veri_hacmi_anomali_z > 3.5"


def with_ueba0003_z(catalog: List[dict], z: float) -> List[dict]:
    """UEBA-0003'ün tetikleme eşiğini değiştirir (şiddet eşiği sabit kalır: yalnız tetikleme ölçülür)."""
    cat = json.loads(json.dumps(catalog))
    rule = next(r for r in cat if r["id"] == "UEBA-0003")
    if rule["mantik"]["kosullar"] != [UEBA_0003_CONDITION]:
        raise ValueError(f"UEBA-0003 koşulu beklenenden farklı: {rule['mantik']['kosullar']}")
    rule["mantik"]["kosullar"] = [f"veri_hacmi_anomali_z > {float(z)!r}"]
    return cat


def variant_row(name: str, pm: Dict[str, dict]) -> dict:
    row: dict = dict(varyant=name)
    for part in ("tumu", "dogrulama", "test"):
        row[f"{part}_yakalama"] = pm[part]["degerlendirilebilir"]["yakalama"]
        row[f"{part}_p@1"] = pm[part]["precision@1"]
    return row


def run_threshold_variants(
    cfg: TenantConfig,
    data: Dataset,
    catalog: List[dict],
    out_dir: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    warmup_days: int,
    split: dict,
    variants: Dict[str, Tuple[float, float]],
    pipeline_factory: Optional[Callable] = None,
) -> List[dict]:
    """Her (z eşiği, akran nötr noktası) varyantını aynı yüklenmiş veriyle koşar. Boru hattı girdi olayları kopyalayıp
    çözümlediği için olaylar paylaşılır (13M satırı her varyantta kopyalamak RAM'i taşırırdı); dizin ve cevap anahtarı
    varyant başına kopyalanır."""
    from ztp.pipeline import ZeroTrustPredictionPipeline

    factory = pipeline_factory or ZeroTrustPredictionPipeline
    rows = []
    for name, (z, neutral) in variants.items():
        vcfg = replace(cfg, tenant_id=f"{cfg.tenant_id}__{name}", llm_backend="none", sinks=[], peer_neutral_ratio=neutral)
        vcat = with_ueba0003_z(catalog, z)
        vdata = Dataset(
            data.name,
            data.directory.copy(),
            data.ip_leases,
            data.events,
            data.leaves,
            json.loads(json.dumps(data.ground_truth)),
            list(data.critical_assets),
            honeytokens=dict(data.honeytokens),
        )
        LOG.info("Eşik varyantı %s: z=%s, akran nötr=%s", name, z, neutral)
        pipe = factory(vcfg, vdata, vcat, out_dir)
        pipe.run(start, end, warmup_days)
        row = variant_row(name, part_metrics(pipe.metrics, split))
        row.update(z_esigi=z, akran_notr=neutral)
        rows.append(row)
        del pipe, vdata
        gc.collect()
    return rows
