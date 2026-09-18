from deport_ai.stats_engine import extract_player_shots, extract_team_matches


def test_extracts_fixture_stats_and_player_shots():
    row = {
        "fixture": {"id": 77, "date": "2026-01-01T00:00:00+00:00"},
        "teams": {"home": {"id": 1}, "away": {"id": 2}},
        "goals": {"home": 2, "away": 1},
        "statistics": [
            {
                "team": {"id": 1},
                "statistics": [
                    {"type": "Shots on Goal", "value": 6},
                    {"type": "Corner Kicks", "value": 5},
                    {"type": "Ball Possession", "value": "54%"},
                ],
            },
            {
                "team": {"id": 2},
                "statistics": [
                    {"type": "Shots on Goal", "value": 3},
                    {"type": "Corner Kicks", "value": 4},
                ],
            },
        ],
        "players": [
            {
                "team": {"id": 1},
                "players": [
                    {
                        "player": {"id": 9, "name": "Nueve"},
                        "statistics": [{"games": {"minutes": 90}, "shots": {"on": 2}}],
                    }
                ],
            }
        ],
    }
    matches = extract_team_matches([row], 1, {77: row})
    assert matches[0].goals_for == 2
    assert matches[0].stats_for["possession"] == 54
    assert matches[0].stats_against["corner_kicks"] == 4
    shots = extract_player_shots([row])
    assert shots[0].name == "Nueve"
    assert shots[0].shots_on_target == 2

