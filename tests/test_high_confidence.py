"""Lista de alta confianza y mercados débiles suspendidos (24/11/2026)."""

import importlib.util
from pathlib import Path

import pytest

import deport_ai.statistical_markets as sm
from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team
from deport_ai.dynamic_calibration import DynamicCalibrationSummary, side_key
from deport_ai.statistical_markets import market_type, select_high_confidence

ROOT = Path(__file__).resolve().parent.parent


def _c(cid, category, selection, probability, side=None, group=None, line=None, projection=None):
    return {"id": cid, "category": category, "market": category, "selection": selection, "probability": probability,
            "side": side, "group": group or cid, "explanation": "Porque sí.", "line": line, "projection": projection}


@pytest.fixture
def run(monkeypatch):
    def _run(candidates, factors=None):
        monkeypatch.setattr(sm, "calculate_candidate_markets", lambda *a, **k: [dict(c) for c in candidates])
        monkeypatch.setattr(sm.MarketPresentationCatalog, "is_presentable", staticmethod(lambda c: True))
        probs = ProbabilityReport(home_win=0.5, draw=0.25, away_win=0.25, over_15=0.7, over_25=0.5, under_25=0.5,
                                  btts=0.5, expected_home_goals=1.4, expected_away_goals=1.1, score_matrix=[[1.0]])
        summary = DynamicCalibrationSummary(True, 8, "PL", 100, 0.75, factors or {}, {})
        markets = sm.select_statistical_markets(Team(1, "A"), Team(2, "B"), probs, ExpectedMetrics(),
                                                calibration=summary)
        return {m["selection"] for m in markets}
    return _run


def _side(n=40):
    return {"hit_rate": 0.8, "shrinkage_factor": 1.0, "bias_offset": 0.0, "sample_size": n}


def test_team_corner_and_card_unders_are_suspended(run):
    factors = {side_key("Córners", "under"): _side(), side_key("Tarjetas", "under"): _side()}
    shown = run([
        _c("c1", "Córners", "B Menos de 5.5 córners", 0.82, "under", line=5.5, projection=2.5),
        _c("c2", "Córners", "Menos de 10.5 córners", 0.82, "under", line=10.5, projection=7.5),
        _c("t1", "Tarjetas", "A Menos de 2.5 tarjetas", 0.82, "under"),
        _c("t2", "Tarjetas", "A Más de 1.5 tarjetas", 0.82, "over"),
    ], factors)
    assert shown == {"Menos de 10.5 córners", "A Más de 1.5 tarjetas"}


def test_shots_on_target_race_is_suspended(run):
    shown = run([_c("s1", "Tiros al arco", "A tiene más tiros al arco", 0.82, "1x2", group="shots_on_1x2"),
                 _c("s2", "Tiros al arco", "Más de 6.5 tiros al arco", 0.82, "over")])
    assert shown == {"Más de 6.5 tiros al arco"}


def test_market_type_distinguishes_match_totals_and_teams():
    assert market_type({"category": "Faltas", "selection": "A Más de 10.5 faltas"}) == ("Faltas", "equipo", "over")
    assert market_type({"category": "Faltas", "selection": "Menos de 27.5 faltas"}) == ("Faltas", "total", "under")
    assert market_type({"category": "Resultado", "selection": "A o Empate (1X)"}) == ("Resultado", "equipo", None)


def test_high_confidence_is_the_most_probable_of_the_best_types():
    markets = [
        {"category": "Goles", "selection": "Más de 1.5 goles", "probability": 0.86},  # no es de los tipos
        {"category": "Remates", "selection": "Más de 21.5 remates", "probability": 0.81},
        {"category": "Tiros al arco", "selection": "Más de 6.5 tiros al arco", "probability": 0.83},
        {"category": "Faltas", "selection": "Menos de 27.5 faltas", "probability": 0.85},  # total "Menos": no
    ]
    assert select_high_confidence(markets)["selection"] == "Más de 6.5 tiros al arco"
    assert select_high_confidence(markets[:1]) is None
    # En el histórico se ordena por la probabilidad registrada.
    settled = [{"category": "Faltas", "selection": "A Más de 10.5 faltas", "predicted_prob": 0.80},
               {"category": "Remates", "selection": "Más de 21.5 remates", "predicted_prob": 0.84}]
    assert select_high_confidence(settled)["selection"] == "Más de 21.5 remates"


def test_report_counts_one_high_confidence_selection_per_fixture():
    spec = importlib.util.spec_from_file_location("track_cli", ROOT / "track.py")
    track = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(track)
    settled = [
        {"fixture_id": 1, "category": "Remates", "selection": "Más de 21.5 remates", "predicted_prob": 0.84, "status": "WON"},
        {"fixture_id": 1, "category": "Faltas", "selection": "A Más de 10.5 faltas", "predicted_prob": 0.80, "status": "LOST"},
        {"fixture_id": 2, "category": "Tiros al arco", "selection": "Más de 6.5 tiros al arco", "predicted_prob": 0.82, "status": "LOST"},
        {"fixture_id": 3, "category": "Goles", "selection": "Más de 1.5 goles", "predicted_prob": 0.85, "status": "WON"},
    ]
    assert track.high_confidence_record(settled) == (1, 1)


def test_report_shows_the_high_confidence_section():
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone

    from deport_ai.formatter import format_adaptive_report
    from deport_ai.storage import DatabaseManager
    from tests.test_settlement_tracking_fixes import _analyze  # análisis completo con datos de prueba

    report = _analyze(DatabaseManager(":memory:"), (datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    assert report.high_confidence is None  # ninguna de sus selecciones es de los tipos elegidos
    assert "🎯 Alta confianza" not in format_adaptive_report(report)
    high = {"category": "Faltas", "selection": "Local Más de 10.5 faltas", "probability": 0.83}
    text = format_adaptive_report(replace(report, high_confidence=high))
    assert "🎯 Alta confianza" in text and "Local Más de 10.5 faltas — 83.0%" in text


def test_club_tier_coverage_counts_fixtures_with_a_listed_club():
    from types import SimpleNamespace

    from deport_ai.backtesting import club_tier_coverage
    from deport_ai.domain import TeamMatch

    def matches(team_id):
        return [TeamMatch(fixture_id=team_id * 100 + i, date=f"2026-01-{i + 1:02d}", team_id=team_id, opponent_id=9,
                          opponent_name="X", is_home=True, goals_for=1, goals_against=0, result="W") for i in range(8)]

    def sample(fid, home, away):
        return SimpleNamespace(fixture_id=fid, date="2026-03-01", league_id=8, home_name=home, away_name=away,
                               home=SimpleNamespace(team_id=1), away=SimpleNamespace(team_id=2))

    by_team = {1: matches(1), 2: matches(2)}
    fixtures = [sample(1, "Arsenal", "Brentford"), sample(2, "Brentford", "Fulham")]
    assert club_tier_coverage(fixtures, by_team) == (2, 1)
