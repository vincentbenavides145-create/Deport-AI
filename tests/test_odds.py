from deport_ai.odds import normalize_odds


def test_normalizes_common_markets():
    rows = [
        {
            "bookmakers": [
                {
                    "bets": [
                        {
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "2.10"},
                                {"value": "Draw", "odd": "3.20"},
                                {"value": "Away", "odd": "3.40"},
                            ],
                        },
                        {
                            "name": "Goals Over/Under",
                            "values": [{"value": "Over 2.5", "odd": "1.95"}],
                        },
                        {
                            "name": "Both Teams To Score",
                            "values": [{"value": "Yes", "odd": "1.80"}],
                        },
                    ]
                }
            ]
        }
    ]
    result = normalize_odds(rows)
    assert result["home_win"] == 2.1
    assert result["over_25"] == 1.95
    assert result["btts_yes"] == 1.8


def test_normalizes_v3_extended_betano_markets():
    rows = [
        {"market_description": "Double Chance", "label": "Home/Draw", "value": "1.14"},
        {"market_description": "Double Chance", "label": "Draw/Away", "value": "2.10"},
        {"market_description": "Draw No Bet", "label": "1", "value": "1.28"},
        {"market_description": "Asian Handicap", "label": "Home", "handicap": "-1.5", "value": "2.66"},
        {"market_description": "Asian Handicap", "label": "Away", "handicap": "+1.5", "value": "1.45"},
        {"market_description": "Goals Over/Under 1st Half", "label": "Over", "total": "0.5", "value": "1.36"},
        {"market_description": "Clean Sheet", "label": "1", "handicap": "Yes", "value": "2.20"},
        {"market_description": "Total - Home", "label": "Over", "total": "1.5", "value": "1.75"},
        {"market_description": "Corners Over Under", "label": "Over", "total": "8.5", "value": "1.75"},
        {"market_description": "Corners Over Under", "label": "Under", "total": "10.5", "value": "1.30"},
    ]
    result = normalize_odds(rows)
    assert result["double_chance_1x"] == 1.14
    assert result["double_chance_x2"] == 2.10
    assert result["dnb_home"] == 1.28
    assert result["ah_home_minus_15"] == 2.66
    assert result["ah_away_plus_15"] == 1.45
    assert result["first_half_over_05"] == 1.36
    assert result["clean_sheet_home"] == 2.20
    assert result["home_over_15"] == 1.75
    assert result["over_85_corners"] == 1.75
    assert result["under_105_corners"] == 1.30


