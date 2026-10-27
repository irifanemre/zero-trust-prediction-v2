"""Aldatma katmanı (honeytoken): yapılandırma doğrulama, eşleştirme, tuzak hesap atfı, özellik/sinyal, kritik istisna, uçtan uca."""

import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.data.synthetic import HONEYTOKENS_DEFAULT, SyntheticOrg
from ztp.deception import KIND_ACCOUNT, TOKEN_COLUMN, HoneytokenRegistry
from ztp.detection.catalog import load_catalog, validate_rule
from ztp.detection.engine import Hit
from ztp.features import extract_features
from ztp.feedback import LabelStore
from ztp.graph.knowledge import KnowledgeGraph
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.schema import EVENT_COLUMNS, OCSF_AUTH, OCSF_FILE
from ztp.scoring import RiskScorer
from ztp.state import hits_from_records, hits_to_records

T0 = pd.Timestamp("2026-03-02 09:00")


def _ev(i, source, actor, cls=OCSF_AUTH, device=None, resource=None, src_ip=None, canonical=None, is_service=False, hour=0):
    row = dict.fromkeys(EVENT_COLUMNS)
    row.update(
        event_id=f"E-{i:04d}",
        time=T0 + pd.Timedelta(hours=hour),
        received_time=T0 + pd.Timedelta(hours=hour, minutes=1),
        class_uid=cls,
        source=source,
        actor_raw=actor,
        device=device,
        resource=resource,
        src_ip=src_ip,
        action="logon" if cls == OCSF_AUTH else "read",
        outcome="success",
        bytes_out=0,
    )
    row["canonical"], row["is_service"] = canonical, is_service
    return row


REG = HoneytokenRegistry.from_config(dict(hesaplar=["SVC-Decoy"], kaynaklar=[r"\\FS\finans\bonus_*"], cihazlar=["honey-srv-01"]))


def _vals(series):
    """Eksik değer pandas sürümüne göre None ya da NaN olabilir (3.0'da str dtype); karşılaştırma için None'a indirgenir."""
    return [v if isinstance(v, str) else None for v in series]


def test_registry_config_validation():
    assert not HoneytokenRegistry.from_config(None) and not HoneytokenRegistry.empty()
    assert REG and len(REG) == 3 and "svc-decoy" in REG.accounts and "honey-srv-01" in REG.devices
    with pytest.raises(ValueError):
        HoneytokenRegistry.from_config({"hesap": ["x"]})  # bilinmeyen alan
    with pytest.raises(ValueError):
        HoneytokenRegistry.from_config({"hesaplar": ["ok", 3]})  # metin olmayan
    with pytest.raises(ValueError):
        TenantConfig(honeytokens={"kaynaklar": "tek-metin"})  # yapılandırma şema hatası açık hata verir
    assert TenantConfig(honeytokens={"hesaplar": ["a"]}).honeytoken_registry.accounts == frozenset({"a"})


def test_tag_matches_case_insensitively_with_glob_and_priority():
    ev = pd.DataFrame(
        [
            _ev(1, "ad", "svc-decoy", device="HOST-1"),  # tuzak hesap
            _ev(
                2, "file_server", "ali", cls=OCSF_FILE, device="HOST-2", resource=r"\\FS\Finans\BONUS_2026.xlsx"
            ),  # glob, büyük/küçük
            _ev(3, "ad", "veli", device="HONEY-SRV-01"),  # tuzak cihaz
            _ev(4, "ad", "SVC-DECOY", device="HONEY-SRV-01"),  # ikisi de: hesap önceliklidir
            _ev(5, "file_server", "ayse", cls=OCSF_FILE, device="HOST-3", resource=r"\\FS\finans\raporlar"),  # eşleşmez
            _ev(6, "ad", "can"),  # cihaz/kaynak yok
        ]
    )
    tag = REG.tag(ev)
    assert _vals(tag) == [
        "hesap:svc-decoy",
        r"kaynak:\\FS\Finans\BONUS_2026.xlsx",
        "cihaz:HONEY-SRV-01",
        "hesap:SVC-DECOY",
        None,
        None,
    ]
    assert HoneytokenRegistry.empty().tag(ev).isna().all()


def test_apply_attributes_decoy_account_use_to_source_not_to_decoy():
    leases = pd.DataFrame([dict(ip="10.0.0.9", sid="U-LEASE", start=T0 - pd.Timedelta(days=1), end=T0 + pd.Timedelta(days=1))])
    ev = pd.DataFrame(
        [
            _ev(1, "ad", "svc-decoy", device="HOST-OWNED", canonical=None),  # cihaz sahibine
            _ev(2, "ad", "svc-decoy", device="LAB-PC", src_ip="10.0.0.9", canonical=None),  # kiralamaya
            _ev(3, "ad", "svc-decoy", device="LAB-PC", src_ip="10.9.9.9", canonical="U-DECOY"),  # tuzağın kendi kimliği kalır
            _ev(4, "ad", "svc-decoy", device=None, src_ip=None, canonical=None),  # atfedilemez → kuyruk
            _ev(
                5, "file_server", "svc-backup", cls=OCSF_FILE, resource=r"\\FS\finans\bonus_1", canonical="U-SVC", is_service=True
            ),
            _ev(6, "file_server", "ali", cls=OCSF_FILE, resource=r"\\FS\finans\bonus_1", canonical="U-ALI"),  # normal etiketli
        ]
    )
    out, lost = REG.apply(ev, {"HOST-OWNED": "U-OWNER"}, leases, {"U-SVC"})
    assert _vals(out["canonical"]) == ["U-OWNER", "U-LEASE", "U-DECOY", None, "U-SVC", "U-ALI"]
    assert out[TOKEN_COLUMN].notna().sum() == 6 and out.loc[0, TOKEN_COLUMN].startswith(KIND_ACCOUNT + ":")
    assert list(lost["event_id"]) == ["E-0004", "E-0005"] and list(lost["neden"]) == ["kimlik çözümlenemedi", "servis hesabı"]
    # tuzak yoksa hiçbir şey değişmez
    same, none = HoneytokenRegistry.empty().apply(ev, {}, leases, set())
    assert same[TOKEN_COLUMN].isna().all() and none.empty and _vals(same["canonical"]) == _vals(ev["canonical"])


def test_features_count_honeytokens_outside_baseline_with_split_evidence():
    ev = pd.DataFrame(
        [
            _ev(1, "ad", "ali", device="HOST-1", canonical="U-1", hour=0),
            _ev(
                2, "file_server", "ali", cls=OCSF_FILE, device="HOST-1", resource=r"\\FS\finans\bonus_x", canonical="U-1", hour=1
            ),
            _ev(3, "ad", "ali", device="HONEY-SRV-01", canonical="U-1", hour=2),
            _ev(4, "ad", "veli", device="HOST-2", canonical="U-2", hour=0),
        ]
    )
    ev[TOKEN_COLUMN] = REG.tag(ev)
    f = extract_features(ev, []).set_index("sid")
    assert f.loc["U-1", "honeytoken_count"] == 2 and f.loc["U-2", "honeytoken_count"] == 0
    assert f.loc["U-1", "honeytokens"] == frozenset({r"kaynak:\\FS\finans\bonus_x", "cihaz:HONEY-SRV-01"})
    assert f.loc["U-1", "evidence"]["honeytoken_kaynak"] == ["E-0002"] and f.loc["U-1", "evidence"]["honeytoken_cihaz"] == [
        "E-0003"
    ]
    assert "honeytoken_count" not in __import__("ztp.features", fromlist=["NUM_FEATURES"]).NUM_FEATURES  # baseline'a girmez
    # etiket kolonu olmayan olaylar (eski durum / dosya girişi) da çalışır
    g = extract_features(ev.drop(columns=[TOKEN_COLUMN]), []).set_index("sid")
    assert (g["honeytoken_count"] == 0).all() and all(v == frozenset() for v in g["honeytokens"])


def test_catalog_has_three_critical_honey_rules_and_rejects_bad_flag():
    cat = {r["id"]: r for r in load_catalog()}
    for rid, sig in (
        ("HONEY-0018", "tuzak_hesap_sayisi"),
        ("HONEY-0019", "tuzak_kaynak_sayisi"),
        ("HONEY-0020", "tuzak_cihaz_sayisi"),
    ):
        r = cat[rid]
        assert r["kritik"] is True and r["katman"] == "aldatma" and r["durum"] == "yayinda" and r["bastirma"] == []
        assert r["mantik"]["kosullar"] == [f"{sig} >= 1"] and r["veri_kaynaklari"] == ["tuzak"]
    bad = dict(cat["HONEY-0018"], kritik="evet")
    assert any("kritik" in e for e in validate_rule(bad))


def _hit(rule, day, w, kritik=False):
    return Hit(rule, rule, "aldatma", day, 0.99, w, ["T1078"], ["E-1"], {}, "yayinda", "", "RB", kritik)


def test_critical_hit_bypasses_budget_and_survives_state_roundtrip(tmp_path):
    day = pd.Timestamp("2026-02-10")
    scorer = RiskScorer(TenantConfig(alarm_budget_per_day=1), KnowledgeGraph(), LabelStore(tmp_path / "l.json"))
    # bütçeyi tek başına dolduran yüksek skor (iki kural: doğrulama kapısından geçer, test yalnız bütçe istisnasını sınar)
    scorer.add_hits("BIG", [_hit("UEBA-0003", day, 40.0), _hit("UEBA-0017", day, 40.0)])
    scorer.add_hits("HONEY", [_hit("HONEY-0018", day, 20.0, kritik=True)])
    for _ in range(50):  # yüzdelik havuzu: kritik yüzdelik eşiğine ulaşılmasın diye sıfırlar
        scorer.pool.append((day, 0.0))
    res = {s: scorer.compute(s, day, {}) for s in ("BIG", "HONEY")}
    scorer.calibrate(day, res)
    assert res["HONEY"].critical and res["HONEY"].raw < res["BIG"].raw
    assert scorer.select_queue(day, res) == ["HONEY", "BIG"]  # kritik önce, bütçe (1) aşılır
    back = hits_from_records(hits_to_records(scorer.hit_log), Hit)
    assert back["HONEY"][0].kritik is True and back["BIG"][0].kritik is False


@pytest.mark.slow
def test_pipeline_end_to_end_honeytoken_case(tmp_path):
    end = pd.Timestamp("2026-09-16")
    cfg = TenantConfig(tenant_id="honey", alarm_budget_per_day=1, threshold_jitter=0.0)
    data = SyntheticOrg(
        n_users=60, n_days=cfg.long_window_days + 6 + 14, eval_days=14, end_day=end, seed=3, honeytokens=True
    ).build()
    assert data.honeytokens == HONEYTOKENS_DEFAULT
    gt = next(g for g in data.ground_truth if g["senaryo"] == "S10_tuzak_etkilesimi")
    pipe = ZeroTrustPredictionPipeline(cfg, data, load_catalog(), tmp_path)
    pipe.run(end - pd.Timedelta(days=13), end, 6)
    mine = [c for c in pipe.cases if c["_sid"] == gt["sid"]]
    rules = {h["kural"] for c in mine for h in c["tespitler"]}
    assert {"HONEY-0018", "HONEY-0019", "HONEY-0020"} <= rules
    # tuzak etkileşiminin OLDUĞU günlerdeki vakalar kritiktir (sonraki günlerde pencere içi tespit kritik saymaz)
    honey_days = [c for c in mine if any(h["kural"].startswith("HONEY") and h["gun"] == c["gun"] for h in c["tespitler"])]
    assert len(honey_days) >= 2 and all(c["kritik"] for c in honey_days)
    first = min(honey_days, key=lambda c: c["gun"])
    assert first["gun"] == gt["baslangic_tarihi"]  # bütçe 1 iken bile ilk etkileşim günü kuyrukta (kritik istisna)
    assert any("TUZAK ETKİLEŞİMİ" in line for line in first["rapor"].splitlines())
    honey_hits = [h for h in first["tespitler"] if h["kural"].startswith("HONEY")]
    assert all(h["kanit"] and h["runbook"].startswith("RB-HONEY") for h in honey_hits)
    assert (tmp_path / "honey" / "honeytoken_unattributed.csv").exists() and pipe.honeytoken_unattributed.empty
