"""Integridad de la calibración: simulación sin guardar, factores específicos, historial
antiguo, borrados y categorías frenadas que se registran sin publicar."""

import argparse
import importlib.util
from pathlib import Path

import pytest

import deport_ai.statistical_markets as sm
from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team
from deport_ai.dynamic_calibration import (
    FREEZE_MIN_SAMPLE,
    DynamicCalibrationSummary,
    DynamicCalibrator,
    side_key,
    total_side_key,
)
from deport_ai.storage import DatabaseManager

ROOT = Path(__file__).resolve().parent.parent


def _backtest_module():
    spec = importlib.util.spec_from_file_location("backtest_cli", ROOT / "backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**kwargs):
    base = {"synthetic": False, "fit": False, "save_params": False, "as_default": False, "save_calibration": False}
    return argparse.Namespace(**{**base, **kwargs})


# ---------------------------------------------------------------- 1. backtest

def test_synthetic_league_never_saves_parameters_or_calibration():
    conflict = _backtest_module().storage_conflict
    assert conflict(_args(synthetic=True, fit=True, save_params=True))
    assert conflict(_args(synthetic=True, fit=True, save_params=True, as_default=True))
    assert conflict(_args(synthetic=True, save_calibration=True))
    assert conflict(_args(synthetic=True, fit=True)) is None  # solo medir sí se puede


def test_fit_and_save_calibration_are_not_combined():
    conflict = _backtest_module().storage_conflict
    assert conflict(_args(fit=True, save_calibration=True))
    assert conflict(_args(fit=True, save_params=True)) is None
    assert conflict(_args(save_calibration=True)) is None


# ---------------------------------------------------------------- 2. factor del total

@pytest.fixture
def select(monkeypatch):
    def _run(candidates, factors, frozen=(), unpublished=None):
        monkeypatch.setattr(sm, "calculate_candidate_markets", lambda *a, **k: [dict(c) for c in candidates])
        monkeypatch.setattr(sm.MarketPresentationCatalog, "is_presentable", staticmethod(lambda c: True))
        probs = ProbabilityReport(home_win=0.5, draw=0.25, away_win=0.25, over_15=0.7, over_25=0.5, under_25=0.5,
                                  btts=0.5, expected_home_goals=1.4, expected_away_goals=1.1, score_matrix=[[1.0]])
        summary = DynamicCalibrationSummary(True, 8, "PL", 100, 0.75, factors, {}, frozen_categories=frozen)
        markets = sm.select_statistical_markets(Team(1, "A"), Team(2, "B"), probs, ExpectedMetrics(),
                                                calibration=summary, unpublished=unpublished)
        return {m["selection"]: m["probability"] for m in markets}
    return _run


def _factor(shrinkage, n):
    return {"hit_rate": 0.8, "shrinkage_factor": shrinkage, "bias_offset": 0.0, "sample_size": n}


def _goals(selection, probability, side):
    return {"id": selection, "category": "Goles", "market": "Goles", "selection": selection,
            "probability": probability, "side": side, "group": selection, "explanation": "Porque sí."}


def test_match_total_goal_factor_is_applied_not_only_checked(select):
    factors = {total_side_key("Goles", "under"): _factor(0.95, 30), side_key("Goles", "under"): _factor(1.0, 150)}
    shown = select([_goals("Menos de 3.5 goles", 0.84, "under")], factors)
    assert shown["Menos de 3.5 goles"] == pytest.approx(0.798)  # 0.84 × 0.95, no × 1.00
    factors[total_side_key("Goles", "under")] = _factor(0.80, 30)
    assert select([_goals("Menos de 3.5 goles", 0.84, "under")], factors) == {}  # 0.672: no se publica


def test_team_goal_unders_keep_the_side_factor(select):
    factors = {total_side_key("Goles", "under"): _factor(0.80, 30), side_key("Goles", "under"): _factor(0.95, 150)}
    shown = select([_goals("B Menos de 2.5 goles", 0.84, "under")], factors)
    assert shown["B Menos de 2.5 goles"] == pytest.approx(0.798)


# ---------------------------------------------------------------- 3. historial antiguo

def _save(db, fid, league_id, preds, date="2026-11-20T15:00:00+00:00"):
    db.save_fixture_and_predictions(fid, 1, "Local", 2, "Rival", league_id, "PL", date, preds)


def _settle(db, fid, won):
    db.update_fixture_result(fid, {"home_goals": 1, "away_goals": 0, "corners_home": 6, "corners_away": 6})
    for pred in db.get_predictions_for_fixture(fid):
        db.update_prediction_status(pred["id"], "WON" if won(pred) else "LOST", None)


def test_factor_uses_staged_predictions_once_there_are_enough(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    over = {"category": "Faltas", "market": "Faltas totales", "selection": "Más de 21.5 faltas", "line": 21.5,
            "side": "over"}
    for fid in range(1, 41):  # antiguas: solo la publicada (0.70); acertaron 100 %
        _save(db, fid, 8, [{**over, "probability": 0.70}])
        _settle(db, fid, lambda p: True)
    for fid in range(100, 130):  # nuevas con la del modelo (0.80); acertaron 60 %
        _save(db, fid, 8, [{**over, "probability": 0.80, "model_prob": 0.80, "prob_before_band": 0.80}])
        _settle(db, fid, lambda p, fid=fid: fid % 5 < 3)
    DynamicCalibrator(db).recompute_calibrations()
    row = DynamicCalibrator(db).get_calibration_summary(8).category_factors[side_key("Faltas", "over")]
    assert row["sample_size"] == 70 and row["hit_rate"] == pytest.approx(58 / 70, abs=1e-4)  # acierto: todas
    assert row["shrinkage_factor"] < 1.0  # factor: solo las 30 nuevas (60 % con 80 % prometido)


def test_legacy_only_rows_keep_the_approximation(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    for fid in range(1, 41):
        _save(db, fid, 8, [{"category": "Faltas", "market": "Faltas totales", "selection": "Más de 21.5 faltas",
                            "line": 21.5, "side": "over", "probability": 0.70}])
        _settle(db, fid, lambda p: True)
    DynamicCalibrator(db).recompute_calibrations()
    row = DynamicCalibrator(db).get_calibration_summary(8).category_factors[side_key("Faltas", "over")]
    assert row["shrinkage_factor"] > 1.0  # sin muestra nueva: se mide sobre la publicada


# ---------------------------------------------------------------- 4. borrado

def test_removing_a_fixture_recomputes_the_calibration(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    for fid in range(1, 31):
        _save(db, fid, 8, [{"category": "Faltas", "market": "Faltas totales", "selection": "Más de 21.5 faltas",
                            "line": 21.5, "side": "over", "probability": 0.75}])
        _settle(db, fid, lambda p: True)
    DynamicCalibrator(db).recompute_calibrations()
    assert DynamicCalibrator(db).get_calibration_summary(8).category_factors["Faltas"]["sample_size"] == 30
    assert db.remove_fixture(30, "prueba")
    summary = DynamicCalibrator(db).get_calibration_summary(8)
    assert "Faltas" not in summary.category_factors and not summary.active  # 29: ya no llega al mínimo


# ---------------------------------------------------------------- 5. categorías frenadas

def test_frozen_category_selections_are_returned_as_unpublished(select):
    corners = {"id": "c1", "category": "Córners", "market": "Córners", "selection": "Más de 7.5 córners",
               "probability": 0.80, "side": "over", "group": "c1", "explanation": "Porque sí.",
               "line": 7.5, "projection": 10.5}
    unpublished = []
    shown = select([corners, _goals("Más de 1.5 goles", 0.80, "over")], {}, frozen=("Córners",),
                   unpublished=unpublished)
    assert set(shown) == {"Más de 1.5 goles"}
    assert [m["selection"] for m in unpublished] == ["Más de 7.5 córners"]


def test_unpublished_predictions_measure_but_do_not_count_as_published(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    corners = {"category": "Córners", "market": "Córners totales", "selection": "Más de 7.5 córners", "line": 7.5,
               "side": "over", "probability": 0.80}
    day = 0
    for fid in range(1, FREEZE_MIN_SAMPLE + 1):  # 20 publicadas: 50 % → frena la categoría
        day += 1
        _save(db, fid, 8, [dict(corners)], date=f"2026-10-{day:02d}T15:00:00+00:00")
        _settle(db, fid, lambda p, fid=fid: fid % 2 == 0)
    DynamicCalibrator(db).recompute_calibrations()
    assert DynamicCalibrator(db).get_calibration_summary(8).frozen_categories == ("Córners",)

    for fid in range(100, 100 + FREEZE_MIN_SAMPLE):  # 20 sin publicar, todas acertadas
        _save(db, fid, 8, [{**corners, "unpublished": True}], date=f"2026-11-{fid - 99:02d}T15:00:00+00:00")
        _settle(db, fid, lambda p: True)
    DynamicCalibrator(db).recompute_calibrations()

    # Las 20 más recientes (sin publicar) levantan el freno...
    assert DynamicCalibrator(db).get_calibration_summary(8).frozen_categories == ()
    # ...pero el acierto publicado solo cuenta las publicadas.
    stats = db.get_summary_stats()
    assert (stats["won"], stats["lost"]) == (10, 10)
    assert len(db.get_settled_predictions()) == 20
    assert len(db.get_settled_predictions(include_unpublished=True)) == 40
    assert all(p["unpublished"] == 1 for p in db.get_predictions_for_fixture(100))


def test_unpublished_flag_survives_the_history_round_trip(tmp_path):
    source = DatabaseManager(tmp_path / "a.db", history_path=tmp_path / "h.jsonl")
    _save(source, 1, 8, [{"category": "Córners", "market": "Córners totales", "selection": "Más de 7.5 córners",
                          "line": 7.5, "side": "over", "probability": 0.80, "unpublished": True}])
    source.export_history()
    copy = DatabaseManager(tmp_path / "b.db", history_path=tmp_path / "h.jsonl")
    assert copy.get_predictions_for_fixture(1)[0]["unpublished"] == 1


# ---------------------------------------------------------------- guardado del backtest

def _backtest_result(fixture_ids):
    from types import SimpleNamespace

    records, samples, actuals = [], {}, {}
    for fid in fixture_ids:
        records.append({"fixture_id": fid, "league_id": 8, "category": "Goles", "market": "Goles totales",
                        "selection": "Más de 1.5 goles", "line": 1.5, "side": "over", "projection": 2.8,
                        "probability": 0.81, "won": True, "shown": True, "odds": None})
        records.append({"fixture_id": fid, "league_id": 8, "category": "Faltas", "market": "Faltas totales",
                        "selection": "Más de 21.5 faltas", "line": 21.5, "side": "over", "projection": 24.0,
                        "probability": 0.77, "won": False, "shown": False, "odds": None})
        samples[fid] = SimpleNamespace(home=SimpleNamespace(team_id=1), away=SimpleNamespace(team_id=2),
                                       home_name="Local", away_name="Rival", league_id=8,
                                       date="2025-03-01T15:00:00+00:00")
        actuals[fid] = {"home_goals": 2, "away_goals": 1}
    return SimpleNamespace(records=records, samples=samples, actuals=actuals)


def test_backtest_calibration_is_exported_unpublished_and_skips_fitted_fixtures(tmp_path):
    save = _backtest_module().save_calibration_from_backtest
    history = tmp_path / "h.jsonl"
    db = DatabaseManager(tmp_path / "a.db", history_path=history)
    saved, skipped = save(_backtest_result([501, 502, 503]), db=db, excluded={503})
    assert (saved, skipped) == (2, 1)  # solo las mostradas, sin el partido usado en el ajuste

    rebuilt = DatabaseManager(tmp_path / "b.db", history_path=history)  # sesión nueva: desde el histórico
    preds = rebuilt.get_predictions_for_fixture(501)
    assert [(p["selection"], p["status"], p["unpublished"], p["model_prob"]) for p in preds] == [
        ("Más de 1.5 goles", "WON", 1, 0.81)
    ]
    assert rebuilt.get_fixture(503) is None
    assert rebuilt.get_summary_stats()["resolved"] == 0  # no cuentan como publicadas


def test_fitted_fixture_ids_are_saved_and_collected(tmp_path):
    from deport_ai.model_params import ModelParameters, fitted_fixture_ids, load_parameters, save_parameters

    path = tmp_path / "params.json"
    save_parameters("8", ModelParameters(fitted=True, fitted_fixture_ids=(11, 12)), path)
    save_parameters("default", ModelParameters(fitted=True, fitted_fixture_ids=(12, 13)), path)
    assert fitted_fixture_ids(path) == {11, 12, 13}
    assert load_parameters(8, path).fitted_fixture_ids == (11, 12)
    assert fitted_fixture_ids(tmp_path / "missing.json") == set()
