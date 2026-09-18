from deport_ai.domain import ConfidenceScore, FactorAttribution, PlayerShot, TeamMatch
from deport_ai.formatter import _observed_stats, _venue_form
from deport_ai.stats_engine import (
    _bivariate_poisson,
    _negative_binomial,
    _poisson,
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
    assert report.shared_goal_component > 0


def test_bivariate_poisson_preserves_independent_case_and_adds_shared_component():
    independent = _bivariate_poisson(1, 1, 1.2, 0.9, 0.0)
    assert abs(independent - _poisson(1, 1.2) * _poisson(1, 0.9)) < 1e-12
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


def test_visible_observed_stats_and_venue_form():
    assert "3 partidos" in _venue_form(HOME, True)
    rendered = _observed_stats(HOME)
    assert "al arco" in rendered
    assert "córners" in rendered


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

    # 4. Amistosos / Pretemporada
    assert classify_competition("Club Friendlies 1", 1101) == ("FRIENDLY", 0.20)
    assert classify_competition("Torneo de Verano Betano") == ("FRIENDLY", 0.20)
    assert classify_competition("Trofeo Joan Gamper") == ("FRIENDLY", 0.20)

    # 5. Competición Desconocida -> Zero-Trust UNKNOWN (0.00)
    assert classify_competition("Torneo Fantasma 2026") == ("UNKNOWN", 0.00)
    assert classify_competition("Copa Regional Desconocida XYZ") == ("DOMESTIC_CUP", 0.75)
    assert classify_competition("Exhibition Invitation Unknown") == ("FRIENDLY", 0.20)
    assert classify_competition("Random Tournament 123") == ("UNKNOWN", 0.00)


def test_extract_common_opponents():
    from deport_ai.stats_engine import extract_common_opponents

    home_m = [
        match(1, 10, 500, True, 3, 0, 6, 2, 7, 1),   # Opponent 500: Home won 3-0 (+3)
        match(2, 10, 600, False, 1, 1, 4, 4, 3, 3),  # Opponent 600: Home drew 1-1 (0)
        match(3, 10, 700, True, 2, 1, 5, 3, 6, 2),   # Opponent 700
    ]
    away_m = [
        match(4, 20, 500, False, 0, 2, 3, 7, 2, 6),  # Opponent 500: Away lost 0-2 (-2)
        match(5, 20, 600, True, 2, 0, 5, 2, 5, 2),   # Opponent 600: Away won 2-0 (+2)
        match(6, 20, 800, False, 1, 0, 4, 3, 4, 3),  # Opponent 800
    ]

    opps = extract_common_opponents(home_m, away_m)
    assert len(opps) == 2  # Opponents 500 and 600 are shared

    # Opponent 500: Home GD = +3, Away GD = -2 -> Net Advantage = +5
    opp500 = next(item for item in opps if item["opponent_id"] == 500)
    assert opp500["home_gd"] == 3
    assert opp500["away_gd"] == -2
    assert opp500["net_advantage"] == 5

    # Opponent 600: Home GD = 0, Away GD = +2 -> Net Advantage = -2
    opp600 = next(item for item in opps if item["opponent_id"] == 600)
    assert opp600["home_gd"] == 0
    assert opp600["away_gd"] == 2
    assert opp600["net_advantage"] == -2


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


def test_altitude_veto_and_starting_xi_clause_in_formatter():
    from deport_ai.domain import AnalysisReport, Team
    from deport_ai.formatter import format_report
    from deport_ai.stats_engine import detect_altitude_impact, expected_metrics, goal_probabilities

    home = Team(13264, "Club Cienciano")
    away = Team(198900, "Montevideo City Torque")
    impact = detect_altitude_impact(home.id, home.name, away.id, away.name)

    prob = goal_probabilities(HOME, AWAY, 1550.0, 1450.0, altitude_impact=impact)
    players = [
        PlayerShot(1, "Alejandro Hohberg", 13264, 2, 85, 5.0),
        PlayerShot(1, "Alejandro Hohberg", 13264, 3, 90, 6.0),
    ]
    expected = expected_metrics(HOME, AWAY, players, home.id, away.id, altitude_impact=impact)

    report = AnalysisReport(
        home=home,
        away=away,
        fixture=None,
        recent_home=HOME,
        recent_away=AWAY,
        h2h=[],
        probabilities=prob,
        expected=expected,
        elo_home=1550.0,
        elo_away=1450.0,
        injuries=[],
        lineups=[],
        odds={},
        opportunities=[],
        risks=[f"🏔️ FACTOR ALTITUD (3400 m.s.n.m.): {impact['description']}"],
        sources=["Sportmonks"],
        generated_at="2026-03-01T00:00:00",
    )

    rendered = format_report(report)

    # 1. Torque (+1.5 HA) NO debe aparecer recomendado
    assert "Montevideo City Torque (+1.5 Hándicap Asiático)" not in rendered

    # 2. Veto Estratégico explícito en la sección de Hándicap
    assert "VETO ESTRATÉGICO" in rendered
    assert "choque fisiológico a 3,400 m.s.n.m." in rendered

    # 3. Cláusula de Titularidad Oficial presente en remates de jugador
    assert "[⚠️ Sujeto a Titularidad Oficial]" in rendered
    assert "Cláusula de Titularidad:" in rendered

    # 4. Remates y tiros a puerta de equipo destacados
    assert "Remates de Equipo / Tiros a Puerta:" in rendered


def test_smart_player_prop_and_line_escalation_for_heavy_favorites():
    from deport_ai.domain import AnalysisReport, Team
    from deport_ai.formatter import _select_smart_player_prop, format_report
    from deport_ai.stats_engine import expected_metrics, goal_probabilities

    # 1. Test unitario directo de _select_smart_player_prop para superestrella (Mbappé)
    superstar_pl = {
        "name": "Kylian Mbappé",
        "appearances": 14,
        "expected_per_match": 4.8,
        "probability_two_plus": 0.956,      # Cuota 1.04 -> BASURA INJUGABLE
        "probability_three_plus": 0.845,
        "probability_four_plus": 0.715,     # Cuota ~1.40 -> Escalado viable
        "probability_five_plus": 0.520,
        "expected_shots_on_target": 2.4,
        "probability_sot_one_plus": 0.909,
        "probability_sot_two_plus": 0.692,  # Cuota ~1.70 -> ORO PURO EN APUESTAS
        "probability_sot_three_plus": 0.430,
    }
    smart_prop = _select_smart_player_prop(superstar_pl, "Real Madrid")
    # Para superestrella con p2 >= 0.85, DEBE escalar a 2+ Tiros al Arco (o 4+ remates), NUNCA 2+ remates
    assert smart_prop["is_escalated"] is True
    assert "Tiros al Arco" in smart_prop["prop_desc"] or "4+ Remates" in smart_prop["prop_desc"]
    assert smart_prop["probability"] < 0.85
    assert smart_prop["probability"] >= 0.60

    # 2. Test para jugador de volumen regular (p2 en sweet spot)
    regular_pl = {
        "name": "Federico Valverde",
        "appearances": 15,
        "expected_per_match": 2.1,
        "probability_two_plus": 0.620,
        "probability_three_plus": 0.350,
        "probability_four_plus": 0.150,
        "probability_five_plus": 0.050,
        "expected_shots_on_target": 0.9,
        "probability_sot_one_plus": 0.500,
        "probability_sot_two_plus": 0.250,
        "probability_sot_three_plus": 0.080,
    }
    reg_prop = _select_smart_player_prop(regular_pl, "Real Madrid")
    assert reg_prop["is_escalated"] is False
    assert "2+ Remates Totales" in reg_prop["prop_desc"]

    # 3. Test de integración en ticket decisivo para partido con favorito pesado
    home = Team(3468, "Real Madrid")
    away = Team(3458, "Rayo Vallecano")
    players = [
        PlayerShot(1, "Kylian Mbappé", 3468, 5, 90, 4.8),
        PlayerShot(1, "Kylian Mbappé", 3468, 4, 85, 4.8),
        PlayerShot(2, "Álvaro García", 3458, 1, 70, 1.2),
    ]
    prob = goal_probabilities(HOME, AWAY, 1850.0, 1400.0)  # Heavy favorite home win >= 0.70
    expected = expected_metrics(HOME, AWAY, players, home.id, away.id)

    report = AnalysisReport(
        home=home,
        away=away,
        fixture=None,
        recent_home=HOME,
        recent_away=AWAY,
        h2h=[],
        probabilities=prob,
        expected=expected,
        elo_home=1850.0,
        elo_away=1400.0,
        injuries=[],
        lineups=[],
        odds={},
        opportunities=[],
        risks=["Partido clave."],
        sources=["Sportmonks"],
        generated_at="2026-03-01T00:00:00",
    )
    rendered = format_report(report)

    # El jugador del partido para Mbappé NO debe ser "2+ Remates Totales — 95.6%" o similar cuota basura
    assert "Kylian Mbappé" in rendered
    assert "2+ Tiros al Arco" in rendered or "4+ Remates" in rendered
    assert "JUGADOR DEL PARTIDO: Kylian Mbappé" in rendered

    # Ninguna recomendación de córners Over ni remates Over para el Underdog en partido con favorito pesado
    assert "Rayo Vallecano Más de 4.5 Córners" not in rendered
    assert "Rayo Vallecano Más de 13.5 remates" not in rendered

    # Verificar que el ticket decisivo respeta el sweet spot global (60% a 80%)
    import re
    p1_match = re.search(r"PICK PRINCIPAL: (.*?) — (\d+\.\d+)%", rendered)
    p2_match = re.search(r"PICK SECUNDARIO: (.*?) — (\d+\.\d+)%", rendered)
    p_player_match = re.search(r"JUGADOR DEL PARTIDO: (.*?) — (\d+\.\d+)%", rendered)

    if p1_match:
        p1_val = float(p1_match.group(2))
        assert 60.0 <= p1_val <= 80.0, f"Pick principal {p1_val}% fuera del sweet spot 60-80%"
    if p2_match:
        p2_val = float(p2_match.group(2))
        assert 60.0 <= p2_val <= 80.0, f"Pick secundario {p2_val}% fuera del sweet spot 60-80%"
    if p_player_match:
        pp_val = float(p_player_match.group(2))
        assert 60.0 <= pp_val <= 80.0, f"Jugador del partido {pp_val}% fuera del sweet spot 60-80%"


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
        HOME + HOME, AWAY + AWAY, lineups_confirmed=True, odds_available=True
    )
    assert high_conf.score >= 75
    assert high_conf.level == "ALTA"
    assert high_conf.lineups_confirmed is True

    # 2. Baja/Media confianza: pocos partidos y alineación sin confirmar
    low_conf = calculate_confidence_score(
        HOME[:3], AWAY[:3], lineups_confirmed=False, odds_available=False
    )
    assert low_conf.score < high_conf.score
    assert low_conf.level in ("MEDIA", "BAJA")
    assert low_conf.lineups_confirmed is False


def test_factor_attribution_waterfall():
    prob = goal_probabilities(
        HOME, AWAY, 1750.0, 1450.0, league_id=8, rest_days_home=4.0, rest_days_away=2.0
    )
    ah = prob.attribution_home
    aa = prob.attribution_away
    assert ah is not None
    assert aa is not None

    # Verificar que los sumandos del waterfall de home reconstruyen el xG final (margen de redondeo <= 0.05)
    sum_h = ah.base_league_goals + ah.venue_impact + ah.elo_impact + ah.recent_form_impact + ah.rest_impact
    assert abs(sum_h - ah.final_expected_goals) <= 0.05

    # Para away, rest_days < 3 debe aplicar penalización de fatiga negativa
    assert aa.rest_impact < 0.0


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


def test_strict_minimum_60_percent_across_all_markets():
    from deport_ai.domain import AnalysisReport, ExpectedMetrics, ProbabilityReport, Team
    from deport_ai.formatter import format_report
    from deport_ai.odds import select_opportunities

    home = Team(1, "Equipo Local")
    away = Team(2, "Equipo Visitante")

    # Probabilidades con valores menores a 0.60
    prob = ProbabilityReport(
        home_win=0.58,  # < 0.60
        draw=0.22,
        away_win=0.20,
        over_15=0.75,   # >= 0.60
        over_25=0.55,   # < 0.60
        under_25=0.45,  # < 0.60
        btts=0.58,      # < 0.60
        expected_home_goals=1.6,
        expected_away_goals=1.0,
        shared_goal_component=0.0,
        score_matrix=[[1.0]],
        first_half_over_05=0.55,  # < 0.60
        second_half_over_05=0.62, # >= 0.60
    )

    # Expected metrics con líneas alrededor del 55-59%
    expected = ExpectedMetrics(
        corners_home=5.1,
        corners_away=4.2,
        over_45_corners_home=0.58,  # < 0.60 -> debe eliminarse
        over_55_corners_home=0.45,
        over_45_corners_away=0.52,
        over_75_corners=0.59,       # < 0.60 -> debe eliminarse
        over_85_corners=0.48,
        cards_home=2.0,
        cards_away=2.1,
        over_15_cards_home=0.59,    # < 0.60 -> debe eliminarse
        over_35_cards=0.54,         # < 0.60 -> debe eliminarse
        total_shots_home=12.0,
        total_shots_away=10.0,
        over_115_shots_home=0.59,   # < 0.60 -> debe eliminarse
        over_215_total_shots=0.58,  # < 0.60 -> debe eliminarse
        shots_on_home=4.2,
        shots_on_away=3.5,
        over_45_shots_on_home=0.59, # < 0.60 -> debe eliminarse
        over_75_shots_on=0.58,      # < 0.60 -> debe eliminarse
        over_05_woodwork=0.38,      # < 0.60 -> debe eliminarse
        offsides_home=1.5,
        offsides_away=1.2,
        over_25_offsides=0.58,      # < 0.60 -> debe eliminarse
        under_35_offsides=0.59,     # < 0.60 -> debe eliminarse
        player_shots={
            1: [{
                "name": "Jugador Borde",
                "appearances": 10,
                "expected_per_match": 1.8,
                "probability_two_plus": 0.58,  # < 0.60 -> debe eliminarse
                "probability_three_plus": 0.30,
                "probability_sot_one_plus": 0.55,
                "probability_sot_two_plus": 0.20,
            }]
        },
        anytime_goalscorers={
            1: [{
                "name": "Goleador Moderado",
                "appearances": 10,
                "probability_goal": 0.38,  # < 0.60 -> debe eliminarse
            }]
        },
    )

    report = AnalysisReport(
        home=home,
        away=away,
        fixture=None,
        recent_home=HOME,
        recent_away=AWAY,
        h2h=[],
        probabilities=prob,
        expected=expected,
        elo_home=1500.0,
        elo_away=1500.0,
        injuries=[],
        lineups=[],
        odds={"home_win": 2.20},  # Implied prob 45.4%, model 58% -> edge > 0.02 pero prob < 0.60
        opportunities=[],
        risks=["Sin novedades."],
        sources=["Sportmonks"],
        generated_at="2026-03-01T00:00:00",
    )

    rendered = format_report(report)

    # Verificar que NINGUNA línea destacada de apuesta tenga < 60%
    import re
    # Buscar cualquier porcentaje en el bloque de Líneas Destacadas
    if "Líneas de Apuesta Destacadas (≥ 60%):" in rendered:
        destacadas_part = rendered.split("Líneas de Apuesta Destacadas (≥ 60%):")[1].split("Jugadores con mayor probabilidad")[0]
        percentages = [float(p) for p in re.findall(r"\((\d+\.\d+)%\)", destacadas_part)]
        for p in percentages:
            assert p >= 60.0, f"Encontrada probabilidad {p}% < 60.0% en líneas destacadas"

    # Verificar que el prop de jugador con 58% fue descartado
    assert "Jugador Borde: 2+ Remates" not in rendered
    assert "No hay jugadores que superen el umbral de remates totales (≥60%)" in rendered

    # Verificar que el goleador con 38% fue descartado
    assert "Goleador Moderado" not in rendered

    # Verificar select_opportunities en odds.py con edge positivo pero prob < 0.60
    opps = select_opportunities(prob, {"home_win": 2.20})
    # Debe ser filtrado porque prob.home_win = 0.58 < 0.60
    assert not any(o["market"] == "Victoria local" for o in opps)
    assert all(o["probability"] >= 0.60 for o in opps)





