"""19.2 yansız ölçüm: kullanıcı bazlı bölme, parça bazlı metrikler, 26/27 uzlaştırması, LR protokolü, eşik varyantı."""

import json

import numpy as np
import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.detection.catalog import load_catalog
from ztp.detection.engine import peer_severity_factor
from ztp.evaluation import (
    PARTS,
    allocate,
    count_reconciliation,
    insider_strata,
    load_or_create_split,
    lr_protocol,
    make_user_split,
    part_metrics,
    with_ueba0003_z,
)
from ztp.metrics import MetricsCollector
from ztp.prediction_model import PREDICTION_FEATURES

D = pd.Timestamp


def _gt(sid, scen, start, end, beklenen=("UEBA-0003",)):
    return dict(
        senaryo=f"CERT-r4.2-S{scen}-{sid}",
        aktor="?",
        sid=sid,
        baslangic_tarihi=start,
        olay_tarihi=end,
        pencere=[start, end],
        teknikler=[],
        beklenen=list(beklenen),
        veri_kaynagi=["proxy"],
    )


def _population(n_benign=200):
    gt = [_gt(f"I{i:02d}", 1 + i % 3, "2010-10-01", "2010-10-10") for i in range(20)]
    users = [f"U{i:03d}" for i in range(n_benign)] + [g["sid"] for g in gt]
    return users, gt


# --------------------------------------------------------------------------------------------------- bölme
def test_allocate_preserves_total_and_rounds_by_largest_remainder():
    for n in (0, 1, 3, 7, 34, 999, 1000):
        assert sum(allocate(n, (0.7, 0.15, 0.15))) == n
    assert allocate(34, (0.7, 0.15, 0.15)) == [24, 5, 5]
    assert allocate(3, (0.7, 0.15, 0.15)) == [2, 1, 0]  # 3 kişilik katman 15%'e bölünemez; eşitlikte sıra korunur


def test_split_is_deterministic_complete_and_stratified():
    users, gt = _population()
    a, b = make_user_split(users, gt, seed=7), make_user_split(list(reversed(users)), gt, seed=7)
    assert a == b  # girdi sırası sonucu değiştirmez (sıralı nüfus + tohum)
    assert make_user_split(users, gt, seed=8)["atama"] != a["atama"]
    assert sorted(a["atama"]) == sorted(set(users)) and set(a["atama"].values()) == set(PARTS)
    strata = insider_strata(gt)
    oz = a["meta"]["ozet"]
    assert [oz[p]["insider"] for p in PARTS] == allocate(20, (0.7, 0.15, 0.15))  # insider toplamı kesin orantılı
    for scen in ("S1", "S2", "S3"):
        members = [u for u, s in strata.items() if s == scen]
        for p, f in zip(PARTS, (0.7, 0.15, 0.15)):
            got = sum(1 for u in members if a["atama"][u] == p)
            assert int(len(members) * f) <= got <= int(len(members) * f) + 1  # her tür oranına en yakın tam sayıda
    assert sum(oz[p]["kullanici"] for p in PARTS) == 220


def _stratified_gt(sizes):
    return [_gt(f"{s}{i:02d}", s[1:], "2010-10-01", "2010-10-10") for s, n in sizes.items() for i in range(n)]


def test_small_strata_do_not_all_fall_into_training():
    """Tek kişilik katmanları bağımsız yuvarlamak hepsini eğitime atar (doğrulama/test insider'sız kalır)."""
    gt = _stratified_gt({f"S{i}": 1 for i in range(1, 9)})  # sentetik senaryolar: her türden bir insider
    split = make_user_split([f"U{i:03d}" for i in range(142)], gt, seed=42)
    assert [split["meta"]["ozet"][p]["insider"] for p in PARTS] == [6, 1, 1]


def test_cert_like_strata_keep_exact_insider_quota():
    """CERT r4.2 dağılımı (S1 14, S2 17, S3 3): katman katman yuvarlama 24/6/4 verirdi; kontrollü yuvarlama 24/5/5."""
    gt = _stratified_gt({"S1": 14, "S2": 17, "S3": 3})
    for seed in (1, 42, 2024):
        oz = make_user_split([f"U{i:03d}" for i in range(966)], gt, seed=seed)["meta"]["ozet"]
        assert [oz[p]["insider"] for p in PARTS] == [24, 5, 5]
        assert [oz[p]["kullanici"] for p in PARTS] == [700, 150, 150]
        assert oz["egitim"]["katmanlar"]["S1"] == 10 and oz["egitim"]["katmanlar"]["S2"] == 12


def test_split_file_roundtrip_and_fingerprint_guard(tmp_path):
    users, gt = _population()
    path = tmp_path / "bolme.json"
    first, created = load_or_create_split(path, users, gt, seed=42)
    again, created2 = load_or_create_split(path, users, gt, seed=999)  # dosya varken tohum yok sayılır: dosya esastır
    assert created and not created2 and again == first
    assert json.loads(path.read_text(encoding="utf-8"))["meta"]["tohum"] == 42
    with pytest.raises(ValueError, match="uyuşmuyor"):
        load_or_create_split(path, users + ["YENI"], gt)  # nüfus değişti → sessizce yeni bölme yok


# ---------------------------------------------------------------------------------------- parça metrikleri
def _metrics_fixture():
    gt = [
        _gt("A", 1, "2010-10-05", "2010-10-12"),  # beklenen kuralla kuyrukta → GEÇTİ
        _gt("B", 2, "2010-10-05", "2010-10-12"),  # kuyrukta ama beklenmeyen kuralla → REVİZYON ('27'de var, '26'da yok)
        _gt("C", 1, "2010-10-05", "2010-10-12"),  # hiç kuyruğa girmedi → KALDI
        _gt("P", 2, "2010-08-01", "2010-10-03"),  # başlangıcı dönem dışında → kısmi pencere
    ]
    m = MetricsCollector(TenantConfig(), gt, [])
    m.eval_range = (D("2010-10-01"), D("2010-10-31"))
    m.alerts_by_sid.update(
        A=[(D("2010-10-08"), {"UEBA-0003"})],
        B=[(D("2010-10-09"), {"UEBA-0001"})],
        P=[(D("2010-10-02"), {"UEBA-0003"})],
        X=[(D("2010-10-08"), {"UEBA-0002"})],  # insider olmayan → yanlış pozitif
    )
    m.queue_by_day = {D("2010-10-08"): ["X", "A"], D("2010-10-09"): ["B"], D("2010-10-02"): ["P"]}
    split = dict(atama=dict(A="egitim", B="egitim", C="test", P="egitim", X="egitim", Y="test"))
    return m, split


def test_part_metrics_separates_partial_and_builds_user_confusion():
    m, split = _metrics_fixture()
    pm = part_metrics(m, split)
    tr, te = pm["egitim"], pm["test"]
    assert tr["degerlendirilebilir"] == dict(senaryo=2, gecti=1, yakalama=0.5, pencerede_kuyrukta=2)
    assert tr["kismi_pencereli"] == dict(senaryo=1, gecti=1, pencerede_kuyrukta=1)
    # A ve B kendi pencerelerinde kuyrukta (TP), X yanlış pozitif, P kısmi → matris dışı
    assert tr["confusion"] == dict(tp=2, fn=0, fp=1, tn=0, matris_disi_kismi_insider=1, precision=0.667, recall=1.0)
    assert te["confusion"]["fn"] == 1 and te["confusion"]["tn"] == 1  # C kaçırıldı, Y hiç kuyruğa girmedi
    # precision@1 eğitim parçasında: 10-08 → X (yanlış), 10-09 → B (doğru), 10-02 → P (doğru)
    assert tr["precision@1"] == 0.667 and te["precision@1"] is None
    assert pm["tumu"]["degerlendirilebilir"]["senaryo"] == 3


def test_count_reconciliation_names_the_insider_between_26_and_27():
    m, _ = _metrics_fixture()
    rec = count_reconciliation(m)
    assert rec["coverage_gecti"] == 2 and rec["kullanici_bazinda_pencerede_kuyrukta"] == 3  # A, P geçti; A, B, P kuyrukta
    assert [r["sid"] for r in rec["yalnizca_kuyrukta"]] == ["B"] and rec["yalnizca_gecti"] == []
    assert rec["yalnizca_kuyrukta"][0]["sonuc"].startswith("REVİZYON")


# ------------------------------------------------------------------------------------------------ LR protokolü
def _lr_rows(seed=0):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2010-09-01", periods=60, freq="D")
    users = [f"U{i:03d}" for i in range(90)]
    split = dict(atama={u: PARTS[0] if i < 60 else PARTS[1] if i < 75 else PARTS[2] for i, u in enumerate(users)})
    rows, y = [], []
    for u in users:
        risky = rng.random() < 0.15
        for d in days:
            pos = risky and rng.random() < 0.4
            f = {k: float(rng.normal()) for k in PREDICTION_FEATURES}
            f["veri_hacmi_z"] += 2.5 * pos
            rows.append(dict(gun=str(d.date()), sid=u, ozellikler=f, p7=0.0, p7_sezgisel=float(rng.random() * 0.1)))
            y.append(int(pos))
    return rows, np.array(y), split


def test_lr_protocol_trains_on_train_users_before_cut_and_embargoes():
    rows, y, split = _lr_rows()
    rep = lr_protocol(rows, y, split, c_grid=(0.01, 1.0), embargo_days=7, holdout_frac=0.3)
    b = rep["bolme"]
    cut, emb = D(b["kesim"]), D(b["embargo_bitis"])
    assert emb - cut == pd.Timedelta(days=7)
    days = {r["gun"] for r in rows}
    assert b["egitim"]["kullanici"] == 60 and b["dogrulama"]["kullanici"] == 15 and b["test"]["kullanici"] == 15
    n_before = sum(1 for d in days if D(d) < cut)
    n_after = sum(1 for d in days if D(d) >= emb)
    assert b["egitim"]["satir"] == 60 * n_before and b["test"]["satir"] == 15 * n_after
    assert rep["secilen_C"] in (0.01, 1.0) and rep["test"]["auc"] is not None
    assert all("dogrulama_f1" in g for g in rep["c_izgarasi"])  # her C için F1 raporlanır
    assert "eski_protokol_bu_kosu" in rep


def test_lr_protocol_selection_never_sees_test_labels():
    rows, y, split = _lr_rows(seed=3)
    test_idx = np.array([split["atama"][r["sid"]] == "test" for r in rows])
    flipped = y.copy()
    flipped[test_idx] = 1 - flipped[test_idx]  # test etiketleri ters çevrilse bile seçim aynı kalmalı
    a = lr_protocol(rows, y, split, c_grid=(0.001, 0.1, 10.0))
    b = lr_protocol(rows, flipped, split, c_grid=(0.001, 0.1, 10.0))
    assert a["secilen_C"] == b["secilen_C"] and a["c_izgarasi"] == b["c_izgarasi"]
    assert a["test"]["auc"] != b["test"]["auc"]  # test yalnızca sonda ölçülür ve etiketleri yalnız orada kullanılır


def test_lr_protocol_flags_selection_without_validation_positives_and_reports_companion():
    rows, y, split = _lr_rows(seed=5)
    val = np.array([split["atama"][r["sid"]] == "dogrulama" for r in rows])
    y = y.copy()
    y[val] = 0  # doğrulamada hiç pozitif yok → log-loss en düşük olasılığı ödüllendirir; seçim geçersiz sayılmalı
    rep = lr_protocol(rows, y, split, c_grid=(0.01, 1.0))
    assert "secim_gecersiz" in rep
    comp = rep["tamamlayici_tum_gunler"]
    assert comp["bolme"]["egitim"]["kullanici"] == 60 and comp["bolme"]["test"]["satir"] > rep["bolme"]["test"]["satir"]
    assert "test" in comp and "secilen_C" in comp


# -------------------------------------------------------------------------------------------- eşik varyantları
def test_threshold_variant_changes_only_ueba0003_trigger():
    cat = load_catalog()
    v = with_ueba0003_z(cat, 4.0)
    rule = next(r for r in v if r["id"] == "UEBA-0003")
    assert rule["mantik"]["kosullar"] == ["veri_hacmi_anomali_z > 4.0"] and rule["siddet"]["esik"] == 3.5
    assert [r for r in v if r["id"] != "UEBA-0003"] == [r for r in cat if r["id"] != "UEBA-0003"]
    assert next(r for r in cat if r["id"] == "UEBA-0003")["mantik"]["kosullar"] == ["veri_hacmi_anomali_z > 3.5"]
    with pytest.raises(ValueError):
        with_ueba0003_z(v, 3.0)  # beklenmeyen koşul üzerine sessizce yazılmaz


def test_peer_neutral_ratio_is_configurable_and_validated():
    assert peer_severity_factor(4.0, neutral=4.0) == pytest.approx(1.0)
    assert peer_severity_factor(4.5, neutral=6.0) < peer_severity_factor(4.5, neutral=4.0)
    assert TenantConfig().peer_neutral_ratio == 5.0
    with pytest.raises(ValueError):
        TenantConfig(peer_neutral_ratio=1.0)
