"""Fuerza del once: minutos y titulares por partido, déficit frente al once habitual y su uso."""

from deport_ai.domain import TeamMatch
from deport_ai.model_params import ModelParameters
from deport_ai.sportmonks import _convert_players
from deport_ai.stats_engine import _player_minutes, goal_probabilities, lineup_deficit

REGULARS = tuple(range(1, 12))  # 11 titulares de siempre
BENCH = tuple(range(20, 31))


def _match(i, starters=REGULARS, team_id=1):
    minutes = {pid: 90.0 for pid in starters}
    return TeamMatch(fixture_id=100 + i, date=f"2026-10-{20 - i:02d}", team_id=team_id, opponent_id=50,
                     is_home=i % 2 == 0, goals_for=1, goals_against=1, result="D", league_id=8,
                     minutes=minutes, starters=tuple(starters), player_data=True)


def test_convert_players_marks_starters_from_lineup_type():
    rows = [
        {"team_id": 1, "player_id": 7, "player_name": "Titular", "type_id": 11,
         "details": [{"type": {"developer_name": "MINUTES_PLAYED"}, "data": {"value": 90}}]},
        {"team_id": 1, "player_id": 8, "player_name": "Suplente", "type_id": 12,
         "details": [{"type": {"developer_name": "MINUTES_PLAYED"}, "data": {"value": 20}}]},
    ]
    blocks = _convert_players(rows, [{"id": 1, "name": "A"}])
    assert _player_minutes(blocks, 1) == ({7: 90.0, 8: 20.0}, (7,))


def test_usual_lineup_has_no_deficit_and_rotation_does():
    history = [_match(i) for i in range(8)]
    assert lineup_deficit(history, REGULARS) == 0.0
    half = REGULARS[:6] + BENCH[:5]
    assert abs(lineup_deficit(history, half) - 5 / 11) < 0.01
    assert lineup_deficit(history, BENCH) == 0.5  # tope


def test_team_that_always_rotates_is_not_penalised_for_rotating():
    # Alterna dos onces: su once "habitual" ya es la mitad de los minutos.
    history = [_match(i, REGULARS if i % 2 else BENCH) for i in range(8)]
    assert lineup_deficit(history, REGULARS) == 0.0


def test_deficit_needs_enough_lineups():
    assert lineup_deficit([_match(i) for i in range(3)], BENCH) == 0.0
    assert lineup_deficit([_match(i) for i in range(8)], BENCH[:9]) == 0.0  # once incompleto


def test_lineup_weight_moves_goals_only_when_enabled():
    home = [_match(i) for i in range(8)]
    away = [_match(i, team_id=2) for i in range(8)]
    base = goal_probabilities(home, away, 1500, 1500, league_id=8)
    off = goal_probabilities(home, away, 1500, 1500, league_id=8, lineup_deficit_home=0.4)
    on = goal_probabilities(home, away, 1500, 1500, league_id=8, lineup_deficit_home=0.4,
                            params=ModelParameters(lineup_weight=1.0))
    assert off.expected_home_goals == base.expected_home_goals
    assert on.expected_home_goals < base.expected_home_goals  # marca menos
    assert on.expected_away_goals > base.expected_away_goals  # y concede más
