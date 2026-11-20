"""Mejoras tras revisar los resultados reales: tarjetas, props de jugador, titularidad y offsides."""

from datetime import datetime, timedelta, timezone

from deport_ai.domain import ExpectedMetrics, PlayerShot, ProbabilityReport, Team, TeamMatch
from deport_ai.service import lineups_are_official, unreliable_categories
from deport_ai.statistical_markets import select_statistical_markets
from deport_ai.stats_engine import CARDS_KEY, _expected_count, _player_probabilities, stat_value

HOME = Team(1, "Local")
AWAY = Team(2, "Visitante")


def _match(i, stats_for=None, stats_against=None, league_id=648):
    return TeamMatch(
        fixture_id=i,
        date=f"2026-10-{28 - i:02d}",
        team_id=1,
        opponent_id=100 + i,
        is_home=i % 2 == 0,
        goals_for=1,
        goals_against=1,
        result="D",
        stats_for=stats_for or {},
        stats_against=stats_against or {},
        league_id=league_id,
    )


def _probabilities() -> ProbabilityReport:
    return ProbabilityReport(
        home_win=0.5, draw=0.25, away_win=0.25, over_15=0.7, over_25=0.5, under_25=0.5, btts=0.5,
        expected_home_goals=1.4, expected_away_goals=1.1, shared_goal_component=0.0, score_matrix=[[1.0]],
    )


# ---------------------------------------------------------------- 1. tarjetas = amarillas + rojas

def test_cards_key_sums_yellow_and_red_and_fills_zero_in_detailed_matches():
    assert stat_value({"yellow_cards": 2, "red_cards": 1}, CARDS_KEY) == 3
    assert stat_value({"total_shots": 10, "yellow_cards": 2}, CARDS_KEY) == 2  # sin rojas publicadas: 0
    assert stat_value({"total_shots": 10}, CARDS_KEY) == 0  # partido detallado sin tarjetas
    assert stat_value({}, CARDS_KEY) is None


def test_card_projection_counts_red_cards_and_zero_card_matches():
    detailed = {"total_shots": 10}
    team = [_match(i, stats_for={**detailed, "yellow_cards": 2, "red_cards": 1}) for i in range(4)] + [
        _match(4 + i, stats_for=dict(detailed)) for i in range(4)
    ]
    rival = [_match(i, stats_against={**detailed, "yellow_cards": 2}) for i in range(8)]
    yellow_only = _expected_count(team, rival, True, False, "yellow_cards")
    total = _expected_count(team, rival, True, False, CARDS_KEY)
    assert total is not None and yellow_only is not None
    assert total != yellow_only


def test_card_explanation_uses_total_cards():
    rec = [_match(i, stats_for={"total_shots": 10, "yellow_cards": 2, "red_cards": 1}) for i in range(8)]
    expected = ExpectedMetrics(cards_home=3.0, cards_away=1.0, dispersion_cards=0.1)
    markets = select_statistical_markets(HOME, AWAY, _probabilities(), expected, recent_home=rec, recent_away=rec)
    card_lines = [m for m in markets if m["category"] == "Tarjetas" and m["selection"].startswith("Local")]
    assert card_lines and "promedia 3.0 tarjetas" in card_lines[0]["explanation"]


# ---------------------------------------------------------------- 2. props de jugador con historial real

def _shots(history_shots, prob=0.75, is_starter=None):
    return {1: [{
        "name": "Nueve",
        "expected_total_shots": 2.6,
        "probability_two_plus": prob,
        "is_starter": is_starter,
        "history_shots": history_shots,
    }]}


def _player_markets(history_shots, **kwargs):
    expected = ExpectedMetrics(player_shots=_shots(history_shots, **kwargs))
    markets = select_statistical_markets(HOME, AWAY, _probabilities(), expected, suspended_categories=frozenset())
    return [m for m in markets if m["category"] == "Jugadores"]


def test_player_prop_cites_real_history():
    markets = _player_markets([3, 2, 2, 4, 2, 1, 3, 2])
    assert markets
    assert markets[0]["explanation"] == (
        "Porque Nueve registró 2+ remates en 7 de sus últimos 8 partidos como titular (promedio 2.4 remates)."
    )


def test_player_prop_without_enough_history_is_hidden():
    assert _player_markets([3, 2, 2]) == []  # menos de 6 partidos como titular
    assert _player_markets([]) == []


def test_player_prop_contradicted_by_history_is_hidden():
    assert _player_markets([1, 0, 2, 1, 0, 1, 2, 1]) == []  # 2 de 8 contra un 75% prometido


def test_player_history_only_counts_starts_with_known_shot_totals():
    rows = [PlayerShot(9, "Nueve", 1, shots_on_target=1, minutes=90, total_shots=3) for _ in range(5)]
    rows += [PlayerShot(9, "Nueve", 1, shots_on_target=1, minutes=15, total_shots=0)]  # suplente
    rows += [PlayerShot(9, "Nueve", 1, shots_on_target=1, minutes=90, total_shots=2.2, total_shots_known=False)]
    player = _player_probabilities(rows, team_id=1)[0]
    assert player["history_shots"] == [3, 3, 3, 3, 3]
    assert len(player["history_sot"]) == 6


# ---------------------------------------------------------------- 3. once oficial solo cerca del inicio

def test_lineups_are_official_only_close_to_kickoff():
    both = [{"startXI": [{"player": {"id": 1}}]}, {"startXI": [{"player": {"id": 2}}]}]
    now = datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc)
    kickoff = "2026-11-18T17:30:00-05:00"  # 22:30 UTC: faltan 150 minutos
    assert not lineups_are_official(both, kickoff, now=now)
    assert lineups_are_official(both, kickoff, now=now + timedelta(minutes=95))
    assert lineups_are_official(both, kickoff, now=now + timedelta(hours=3))  # ya empezó
    assert not lineups_are_official(both[:1], kickoff, now=now + timedelta(minutes=95))
    assert not lineups_are_official(both, None, now=now)


# ---------------------------------------------------------------- 4. fueras de juego según cobertura

def test_offsides_excluded_when_competition_rarely_publishes_them():
    detailed = {"corner_kicks": 5, "total_shots": 12}
    without = [_match(i, stats_for=dict(detailed), league_id=1082) for i in range(5)]
    with_off = [_match(10 + i, stats_for={**detailed, "offsides": 2}, league_id=1082) for i in range(5)]
    assert unreliable_categories(without, without, 1082) == {"Fueras de juego"}
    assert unreliable_categories(with_off, with_off, 1082) == set()
    # Pocos partidos de esa competición: no se decide nada.
    assert unreliable_categories(without[:2], [], 1082) == set()
    # Sin competición conocida se usa la más frecuente de la muestra.
    assert unreliable_categories(without, without, None) == {"Fueras de juego"}
    assert unreliable_categories([], [], None) == set()


def test_excluded_category_is_not_published():
    rec = [_match(i, stats_for={"offsides": 1, "total_shots": 10}, stats_against={"offsides": 1}) for i in range(8)]
    expected = ExpectedMetrics(offsides_home=1.0, offsides_away=1.0, dispersion_offsides=0.1)
    base = select_statistical_markets(
        HOME, AWAY, _probabilities(), expected, recent_home=rec, recent_away=rec, suspended_categories=frozenset()
    )
    assert any(m["category"] == "Fueras de juego" for m in base)
    filtered = select_statistical_markets(
        HOME, AWAY, _probabilities(), expected, recent_home=rec, recent_away=rec,
        exclude_categories={"Fueras de juego"}, suspended_categories=frozenset(),
    )
    assert not any(m["category"] == "Fueras de juego" for m in filtered)
