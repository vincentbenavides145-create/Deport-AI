from deport_ai.domain import (
    AnalysisReport,
    Team,
    TeamMatch,
)
from deport_ai.formatter import format_adaptive_report
from deport_ai.presentation_catalog import MarketPresentationCatalog
from deport_ai.statistical_markets import (
    select_statistical_markets,
    select_top_recommended_pick,
)
from deport_ai.stats_engine import goal_probabilities, expected_metrics


def _sample_matches(team_id: int, n: int = 5) -> list[TeamMatch]:
    matches = []
    for i in range(n):
        matches.append(
            TeamMatch(
                fixture_id=100 + i,
                date=f"2026-03-{10 + i:02d}",
                team_id=team_id,
                opponent_id=999,
                is_home=(i % 2 == 0),
                goals_for=2,
                goals_against=1,
                result="W",
                opponent_name="Rival FC",
                stats_for={
                    "corner_kicks": 6.0,
                    "yellow_cards": 2.0,
                    "total_shots": 14.0,
                    "shots_on_goal": 5.0,
                    "offsides": 2.0,
                    "fouls": 13.0,
                },
                stats_against={
                    "corner_kicks": 4.0,
                    "yellow_cards": 3.0,
                    "total_shots": 9.0,
                    "shots_on_goal": 3.0,
                    "offsides": 1.0,
                    "fouls": 15.0,
                },
                competition_weight=1.0,
                league_id=564,
            )
        )
    return matches


def test_multigoals_and_combos_calculated():
    home_matches = _sample_matches(1, 5)
    away_matches = _sample_matches(2, 5)
    
    probs = goal_probabilities(
        home_matches=home_matches,
        away_matches=away_matches,
        elo_home=1600.0,
        elo_away=1500.0,
        league_id=564,
    )
    
    # Multigoles
    assert probs.multigoal_1_3 is not None
    assert 0.0 < probs.multigoal_1_3 <= 1.0
    assert probs.multigoal_2_4 is not None
    assert 0.0 < probs.multigoal_2_4 <= 1.0
    assert probs.multigoal_2_5 is not None
    assert 0.0 < probs.multigoal_2_5 <= 1.0
    
    # Combos 1X2 + BTTS
    assert probs.home_win_and_btts is not None
    assert probs.dc_1x_and_btts is not None
    assert probs.dc_1x_and_btts >= probs.home_win_and_btts
    assert probs.btts_second_half is not None
    assert 0.0 < probs.btts_second_half <= 1.0


def test_fouls_and_corners_1h_in_expected_metrics():
    home_matches = _sample_matches(1, 5)
    away_matches = _sample_matches(2, 5)
    
    exp = expected_metrics(
        home_matches=home_matches,
        away_matches=away_matches,
        player_rows=[],
        home_id=1,
        away_id=2,
        elo_home=1600.0,
        elo_away=1500.0,
        league_id=564,
    )
    
    assert exp.fouls_home is not None and exp.fouls_home > 0
    assert exp.fouls_away is not None and exp.fouls_away > 0
    assert exp.corners_first_half is not None and exp.corners_first_half > 0
    total_corners = (exp.corners_home or 0) + (exp.corners_away or 0)
    assert abs(exp.corners_first_half - (total_corners * 0.45)) < 0.1


def test_new_markets_catalog_presentation_rules():
    # Validar que las nuevas líneas declaradas son presentables
    assert MarketPresentationCatalog.is_presentable({
        "group": "multigoals",
        "selection": "1 a 3 goles",
        "side": "binary",
    })
    assert MarketPresentationCatalog.is_presentable({
        "group": "combo_1x2_btts",
        "selection": "Barcelona gana y Ambos Marcan",
        "side": "binary",
    })
    assert MarketPresentationCatalog.is_presentable({
        "group": "corners_first_half",
        "selection": "1T Más de 3.5 córners",
        "side": "over",
        "line": 3.5,
    })
    assert MarketPresentationCatalog.is_presentable({
        "group": "fouls_total",
        "selection": "Más de 23.5 faltas",
        "side": "over",
        "line": 23.5,
    })
    
    # Validar que líneas no catalogadas o triviales son rechazadas
    assert not MarketPresentationCatalog.is_presentable({
        "group": "fouls_total",
        "selection": "Más de 15.5 faltas",
        "side": "over",
        "line": 15.5,
    })


def test_select_top_recommended_pick_and_report_rendering():
    home = Team(id=1, name="Real Madrid", country="Spain")
    away = Team(id=2, name="Barcelona", country="Spain")
    home_matches = _sample_matches(1, 5)
    away_matches = _sample_matches(2, 5)
    
    probs = goal_probabilities(
        home_matches=home_matches,
        away_matches=away_matches,
        elo_home=1750.0,
        elo_away=1700.0,
        league_id=564,
    )
    exp = expected_metrics(
        home_matches=home_matches,
        away_matches=away_matches,
        player_rows=[],
        home_id=1,
        away_id=2,
        elo_home=1750.0,
        elo_away=1700.0,
        league_id=564,
    )
    
    selected_markets = select_statistical_markets(
        home=home,
        away=away,
        probabilities=probs,
        expected=exp,
        recent_home=home_matches,
        recent_away=away_matches,
    )
    
    top_pick = select_top_recommended_pick(
        selected_markets=selected_markets,
        recent_home=home_matches,
        recent_away=away_matches,
        probabilities=probs,
        expected=exp,
    )
    
    assert top_pick is not None
    assert top_pick["probability"] >= 0.60
    assert "selection" in top_pick
    assert "explanation" in top_pick
    
    report = AnalysisReport(
        home=home,
        away=away,
        fixture=None,
        recent_home=home_matches,
        recent_away=away_matches,
        h2h=[],
        probabilities=probs,
        expected=exp,
        elo_home=1750.0,
        elo_away=1700.0,
        injuries=[],
        lineups=[],
        odds={},
        risks=[],
        sources=[],
        generated_at="2026-09-21T18:00:00Z",
        statistical_markets=selected_markets,
        top_pick=top_pick,
    )
    
    rendered = format_adaptive_report(report)
    assert "### ⭐ PICK RECOMENDADO POR EL MODELO (AI Top Pick)" in rendered
    assert top_pick["selection"] in rendered
    assert f"{top_pick['probability'] * 100:.1f}%" in rendered
