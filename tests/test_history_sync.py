from __future__ import annotations

import json

from deport_ai.settlement import evaluate_prediction
from deport_ai.storage import DatabaseManager


def _save(db: DatabaseManager) -> None:
    db.save_fixture_and_predictions(
        fixture_id=42, home_team_id=1, home_team_name="Local FC", away_team_id=2,
        away_team_name="Visita", league_id=564, league_name="La Liga", match_date="2026-11-20T20:00:00Z",
        predictions=[{"category": "Goles", "market": "Goles totales", "selection": "Más de 1.5 goles",
                      "line": 1.5, "side": "over", "probability": 0.78, "odds": 1.4}],
    )


def test_export_and_rebuild_from_history(tmp_path):
    history = tmp_path / "history" / "predictions.jsonl"
    db = DatabaseManager(tmp_path / "a.db", history_path=history)
    _save(db)
    db.export_history()
    record = json.loads(history.read_text(encoding="utf-8").splitlines()[0])
    assert record["fixture_id"] == 42 and record["predictions"][0]["selection"] == "Más de 1.5 goles"

    # Sesión nueva: base vacía que se reconstruye desde el histórico del repositorio.
    fresh = DatabaseManager(tmp_path / "b.db", history_path=history)
    preds = fresh.get_predictions_for_fixture(42)
    assert len(preds) == 1 and preds[0]["line"] == 1.5 and preds[0]["odds"] == 1.4
    # Reabrir no duplica.
    again = DatabaseManager(tmp_path / "b.db", history_path=history)
    assert len(again.get_predictions_for_fixture(42)) == 1


def test_memory_db_does_not_touch_history(tmp_path):
    db = DatabaseManager(":memory:")
    assert db.export_history() is None


def test_old_predictions_without_line_are_settled_from_text():
    actual = {"home_goals": 2, "away_goals": 1, "corners_home": 6, "corners_away": 3}
    pred = {"category": "Goles", "selection": "Más de 2.5 goles", "line": None, "side": None}
    assert evaluate_prediction(pred, actual, "Local", "Visita") == "WON"
    pred = {"category": "Córners", "selection": "Visita Menos de 3.5 córners", "line": None, "side": None}
    assert evaluate_prediction(pred, actual, "Local", "Visita") == "WON"
