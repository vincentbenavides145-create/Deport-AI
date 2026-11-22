"""Política de publicación: mínimo 75 %, calibración por lado y categorías suspendidas."""

import pytest

import deport_ai.statistical_markets as sm
from deport_ai.dynamic_calibration import (
    DynamicCalibrationSummary,
    DynamicCalibrator,
    factor_for,
    selection_side,
    side_key,
)
from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team
from deport_ai.storage import DatabaseManager


def _candidate(cid, category, selection, probability, side=None, group=None):
    return {"id": cid, "category": category, "market": category, "selection": selection,
            "probability": probability, "side": side, "group": group or cid, "explanation": "Porque sí."}


@pytest.fixture
def run(monkeypatch):
    """Ejecuta el selector con candidatos fijos (sin depender del modelo)."""
    def _run(candidates, calibration=None):
        monkeypatch.setattr(sm, "calculate_candidate_markets", lambda *a, **k: [dict(c) for c in candidates])
        monkeypatch.setattr(sm.MarketPresentationCatalog, "is_presentable", staticmethod(lambda c: True))
        probs = ProbabilityReport(home_win=0.5, draw=0.25, away_win=0.25, over_15=0.7, over_25=0.5, under_25=0.5,
                                  btts=0.5, expected_home_goals=1.4, expected_away_goals=1.1, score_matrix=[[1.0]])
        markets = sm.select_statistical_markets(Team(1, "A"), Team(2, "B"), probs, ExpectedMetrics(),
                                                calibration=calibration)
        return {m["selection"]: m["probability"] for m in markets}
    return _run


def _summary(factors):
    return DynamicCalibrationSummary(active=True, league_id=8, league_name="PL", sample_size=100,
                                     overall_hit_rate=0.75, category_factors=factors, bias_offsets={})


def test_minimum_published_probability_is_75_percent(run):
    shown = run([
        _candidate("g1", "Goles", "Más de 1.5 goles", 0.76, "over"),
        _candidate("g2", "Resultado", "A o Empate (1X)", 0.74),
    ])
    assert "Más de 1.5 goles" in shown and "A o Empate (1X)" not in shown


def test_halves_are_suspended(run):
    assert run([_candidate("h1", "Mitades", "1T Menos de 1.5 goles", 0.80, "under")]) == {}


def test_count_unders_need_their_own_calibration(run):
    corners_under = _candidate("c1", "Córners", "Menos de 10.5 córners", 0.80, "under")
    corners_over = _candidate("c2", "Córners", "Más de 7.5 córners", 0.80, "over")
    goals_under = _candidate("g1", "Goles", "Menos de 3.5 goles", 0.80, "under")
    shown = run([corners_under, corners_over, goals_under])
    assert "Menos de 10.5 córners" not in shown  # sin calibración propia del lado
    assert {"Más de 7.5 córners", "Menos de 3.5 goles"} <= set(shown)

    side = {"hit_rate": 0.80, "shrinkage_factor": 1.0, "bias_offset": 0.0, "sample_size": 40}
    shown = run([corners_under], _summary({side_key("Córners", "under"): side}))
    assert "Menos de 10.5 córners" in shown


def test_side_factor_wins_over_category_factor(run):
    factors = {
        "Córners": {"hit_rate": 0.75, "shrinkage_factor": 1.0, "bias_offset": 0.0, "sample_size": 150},
        side_key("Córners", "under"): {"hit_rate": 0.64, "shrinkage_factor": 0.90, "bias_offset": 0.0,
                                       "sample_size": 61},
    }
    shown = run([_candidate("c1", "Córners", "Menos de 10.5 córners", 0.86, "under"),
                 _candidate("c2", "Córners", "Más de 7.5 córners", 0.80, "over", group="c2")],
                _summary(factors))
    assert shown["Menos de 10.5 córners"] == pytest.approx(0.774)  # 0.86 × 0.90
    assert shown["Más de 7.5 córners"] == 0.80
    # Un "Menos" al 82 % baja al 73.8 % con su factor y deja de publicarse.
    shown = run([_candidate("c1", "Córners", "Menos de 10.5 córners", 0.82, "under")], _summary(factors))
    assert shown == {}


def test_selection_side_and_factor_lookup():
    assert selection_side({"side": "under"}) == "under"
    assert selection_side({"selection": "Celta Más de 3.5 córners"}) == "over"
    assert selection_side({"selection": "A o Empate (1X)"}) is None
    factors = {"Tarjetas": {"sample_size": 50}, side_key("Tarjetas", "over"): {"sample_size": 31}}
    assert factor_for(factors, "Tarjetas", "over")["sample_size"] == 31
    assert factor_for(factors, "Tarjetas", "under")["sample_size"] == 50
    assert factor_for(factors, "Tarjetas", None)["sample_size"] == 50


# ---------------------------------------------------------------- calibración por lado

def _save(db, fid, league_id, predictions):
    db.save_fixture_and_predictions(fid, 1, "Local", 2, "Rival", league_id, "PL", "2026-11-20T15:00:00+00:00",
                                    predictions)


def test_recompute_creates_side_rows_and_summary_merges_global(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    for fid in range(1, 41):
        _save(db, fid, 8, [
            {"category": "Córners", "market": "Córners totales", "selection": "Menos de 10.5 córners",
             "line": 10.5, "side": "under", "probability": 0.75, "projection": 9.0},
            {"category": "Córners", "market": "Córners totales", "selection": "Más de 7.5 córners",
             "line": 7.5, "side": "over", "probability": 0.75, "projection": 9.0},
        ])
        db.update_fixture_result(fid, {"home_goals": 1, "away_goals": 0, "corners_home": 6, "corners_away": 6})
        for pred in db.get_predictions_for_fixture(fid):
            won = pred["side"] == "over" or fid % 2 == 0  # los "Menos" aciertan la mitad
            db.update_prediction_status(pred["id"], "WON" if won else "LOST", None)
    _save(db, 99, 564, [])  # otra liga, sin calibración propia
    DynamicCalibrator(db).recompute_calibrations()

    summary = DynamicCalibrator(db).get_calibration_summary(8)
    factors = summary.category_factors
    assert factors[side_key("Córners", "under")]["hit_rate"] == 0.5
    assert factors[side_key("Córners", "over")]["hit_rate"] == 1.0
    assert factors[side_key("Córners", "under")]["shrinkage_factor"] < 1.0 < factors[side_key("Córners", "over")]["shrinkage_factor"]
    assert summary.sample_size == 80  # las filas por lado no se suman otra vez
    assert factors[side_key("Córners", "under")]["bias_offset"] == 0.0
    assert "Córners" in summary.bias_offsets  # 12 reales vs 9 proyectados

    other = DynamicCalibrator(db).get_calibration_summary(564)  # sin filas propias: usa la global
    assert side_key("Córners", "under") in other.category_factors


# ---------------------------------------------------------------- calibración por tramo

def test_band_key_covers_published_range():
    from deport_ai.dynamic_calibration import band_key

    assert band_key(0.76) == "prob|0.75"
    assert band_key(0.85) == "prob|0.85"
    assert band_key(0.885) == "prob|0.85"
    assert band_key(0.59) is None and band_key(0.90) is None


def test_band_factor_corrects_overconfident_top_band_and_changes_the_pick(run):
    band = {"hit_rate": 0.73, "shrinkage_factor": 0.88, "bias_offset": 0.0, "sample_size": 150}
    shown = run([
        _candidate("g1", "Goles", "Más de 1.5 goles", 0.87, "over"),
        _candidate("r1", "Resultado", "A o Empate (1X)", 0.83),
    ], _summary({"prob|0.85": band}))
    assert shown["Más de 1.5 goles"] == pytest.approx(0.7656)  # 0.87 × 0.88
    assert shown["A o Empate (1X)"] == 0.83  # su tramo no tiene corrección
    assert max(shown, key=shown.get) == "A o Empate (1X)"


def test_maximum_is_checked_before_the_band(run):
    band = {"hit_rate": 0.73, "shrinkage_factor": 0.80, "bias_offset": 0.0, "sample_size": 150}
    # 0.95 del modelo no se publica aunque el tramo lo bajara (sin datos por encima del 88 %).
    assert run([_candidate("g1", "Goles", "Más de 0.5 goles", 0.95, "over")],
               _summary({"prob|0.85": band})) == {}


def test_published_predictions_keep_each_stage_probability(run):
    side = {"hit_rate": 0.70, "shrinkage_factor": 0.95, "bias_offset": 0.0, "sample_size": 61}
    band = {"hit_rate": 0.73, "shrinkage_factor": 0.90, "bias_offset": 0.0, "sample_size": 150}
    import deport_ai.statistical_markets as sm_module

    captured = {}
    original = sm_module.select_statistical_markets

    def spy(*args, **kwargs):
        markets = original(*args, **kwargs)
        captured.update({m["selection"]: m for m in markets})
        return markets

    sm_module.select_statistical_markets = spy
    try:
        run([_candidate("c1", "Córners", "Más de 7.5 córners", 0.90, "over")],
            _summary({side_key("Córners", "over"): side, "prob|0.85": band}))
    finally:
        sm_module.select_statistical_markets = original
    item = captured["Más de 7.5 córners"]
    assert item["model_prob"] == 0.90
    assert item["prob_before_band"] == pytest.approx(0.855)
    assert item["probability"] == pytest.approx(0.7695)


def test_band_rows_are_measured_before_the_band_and_stored(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    for fid in range(1, 41):
        _save(db, fid, 8, [
            {"category": "Goles", "market": "Goles totales", "selection": "Más de 1.5 goles", "line": 1.5,
             "side": "over", "probability": 0.77, "model_prob": 0.86, "prob_before_band": 0.86},
        ])
        db.update_fixture_result(fid, {"home_goals": 1, "away_goals": 1})
        for pred in db.get_predictions_for_fixture(fid):
            assert (pred["model_prob"], pred["prob_before_band"]) == (0.86, 0.86)
            db.update_prediction_status(pred["id"], "WON" if fid % 4 else "LOST", None)  # 75 %
    DynamicCalibrator(db).recompute_calibrations()
    factors = DynamicCalibrator(db).get_calibration_summary(8).category_factors
    # Medido sobre 0.86 (antes del tramo), no sobre 0.77 (lo publicado): baja, no sube.
    assert "prob|0.85" in factors and factors["prob|0.85"]["shrinkage_factor"] < 1.0
    assert "prob|0.75" not in factors
    assert DynamicCalibrator(db).get_calibration_summary(8).sample_size == 40  # no suma los tramos


# ---------------------------------------------------------------- máximo por partido

def test_cap_keeps_pick_and_most_probable_in_original_order():
    from deport_ai.statistical_markets import MAX_SELECTIONS_PER_MATCH, cap_selections

    markets = [{"selection": f"S{i}", "probability": p} for i, p in enumerate([0.76, 0.86, 0.80, 0.78, 0.84, 0.77, 0.82])]
    pick = {"selection": "S0", "probability": 0.76}  # p. ej. elegido por EV, no por probabilidad
    capped = cap_selections(markets, pick)
    assert len(capped) == MAX_SELECTIONS_PER_MATCH == 5
    assert [m["selection"] for m in capped] == ["S0", "S1", "S2", "S4", "S6"]
    assert [m["selection"] for m in cap_selections(markets)] == ["S1", "S2", "S3", "S4", "S6"]
    assert cap_selections(markets[:3], pick) == markets[:3]


def test_service_registers_at_most_five_selections_per_match():
    from datetime import datetime, timedelta, timezone

    from tests.test_settlement_tracking_fixes import _analyze

    db = DatabaseManager(":memory:")
    report = _analyze(db, (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    tracked = db.get_predictions_for_fixture(555)
    assert len(report.statistical_markets) <= 5 and len(tracked) == len(report.statistical_markets)
    if report.top_pick:
        assert report.top_pick["selection"] in {p["selection"] for p in tracked}
    assert len(report.featured_markets) <= 4
