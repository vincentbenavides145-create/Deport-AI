from __future__ import annotations

from deport_ai.ai_critic import AICritic
from deport_ai.storage import DatabaseManager


def test_ai_critic_report_empty():
    db = DatabaseManager(":memory:")
    critic = AICritic(db)
    report = critic.generate_diagnostic_report()
    assert "No hay apuestas liquidadas" in report


def test_ai_critic_report_with_settled_bets():
    db = DatabaseManager(":memory:")
    db.save_fixture_and_predictions(
        fixture_id=10,
        home_team_id=1,
        home_team_name="Barcelona",
        away_team_id=2,
        away_team_name="Sevilla",
        league_id=564,
        league_name="La Liga",
        match_date="2026-09-10T20:00:00Z",
        predictions=[
            {
                "category": "Goles",
                "market": "Goles Totales",
                "selection": "Más de 2.5 goles",
                "line": 2.5,
                "side": "over",
                "probability": 0.72,
                "projection": 3.4,
            },
            {
                "category": "Córners",
                "market": "Córners Totales",
                "selection": "Más de 8.5 córners",
                "line": 8.5,
                "side": "over",
                "probability": 0.68,
                "projection": 10.2,
            },
            {
                "category": "Tarjetas",
                "market": "Tarjetas Totales",
                "selection": "Más de 4.5 tarjetas",
                "line": 4.5,
                "side": "over",
                "probability": 0.65,
                "projection": 5.1,
            },
        ],
    )

    db.update_fixture_result(
        fixture_id=10,
        actual_stats={
            "home_goals": 2,
            "away_goals": 1,
            "corners_home": 6,
            "corners_away": 4,
            "cards_home": 1,
            "cards_away": 1,
        },
        status="FINISHED",
    )

    preds = db.get_predictions_for_fixture(10)
    db.update_prediction_status(preds[0]["id"], "WON")   # Goles won
    db.update_prediction_status(preds[1]["id"], "WON")   # Córners won
    db.update_prediction_status(preds[2]["id"], "LOST")  # Tarjetas lost

    critic = AICritic(db)
    analysis = critic.analyze_settled_performance()
    assert analysis["total_evaluated"] == 3
    assert analysis["won"] == 2
    assert analysis["lost"] == 1
    assert round(analysis["hit_rate"], 2) == 0.67

    md_report = critic.generate_diagnostic_report()
    assert "Diagnóstico y Auditoría de Pronósticos" in md_report
    assert "Goles" in md_report
    assert "Córners" in md_report
    assert "Tarjetas" in md_report
