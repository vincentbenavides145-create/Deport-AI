from deport_ai.sportmonks import _convert_fixture, _name_score


def test_converts_sportmonks_fixture_to_internal_contract():
    raw = {
        "id": 123,
        "league_id": 564,
        "season_id": 99,
        "starting_at": "2026-05-10 19:00:00",
        "starting_at_timestamp": 1_778_000_000,
        "state": {"developer_name": "FT"},
        "league": {"name": "La Liga"},
        "season": {"name": "2025/2026"},
        "participants": [
            {"id": 83, "name": "FC Barcelona", "meta": {"location": "home"}},
            {"id": 3468, "name": "Real Madrid", "meta": {"location": "away"}},
        ],
        "scores": [
            {"participant_id": 83, "description": "CURRENT", "score": {"goals": 2}},
            {"participant_id": 3468, "description": "CURRENT", "score": {"goals": 0}},
        ],
        "statistics": [
            {
                "participant_id": 83,
                "data": {"value": 6},
                "type": {"developer_name": "CORNERS"},
            },
            {
                "participant_id": 83,
                "data": {"value": 7},
                "type": {"developer_name": "SHOTS_ON_TARGET"},
            },
            {
                "participant_id": 83,
                "data": {"value": 1.8},
                "type": {"developer_name": "EXPECTED_GOALS"},
            },
        ],
        "lineups": [
            {
                "player_id": 10,
                "player_name": "Delantero",
                "team_id": 83,
                "details": [
                    {"data": {"value": 90}, "type": {"developer_name": "MINUTES_PLAYED"}},
                    {"data": {"value": 2}, "type": {"developer_name": "SHOTS_ON_TARGET"}},
                ],
            }
        ],
    }
    row = _convert_fixture(raw, "America/Lima")
    assert row["fixture"]["status"]["short"] == "FT"
    assert row["fixture"]["date"].endswith("-05:00")
    assert row["teams"]["home"]["id"] == 83
    assert row["goals"] == {"home": 2, "away": 0}
    assert row["statistics"][0]["statistics"][0] == {"type": "Corner Kicks", "value": 6}
    assert {"type": "Expected Goals", "value": 1.8} in row["statistics"][0]["statistics"]
    player = row["players"][0]["players"][0]
    assert player["statistics"][0]["shots"]["on"] == 2


def test_bare_barcelona_prefers_fc_barcelona():
    assert _name_score("Barcelona", "FC Barcelona") > _name_score(
        "Barcelona", "Barcelona Guayaquil"
    )


def test_sportmonks_client_parse_season_stats():
    from deport_ai.sportmonks import SportmonksClient

    client = SportmonksClient("test_token")
    mock_stats = [
        {"type": {"name": "Goals Scored"}, "value": {"home": 2.1, "away": 1.4}},
        {"type": {"name": "Goals Conceded"}, "value": {"home": 0.8, "away": 1.2}},
    ]
    parsed = client._parse_season_stats(mock_stats)
    assert parsed["goals"]["for"]["average"]["home"] == 2.1
    assert parsed["goals"]["for"]["average"]["away"] == 1.4
    assert parsed["goals"]["against"]["average"]["home"] == 0.8
    assert parsed["goals"]["against"]["average"]["away"] == 1.2


def test_sportmonks_client_dynamic_coverage():
    from deport_ai.sportmonks import SportmonksClient

    client = SportmonksClient("test_token")
    # Initial state defaults
    cov = client.coverage(384, 2024)
    assert cov["fixtures"]["lineups"] is True
    assert cov["odds"] is True

    # When plan capability is marked false on 403
    client._plan_capabilities["odds"] = False
    client._plan_capabilities["injuries"] = False
    cov_after = client.coverage(384, 2024)
    assert cov_after["odds"] is False
    assert cov_after["injuries"] is False

