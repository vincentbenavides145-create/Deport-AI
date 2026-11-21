from deport_ai.domain import Team
from deport_ai.formatter import format_adaptive_report
from deport_ai.service import AnalysisService


def fixture(fixture_id: int, team_id: int, opponent_id: int, is_home: bool, gf: int, ga: int):
    home_id, away_id = (team_id, opponent_id) if is_home else (opponent_id, team_id)
    home_goals, away_goals = (gf, ga) if is_home else (ga, gf)
    return {
        "fixture": {
            "id": fixture_id,
            "date": f"2026-02-{fixture_id:02d}T12:00:00+00:00",
            "timestamp": 1_770_000_000 + fixture_id,
            "status": {"short": "FT"},
        },
        "league": {"id": 140, "name": "Liga de prueba", "season": 2025},
        "teams": {
            "home": {"id": home_id, "name": f"Equipo {home_id}"},
            "away": {"id": away_id, "name": f"Equipo {away_id}"},
        },
        "goals": {"home": home_goals, "away": away_goals},
        "statistics": [
            {
                "team": {"id": home_id},
                "statistics": [
                    {"type": "Corner Kicks", "value": 5},
                    {"type": "Shots on Goal", "value": 5},
                ],
            },
            {
                "team": {"id": away_id},
                "statistics": [
                    {"type": "Corner Kicks", "value": 4},
                    {"type": "Shots on Goal", "value": 3},
                ],
            },
        ],
        "players": [],
    }


class FakeAPI:
    def __init__(self):
        self.rows = {
            1: [fixture(i, 1, 100 + i, i % 2 == 0, 2, 1) for i in range(1, 7)],
            2: [fixture(i, 2, 200 + i, i % 2 == 1, 1, 1) for i in range(7, 13)],
        }

    def resolve_team(self, name):
        return Team(1, "Local") if "local" in name.lower() else Team(2, "Visitante")

    def upcoming_between(self, first_id, second_id):
        return None

    def recent_fixtures(self, team_id, count):
        return self.rows[team_id][:count]

    def fixture_details(self, ids):
        all_rows = self.rows[1] + self.rows[2]
        return {row["fixture"]["id"]: row for row in all_rows if row["fixture"]["id"] in ids}

    def h2h(self, first_id, second_id, count):
        return []

    def coverage(self, league_id, season):
        return {}

    def team_season_statistics(self, team_id, league_id, season):
        return {}


def test_full_service_flow_without_network_or_persistence():
    report = AnalysisService(FakeAPI(), recent_count=6, h2h_count=5).analyze(
        "Analiza Local vs Visitante"
    )
    assert report.home.name == "Local"
    assert report.fixture is None
    assert len(report.recent_home) == 6
    assert abs(
        report.probabilities.home_win
        + report.probabilities.draw
        + report.probabilities.away_win
        - 1
    ) < 1e-9
    assert any("cruce hipotético" in risk for risk in report.risks)
    assert report.confidence is not None
    assert report.statistical_markets
    assert report.json_payload()["statistical_markets"] == report.statistical_markets
    assert all("odds" not in item and "edge" not in item for item in report.statistical_markets)
    rendered = format_adaptive_report(report)
    assert rendered.startswith("# ⚽ Local vs Visitante")
    assert "#### 📊 Proyecciones numéricas" in rendered


def test_live_match_handled_gracefully():
    class LiveAPI(FakeAPI):
        def upcoming_between(self, first_id, second_id):
            return {
                "fixture": {"id": 9999, "date": "2026-08-29T16:00:00Z", "status": {"short": "1H"}},
                "state": {"developer_name": "INPLAY_1ST_HALF"},
                "teams": {
                    "home": {"id": first_id, "name": "Local"},
                    "away": {"id": second_id, "name": "Visitante"},
                },
            }

    service = AnalysisService(LiveAPI())
    report = service.analyze("Local vs Visitante")
    assert any("en vivo" in risk.lower() for risk in report.risks)
    assert report.probabilities.home_win > 0



class StubXG:
    """Proveedor de xG sin red: el local genera 3.0 xG por partido y el visitante 0.3."""

    def __init__(self):
        self.fetched: list[int] = []

    def fetch(self, fixtures, max_new=None):
        self.fetched = [f.fixture_id for f in fixtures]
        return {}

    def get(self, fixture_id):
        return {"xg_home": 3.0, "xg_away": 0.3} if fixture_id <= 6 else {"xg_home": 0.3, "xg_away": 0.3}


def test_service_uses_flashscore_xg_when_enabled(monkeypatch):
    import deport_ai.service as service_module

    base = AnalysisService(FakeAPI(), recent_count=6, h2h_count=5, auto_track=False).analyze(
        "Analiza Local vs Visitante", track=False
    )
    monkeypatch.setattr(service_module, "XG_ENABLED", True)
    svc = AnalysisService(FakeAPI(), recent_count=6, h2h_count=5, auto_track=False)
    svc.xg_provider = StubXG()
    with_xg = svc.analyze("Analiza Local vs Visitante", track=False)
    assert sorted(svc.xg_provider.fetched) == list(range(1, 13))
    assert with_xg.probabilities.expected_home_goals != base.probabilities.expected_home_goals


def test_service_keeps_working_if_xg_fails(monkeypatch):
    import deport_ai.service as service_module

    class Broken:
        def fetch(self, fixtures, max_new=None):
            raise RuntimeError("sin red")

    monkeypatch.setattr(service_module, "XG_ENABLED", True)
    svc = AnalysisService(FakeAPI(), recent_count=6, h2h_count=5, auto_track=False)
    svc.xg_provider = Broken()
    report = svc.analyze("Analiza Local vs Visitante", track=False)
    assert report.statistical_markets
