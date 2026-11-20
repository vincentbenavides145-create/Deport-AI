"""Renombre "tiros a puerta" -> "tiros al arco" sin perder el histórico."""

import json

from deport_ai.settlement import evaluate_prediction, rename_shots_on_target
from deport_ai.storage import DatabaseManager

ACTUAL = {"home_goals": 1, "away_goals": 0, "shots_on_home": 5, "shots_on_away": 3}


def test_old_labels_still_settle():
    old = {"category": "Tiros a puerta", "selection": "Más de 6.5 tiros a puerta", "line": 6.5, "side": "over"}
    new = {"category": "Tiros al arco", "selection": "Más de 6.5 tiros al arco", "line": 6.5, "side": "over"}
    assert evaluate_prediction(old, ACTUAL, "A", "B") == "WON"
    assert evaluate_prediction(new, ACTUAL, "A", "B") == "WON"
    versus_old = {"category": "Tiros a puerta", "selection": "A tiene más tiros a puerta"}
    assert evaluate_prediction(versus_old, ACTUAL, "A", "B") == "WON"


def test_rename_helper():
    assert rename_shots_on_target("Ambos equipos tienen 3+ tiros a puerta") == "Ambos equipos tienen 3+ tiros al arco"
    assert rename_shots_on_target("Tiros a puerta de Bayern") == "Tiros al arco de Bayern"
    assert rename_shots_on_target(None) == ""


def test_history_with_old_labels_is_migrated(tmp_path):
    history = tmp_path / "history" / "predictions.jsonl"
    history.parent.mkdir()
    record = {
        "fixture_id": 1, "home_team_id": 1, "home_team_name": "A", "away_team_id": 2, "away_team_name": "B",
        "status": "FINISHED", "created_at": "2026-11-20T00:00:00",
        "predictions": [{
            "fixture_id": 1, "category": "Tiros a puerta", "market": "Tiros a puerta totales",
            "selection": "Más de 6.5 tiros a puerta", "predicted_prob": 0.8, "status": "WON",
            "explanation": "Porque promedian 9 tiros a puerta.", "created_at": "2026-11-20T00:00:00",
        }],
    }
    history.write_text(json.dumps(record) + "\n", encoding="utf-8")
    db = DatabaseManager(db_path=tmp_path / "db.sqlite", history_path=history)
    [pred] = db.get_predictions_for_fixture(1)
    assert pred["category"] == "Tiros al arco"
    assert pred["market"] == "Tiros al arco totales"
    assert pred["selection"] == "Más de 6.5 tiros al arco"
    assert "a puerta" not in pred["explanation"]
    db.export_history()
    assert "a puerta" not in history.read_text(encoding="utf-8")
