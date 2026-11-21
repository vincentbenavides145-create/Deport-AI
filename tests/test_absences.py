"""Peso de las bajas: datos de Sportmonks, cálculo del descuento y su uso en el modelo."""

from deport_ai.domain import TeamMatch
from deport_ai.model_params import ModelParameters
from deport_ai.sportmonks import _convert_players, _convert_sidelined
from deport_ai.stats_engine import absence_share, extract_team_matches, goal_probabilities


# ---------------------------------------------------------------- datos de Sportmonks

def test_convert_sidelined_reads_player_team_and_dates():
    rows = [
        {"player_id": 7, "participant_id": 503, "player_name": "Luis Díaz",
         "sideline": {"category": "injury", "start_date": "2026-10-22", "end_date": "2026-11-30"}},
        {"player_id": None, "participant_id": 503, "sideline": {}},  # sin jugador: se ignora
        {"sideline": {"player_id": 8, "team_id": 503, "category": "injury", "start_date": "2026-11-08"}},
    ]
    out = _convert_sidelined(rows)
    assert [(r["player_id"], r["team_id"]) for r in out] == [(7, 503), (8, 503)]
    assert out[0]["name"] == "Luis Díaz" and out[0]["end_date"] == "2026-11-30"


def test_convert_players_keeps_assists():
    rows = [{
        "team_id": 1, "player_id": 10, "player_name": "Nueve",
        "details": [
            {"type": {"developer_name": "MINUTES_PLAYED"}, "data": {"value": 90}},
            {"type": {"developer_name": "GOALS"}, "data": {"value": 2}},
            {"type": {"developer_name": "ASSISTS"}, "data": {"value": 1}},
        ],
    }]
    [block] = _convert_players(rows, [{"id": 1, "name": "Local"}])
    goals = block["players"][0]["statistics"][0]["goals"]
    assert goals == {"total": 2, "assists": 1}


def _row(fid, day, home_id, away_id, hg, ag, players=None, sidelined=None):
    return {
        "fixture": {"id": fid, "date": f"2026-11-{day:02d}T18:00:00", "status": {"short": "FT"}},
        "league": {"id": 82, "name": "Bundesliga"},
        "teams": {"home": {"id": home_id, "name": "A"}, "away": {"id": away_id, "name": "B"}},
        "goals": {"home": hg, "away": ag},
        "statistics": [],
        "players": players or [],
        "sidelined": sidelined or [],
    }


def _players(team_id, contribs):
    return [{
        "team": {"id": team_id},
        "players": [
            {"player": {"id": pid, "name": f"J{pid}"}, "statistics": [{"goals": {"total": g, "assists": a}}]}
            for pid, (g, a) in contribs.items()
        ],
    }]


def test_extract_team_matches_fills_contributions_and_current_sidelined():
    row = _row(
        1, 20, 1, 2, 2, 1,
        players=_players(1, {10: (2, 0), 11: (0, 1), 12: (0, 0)}) + _players(2, {20: (1, 0)}),
        sidelined=[
            {"player_id": 30, "team_id": 1, "start_date": "2026-11-01", "end_date": None},
            {"player_id": 31, "team_id": 1, "start_date": "2026-10-01", "end_date": "2026-11-10"},  # ya volvió
            {"player_id": 32, "team_id": 1, "start_date": "2026-11-25", "end_date": None},  # aún no
            {"player_id": 40, "team_id": 2, "start_date": "2026-11-01", "end_date": None},  # del rival
        ],
    )
    [match] = extract_team_matches([row], 1, {})
    assert match.contributions == {10: 2.0, 11: 1.0}
    assert match.player_data is True
    assert match.sidelined == (30,)


# ---------------------------------------------------------------- cálculo del descuento

def _history(contribs_per_match, n=8, team_id=1):
    out = []
    for i in range(n):
        out.append(TeamMatch(
            fixture_id=100 + i, date=f"2026-10-{20 - i:02d}", team_id=team_id, opponent_id=50 + i,
            is_home=i % 2 == 0, goals_for=1, goals_against=1, result="D", league_id=82,
            contributions=dict(contribs_per_match), player_data=True,
        ))
    return out


def test_absence_share_is_lost_part_of_recent_goals_and_assists():
    hist = _history({9: 2.0, 10: 1.0, 11: 1.0})  # el 9 aporta la mitad
    assert absence_share(hist, [9]) == 0.5
    assert absence_share(hist, [10]) == 0.25
    assert absence_share(hist, [10, 11]) == 0.5
    assert absence_share(hist, [9, 10, 11]) == 0.5  # tope del 50 %
    assert absence_share(hist, []) == 0.0
    assert absence_share(hist, [99]) == 0.0  # no jugaba: su ausencia ya está en la forma


def test_absence_share_needs_enough_matches_with_player_data():
    assert absence_share(_history({9: 2.0}, n=3), [9]) == 0.0
    no_data = [TeamMatch(fixture_id=i, date="2026-10-01", team_id=1, opponent_id=2, is_home=True,
                         goals_for=1, goals_against=0, result="W") for i in range(8)]
    assert absence_share(no_data, [9]) == 0.0


def test_absence_weight_lowers_expected_goals_only_when_enabled():
    home, away = _history({9: 2.0, 10: 2.0}), _history({20: 1.0}, team_id=2)
    base = goal_probabilities(home, away, 1500, 1500, league_id=82)
    off = goal_probabilities(home, away, 1500, 1500, league_id=82, absence_home=0.5)
    on = goal_probabilities(home, away, 1500, 1500, league_id=82, absence_home=0.5,
                            params=ModelParameters(absence_weight=1.0))
    assert off.expected_home_goals == base.expected_home_goals  # peso 0: sin cambios
    assert abs(on.expected_home_goals - base.expected_home_goals * 0.5) < 0.02
    assert on.expected_away_goals == base.expected_away_goals


# ---------------------------------------------------------------- backtest

def test_walk_forward_uses_sidelined_of_the_evaluated_match():
    from dataclasses import replace

    from deport_ai.backtesting import absence_coverage, build_fixtures, fixtures_with_injury_data, run_walk_forward

    home_hist = _history({9: 3.0, 10: 1.0}, team_id=1)
    away_hist = _history({20: 1.0}, team_id=2)
    target_home = TeamMatch(fixture_id=999, date="2026-11-01", team_id=1, opponent_id=2, is_home=True,
                            goals_for=0, goals_against=1, result="L", league_id=82, sidelined=(9,))
    target_away = TeamMatch(fixture_id=999, date="2026-11-01", team_id=2, opponent_id=1, is_home=False,
                            goals_for=1, goals_against=0, result="W", league_id=82)
    by_team = {1: home_hist + [target_home], 2: away_hist + [target_away]}
    fixtures = fixtures_with_injury_data(build_fixtures(by_team, {1: "A", 2: "B"}))
    assert [f.fixture_id for f in fixtures] == [999]
    assert absence_coverage(fixtures, by_team) == (1, 1)
    base = run_walk_forward(fixtures, by_team, params=ModelParameters(absence_weight=0.0))
    adjusted = run_walk_forward(fixtures, by_team, params=replace(ModelParameters(), absence_weight=1.0))
    assert adjusted.scoreline_log_loss != base.scoreline_log_loss


# ---------------------------------------------------------------- servicio

def test_service_notes_absences_and_applies_weight(monkeypatch):
    import deport_ai.service as service_module
    from deport_ai.service import AnalysisService
    from tests.test_service import FakeAPI, FakeExplainer

    class InjuryAPI(FakeAPI):
        def __init__(self):
            super().__init__()
            for team_id in (1, 2):
                for row in self.rows[team_id]:
                    row["players"] = _players(team_id, {team_id * 100 + 9: (2, 0), team_id * 100 + 1: (0, 1)})

        def upcoming_between(self, first_id, second_id):
            return {
                "fixture": {"id": 555, "date": "2026-03-01T18:00:00+00:00", "status": {"short": "NS"}},
                "league": {"id": 140, "name": "Liga de prueba", "season": 2025},
                "teams": {"home": {"id": 1, "name": "Local"}, "away": {"id": 2, "name": "Visitante"}},
                "goals": {"home": None, "away": None},
            }

        def sidelined_players(self, fixture_id):
            return [{"player_id": 109, "team_id": 1, "name": "Goleador", "end_date": None}]

    monkeypatch.setattr(service_module, "load_parameters", lambda _lid: ModelParameters(absence_weight=1.0))
    report = AnalysisService(InjuryAPI(), FakeExplainer(), recent_count=6, h2h_count=5,
                             auto_track=False).analyze("Analiza Local vs Visitante", track=False)
    assert any("Bajas de Local: Goleador" in risk for risk in report.risks)

    monkeypatch.setattr(service_module, "load_parameters", lambda _lid: ModelParameters(absence_weight=0.0))
    base = AnalysisService(InjuryAPI(), FakeExplainer(), recent_count=6, h2h_count=5,
                           auto_track=False).analyze("Analiza Local vs Visitante", track=False)
    assert report.probabilities.expected_home_goals < base.probabilities.expected_home_goals
