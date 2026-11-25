"""Factor árbitro en tarjetas, categorías suspendidas e ids verificados contra Sportmonks."""

from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team, TeamMatch
from deport_ai.sportmonks import SportmonksClient
from deport_ai.statistical_markets import SUSPENDED_CATEGORIES, select_statistical_markets
from deport_ai.stats_engine import (
    COUNTRY_TIER_ELO,
    apply_referee_factor,
    detect_altitude_impact,
    get_club_tier_offset,
    get_competition_profile,
    get_team_altitude,
)

HOME = Team(1, "Local")
AWAY = Team(2, "Visitante")


# ---------------------------------------------------------------- factor árbitro

def test_referee_factor_blends_with_shrinkage():
    home, away = apply_referee_factor(2.0, 2.0, (6.0, 45))
    # peso = 0.75 * 45 / (45 + 15) = 0.5625 -> total = 0.4375 * 4 + 0.5625 * 6 = 5.125
    assert abs((home + away) - 5.125) < 0.02
    assert home == away  # mantiene el reparto local/visitante


def test_referee_factor_ignored_without_enough_data():
    assert apply_referee_factor(2.0, 2.0, None) == (2.0, 2.0)
    assert apply_referee_factor(2.0, 2.0, (8.0, 3)) == (2.0, 2.0)  # menos de 5 partidos dirigidos
    assert apply_referee_factor(None, 2.0, (6.0, 40)) == (None, 2.0)


class FakeRefereeClient(SportmonksClient):
    def __init__(self):
        super().__init__("dummy")

    def _get(self, path, **params):
        if path == "fixtures/10":
            return {
                "season_id": 26763,
                "referees": [
                    {"referee_id": 900, "type_id": 7},
                    {"referee_id": 29044, "type_id": 6},
                ],
            }
        if path == "referees/29044":
            def season(sid, matches, yellow, red):
                return {
                    "season_id": sid,
                    "details": [
                        {"type": {"developer_name": "MATCHES"}, "value": {"count": matches}},
                        {"type": {"developer_name": "YELLOWCARDS"}, "value": {"all": {"count": yellow + 2, "on_pitch": yellow}}},
                        {"type": {"developer_name": "REDCARDS"}, "value": {"all": {"count": red}}},
                    ],
                }
            return {"statistics": [season(26763, 20, 93, 3), season(23265, 21, 125, 6)]}
        return None


def test_fixture_referee_picks_main_referee():
    assert FakeRefereeClient().fixture_referee(10) == {"referee_id": 29044, "season_id": 26763, "name": None}
    assert FakeRefereeClient().fixture_referee(None) is None


def test_referee_card_rate_counts_player_cards_and_can_exclude_season():
    client = FakeRefereeClient()
    # (93 + 3 + 125 + 6) / 41 partidos; usa las tarjetas en el campo, no las del banco
    assert client.referee_card_rate(29044) == (round(227 / 41, 3), 41)
    assert client.referee_card_rate(29044, exclude_season=26763) == (round(131 / 21, 3), 21)


# ---------------------------------------------------------------- categorías suspendidas

def _match(i):
    return TeamMatch(
        fixture_id=i, date=f"2026-10-{20 - i:02d}", team_id=1, opponent_id=50 + i, is_home=True,
        goals_for=1, goals_against=1, result="D",
        stats_for={"offsides": 1, "total_shots": 10}, stats_against={"offsides": 1},
    )


def test_player_props_and_offsides_are_suspended_by_default():
    assert SUSPENDED_CATEGORIES == {"Jugadores", "Fueras de juego", "Mitades"}
    probs = ProbabilityReport(
        home_win=0.5, draw=0.25, away_win=0.25, over_15=0.7, over_25=0.5, under_25=0.5, btts=0.5,
        expected_home_goals=1.4, expected_away_goals=1.1, score_matrix=[[1.0]],
    )
    expected = ExpectedMetrics(
        offsides_home=1.0, offsides_away=1.0, dispersion_offsides=0.1,
        player_shots={1: [{"name": "Nueve", "probability_two_plus": 0.75, "history_shots": [3, 2, 2, 3, 2, 3, 4, 2]}]},
    )
    rec = [_match(i) for i in range(8)]
    published = select_statistical_markets(HOME, AWAY, probs, expected, recent_home=rec, recent_away=rec)
    assert not {m["category"] for m in published} & SUSPENDED_CATEGORIES
    full = select_statistical_markets(
        HOME, AWAY, probs, expected, recent_home=rec, recent_away=rec, suspended_categories=frozenset()
    )
    assert {"Jugadores", "Fueras de juego"} <= {m["category"] for m in full}


# ---------------------------------------------------------------- altitud

def test_sao_paulo_is_not_treated_as_high_altitude():
    # 3496 es São Paulo en Sportmonks (antes figuraba como Bolívar, 3640 m)
    assert get_team_altitude(3496, "São Paulo", "5") == 0
    assert detect_altitude_impact(3496, "São Paulo", 1095, "Fluminense", "5", "5") is None


def test_altitude_ids_and_name_fallback_are_safe():
    assert get_team_altitude(6308, "Club Bolívar", "7598") == 3640
    assert get_team_altitude(None, "Club Bolívar", None) == 3640  # sin país conocido: por nombre
    # Equipos de llano con nombres parecidos: el país descarta la coincidencia
    assert get_team_altitude(None, "San Jose Earthquakes", "3483") == 0
    assert get_team_altitude(None, "Unión de Santa Fe", "44") == 0
    # Solo palabras completas
    assert get_team_altitude(None, "Gutcastle", None) == 0


def test_america_de_cali_and_pumas_tabasco_are_not_mexico_city():
    # "america" y "pumas" sueltos daban 2,240 m a América de Cali y a Pumas Tabasco.
    assert get_team_altitude(9269, "América de Cali", "353") < 2200
    assert get_team_altitude(None, "América de Cali", "353") == 0
    assert detect_altitude_impact(9269, "América de Cali", 4296, "Deportivo Cali", "353", "353") is None
    assert get_team_altitude(None, "Pumas Tabasco", "458") == 0
    assert get_team_altitude(2687, "América", "458") == 2240
    assert get_team_altitude(2989, "Pumas UNAM", "458") == 2240


# ---------------------------------------------------------------- ids de ligas y países

def test_league_profiles_use_sportmonks_ids():
    assert get_competition_profile(648).name == "Brasileirão"
    assert get_competition_profile(764).name == "Liga 1 Perú"
    assert get_competition_profile(672).name == "Liga BetPlay"
    assert get_competition_profile(968).name != "Liga 1 Perú"  # 968 es la J1 de Japón


def test_country_tiers_and_continental_bonus_use_sportmonks_ids():
    assert COUNTRY_TIER_ELO["5"] == 1720.0  # Brasil
    assert COUNTRY_TIER_ELO["462"] == 1820.0  # Inglaterra
    assert "2" not in COUNTRY_TIER_ELO  # el 2 es Polonia, no Italia
    assert get_club_tier_offset("Club Sin Tier", league_id=2451) == 0.0  # Club Friendlies 3


def test_cards_dispersion_follows_validated_values():
    from deport_ai.stats_engine import expected_metrics

    def m(i):
        return TeamMatch(
            fixture_id=i, date=f"2026-10-{20 - i:02d}", team_id=1, opponent_id=50 + i, is_home=i % 2 == 0,
            goals_for=1, goals_against=1, result="D",
            stats_for={"yellow_cards": 2, "total_shots": 10}, stats_against={"yellow_cards": 2, "total_shots": 9},
        )

    rec = [m(i) for i in range(8)]
    without = expected_metrics(rec, rec, [], 1, 2, league_id=648)
    with_ref = expected_metrics(rec, rec, [], 1, 2, league_id=648, referee_cards=(6.0, 60))
    assert without.dispersion_cards == 0.15
    assert with_ref.dispersion_cards == 0.05
    assert with_ref.cards_home + with_ref.cards_away > without.cards_home + without.cards_away


def test_report_shows_the_referee_used_in_the_card_projection():
    from types import SimpleNamespace

    from deport_ai.formatter import _referee_suffix

    used = SimpleNamespace(referee={"name": "Chris Kavanagh", "cards_per_match": 4.355, "matches": 72})
    assert _referee_suffix(used) == " (árbitro Chris Kavanagh: 4.36 por partido en 72)"
    assert _referee_suffix(SimpleNamespace(referee={"name": "X", "cards_per_match": 5.0, "matches": 3})) == ""
    assert _referee_suffix(SimpleNamespace(referee=None)) == ""


# ---------------------------------------------------------------- tabla de niveles de club

def test_club_tiers_need_the_whole_name_not_a_part_of_it():
    from deport_ai.stats_engine import get_club_tier_offset as tier

    # Clubes de la tabla con sus nombres en Sportmonks (partículas y números aparte).
    assert tier("FC Barcelona") == tier("Barcelona") == 180.0
    assert tier("FC Bayern München") == 200.0
    assert tier("Bayer 04 Leverkusen") == 170.0
    assert tier("AC Milan") == 170.0 and tier("Inter") == 180.0
    assert tier("FC St. Pauli") == -130.0 and tier("Angers SCO") == -130.0
    assert tier("Independiente Santa Fe") == tier("Santa Fe") == 85.0
    # Homónimos de otros países y filiales: antes heredaban el nivel del club grande.
    for other in ("Liverpool Montevideo", "Arsenal de Sarandí", "Barcelona SC", "Inter Turku", "Unión Santa Fe",
                  "Botafogo-SP", "Real Madrid Castilla", "Juventus Next Gen", "Benfica B", "Milan Futuro",
                  "Atalanta U23"):
        assert tier(other) == 0.0, other
    assert tier("Equipo sin tabla", league_id=2) == 120.0  # Champions: bonus genérico


def test_mid_altitude_visitors_reduce_the_altitude_gap():
    # Atlas (Guadalajara, ~1,566 m) en Toluca (2,660 m): ~1,100 m, bajo el umbral de 1,200 m.
    assert get_team_altitude(680, "Atlas", "458") == 1566
    assert detect_altitude_impact(967, "Toluca", 680, "Atlas", "458", "458") is None
    # Un visitante de llano sí recibe el ajuste.
    assert detect_altitude_impact(967, "Toluca", 11023, "Tijuana", "458", "458") is not None
    # Medellín (1,495 m) en Bogotá (2,640 m): 1,145 m, sin ajuste; Junior (Barranquilla) sí.
    assert detect_altitude_impact(12506, "Santa Fe", 6597, "Atlético Nacional", "353", "353") is None
    assert detect_altitude_impact(12506, "Santa Fe", 7792, "Junior FC", "353", "353") is not None
