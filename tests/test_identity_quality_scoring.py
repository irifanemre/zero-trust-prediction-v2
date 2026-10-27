"""Kimlik eşleştirme (8.2), takma adlaştırma (20.1), veri kalitesi (8.3), risk skorlama ve alarm bütçesi (13.x)."""

import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.detection.engine import Hit
from ztp.feedback import LabelStore
from ztp.graph.knowledge import KnowledgeGraph
from ztp.identity import IdentityResolver, Pseudonymizer
from ztp.quality import DataQualityMonitor
from ztp.schema import EVENT_COLUMNS
from ztp.scoring import RiskScorer


def _directory():
    return pd.DataFrame(
        [
            dict(
                sid="S-1",
                ad_sam="KURUM\\ali.kaya",
                upn="ali.kaya@kurum.com",
                vpn_user="akaya",
                is_service=False,
                primary_device="HOST-1",
                display_name="Ali",
            ),
            dict(
                sid="S-2",
                ad_sam="KURUM\\svc_backup",
                upn="svc@kurum.com",
                vpn_user="svc",
                is_service=True,
                primary_device="SRV-1",
                display_name="svc",
            ),
        ]
    )


def _events(rows):
    df = pd.DataFrame(rows)
    for c in EVENT_COLUMNS:
        if c not in df:
            df[c] = None
    df["time"] = pd.to_datetime(df["time"])
    df["received_time"] = pd.to_datetime(df.get("received_time", df["time"]))
    return df[EVENT_COLUMNS]


def test_identity_resolution_by_source_and_time_ranged_ip():
    leases = pd.DataFrame([dict(ip="10.0.0.5", sid="S-1", start=pd.Timestamp("2026-01-01"), end=pd.Timestamp("2026-01-10"))])
    ev = _events(
        [
            dict(event_id="e1", time="2026-01-03 09:00", source="ad", actor_raw="kurum\\ALI.KAYA"),
            dict(event_id="e2", time="2026-01-03 09:05", source="proxy", actor_raw="10.0.0.5", src_ip="10.0.0.5"),
            dict(
                event_id="e3", time="2026-01-12 09:05", source="proxy", actor_raw="10.0.0.5", src_ip="10.0.0.5"
            ),  # kiralama süresi dışı
            dict(event_id="e4", time="2026-01-03 02:00", source="edr", actor_raw="S-2"),
        ]
    )
    res = IdentityResolver(_directory(), leases).resolve(ev)
    by = res.set_index("event_id")
    assert by.loc["e1", "canonical"] == "S-1"
    assert by.loc["e2", "canonical"] == "S-1"
    assert pd.isna(by.loc["e3", "canonical"])  # sessizce yanlış kişiye yazılmaz
    assert by.loc["e4", "is_service"]
    assert IdentityResolver(_directory(), leases).resolve(ev).pipe(lambda d: d["canonical"].isna().sum()) == 1


def test_pseudonymizer_is_stable_and_break_glass_requires_second_approver(tmp_path):
    ps = Pseudonymizer("gizli", tmp_path / "audit.jsonl")
    p = ps.pseudo("S-1")
    assert p.startswith("U-") and ps.pseudo("S-1") == p
    assert Pseudonymizer("gizli").pseudo("S-1") == p  # aynı anahtar → aynı takma ad
    assert Pseudonymizer("baska").pseudo("S-1") != p
    with pytest.raises(PermissionError):
        ps.break_glass(p, analyst="a1", approver="a1", reason="x")
    assert ps.break_glass(p, analyst="a1", approver="a2", reason="vaka") == "S-1"
    assert "break_glass" in (tmp_path / "audit.jsonl").read_text(encoding="utf-8")


def test_data_quality_suspends_single_source_drop_but_not_calendar_effect():
    rows = []
    for d in range(1, 30):
        day = pd.Timestamp("2026-01-01") + pd.Timedelta(days=d)
        n_ad, n_px = (60, 60)
        if day.dayofweek >= 5:  # hafta sonu: her iki kaynak birlikte düşer
            n_ad, n_px = 3, 3
        if day == pd.Timestamp("2026-01-27"):  # yalnızca proxy çöker
            n_px = 2
        for i in range(n_ad):
            rows.append(dict(event_id=f"a{d}-{i}", time=day + pd.Timedelta(hours=9), source="ad", actor_raw="x", canonical="S-1"))
        for i in range(n_px):
            rows.append(
                dict(event_id=f"p{d}-{i}", time=day + pd.Timedelta(hours=10), source="proxy", actor_raw="x", canonical="S-1")
            )
    ev = pd.DataFrame(rows)
    ev["received_time"] = ev["time"]
    dq = DataQualityMonitor.from_events(TenantConfig(), ev)
    assert dq.assess(pd.Timestamp("2026-01-27"))["proxy"]["durum"] == "askida"
    assert dq.assess(pd.Timestamp("2026-01-27"))["ad"]["durum"] == "ok"
    sat = dq.assess(pd.Timestamp("2026-01-24"))
    assert sat["proxy"]["durum"] == "ok" and sat["ad"]["durum"] == "ok"


def _hit(rule, day, w=5.0, sev=0.8, attack=("T1078",)):
    return Hit(rule, rule, "UEBA", day, sev, w, list(attack), [], {}, "yayinda")


def test_scoring_decay_multipliers_and_budget(tmp_path):
    cfg = TenantConfig(alarm_budget_per_day=2, kuyruk_dogrulama=False)  # bütçe mekanizması; kapı ayrı testte
    scorer = RiskScorer(cfg, KnowledgeGraph(), LabelStore(tmp_path / "labels.json"))
    day = pd.Timestamp("2026-02-10")
    assert scorer.decay(0) == 1.0 and scorer.decay(7) == pytest.approx(0.3)
    # farklı taktiklerden 2 tespit → ×2.5 (13.3 merkezi karar)
    scorer.add_hits("A", [_hit("R1", day, attack=("T1078",)), _hit("R2", day, attack=("T1567",))])
    a = scorer.compute("A", day, dict(hesap_yasi_gun=500))
    assert a.multipliers == {"farkli_taktik_2": 2.5}
    assert a.raw == pytest.approx(2 * 5.0 * 0.8 * 2.5)
    # 8 gün önceki tespit pencere dışında kalır
    scorer.add_hits("B", [_hit("R1", day - pd.Timedelta(days=8))])
    assert scorer.compute("B", day, {}).raw == 0.0
    scorer.add_hits("C", [_hit("R1", day, w=1.0, sev=0.5)])
    scorer.add_hits("D", [_hit("R1", day, w=2.0, sev=0.5)])
    results = {s: scorer.compute(s, day, {}) for s in "ABCD"}
    scorer.calibrate(day, results)
    assert results["A"].percentile > results["D"].percentile > results["C"].percentile
    queue = scorer.select_queue(day, results)
    assert queue == ["A", "D"]  # bütçe 2: en riskli iki varlık-gün
    # açık vaka: ertesi gün yeni kanıt yoksa yeniden sunulmaz
    results2 = {s: scorer.compute(s, day + pd.Timedelta(days=1), {}) for s in "ABCD"}
    scorer.calibrate(day + pd.Timedelta(days=1), results2)
    assert "A" not in scorer.select_queue(day + pd.Timedelta(days=1), results2)


def test_corroboration_gate_sends_single_weak_signal_to_watch_list(tmp_path):
    scorer = RiskScorer(TenantConfig(alarm_budget_per_day=10), KnowledgeGraph(), LabelStore(tmp_path / "labels.json"))
    day = pd.Timestamp("2026-02-10")
    scorer.add_hits("TEK", [_hit("R1", day)])  # tek kural, tek gün → izleme listesi
    scorer.add_hits("IKI_KURAL", [_hit("R1", day), _hit("R2", day)])
    scorer.add_hits("TEKRAR", [_hit("R1", day - pd.Timedelta(days=d)) for d in (0, 2, 4)])  # aynı sinyal 3 farklı gün
    scorer.add_hits("IKI_GUN", [_hit("R1", day - pd.Timedelta(days=d)) for d in (0, 2)])  # 2 gün yetmez
    results = {s: scorer.compute(s, day, {}) for s in ("TEK", "IKI_KURAL", "TEKRAR", "IKI_GUN")}
    scorer.calibrate(day, results)
    assert set(scorer.select_queue(day, results)) == {"IKI_KURAL", "TEKRAR"}  # bütçe boş kalsa da doldurulmaz
    assert set(scorer.watch_by_day[day]) == {"TEK", "IKI_GUN"}
    # tek ama kurumun en uç skoru: kaçış yüzdeliğini aşınca kapıdan geçer
    results["TEK"].percentile = 0.9985
    assert "TEK" in scorer.select_queue(day + pd.Timedelta(days=1), {"TEK": results["TEK"]})


def test_previously_labeled_false_positive_pattern_dampens_score(tmp_path):
    store = LabelStore(tmp_path / "labels.json")
    case = dict(case_id="C-1", gun="2026-02-01", kullanici="U-1", _sid="A", tespitler=[dict(kural="R1")])
    store.add(case, "yanlis_pozitif", "analist", reason="bilinen_istisna")
    with pytest.raises(ValueError):
        store.add(case, "yanlis_pozitif", "analist")  # sebep zorunlu (17.3)
    scorer = RiskScorer(TenantConfig(), KnowledgeGraph(), store)
    day = pd.Timestamp("2026-02-10")
    scorer.add_hits("A", [_hit("R1", day)])
    assert scorer.compute("A", day, {}).multipliers == {"daha_once_normal": 0.2}
    assert store.metrics()["yanlis_pozitif"] == 1
