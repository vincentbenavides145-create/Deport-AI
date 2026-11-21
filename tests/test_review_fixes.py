"""Correcciones de la revisión externa: combinadas, tiros al palo, estados, tildes y calibración."""

from deport_ai.dynamic_calibration import DynamicCalibrationSummary, DynamicCalibrator
from deport_ai.domain import ExpectedMetrics, ProbabilityReport
from deport_ai.fixture_contract import FINISHED_STATUSES
from deport_ai.settlement import evaluate_prediction, extract_match_actual_stats
from deport_ai.sportmonks import TEAM_ALIASES, TEAM_ID_OVERRIDES, _normalize, _sportmonks_status
from deport_ai.storage import DatabaseManager


def _result(selection, hg, ag):
    return evaluate_prediction(
        {"category": "Resultado", "market": "Combinada", "selection": selection},
        {"home_goals": hg, "away_goals": ag},
        "Local",
        "Visitante",
    )


# ---------------------------------------------------------------- combinadas

def test_double_chance_combo_needs_both_conditions():
    assert _result("Local o Empate (1X) y Más de 1.5 goles", 0, 0) == "LOST"  # antes salía ganada
    assert _result("Local o Empate (1X) y Más de 1.5 goles", 1, 0) == "LOST"
    assert _result("Local o Empate (1X) y Más de 1.5 goles", 1, 1) == "WON"
    assert _result("Local o Empate (1X) y Menos de 3.5 goles", 2, 2) == "LOST"  # 4 goles
    assert _result("Local o Empate (1X) y Menos de 3.5 goles", 2, 1) == "WON"
    assert _result("Visitante o Empate (X2) y Más de 1.5 goles", 0, 2) == "WON"
    assert _result("Visitante o Empate (X2) y Más de 1.5 goles", 2, 0) == "LOST"
    assert _result("Local o Visitante (12) y Más de 2.5 goles", 2, 1) == "WON"
    assert _result("Local o Visitante (12) y Más de 2.5 goles", 1, 1) == "LOST"


def test_double_chance_and_btts_combo():
    assert _result("Local o Empate (1X) y Ambos Marcan", 1, 0) == "LOST"
    assert _result("Local o Empate (1X) y Ambos Marcan", 1, 1) == "WON"
    assert _result("Local o Empate (1X) y Ambos Marcan", 1, 2) == "LOST"


def test_plain_double_chance_still_settles():
    assert _result("Local o Empate (1X)", 0, 0) == "WON"
    assert _result("Visitante o Empate (X2)", 1, 0) == "LOST"
    assert _result("Local o Visitante (12)", 1, 1) == "LOST"


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


def test_woodwork_unknown_without_statistics():
    actual = extract_match_actual_stats(_detail({}, {}))
    assert actual["woodwork_hit"] is None
    pred = {"category": "Especiales", "market": "Tiros al palo", "selection": "Tiro al palo en el partido"}
    assert evaluate_prediction(pred, actual, "Local", "Visitante") == "PENDING"


def test_woodwork_zero_when_match_has_full_statistics():
    detailed = {"Corner Kicks": 5, "Total Shots": 12, "Shots on Goal": 4}
    actual = extract_match_actual_stats(_detail(detailed, detailed))
    assert actual["woodwork_hit"] == 0  # Sportmonks omite el dato cuando no hubo tiros al palo
    actual = extract_match_actual_stats(_detail({**detailed, "Hit Woodwork": 1}, detailed))
    assert actual["woodwork_hit"] == 1


# ---------------------------------------------------------------- estados de Sportmonks

def _status(name):
    return _sportmonks_status({"state": {"developer_name": name}})


def test_live_extra_time_and_penalties_are_not_finished():
    for live in ("INPLAY_EXTRA_TIME", "INPLAY_PENALTIES", "EXTRA_TIME_BREAK", "PEN_BREAK", "INPLAY_1ST_HALF", "HT"):
        assert _status(live) not in FINISHED_STATUSES, live
    assert _status("INPLAY_EXTRA_TIME") == "ET"
    assert _status("INPLAY_PENALTIES") == "PEN_LIVE"
    assert _status("INPLAY_2ND_HALF") == "2H"


def test_finished_states_still_finished():
    assert _status("FT") == "FT"
    assert _status("AET") == "AET"
    assert _status("FT_PEN") == "PEN"
    assert _status("NS") == "NS"


# ---------------------------------------------------------------- tildes

def test_normalize_strips_accents():
    assert _normalize("España") == "espana"
    assert _normalize("Bélgica") == "belgica"
    assert _normalize("Turquía") == "turquia"
    assert _normalize("São Paulo") == "sao paulo"
    assert _normalize("Côte d'Ivoire") == "cote d ivoire"


def test_aliases_match_accented_queries():
    assert TEAM_ALIASES[_normalize("España")] == "Spain"
    assert TEAM_ALIASES[_normalize("Bélgica")] == "Belgium"
    assert TEAM_ALIASES[_normalize("Turquía")] == "Türkiye"  # nombre de Sportmonks
    assert TEAM_ALIASES["turkey"] == "Türkiye"
    assert _normalize("Atlético de Madrid") in TEAM_ID_OVERRIDES


# ---------------------------------------------------------------- calibración

def test_calibration_no_longer_moves_expected_goals_after_the_score_matrix():
    calibrator = DynamicCalibrator(DatabaseManager(":memory:"))
    probs = ProbabilityReport(
        home_win=0.5, draw=0.25, away_win=0.25, over_15=0.7, over_25=0.5, under_25=0.5, btts=0.5,
        expected_home_goals=1.4, expected_away_goals=1.1, score_matrix=[[1.0]],
    )
    expected = ExpectedMetrics(corners_home=5.0, corners_away=4.0)
    summary = DynamicCalibrationSummary(
        active=True, league_id=1, league_name="L", sample_size=100, overall_hit_rate=0.7,
        category_factors={}, bias_offsets={"Goles": 1.0, "Córners": -1.0},
    )
    calibrator.apply_dynamic_calibration_to_projections(expected, probs, summary)
    assert (probs.expected_home_goals, probs.expected_away_goals) == (1.4, 1.1)
    assert round(expected.corners_home + expected.corners_away, 2) == 8.4  # 9 - 0.6
