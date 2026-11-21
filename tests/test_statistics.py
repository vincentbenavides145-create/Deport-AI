import math
from deport_ai.domain import PlayerShot, TeamMatch
from deport_ai.stats_engine import (
    _bivariate_poisson,
    _negative_binomial,
    _robust_count_mean,
    calculate_confidence_score,
    calculate_elo,
    expected_metrics,
    get_competition_profile,
    goal_probabilities,
)


def match(
    fixture_id: int,
    team_id: int,
    opponent_id: int,
    is_home: bool,
    goals_for: int,
    goals_against: int,
    corners_for: float,
    corners_against: float,
    shots_for: float,
    shots_against: float,
) -> TeamMatch:
    return TeamMatch(
        fixture_id=fixture_id,
        date=f"2026-01-{fixture_id:02d}T00:00:00+00:00",
        team_id=team_id,
        opponent_id=opponent_id,
        is_home=is_home,
        goals_for=goals_for,
        goals_against=goals_against,
        result="W" if goals_for > goals_against else "D" if goals_for == goals_against else "L",
        stats_for={"corner_kicks": corners_for, "shots_on_goal": shots_for},
        stats_against={"corner_kicks": corners_against, "shots_on_goal": shots_against},
    )


HOME = [
    match(1, 10, 31, True, 2, 0, 6, 3, 7, 2),
    match(2, 10, 32, False, 1, 1, 4, 5, 4, 4),
    match(3, 10, 33, True, 3, 1, 7, 2, 8, 3),
    match(4, 10, 34, False, 0, 1, 3, 6, 2, 5),
    match(5, 10, 35, True, 2, 2, 5, 5, 6, 5),
    match(6, 10, 36, False, 2, 1, 4, 4, 5, 3),
]
AWAY = [
    match(7, 20, 41, False, 1, 2, 3, 7, 3, 6),
    match(8, 20, 42, True, 2, 0, 5, 2, 6, 2),
    match(9, 20, 43, False, 1, 1, 4, 4, 4, 4),
    match(10, 20, 44, True, 0, 1, 6, 3, 3, 4),
    match(11, 20, 45, False, 2, 2, 5, 5, 5, 5),
    match(12, 20, 46, True, 3, 1, 8, 2, 7, 2),
]


def test_probabilities_are_normalized():
    elo_home, elo_away = calculate_elo(HOME, AWAY, 10, 20)
    report = goal_probabilities(HOME, AWAY, elo_home, elo_away)
    assert abs(report.home_win + report.draw + report.away_win - 1.0) < 1e-9
    assert abs(report.over_25 + report.under_25 - 1.0) < 1e-9
    assert abs(sum(map(sum, report.score_matrix)) - 1.0) < 1e-9
    assert 0 < report.btts < 1


def test_bivariate_poisson_preserves_independent_case_and_adds_shared_component():
    independent = _bivariate_poisson(1, 1, 1.2, 0.9, 0.0)
    poisson = lambda k, lam: math.exp(-lam) * lam**k / math.factorial(k)
    assert abs(independent - poisson(1, 1.2) * poisson(1, 0.9)) < 1e-12
    assert _bivariate_poisson(1, 1, 1.2, 0.9, 0.15) > independent


def test_expected_corners_shots_and_players_use_observations():
    players = [
        PlayerShot(99, "Delantero", 10, 1, 80),
        PlayerShot(99, "Delantero", 10, 2, 70),
        PlayerShot(88, "Muestra corta", 10, 1, 20),
    ]
    expected = expected_metrics(HOME, AWAY, players, 10, 20)
    assert expected.corners_home is not None
    assert expected.corners_away is not None
    assert expected.shots_on_home is not None
    assert expected.player_shots[10][0]["name"] == "Delantero"
    assert expected.player_shots[20] == []


def test_robust_count_mean_limits_single_extreme_match():
    assert _robust_count_mean([7, 11, 26]) == 11


def test_zero_trust_classify_competition():
    from deport_ai.stats_engine import classify_competition

    # 1. Ligas oficiales reconocidas
    assert classify_competition("Serie A", 384) == ("OFFICIAL_LEAGUE", 1.00)
    assert classify_competition("Premier League", 8) == ("OFFICIAL_LEAGUE", 1.00)
    assert classify_competition("Liga 1", 968) == ("OFFICIAL_LEAGUE", 1.00)

    # 2. Copas nacionales oficiales
    assert classify_competition("Coppa Italia", 390) == ("DOMESTIC_CUP", 0.75)
    assert classify_competition("FA Cup", 24) == ("DOMESTIC_CUP", 0.75)
    assert classify_competition("DFB Pokal", 109) == ("DOMESTIC_CUP", 0.75)

    # 3. Supercopas
    assert classify_competition("Supercoppa Italiana") == ("SUPERCUP", 0.60)
    assert classify_competition("Community Shield") == ("SUPERCUP", 0.60)

    # 4. Amistosos / Pretemporada (Ponderación reducida a 0.10)
    assert classify_competition("Club Friendlies 1", 1101) == ("FRIENDLY", 0.10)
    assert classify_competition("Torneo de Verano Betano") == ("FRIENDLY", 0.10)
    assert classify_competition("Trofeo Joan Gamper") == ("FRIENDLY", 0.10)

    # 5. Competición Desconocida -> Zero-Trust UNKNOWN (0.00)
    assert classify_competition("Torneo Fantasma 2026") == ("UNKNOWN", 0.00)
    assert classify_competition("Copa Regional Desconocida XYZ") == ("DOMESTIC_CUP", 0.75)
    assert classify_competition("Exhibition Invitation Unknown") == ("FRIENDLY", 0.10)
    assert classify_competition("Random Tournament 123") == ("UNKNOWN", 0.00)


def test_detect_altitude_impact():
    from deport_ai.stats_engine import detect_altitude_impact

    # 1. Cienciano (Cusco, 3,400m) vs Torque (Nivel del mar, 0m) -> EXTREME
    impact_cienciano = detect_altitude_impact(13264, "Club Cienciano", 198900, "Montevideo City Torque")
    assert impact_cienciano is not None
    assert impact_cienciano["home_altitude"] == 3400
    assert impact_cienciano["away_altitude"] == 0
    assert impact_cienciano["delta"] == 3400
    assert impact_cienciano["severity"] == "EXTREME"
    assert impact_cienciano["disallow_away_handicap"] is True
    assert impact_cienciano["lambda_home_mult"] == 1.25
    assert impact_cienciano["lambda_away_mult"] == 0.70

    # 2. Always Ready (El Alto, 4,150m) vs Lowland team
    impact_ar = detect_altitude_impact(10769, "Always Ready", 200, "Boca Juniors")
    assert impact_ar is not None
    assert impact_ar["home_altitude"] == 4150
    assert impact_ar["severity"] == "EXTREME"
    assert impact_ar["disallow_away_handicap"] is True

    # 3. Partidos a nivel del mar (Manchester United vs Sabah) -> None
    impact_lowland = detect_altitude_impact(14, "Manchester United", 50, "Sabah")
    assert impact_lowland is None

    # 4. Ambos equipos en la misma altitud (Millonarios vs Santa Fe en Bogotá a 2,640m) -> Delta = 0 -> None
    impact_bogota = detect_altitude_impact(10197, "Millonarios", 10198, "Santa Fe")
    assert impact_bogota is None


def test_altitude_impact_on_probabilities_and_metrics():
    from deport_ai.stats_engine import detect_altitude_impact, expected_metrics, goal_probabilities

    impact = detect_altitude_impact(13264, "Club Cienciano", 198900, "Montevideo City Torque")
    assert impact is not None

    base_prob = goal_probabilities(HOME, AWAY, 1500.0, 1500.0)
    alt_prob = goal_probabilities(HOME, AWAY, 1500.0, 1500.0, altitude_impact=impact)

    # El ajuste de altitud debe incrementar goles esperados locales y reducir los del visitante
    assert alt_prob.expected_home_goals > base_prob.expected_home_goals
    assert alt_prob.expected_away_goals < base_prob.expected_away_goals
    assert alt_prob.home_win > base_prob.home_win

    # Partidos con total_shots incluidos
    home_with_shots = [
        TeamMatch(
            fixture_id=i,
            date=f"2026-01-0{i}T00:00:00+00:00",
            team_id=13264,
            opponent_id=50,
            is_home=True,
            goals_for=2,
            goals_against=0,
            result="W",
            stats_for={"corner_kicks": 6, "shots_on_goal": 7, "total_shots": 16},
            stats_against={"corner_kicks": 2, "shots_on_goal": 2, "total_shots": 6},
        )
        for i in range(1, 6)
    ]
    away_with_shots = [
        TeamMatch(
            fixture_id=i,
            date=f"2026-01-0{i}T00:00:00+00:00",
            team_id=198900,
            opponent_id=60,
            is_home=False,
            goals_for=1,
            goals_against=1,
            result="D",
            stats_for={"corner_kicks": 3, "shots_on_goal": 3, "total_shots": 8},
            stats_against={"corner_kicks": 5, "shots_on_goal": 5, "total_shots": 14},
        )
        for i in range(6, 11)
    ]

    players = [PlayerShot(1, "Alejandro Hohberg", 13264, 2, 85, 4.0)]
    base_exp = expected_metrics(home_with_shots, away_with_shots, players, 13264, 198900)
    alt_exp = expected_metrics(home_with_shots, away_with_shots, players, 13264, 198900, altitude_impact=impact)

    # Córners y remates del local aumentan por la altitud y balón rápido
    assert alt_exp.corners_home > base_exp.corners_home
    assert alt_exp.total_shots_home > base_exp.total_shots_home
    assert alt_exp.shots_on_home > base_exp.shots_on_home


def test_negative_binomial_vs_poisson():
    import math
    rate = 4.2
    # Cuando alpha = 0, coincide exactamente con Poisson
    for k in range(8):
        nb_zero = _negative_binomial(k, rate, alpha=0.0)
        poisson_val = math.exp(-rate) * (rate**k) / math.factorial(k)
        assert abs(nb_zero - poisson_val) < 1e-7

    # Con alpha > 0 (sobre-dispersión), las colas son más pesadas que Poisson
    alpha = 0.20
    # Cola alta (ej. k = 10 corners) debe tener mayor probabilidad en Binomial Negativa
    p_high_nb = _negative_binomial(10, rate, alpha=alpha)
    p_high_poisson = _negative_binomial(10, rate, alpha=0.0)
    assert p_high_nb > p_high_poisson

    # Suma de probabilidades debe converger a ~1.0
    total_nb = sum(_negative_binomial(k, rate, alpha=alpha) for k in range(35))
    assert abs(total_nb - 1.0) < 0.001


def test_competition_profiles():
    premier = get_competition_profile(8, "Premier League")
    assert premier.home_advantage == 1.09
    assert premier.base_goals == 2.85

    laliga = get_competition_profile(564, "La Liga")
    assert laliga.home_advantage == 1.12
    assert laliga.base_goals == 2.52

    libertadores = get_competition_profile(None, "Copa Libertadores")
    assert libertadores.home_advantage == 1.24
    assert libertadores.away_advantage == 0.76

    default_prof = get_competition_profile(99999, "Liga Desconocida")
    assert default_prof.home_advantage == 1.12
    assert default_prof.base_goals == 2.60


def test_calculate_confidence_score():
    # 1. Alta confianza: 20 partidos, todos con tiros/córners, alineación confirmada
    high_conf = calculate_confidence_score(
        HOME + HOME, AWAY + AWAY, lineups_confirmed=True
    )
    assert high_conf.score >= 75
    assert high_conf.level == "ALTA"
    assert high_conf.lineups_confirmed is True

    # 2. Baja/Media confianza: pocos partidos y alineación sin confirmar
    low_conf = calculate_confidence_score(
        HOME[:3], AWAY[:3], lineups_confirmed=False
    )
    assert low_conf.score < high_conf.score
    assert low_conf.level in ("MEDIA", "BAJA")
    assert low_conf.lineups_confirmed is False


def test_starter_and_expected_minutes_scaling():
    players = [
        PlayerShot(10, "Delantero Estrella", 1, 5, 90, 3.5),
        PlayerShot(10, "Delantero Estrella", 1, 4, 90, 3.5),
    ]

    # Proyección con titular confirmado (75 min)
    starters_map = {10: {"is_starter": True, "expected_minutes": 75.0}}
    metrics_starter = expected_metrics(
        HOME, AWAY, players, 1, 2, starter_info=starters_map
    )
    pl_starter = metrics_starter.player_shots[1][0]

    # Proyección con suplente confirmado (22 min)
    bench_map = {10: {"is_starter": False, "expected_minutes": 22.0}}
    metrics_bench = expected_metrics(
        HOME, AWAY, players, 1, 2, starter_info=bench_map
    )
    pl_bench = metrics_bench.player_shots[1][0]

    # El suplente debe tener sustancialmente menos tiros esperados y menor probabilidad
    assert pl_bench["expected_total_shots"] < pl_starter["expected_total_shots"]
    assert pl_bench["probability_one_plus"] < pl_starter["probability_one_plus"]
    assert pl_bench["expected_minutes"] == 22.0
    assert pl_starter["expected_minutes"] == 75.0


def test_club_tier_offsets_and_sos():
    from deport_ai.stats_engine import (
        get_club_tier_offset,
        get_sos_multiplier,
        calculate_elo,
    )

    # 1. Tier 1 matches
    assert get_club_tier_offset("Real Madrid") == 200.0
    assert get_club_tier_offset("AC Milan") == 170.0
    assert get_club_tier_offset("Paris Saint Germain") == 180.0
    assert get_club_tier_offset("PSG") == 180.0

    # 2. Tier 2 matches
    assert get_club_tier_offset("Borussia Dortmund") == 110.0
    assert get_club_tier_offset("Benfica") == 100.0

    # 3. Tier 4 matches
    assert get_club_tier_offset("US Lecce") == -130.0
    assert get_club_tier_offset("Lecce") == -130.0
    assert get_club_tier_offset("Venezia FC") == -140.0

    # 4. Unknown team fallback
    assert get_club_tier_offset("Equipo Desconocido FC") == 0.0

    # 5. Continental competition fallback
    # Ids de Sportmonks: 2 Champions League, 5 Europa League; 2451 son amistosos de clubes.
    assert get_club_tier_offset("Club Sin Tier", league_id=2) == 120.0  # Champions League
    assert get_club_tier_offset("Club Sin Tier", league_id=5) == 60.0   # Europa League
    assert get_club_tier_offset("Club Sin Tier", league_id=2451) == 0.0  # Club Friendlies 3

    # 6. SoS multipliers
    # Against elite club (Real Madrid +200):
    sos_gf_elite = get_sos_multiplier("Real Madrid", None, "goals_for")
    assert sos_gf_elite > 1.15  # extra credit for scoring against elite
    sos_ga_elite = get_sos_multiplier("Real Madrid", None, "goals_against")
    assert sos_ga_elite < 0.85  # diminished penalty for conceding against elite

    # Against weak club (Lecce -130):
    sos_gf_weak = get_sos_multiplier("Lecce", None, "goals_for")
    assert sos_gf_weak < 0.90   # discounted credit for scoring against weak opponent
    sos_ga_weak = get_sos_multiplier("Lecce", None, "goals_against")
    assert sos_ga_weak > 1.10   # penalized for conceding against weak opponent

    # 7. Elo calculation with team names creates proper stratification
    elo_milan, elo_lecce = calculate_elo(
        HOME, AWAY, 10, 20,
        home_league=384, away_league=384,
        home_name="AC Milan", away_name="US Lecce"
    )
    # Milan should have a significantly higher Elo than Lecce
    assert elo_milan > elo_lecce + 200.0
