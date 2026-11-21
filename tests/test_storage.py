from __future__ import annotations

from deport_ai.storage import DatabaseManager


def test_database_manager_init_memory():
    db = DatabaseManager(":memory:")
    assert db.get_pending_fixtures() == []
    assert db.get_summary_stats()["total_predictions"] == 0


def test_save_and_retrieve_fixture_predictions():
    db = DatabaseManager(":memory:")
    predictions = [
        {
            "category": "Goles",
            "market": "Goles Totales",
            "selection": "Más de 2.5 goles",
            "line": 2.5,
            "side": "over",
            "probability": 0.68,
            "odds": 1.85,
            "projection": 3.12,
            "basis": "Modelo Poisson",
            "explanation": "Porque ambos equipos promedian alto xG.",
        },
        {
            "category": "Córners",
            "market": "Córners Totales",
            "selection": "Más de 8.5 córners",
            "line": 8.5,
            "side": "over",
            "probability": 0.72,
            "odds": 1.70,
            "projection": 10.4,
            "basis": "Binomial Negativa",
            "explanation": "Porque generan alto volumen de tiros de esquina.",
        },
    ]

    db.save_fixture_and_predictions(
        fixture_id=12345,
        home_team_id=1,
        home_team_name="Real Madrid",
        away_team_id=2,
        away_team_name="Barcelona",
        league_id=564,
        league_name="La Liga",
        match_date="2026-09-20T20:00:00Z",
        predictions=predictions,
    )

    pending = db.get_pending_fixtures()
    assert len(pending) == 1
    assert pending[0]["fixture_id"] == 12345
    assert pending[0]["home_team_name"] == "Real Madrid"

    preds = db.get_predictions_for_fixture(12345)
    assert len(preds) == 2
    assert preds[0]["selection"] == "Más de 2.5 goles"
    assert preds[0]["status"] == "PENDING"
    assert preds[1]["selection"] == "Más de 8.5 córners"


def test_update_fixture_and_prediction_status():
    db = DatabaseManager(":memory:")
    predictions = [
        {
            "category": "Goles",
            "market": "Goles Totales",
            "selection": "Más de 2.5 goles",
            "line": 2.5,
            "side": "over",
            "probability": 0.65,
        }
    ]
    db.save_fixture_and_predictions(
        fixture_id=999,
        home_team_id=10,
        home_team_name="Arsenal",
        away_team_id=20,
        away_team_name="Chelsea",
        league_id=8,
        league_name="Premier League",
        match_date="2026-09-20T16:00:00Z",
        predictions=predictions,
    )

    db.update_fixture_result(
        fixture_id=999,
        actual_stats={
            "home_goals": 2,
            "away_goals": 1,
            "corners_home": 6,
            "corners_away": 4,
            "cards_home": 1,
            "cards_away": 2,
            "shots_home": 14,
            "shots_away": 9,
        },
        status="FINISHED",
    )

    preds = db.get_predictions_for_fixture(999)
    db.update_prediction_status(preds[0]["id"], "WON", pnl=0.85)

    settled = db.get_settled_predictions()
    assert len(settled) == 1
    assert settled[0]["status"] == "WON"
    assert settled[0]["actual_home_goals"] == 2
    assert settled[0]["actual_away_goals"] == 1

    summary = db.get_summary_stats()
    assert summary["won"] == 1
    assert summary["overall_hit_rate"] == 1.0


def test_calibration_storage():
    db = DatabaseManager(":memory:")
    db.save_calibration(
        league_id=564,
        category="Córners",
        sample_size=15,
        hit_rate=0.7333,
        brier_score=0.1820,
        bias_offset=-1.25,
        shrinkage_factor=0.95,
    )

    cals = db.get_calibration(league_id=564, category="Córners")
    assert len(cals) == 1
    assert cals[0]["sample_size"] == 15
    assert cals[0]["bias_offset"] == -1.25
    assert cals[0]["hit_rate"] == 0.7333
