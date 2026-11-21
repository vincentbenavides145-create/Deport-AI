"""Liquidación de mercados por mitad, córners del 1T, tarjetas en 0 y fueras de juego no publicados."""

from deport_ai.settlement import SettlementEngine, evaluate_prediction, extract_match_actual_stats
from deport_ai.sportmonks import _convert_fixture
from deport_ai.storage import DatabaseManager

HOME_ID, AWAY_ID = 2864, 303


def _raw_fixture(stats=None, scores=None):
    """Fixture crudo de Sportmonks como el de Corinthians 4-0 Botafogo (18-11-2026)."""
    default_stats = [
        {"participant_id": HOME_ID, "type": {"developer_name": "CORNERS"}, "data": {"value": 2}},
        {"participant_id": AWAY_ID, "type": {"developer_name": "CORNERS"}, "data": {"value": 2}},
        {"participant_id": HOME_ID, "type": {"developer_name": "SHOTS_TOTAL"}, "data": {"value": 18}},
        {"participant_id": AWAY_ID, "type": {"developer_name": "SHOTS_TOTAL"}, "data": {"value": 6}},
        {"participant_id": HOME_ID, "type": {"developer_name": "YELLOWCARDS"}, "data": {"value": 3}},
        {"participant_id": HOME_ID, "type": {"developer_name": "OFFSIDES"}, "data": {"value": 0}},
        {"participant_id": AWAY_ID, "type": {"developer_name": "OFFSIDES"}, "data": {"value": 7}},
    ]
    default_scores = [
        {"participant_id": HOME_ID, "description": "1ST_HALF", "score": {"goals": 1}},
        {"participant_id": AWAY_ID, "description": "1ST_HALF", "score": {"goals": 0}},
        {"participant_id": HOME_ID, "description": "2ND_HALF", "score": {"goals": 4}},
        {"participant_id": AWAY_ID, "description": "2ND_HALF", "score": {"goals": 0}},
        {"participant_id": HOME_ID, "description": "CURRENT", "score": {"goals": 4}},
        {"participant_id": AWAY_ID, "description": "CURRENT", "score": {"goals": 0}},
        {"participant_id": HOME_ID, "description": "2ND_HALF_ONLY", "score": {"goals": 3}},
        {"participant_id": AWAY_ID, "description": "2ND_HALF_ONLY", "score": {"goals": 0}},
    ]
    return {
        "id": 19621736,
        "starting_at": "2026-11-19 00:30:00",
        "state": {"developer_name": "FT"},
        "participants": [
            {"id": HOME_ID, "name": "Corinthians", "meta": {"location": "home"}},
            {"id": AWAY_ID, "name": "Botafogo", "meta": {"location": "away"}},
        ],
        "scores": default_scores if scores is None else scores,
        "statistics": default_stats if stats is None else stats,
    }


def _actual(**kwargs):
    return extract_match_actual_stats(_convert_fixture(_raw_fixture(**kwargs)))


def test_half_goals_come_from_converted_fixture_and_second_half_is_not_cumulative():
    actual = _actual()
    assert (actual["first_half_home_goals"], actual["first_half_away_goals"]) == (1, 0)
    # "2ND_HALF" vale 4 (acumulado); el 2T real es 3 ("2ND_HALF_ONLY").
    assert (actual["second_half_home_goals"], actual["second_half_away_goals"]) == (3, 0)


def test_raw_scores_payload_uses_second_half_only():
    raw = _raw_fixture()
    payload = {
        "fixture": {"status": {"short": "FT"}},
        "teams": {"home": {"id": HOME_ID}, "away": {"id": AWAY_ID}},
        "goals": {"home": 4, "away": 0},
        "scores": raw["scores"],
        "statistics": [],
    }
    actual = extract_match_actual_stats(payload)
    assert actual["first_half_home_goals"] == 1
    assert actual["second_half_home_goals"] == 3


def test_half_markets_settle_instead_of_staying_pending():
    actual = _actual()
    home, away = "Corinthians", "Botafogo"
    assert evaluate_prediction({"category": "Mitades", "selection": "1T Menos de 1.5 goles", "line": 1.5, "side": "under"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Mitades", "selection": "2T Menos de 1.5 goles", "line": 1.5, "side": "under"}, actual, home, away) == "LOST"
    assert evaluate_prediction({"category": "Mitades", "selection": "Habrá gol en ambas mitades"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Mitades", "selection": "Corinthians anota en ambas mitades"}, actual, home, away) == "WON"


def test_missing_cards_in_detailed_match_count_as_zero():
    actual = _actual()  # Botafogo no tiene YELLOWCARDS: no recibió tarjetas
    assert actual["cards_away"] == 0
    assert evaluate_prediction({"category": "Tarjetas", "selection": "Botafogo Menos de 2.5 tarjetas", "line": 2.5, "side": "under"}, actual, "Corinthians", "Botafogo") == "WON"

    without_detail = _actual(stats=[])
    assert without_detail["cards_home"] is None


def test_unpublished_offsides_are_void_not_pending():
    stats = [s for s in _raw_fixture()["statistics"] if s["type"]["developer_name"] != "OFFSIDES"]
    actual = _actual(stats=stats)
    pred = {"category": "Fueras de juego", "selection": "Menos de 3.5 fueras de juego", "line": 3.5, "side": "under"}
    assert evaluate_prediction(pred, actual, "Corinthians", "Botafogo") == "VOID"
    # Sin estadísticas de partido todavía no se decide.
    assert evaluate_prediction(pred, _actual(stats=[]), "Corinthians", "Botafogo") == "PENDING"
    # Con el dato publicado (incluido el 0) se liquida normalmente.
    assert evaluate_prediction(pred, _actual(), "Corinthians", "Botafogo") == "LOST"


class FakeAPI:
    def __init__(self, raw, first_half_corners):
        self.raw = raw
        self.corners = first_half_corners
        self.corner_calls = 0

    def fixture_details(self, ids):
        return {int(i): _convert_fixture(self.raw) for i in ids}

    def period_statistics(self, fixture_id):
        self.corner_calls += 1
        if self.corners is None:
            return None
        return {"1st-half": {team: {"CORNERS": value} for team, value in self.corners.items()}}


def _db_with_predictions(predictions):
    db = DatabaseManager(":memory:")
    db.save_fixture_and_predictions(
        19621736, HOME_ID, "Corinthians", AWAY_ID, "Botafogo", 648, "Serie A", "2026-11-18T19:30:00-05:00", predictions
    )
    return db


def test_settlement_fetches_first_half_corners_and_retries_finished_fixtures():
    predictions = [
        {"category": "Córners", "market": "Córners 1T", "selection": "1T Menos de 5.5 córners", "line": 5.5, "side": "under", "probability": 0.65},
        {"category": "Mitades", "market": "Goles 1T", "selection": "1T Menos de 1.5 goles", "line": 1.5, "side": "under", "probability": 0.72},
    ]
    db = _db_with_predictions(predictions)
    api = FakeAPI(_raw_fixture(), {HOME_ID: 0, AWAY_ID: 1})
    result = SettlementEngine(db, api).settle_fixture(19621736)
    assert result["summary"]["won"] == 2
    assert api.corner_calls == 1
    assert {p["status"] for p in db.get_predictions_for_fixture(19621736)} == {"WON"}


def test_finished_fixture_with_pending_predictions_is_settled_again():
    db = _db_with_predictions([
        {"category": "Mitades", "market": "Goles 1T", "selection": "1T Menos de 1.5 goles", "line": 1.5, "side": "under", "probability": 0.72},
    ])
    db.update_fixture_result(19621736, {"home_goals": 4, "away_goals": 0}, status="FINISHED")
    assert [f["fixture_id"] for f in db.get_pending_fixtures()] == [19621736]

    SettlementEngine(db, FakeAPI(_raw_fixture(), None)).settle_all_pending()
    assert db.get_pending_fixtures() == []
