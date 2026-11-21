from __future__ import annotations

from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team
from deport_ai.dynamic_calibration import DynamicCalibrator
from deport_ai.statistical_markets import select_statistical_markets
from deport_ai.storage import DatabaseManager


def test_dynamic_calibrator_recompute():
    """El sesgo se mide solo con mercados de total del partido, una vez por partido."""
    db = DatabaseManager(":memory:")
    # 30 partidos: el modelo proyectó 11.0 córners totales y hubo 8 (sesgo -3.0). Cada uno
    # trae también un mercado de equipo (proyección 6.0) que NO debe entrar en el sesgo.
    for fid in range(1, 31):
        db.save_fixture_and_predictions(
            fixture_id=fid, home_team_id=1, home_team_name="Local", away_team_id=2,
            away_team_name="Rival", league_id=564, league_name="La Liga",
            match_date=f"2026-09-{fid:02d}T20:00:00Z",
            predictions=[
                {"category": "Córners", "market": "Córners totales", "selection": "Más de 8.5 córners",
                 "line": 8.5, "side": "over", "probability": 0.75, "projection": 11.0},
                {"category": "Córners", "market": "Córners de Local", "selection": "Local Más de 3.5 córners",
                 "line": 3.5, "side": "over", "probability": 0.75, "projection": 6.0},
            ],
        )
        db.update_fixture_result(
            fixture_id=fid,
            actual_stats={"home_goals": 1, "away_goals": 1, "corners_home": 4, "corners_away": 4},
            status="FINISHED",
        )
        for idx, p in enumerate(db.get_predictions_for_fixture(fid)):
            db.update_prediction_status(p["id"], "WON" if (fid <= 18) else "LOST")

    calibrator = DynamicCalibrator(db)
    assert calibrator.recompute_calibrations() >= 1
    summary = calibrator.get_calibration_summary(league_id=564, league_name="La Liga")
    assert summary.active is True
    assert summary.sample_size == 60
    assert summary.overall_hit_rate == 0.60
    assert "Córners" in summary.category_factors
    assert summary.bias_offsets.get("Córners") == -3.0  # (8 - 11), sin mezclar la proyección de equipo


def test_bias_needs_thirty_matches_with_total_projection():
    db = DatabaseManager(":memory:")
    db.save_fixture_and_predictions(
        fixture_id=1, home_team_id=1, home_team_name="Local", away_team_id=2, away_team_name="Rival",
        league_id=564, league_name="La Liga", match_date="2026-09-01T20:00:00Z",
        predictions=[
            {"category": "Córners", "market": "Córners totales", "selection": f"Más de 8.5 córners #{i}",
             "line": 8.5, "side": "over", "probability": 0.75, "projection": 11.0}
            for i in range(40)
        ],
    )
    db.update_fixture_result(fixture_id=1, actual_stats={"home_goals": 1, "away_goals": 1,
                                                         "corners_home": 4, "corners_away": 4}, status="FINISHED")
    for p in db.get_predictions_for_fixture(1):
        db.update_prediction_status(p["id"], "WON")
    calibrator = DynamicCalibrator(db)
    calibrator.recompute_calibrations()
    summary = calibrator.get_calibration_summary(league_id=564, league_name="La Liga")
    assert "Córners" not in summary.bias_offsets  # un solo partido: no hay sesgo fiable


def test_dynamic_calibration_applied_to_projections():
    db = DatabaseManager(":memory:")
    calibrator = DynamicCalibrator(db)

    # Simular calibración con sesgo negativo de -2.0 córners
    db.save_calibration(
        league_id=100,
        category="Córners",
        sample_size=60,
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
        sample_size=45,
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
        score_matrix=[[0.1 for _ in range(5)] for _ in range(5)],
    )

    # Con calibración activa, mercados de tarjetas con shrinkage se podan
    markets = select_statistical_markets(home, away, probs, expected, calibration=summary)
    for m in markets:
        assert m["category"] != "Tarjetas" or m["probability"] >= 0.60


def test_small_real_sample_does_not_activate_calibration():
    db = DatabaseManager(":memory:")
    db.save_calibration(
        league_id=300, category="Córners", sample_size=12, hit_rate=0.90,
        brier_score=0.1, bias_offset=-3.0, shrinkage_factor=1.10,
    )
    summary = DynamicCalibrator(db).get_calibration_summary(league_id=300)
    assert summary.active is False
    assert summary.category_factors == {}
