"""Prórroga, equipos con nombres contenidos, jugadores, partidos anulados y registro."""

from datetime import datetime, timedelta, timezone

from deport_ai.service import AnalysisService, not_started
from deport_ai.settlement import SettlementEngine, evaluate_prediction, extract_match_actual_stats
from deport_ai.storage import DatabaseManager
from tests.test_service import FakeAPI


def _detail(status, final, first_half, second_half_only, stats=None):
    return {
        "fixture": {"id": 1, "status": {"short": status}},
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "goals": {"home": final[0], "away": final[1]},
        "halftime": {"home": first_half[0], "away": first_half[1]},
        "second_half": {"home": second_half_only[0], "away": second_half_only[1]},
        "statistics": stats or [],
    }


# ---------------------------------------------------------------- prórroga y penales

def test_extra_time_matches_settle_with_the_90_minute_score():
    # 1-1 a los 90', 2-1 tras la prórroga: el 1X2 y los goles se liquidan con el 1-1.
    actual = extract_match_actual_stats(_detail("AET", (2, 1), (1, 0), (0, 1)))
    assert (actual["home_goals"], actual["away_goals"]) == (1, 1)
    assert evaluate_prediction({"category": "Resultado", "selection": "Empate"}, actual, "A", "B") == "WON"
    assert evaluate_prediction({"category": "Goles", "selection": "Menos de 2.5 goles"}, actual, "A", "B") == "WON"
    assert (actual["second_half_home_goals"], actual["second_half_away_goals"]) == (0, 1)


def test_penalties_without_period_scores_stay_unresolved():
    actual = extract_match_actual_stats(_detail("PEN", (1, 1), (None, None), (None, None)))
    assert actual["home_goals"] is None
    assert evaluate_prediction({"category": "Resultado", "selection": "Empate"}, actual, "A", "B") == "PENDING"


def test_regular_matches_keep_the_final_score():
    actual = extract_match_actual_stats(_detail("FT", (2, 1), (1, 0), (None, None)))
    assert (actual["home_goals"], actual["away_goals"]) == (2, 1)
    assert (actual["second_half_home_goals"], actual["second_half_away_goals"]) == (1, 1)


# ---------------------------------------------------------------- nombres contenidos

def test_team_whose_name_contains_the_rival_name_is_detected():
    actual = {"home_goals": 0, "away_goals": 3, "corners_home": 2, "corners_away": 7}
    home, away = "Santos", "Santos Laguna"
    sel = {"category": "Goles", "selection": "Santos Laguna Más de 1.5 goles", "line": 1.5, "side": "over"}
    assert evaluate_prediction(sel, actual, home, away) == "WON"  # antes: goles del local (0) -> LOST
    sel = {"category": "Córners", "selection": "Santos saca más córners"}
    assert evaluate_prediction(sel, actual, home, away) == "LOST"
    sel = {"category": "Córners", "selection": "Santos Laguna saca más córners"}
    assert evaluate_prediction(sel, actual, home, away) == "WON"


# ---------------------------------------------------------------- jugadores

def _players(*rows):
    out = {}
    for pid, name, shots in rows:
        entry = {"id": pid, "name": name, "minutes": 90, "shots": shots, "shots_on": shots, "goals": 0}
        out[name.lower()] = entry
        out[str(pid)] = entry
    return out


def test_player_props_need_the_same_player_not_a_shared_first_name():
    actual = {"player_stats": _players((1, "Luis Suárez", 5))}
    pred = {"category": "Jugadores", "selection": "Luis Díaz 2+ remates"}
    assert evaluate_prediction(pred, actual, "A", "B") == "VOID"  # antes: con los remates de Suárez
    pred = {"category": "Jugadores", "selection": "James Rodríguez 1+ tiro al arco"}
    actual = {"player_stats": _players((2, "Rodrigo Echeverría", 0), (3, "Juan Fernando Quintero", 0))}
    assert evaluate_prediction(pred, actual, "A", "B") == "VOID"


def test_player_props_match_accents_and_surname_with_initial():
    actual = {"player_stats": _players((1, "James David Rodríguez", 3), (2, "Luis Díaz", 1))}
    assert evaluate_prediction({"category": "Jugadores", "selection": "James Rodriguez 2+ remates"},
                               actual, "A", "B") == "WON"
    assert evaluate_prediction({"category": "Jugadores", "selection": "Luis Díaz Anota en cualquier momento"},
                               actual, "A", "B") == "LOST"


# ---------------------------------------------------------------- partidos anulados

class _API:
    def __init__(self, status):
        self.status = status

    def fixture_details(self, ids):
        return {ids[0]: {"fixture": {"id": ids[0], "status": {"short": self.status}},
                         "teams": {"home": {"id": 1}, "away": {"id": 2}}, "goals": {}}}


def _db_with_pending():
    db = DatabaseManager(":memory:")
    db.save_fixture_and_predictions(9, 1, "A", 2, "B", 8, "PL", "2026-11-20T15:00:00+00:00", [
        {"category": "Goles", "market": "Goles totales", "selection": "Más de 1.5 goles", "probability": 0.8},
    ])
    return db


def test_cancelled_or_abandoned_matches_void_their_predictions():
    for status in ("CANCELLED", "ABANDONED", "AWARDED"):
        db = _db_with_pending()
        result = SettlementEngine(db, _API(status)).settle_fixture(9)
        assert result["status"] == status
        assert [p["status"] for p in db.get_predictions_for_fixture(9)] == ["VOID"]
        assert db.get_pending_fixtures() == []


def test_postponed_matches_stay_pending():
    db = _db_with_pending()
    SettlementEngine(db, _API("POSTPONED")).settle_fixture(9)
    assert [p["status"] for p in db.get_predictions_for_fixture(9)] == ["PENDING"]


def test_fouls_and_first_half_corners_are_kept_in_the_history(tmp_path):
    db = DatabaseManager(tmp_path / "a.db")
    db.save_fixture_and_predictions(9, 1, "A", 2, "B", 8, "PL", "2026-11-20T15:00:00+00:00", [])
    db.update_fixture_result(9, {"home_goals": 1, "away_goals": 0, "fouls_home": 12, "fouls_away": 9,
                                 "corners_first_half": 4})
    row = db.get_fixture(9)
    assert (row["actual_fouls_home"], row["actual_fouls_away"], row["actual_corners_first_half"]) == (12, 9, 4)


# ---------------------------------------------------------------- registro de análisis

def test_not_started_requires_future_kickoff_and_pre_match_status():
    now = datetime(2026, 11, 21, 17, 0, tzinfo=timezone.utc)
    assert not_started("2026-11-21T18:00:00+00:00", "NS", now)
    assert not_started("2026-11-21T13:00:00-05:00", "NS", now)  # 13:00 Lima = 18:00 UTC: aún no
    assert not_started("2026-11-21T11:00:00-05:00", "NS", now) is False  # 16:00 UTC: ya empezó
    assert not_started("2026-11-21T12:00:00+00:00", "NS", now) is False
    assert not_started("2026-11-21T18:00:00+00:00", "1H", now) is False
    assert not_started("2026-11-21T18:00:00+00:00", "POSTPONED", now) is False
    assert not_started(None, "NS", now) is False


class _UpcomingAPI(FakeAPI):
    def __init__(self, kickoff, status="NS"):
        super().__init__()
        self.kickoff, self.status = kickoff, status

    def upcoming_between(self, first_id, second_id):
        return {
            "fixture": {"id": 555, "date": self.kickoff, "status": {"short": self.status}},
            "league": {"id": 140, "name": "Liga de prueba", "season": 2026},
            "teams": {"home": {"id": 1, "name": "Local"}, "away": {"id": 2, "name": "Visitante"}},
            "goals": {"home": None, "away": None},
        }


def _analyze(db, kickoff, status="NS"):
    return AnalysisService(_UpcomingAPI(kickoff, status), recent_count=6, h2h_count=5, db=db).analyze(
        "Analiza Local vs Visitante", track=True
    )


def test_started_matches_are_not_tracked():
    db = DatabaseManager(":memory:")
    past = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    _analyze(db, past, "1H")
    assert db.get_fixture(555) is None


def test_reanalysis_before_kickoff_replaces_pending_predictions():
    db = DatabaseManager(":memory:")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    report = _analyze(db, future)
    first = {p["selection"] for p in db.get_predictions_for_fixture(555)}
    assert first == {m["selection"] for m in report.statistical_markets}
    with db._get_connection() as conn:  # una selección vieja que el nuevo análisis ya no da
        conn.execute(
            "INSERT INTO tracked_predictions (fixture_id, category, market, selection, predicted_prob, status, created_at)"
            " VALUES (555, 'Goles', 'Goles totales', 'Selección vieja', 0.7, 'PENDING', 'x')"
        )
    _analyze(db, future)
    second = {p["selection"] for p in db.get_predictions_for_fixture(555)}
    assert "Selección vieja" not in second and second == first


# ---------------------------------------------------------------- estadísticas a 90 minutos

VELEZ, BELGRANO = 9904, 6829
# Vélez 2-2 Belgrano (20/11/2026): 1-1 a los 90', 2-2 tras la prórroga, datos reales de Sportmonks.
VELEZ_PERIODS = {
    "1st-half": {VELEZ: {"CORNERS": 3, "SHOTS_TOTAL": 12, "SHOTS_ON_TARGET": 4, "FOULS": 6, "YELLOWCARDS": 1},
                 BELGRANO: {"CORNERS": 2, "SHOTS_TOTAL": 6, "SHOTS_ON_TARGET": 3, "FOULS": 7, "YELLOWCARDS": 2,
                            "HIT_WOODWORK": 1}},
    "2nd-half": {VELEZ: {"CORNERS": 3, "SHOTS_TOTAL": 11, "SHOTS_ON_TARGET": 3, "FOULS": 6, "YELLOWCARDS": 2,
                         "HIT_WOODWORK": 1},
                 BELGRANO: {"CORNERS": 2, "SHOTS_TOTAL": 8, "SHOTS_ON_TARGET": 3, "FOULS": 6, "YELLOWCARDS": 1}},
    "extra-time": {VELEZ: {"CORNERS": 0, "SHOTS_TOTAL": 2, "SHOTS_ON_TARGET": 1, "FOULS": 6, "YELLOWCARDS": 1},
                   BELGRANO: {"CORNERS": 4, "SHOTS_TOTAL": 3, "SHOTS_ON_TARGET": 1, "FOULS": 5}},
}


def test_regulation_stats_leave_out_extra_time():
    from deport_ai.settlement import regulation_stats

    out = regulation_stats(VELEZ_PERIODS, VELEZ, BELGRANO)
    assert (out["corners_home"], out["corners_away"]) == (6, 4)  # total con prórroga: 6 y 8
    assert (out["shots_home"], out["shots_away"]) == (23, 14)
    assert (out["fouls_home"], out["fouls_away"]) == (12, 13)
    assert (out["cards_home"], out["cards_away"]) == (3, 3)  # rojas ausentes = 0
    assert out["woodwork_hit"] == 2
    assert out["offsides_home"] is None  # no se publica por periodo: sin resolver, no el total


class _ExtraTimeAPI:
    def __init__(self, periods):
        self.periods = periods

    def fixture_details(self, ids):
        stats = [{"type": "Corner Kicks", "value": 6}, {"type": "Total Shots", "value": 25},
                 {"type": "Shots on Goal", "value": 8}, {"type": "Fouls", "value": 18}]
        away = [{"type": "Corner Kicks", "value": 8}, {"type": "Total Shots", "value": 17},
                {"type": "Shots on Goal", "value": 7}, {"type": "Fouls", "value": 18}]
        return {ids[0]: {
            "fixture": {"id": ids[0], "status": {"short": "PEN"}},
            "teams": {"home": {"id": VELEZ}, "away": {"id": BELGRANO}},
            "goals": {"home": 2, "away": 2}, "halftime": {"home": 0, "away": 1}, "second_half": {"home": 1, "away": 0},
            "statistics": [{"team": {"id": VELEZ}, "statistics": stats}, {"team": {"id": BELGRANO}, "statistics": away}],
        }}

    def period_statistics(self, fixture_id):
        return self.periods


def _velez_db(match_date="2026-11-20T21:00:00-03:00"):
    db = DatabaseManager(":memory:")
    db.save_fixture_and_predictions(19904991, VELEZ, "Vélez Sarsfield", BELGRANO, "Belgrano", 636, "LPF", match_date, [
        {"category": "Goles", "market": "Goles totales", "selection": "Menos de 3.5 goles", "probability": 0.7,
         "line": 3.5, "side": "under"},
        {"category": "Córners", "market": "Córners totales", "selection": "Menos de 10.5 córners", "probability": 0.7,
         "line": 10.5, "side": "under"},
        {"category": "Fueras de juego", "market": "Fueras de juego", "selection": "Más de 1.5 fueras de juego",
         "probability": 0.7, "line": 1.5, "side": "over"},
    ])
    return db


def test_extra_time_match_settles_goals_and_stats_at_90_minutes():
    db = _velez_db()
    SettlementEngine(db, _ExtraTimeAPI(VELEZ_PERIODS)).settle_fixture(19904991)
    status = {p["selection"]: p["status"] for p in db.get_predictions_for_fixture(19904991)}
    assert status["Menos de 3.5 goles"] == "WON"  # 1-1 a los 90' (antes: 2-2 -> LOST)
    assert status["Menos de 10.5 córners"] == "WON"  # 10 a los 90' (14 con la prórroga)
    assert status["Más de 1.5 fueras de juego"] == "VOID"  # no se publica por periodo
    assert db.get_fixture(19904991)["actual_corners_home"] == 6


def test_stats_without_period_data_wait_and_are_voided_after_a_week():
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    db = _velez_db(match_date=recent)
    SettlementEngine(db, _ExtraTimeAPI(None)).settle_fixture(19904991)
    status = {p["selection"]: p["status"] for p in db.get_predictions_for_fixture(19904991)}
    assert status["Menos de 3.5 goles"] == "WON"
    assert status["Menos de 10.5 córners"] == "PENDING"  # nunca con el total que incluye la prórroga

    db = _velez_db(match_date="2026-10-01T21:00:00-03:00")
    SettlementEngine(db, _ExtraTimeAPI(None)).settle_fixture(19904991)
    status = {p["selection"]: p["status"] for p in db.get_predictions_for_fixture(19904991)}
    assert status["Menos de 10.5 córners"] == "VOID"
    assert db.get_pending_fixtures() == []
