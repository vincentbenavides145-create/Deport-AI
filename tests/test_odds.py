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

