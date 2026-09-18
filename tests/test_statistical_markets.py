from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team
from deport_ai.statistical_markets import select_statistical_markets


def _probabilities() -> ProbabilityReport:
    return ProbabilityReport(
        home_win=0.72,
        draw=0.18,
        away_win=0.10,
        over_15=0.86,
        over_25=0.67,
        under_25=0.33,
        btts=0.52,
        expected_home_goals=2.1,
        expected_away_goals=0.8,
        shared_goal_component=0.0,
        score_matrix=[[1.0]],
        over_35=0.45,
        under_35=0.55,
        first_half_over_05=0.72,
        second_half_over_05=0.79,
        home_over_15=0.66,
    )


def test_extended_statistical_markets_are_model_only_and_deduplicated():
    home = Team(1, "Local")
    away = Team(2, "Visitante")
    expected = ExpectedMetrics(
        corners_home=6.2,
        corners_away=4.1,
        over_75_corners=0.82,
        over_95_corners=0.61,
        over_55_corners_home=0.68,
        over_45_corners_away=0.62,
        cards_home=2.2,
        cards_away=2.4,
        over_35_cards=0.71,
        over_15_cards_home=0.74,
        over_15_cards_away=0.77,
        total_shots_home=15.4,
        total_shots_away=10.8,
        over_215_total_shots=0.70,
        over_135_shots_home=0.65,
        shots_on_home=5.4,
        shots_on_away=3.8,
        over_75_shots_on=0.66,
        over_45_shots_on_home=0.64,
        offsides_home=1.9,
        offsides_away=1.4,
        over_25_offsides=0.68,
        player_shots={
            1: [{
                "name": "Delantero Local",
                "expected_per_match": 3.1,
                "probability_two_plus": 0.74,
                "probability_three_plus": 0.51,
                "probability_sot_one_plus": 0.66,
            }]
        },
    )

    markets = select_statistical_markets(home, away, _probabilities(), expected)

    assert markets
    assert any(item["category"] == "Córners" for item in markets)
    assert any(item["category"] == "Tarjetas" for item in markets)
    assert any(item["category"] == "Remates" for item in markets)
    assert any(item["category"] == "Jugadores" for item in markets)
    assert all(item["probability"] >= 0.60 for item in markets)
    assert all("odds" not in item and "edge" not in item for item in markets)
    assert all("risk" not in item for item in markets)
    assert all("casa" in item["basis"] for item in markets)
    assert sum(item["market"] == "Córners totales" for item in markets) == 1

    player_market = next(item for item in markets if item["category"] == "Jugadores")
    assert player_market["requires_starter_confirmation"] is True
