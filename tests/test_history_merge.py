"""Histórico compartido, calibración con anuladas y tiros al palo con datos parciales."""

import json

from deport_ai.dynamic_calibration import DynamicCalibrator
from deport_ai.settlement import evaluate_prediction, extract_match_actual_stats
from deport_ai.storage import DatabaseManager
from track import merge_xg_caches


def _pred(selection, status="PENDING", category="Goles", market="Goles totales", prob=0.7):
    return {"category": category, "market": market, "selection": selection, "probability": prob,
            "predicted_prob": prob, "status": status}


def _save(db, fixture_id, predictions, league_id=8):
    db.save_fixture_and_predictions(
        fixture_id, 1, "Local", 2, "Visitante", league_id, "Liga", "2026-11-20T15:00:00+00:00", predictions,
    )


def _settle(db, fixture_id, statuses):
    db.update_fixture_result(fixture_id, {"home_goals": 2, "away_goals": 1})
    for pred in db.get_predictions_for_fixture(fixture_id):
        db.update_prediction_status(pred["id"], statuses.get(pred["selection"], "WON"), None)


def _history_of(db, tmp_path, name):
    db.history_path = tmp_path / name
    return db.export_history().read_text(encoding="utf-8")


# ---------------------------------------------------------------- calibración

def test_voided_predictions_do_not_fill_the_calibration_sample(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    for fid in range(1, 31):
        _save(db, fid, [_pred("Más de 1.5 goles")])
        _settle(db, fid, {"Más de 1.5 goles": "WON" if fid == 1 else "VOID"})
    DynamicCalibrator(db).recompute_calibrations()
    summary = DynamicCalibrator(db).get_calibration_summary(8)
    assert summary.active is False  # antes: muestra de 30 con 100 % de acierto
    assert summary.category_factors == {}


def test_thirty_resolved_predictions_still_activate_calibration(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    for fid in range(1, 31):
        _save(db, fid, [_pred("Más de 1.5 goles"), _pred("Menos de 4.5 goles")])
        _settle(db, fid, {"Menos de 4.5 goles": "VOID"})
    DynamicCalibrator(db).recompute_calibrations()
    factors = DynamicCalibrator(db).get_calibration_summary(8).category_factors
    assert factors["Goles"]["sample_size"] == 30


# ---------------------------------------------------------------- histórico compartido

def test_stale_local_copy_takes_the_newer_settlement_from_history(tmp_path):
    shared = DatabaseManager(tmp_path / "shared.db")
    _save(shared, 10, [_pred("Más de 1.5 goles"), _pred("Menos de 4.5 goles")])
    old_history = _history_of(shared, tmp_path, "old.jsonl")
    _settle(shared, 10, {"Menos de 4.5 goles": "LOST"})
    new_history = _history_of(shared, tmp_path, "new.jsonl")

    stale = DatabaseManager(tmp_path / "stale.db")
    stale.merge_history(old_history)
    assert stale.get_fixture(10)["status"] == "PENDING"
    assert stale.merge_history(new_history) == 1
    assert stale.get_fixture(10)["status"] != "PENDING"
    assert {p["selection"]: p["status"] for p in stale.get_predictions_for_fixture(10)} == {
        "Más de 1.5 goles": "WON", "Menos de 4.5 goles": "LOST",
    }
    # Y al revés: un histórico viejo (pendiente) no deshace una liquidación local.
    assert stale.merge_history(old_history) == 0
    assert stale.get_fixture(10)["status"] != "PENDING"


def test_merge_keeps_local_predictions_of_a_reanalysed_fixture(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    _save(db, 10, [_pred("Más de 2.5 goles")])
    old_history = _history_of(db, tmp_path, "old.jsonl")
    with db._get_connection() as conn:
        conn.execute("DELETE FROM tracked_predictions WHERE fixture_id = 10")
    _save(db, 10, [_pred("Más de 1.5 goles")])
    db.merge_history(old_history)
    assert [p["selection"] for p in db.get_predictions_for_fixture(10)] == ["Más de 1.5 goles"]


def test_importing_history_from_another_database_does_not_collide_on_ids(tmp_path):
    other = DatabaseManager(tmp_path / "other.db")
    _save(other, 20, [_pred("Más de 1.5 goles"), _pred("Menos de 4.5 goles")])
    history = tmp_path / "history.jsonl"
    other.history_path = history
    other.export_history()

    local = DatabaseManager(tmp_path / "local.db")
    _save(local, 30, [_pred("Más de 2.5 goles"), _pred("Ambos marcan")])  # ids 1 y 2 ya usados
    reopened = DatabaseManager(tmp_path / "local.db", history_path=history)  # antes: IntegrityError
    assert len(reopened.get_predictions_for_fixture(20)) == 2
    assert len(reopened.get_predictions_for_fixture(30)) == 2


def test_rebuilt_database_activates_calibration_from_history(tmp_path):
    source = DatabaseManager(tmp_path / "source.db")
    for fid in range(1, 31):
        _save(source, fid, [_pred("Más de 1.5 goles")])
        _settle(source, fid, {})
    history = tmp_path / "history.jsonl"
    source.history_path = history
    source.export_history()

    rebuilt = DatabaseManager(tmp_path / "new.db", history_path=history)
    summary = DynamicCalibrator(rebuilt).get_calibration_summary(8)
    assert summary.active is True  # sin esperar a `track.py update`
    assert summary.category_factors["Goles"]["sample_size"] == 30


def test_xg_caches_are_united_with_local_priority():
    local = {"version": 1, "matches": {"1": {"xg_home": 1.0}, "2": {"xg_home": 2.0}}}
    remote = {"version": 1, "matches": {"2": {"xg_home": 9.0}, "3": {"xg_home": 3.0}}}
    merged = merge_xg_caches(local, remote)["matches"]
    assert merged == {"1": {"xg_home": 1.0}, "2": {"xg_home": 2.0}, "3": {"xg_home": 3.0}}
    assert json.loads(json.dumps(merged))  # serializable


# ---------------------------------------------------------------- tiros al palo

def _detail(stats_home, stats_away):
    return {
        "fixture": {"id": 1, "status": {"short": "FT"}},
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "goals": {"home": 1, "away": 0},
        "statistics": [
            {"team": {"id": 1}, "statistics": [{"type": k, "value": v} for k, v in stats_home.items()]},
            {"team": {"id": 2}, "statistics": [{"type": k, "value": v} for k, v in stats_away.items()]},
        ],
    }


WOODWORK = {"category": "Especiales", "market": "Tiros al palo", "selection": "Tiro al palo en el partido"}
DETAILED = {"Corner Kicks": 5, "Total Shots": 12, "Shots on Goal": 4}


def test_woodwork_unknown_when_one_team_has_no_statistics():
    for home in ({"Hit Woodwork": 0}, DETAILED, {**DETAILED, "Hit Woodwork": 0}):
        actual = extract_match_actual_stats(_detail(home, {}))
        assert actual["woodwork_hit"] is None, home  # antes: 0 y la apuesta salía perdida
        assert evaluate_prediction(WOODWORK, actual, "Local", "Visitante") == "PENDING"


def test_woodwork_settles_when_the_known_team_already_hit_it():
    actual = extract_match_actual_stats(_detail({"Hit Woodwork": 1}, {}))
    assert actual["woodwork_hit"] == 1
    assert evaluate_prediction(WOODWORK, actual, "Local", "Visitante") == "WON"


# ---------------------------------------------------------------- borrados

def test_removed_fixture_does_not_come_back_from_an_older_history(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    _save(db, 10, [_pred("Más de 1.5 goles")])
    _save(db, 11, [_pred("Más de 1.5 goles")])
    with_both = _history_of(db, tmp_path, "old.jsonl")
    assert db.remove_fixture(10, "analizado por error") is True
    assert db.get_fixture(10) is None and db.get_predictions_for_fixture(10) == []
    assert db.merge_history(with_both) == 0  # el histórico viejo todavía lo tiene
    assert db.get_fixture(10) is None
    assert db.remove_fixture(10, "otra vez") is False


def test_removals_travel_in_the_history_to_other_copies(tmp_path):
    a = DatabaseManager(tmp_path / "a.db")
    _save(a, 10, [_pred("Más de 1.5 goles")])
    before = _history_of(a, tmp_path, "before.jsonl")
    b = DatabaseManager(tmp_path / "b.db")
    b.merge_history(before)
    assert b.get_fixture(10) is not None

    a.remove_fixture(10, "analizado por error")
    after = _history_of(a, tmp_path, "after.jsonl")
    assert '"removed": true' in after and '"fixture_id": 10' in after
    assert b.merge_history(after) == 1
    assert b.get_fixture(10) is None
    rebuilt = DatabaseManager(tmp_path / "c.db", history_path=tmp_path / "after.jsonl")
    assert rebuilt.get_fixture(10) is None
