from __future__ import annotations

from deport_ai.ai_critic import AICritic
from deport_ai.domain import Team
from deport_ai.dynamic_calibration import DynamicCalibrator
from deport_ai.formatter import format_adaptive_report
from deport_ai.service import AnalysisService
from deport_ai.settlement import SettlementEngine
from deport_ai.storage import DatabaseManager


class MockAPI:
    def __init__(self):
        self.provider_label = "Mock Sportmonks"
        self.max_season = 2026

    def resolve_team(self, query: str):
        if "madrid" in query.lower():
            return Team(10, "Real Madrid", "Spain")
        return Team(20, "Barcelona", "Spain")

    def upcoming_between(self, home_id: int, away_id: int):
        return {
            "fixture": {
                "id": 8888,
                "date": "2026-09-25T20:00:00Z",
                "timestamp": 1790366400,
                "status": {"short": "NS"},
            },
            "league": {"id": 564, "name": "La Liga", "season": 2026},
            "teams": {
                "home": {"id": 10, "name": "Real Madrid"},
                "away": {"id": 20, "name": "Barcelona"},
            },
        }

    def recent_fixtures(self, team_id: int, count: int):
        matches = []
        for i in range(count):
            matches.append(
                {
                    "fixture": {
                        "id": 1000 + i + (team_id * 10),
                        "date": f"2026-08-{i+1:02d}T15:00:00Z",
                        "timestamp": 1788000000 + i,
                        "status": {"short": "FT"},
                    },
                    "league": {"id": 564, "name": "La Liga", "season": 2026},
                    "teams": {
                        "home": {"id": team_id, "name": "Target"},
                        "away": {"id": 99, "name": "Opponent"},
                    },
                    "goals": {"home": 2, "away": 1},
                    "statistics": [
                        {"team": {"id": team_id}, "statistics": [{"type": "Corner Kicks", "value": 6}, {"type": "Yellow Cards", "value": 2}]},
                        {"team": {"id": 99}, "statistics": [{"type": "Corner Kicks", "value": 4}, {"type": "Yellow Cards", "value": 3}]},
                    ],
                }
            )
        return matches

    def fixture_details(self, fixture_ids):
        res = {}
        for fid in fixture_ids:
            if fid == 8888:
                res[fid] = {
                    "fixture": {"id": 8888, "status": {"short": "FT"}},
                    "teams": {"home": {"id": 10, "name": "Real Madrid"}, "away": {"id": 20, "name": "Barcelona"}},
                    "goals": {"home": 3, "away": 1},
                    "scores": [
                        {"participant_id": 10, "description": "1ST_HALF", "score": {"goals": 1}},
                        {"participant_id": 20, "description": "1ST_HALF", "score": {"goals": 0}},
                    ],
                    "statistics": [
                        {"team": {"id": 10}, "statistics": [{"type": "Corner Kicks", "value": 7}, {"type": "Yellow Cards", "value": 2}, {"type": "Total Shots", "value": 15}, {"type": "Shots on Goal", "value": 6}]},
                        {"team": {"id": 20}, "statistics": [{"type": "Corner Kicks", "value": 4}, {"type": "Yellow Cards", "value": 3}, {"type": "Total Shots", "value": 10}, {"type": "Shots on Goal", "value": 4}]},
                    ],
                    "players": [],
                }
            else:
                t_id = 20 if fid >= 1200 else 10
                res[fid] = {
                    "fixture": {"id": fid, "status": {"short": "FT"}},
                    "teams": {"home": {"id": t_id}, "away": {"id": 99}},
                    "goals": {"home": 2, "away": 1},
                    "statistics": [
                        {"team": {"id": t_id}, "statistics": [{"type": "Corner Kicks", "value": 6}, {"type": "Yellow Cards", "value": 2}]},
                        {"team": {"id": 99}, "statistics": [{"type": "Corner Kicks", "value": 4}, {"type": "Yellow Cards", "value": 3}]},
                    ],
                    "players": [],
                }
        return res

    def h2h(self, home_id: int, away_id: int, count: int):
        return []

    def coverage(self, league_id: int, season: int):
        return {}

    def team_season_statistics(self, team_id: int, league_id: int, season: int):
        return {}


def test_full_dynamic_closed_loop():
    # 1. Base de datos aislada en memoria
    db = DatabaseManager(":memory:")
    api = MockAPI()

    # 2. Servicio con tracking activado
    service = AnalysisService(api, recent_count=6, h2h_count=5, detail_count=6, db=db, auto_track=True)

    # 3. Primer análisis: sin calibración previa
    report_initial = service.analyze("Real Madrid vs Barcelona")
    assert report_initial.fixture is not None
    assert report_initial.fixture.fixture_id == 8888
    assert len(report_initial.statistical_markets) > 0

    # Verificar que el pronóstico se guardó en la BD en estado PENDING
    pending = db.get_pending_fixtures()
    assert len(pending) == 1
    assert pending[0]["fixture_id"] == 8888
    preds = db.get_predictions_for_fixture(8888)
    assert len(preds) > 0
    assert all(p["status"] == "PENDING" for p in preds)

    # 4. Simular que el partido finaliza y se liquida con SettlementEngine
    engine = SettlementEngine(db, api)
    settle_res = engine.settle_fixture(8888)
    assert settle_res["status"] == "SETTLED"
    assert settle_res["summary"]["won"] + settle_res["summary"]["lost"] > 0

    # 5. Generar informe post-mortem con AICritic
    critic = AICritic(db)
    diagnostic = critic.generate_diagnostic_report()
    assert "Diagnóstico y Auditoría de Pronósticos" in diagnostic
    assert "Rendimiento Empírico por Mercado" in diagnostic

    # 6. Recalcular calibración: un solo partido real NO alcanza la muestra mínima
    calibrator = DynamicCalibrator(db)
    calibrator.recompute_calibrations()

    # 7. Segundo análisis: la calibración sigue inactiva y no se muestra badge
    report_calibrated = service.analyze("Real Madrid vs Barcelona")
    cal_info = report_calibrated.dynamic_calibration_info
    assert cal_info is not None
    assert cal_info.active is False

    rendered_md = format_adaptive_report(report_calibrated)
    assert "⚡ Calibración Dinámica:" not in rendered_md
    assert "acierto real" not in rendered_md
