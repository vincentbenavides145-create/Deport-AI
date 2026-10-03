from __future__ import annotations

import pytest
from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team
from deport_ai.dynamic_calibration import DynamicCalibrator
from deport_ai.statistical_markets import select_statistical_markets
from deport_ai.storage import DatabaseManager


def test_dynamic_calibrator_recompute():
    db = DatabaseManager(":memory:")
    # Simular 10 predicciones resueltas de Córners en liga 564
    # donde el modelo proyectó 11.0 córners pero el promedio real fue 8.0 (sesgo -3.0)
    # y el hit rate fue de 60%
    db.save_fixture_and_predictions(
        fixture_id=1,
        home_team_id=1,
        home_team_name="Local",
        away_team_id=2,
        away_team_name="Visitante",
        league_id=564,
        league_name="La Liga",
        match_date="2026-09-01T20:00:00Z",
        predictions=[
            {
                "category": "Córners",
                "market": "Córners Totales",
                "selection": f"Más de 8.5 córners #{i}",
                "line": 8.5,
                "side": "over",
                "probability": 0.75,
                "projection": 11.0,
            }
            for i in range(10)
        ],
    )

    db.update_fixture_result(
        fixture_id=1,
        actual_stats={
            "home_goals": 1,
            "away_goals": 1,
            "corners_home": 4,
            "corners_away": 4,  # Total 8 córners
        },
        status="FINISHED",
    )

    preds = db.get_predictions_for_fixture(1)
    for idx, p in enumerate(preds):
        status = "WON" if idx < 6 else "LOST"
        db.update_prediction_status(p["id"], status)

    calibrator = DynamicCalibrator(db)
    updated = calibrator.recompute_calibrations(min_sample=5)
    assert updated >= 1

    summary = calibrator.get_calibration_summary(league_id=564, league_name="La Liga")
    assert summary.active is True
    assert summary.sample_size == 10
    assert summary.overall_hit_rate == 0.60
    assert "Córners" in summary.category_factors
    assert summary.bias_offsets.get("Córners") == -3.0  # (8 - 11)


def test_dynamic_calibration_applied_to_projections():
    db = DatabaseManager(":memory:")
    calibrator = DynamicCalibrator(db)

    # Simular calibración con sesgo negativo de -2.0 córners
    db.save_calibration(
        league_id=100,
        category="Córners",
        sample_size=12,
        hit_rate=0.75,
        brier_score=0.18,
        bias_offset=-2.0,
        shrinkage_factor=0.90,
    )

    summary = calibrator.get_calibration_summary(league_id=100)
    assert summary.active is True

    expected = ExpectedMetrics(
        corners_home=6.0,
        corners_away=5.0,
    )
    probs = ProbabilityReport(
        home_win=0.5,
        draw=0.25,
        away_win=0.25,
        over_15=0.8,
        over_25=0.55,
        under_25=0.45,
        btts=0.52,
        expected_home_goals=1.5,
        expected_away_goals=1.2,
        shared_goal_component=0.05,
        score_matrix=[[0.1 for _ in range(5)] for _ in range(5)],
    )

    calibrator.apply_dynamic_calibration_to_projections(expected, probs, summary)

    # Verificar que los córners esperados se hayan ajustado a la baja
    assert expected.corners_home < 6.0
    assert expected.corners_away < 5.0
    assert round(expected.corners_home + expected.corners_away, 1) < 11.0


def test_dynamic_shrinkage_prunes_low_confidence_bets():
    # Si una categoría tiene un shrinkage_factor de 0.70 porque rinde mal,
    # una apuesta al 65% pasa a 0.65 * 0.70 = 45.5% (< 60%) y queda descartada
    db = DatabaseManager(":memory:")
    calibrator = DynamicCalibrator(db)

    db.save_calibration(
        league_id=200,
        category="Tarjetas",
        sample_size=15,
        hit_rate=0.40,
        brier_score=0.35,
        bias_offset=0.0,
        shrinkage_factor=0.70,
    )

    summary = calibrator.get_calibration_summary(league_id=200)
    home = Team(1, "Equipo A")
    away = Team(2, "Equipo B")
    expected = ExpectedMetrics(
        cards_home=2.0,
        cards_away=2.0,
        dispersion_cards=0.27,
    )
    probs = ProbabilityReport(
        home_win=0.4,
        draw=0.3,
        away_win=0.3,
        over_15=0.75,
        over_25=0.50,
        under_25=0.50,
        btts=0.48,
        expected_home_goals=1.2,
        expected_away_goals=1.0,
        shared_goal_component=0.05,
        score_matrix=[[0.1 for _ in range(5)] for _ in range(5)],
    )

    # Con calibración activa, mercados de tarjetas con shrinkage se podan
    markets = select_statistical_markets(home, away, probs, expected, calibration=summary)
    for m in markets:
        assert m["category"] != "Tarjetas" or m["probability"] >= 0.60
