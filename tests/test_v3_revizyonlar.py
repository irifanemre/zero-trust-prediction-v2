"""v3 revizyonları (r5.2 derslerinden): çok ufuklu biriktirici, kanıt çeşitliliği, varlık katmanlandırma,
öncelik sıralayıcı. Hepsinin ortak sözleşmesi: **varsayılan ayarlarla davranış birebir eskisi gibidir**;
bileşen ancak yapılandırmayla açılır ve ablasyonla ölçülür (14.5)."""

import pandas as pd
import pytest

from ztp.config import TenantConfig
from ztp.detection.engine import Hit
from ztp.feedback import LabelStore
from ztp.graph.knowledge import KnowledgeGraph
from ztp.scoring import RiskScorer

DAY0 = pd.Timestamp("2026-02-10")


def _hit(rule, day=DAY0, w=5.0, sev=0.8, attack=("T1078",), kaynaklar=("ad",)):
    return Hit(rule, rule, "UEBA", day, sev, w, list(attack), [], {}, "yayinda", "", "RB", False, list(kaynaklar))


def _scorer(tmp_path, **cfg):
    return RiskScorer(TenantConfig(**cfg), KnowledgeGraph(), LabelStore(tmp_path / "l.json"))


# ---------------------------------------------------------------- #1 çok ufuklu biriktirici
def test_accumulator_windows_validated():
    assert TenantConfig().accumulator_windows == (1, 3, 7, 14, 30)
    assert TenantConfig(accumulator_windows=[7, 3, 3]).accumulator_windows == (3, 7)  # tekilleşir ve sıralanır
    with pytest.raises(ValueError):
        TenantConfig(accumulator_windows=[0])
    with pytest.raises(ValueError):
        TenantConfig(accumulator_windows=[365])  # uzun pencereyi aşamaz


# ---------------------------------------------------------------- #3 kanıt çeşitliliği
def test_source_diversity_multiplier_off_by_default(tmp_path):
    hits = [
        _hit("R1", kaynaklar=("ad",)),
        _hit("R2", kaynaklar=("dlp",)),
        _hit("R3", kaynaklar=("proxy",)),
    ]
    off = _scorer(tmp_path)
    off.add_hits("A", hits)
    assert "kaynak_cesitliligi" not in off.compute("A", DAY0, {}).multipliers  # varsayılan: kapalı

    on = _scorer(tmp_path, source_diversity_multiplier=1.5)
    on.add_hits("A", hits)
    assert on.compute("A", DAY0, {}).multipliers["kaynak_cesitliligi"] == 1.5


def test_source_diversity_needs_distinct_sources(tmp_path):
    """Beş USB alarmı (tek kaynak) çeşitlilik sayılmaz; iç kaynaklar (risk serisi/graf) saymaz."""
    s = _scorer(tmp_path, source_diversity_multiplier=1.5)
    s.add_hits("A", [_hit(f"R{i}", kaynaklar=("dlp",)) for i in range(5)])
    assert "kaynak_cesitliligi" not in s.compute("A", DAY0, {}).multipliers
    s2 = _scorer(tmp_path, source_diversity_multiplier=1.5)
    s2.add_hits("B", [_hit("R1", kaynaklar=("ad",)), _hit("R2", kaynaklar=("dlp",)), _hit("R3", kaynaklar=("_internal",))])
    assert "kaynak_cesitliligi" not in s2.compute("B", DAY0, {}).multipliers


# ---------------------------------------------------------------- #4 varlık katmanlandırma
def test_asset_tier_multiplier(tmp_path):
    for katman, anahtar, beklenen in ((2, "tier0_varlik", 2.0), (1, "tier1_varlik", 1.5), (0, None, None)):
        s = _scorer(tmp_path, tier0_multiplier=2.0, tier1_multiplier=1.5)
        s.add_hits("A", [_hit("R1")])
        mult = s.compute("A", DAY0, dict(varlik_katmani=katman)).multipliers
        assert (mult.get(anahtar) == beklenen) if anahtar else not {"tier0_varlik", "tier1_varlik"} & set(mult)
    kapali = _scorer(tmp_path)  # varsayılan: çarpan 0 → hiç eklenmez
    kapali.add_hits("A", [_hit("R1")])
    assert not {"tier0_varlik", "tier1_varlik"} & set(kapali.compute("A", DAY0, dict(varlik_katmani=2)).multipliers)


def test_asset_tiers_config_validation():
    assert TenantConfig(asset_tiers={"tier0": [r"\\DC-01\*"]}).asset_tiers["tier0"]
    with pytest.raises(ValueError):
        TenantConfig(asset_tiers={"tier9": ["x"]})


# ---------------------------------------------------------------- #2 öncelik sıralayıcı
def test_priority_equals_raw_when_weights_zero(tmp_path):
    s = _scorer(tmp_path)
    s.add_hits("A", [_hit("R1")])
    r = s.compute("A", DAY0, {})
    assert s.priority(r, {}) == r.raw  # kapalıyken sıra bugünküyle birebir aynı


def test_priority_reorders_without_changing_detection(tmp_path):
    """Tespit skoru (ham) korunur; yalnız SIRA değişir — r5.2'de kaçırılanlar tespit edilmişti ama sırada geride kaldı."""
    cfg = dict(priority_peer_weight=1.0, alarm_budget_per_day=1)
    s = _scorer(tmp_path, **cfg)
    # v2 doğrulama kapısından geçmek için ikisinde de 2 farklı kural var (tek sinyal kuyruğa girmez)
    s.add_hits("ZAYIF_AMA_SAPKIN", [_hit("R1", w=2.5), _hit("R2", w=2.5)])
    s.add_hits("GUCLU", [_hit("R3", w=3.0), _hit("R4", w=3.0)])
    signals = {"ZAYIF_AMA_SAPKIN": dict(akran_yapisal_mesafe=10.0), "GUCLU": dict(akran_yapisal_mesafe=0.0)}
    res = {sid: s.compute(sid, DAY0, signals[sid]) for sid in signals}
    for _ in range(50):
        s.pool.append((DAY0, 0.0))
    s.calibrate(DAY0, res)
    assert res["GUCLU"].raw > res["ZAYIF_AMA_SAPKIN"].raw  # ham skor: güçlü olan önde
    assert s.priority(res["ZAYIF_AMA_SAPKIN"], signals) > s.priority(res["GUCLU"], signals)  # öncelik: sapkın önde
    assert s.select_queue(DAY0, res, signals) == ["ZAYIF_AMA_SAPKIN"]  # bütçe 1 → sıralayıcı belirliyor
