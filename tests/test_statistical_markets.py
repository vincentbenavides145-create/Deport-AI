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
                "history_shots": [3, 2, 4, 2, 3, 1, 2, 3],
                "history_sot": [1, 1, 0, 1, 2, 1, 1, 0],
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


def test_extended_betano_markets_are_included_and_adaptive():
    home = Team(1, "Alianza")
    away = Team(2, "Comerciantes")
    probs = _probabilities()
    probs.dnb_home = 0.84
    probs.ah_away_plus_25 = 0.75
    expected = ExpectedMetrics(
        over_05_woodwork=0.74,
        corners_home=None,
        corners_away=None,
    )

    markets = select_statistical_markets(home, away, probs, expected)
    categories = {m["category"] for m in markets}

    # Verifica mercados tipo Betano
    # Regla 5: doble oportunidad y DNB son la misma familia de resultado -> una sola selección
    result_family = [
        m for m in markets
        if "Doble oportunidad" in m["market"] or "Empate apuesta no válida" in m["market"] or m["market"] == "Resultado del partido"
    ]
    assert len(result_family) == 1
    # Regla 3: +0.5 goles por mitad es una línea trivial y nunca se presenta
    assert not any(m["selection"] in ("1T Más de 0.5 goles", "2T Más de 0.5 goles") for m in markets)
    assert any(m["category"] == "Especiales" for m in markets)

    # Verifica adaptabilidad: si no hay métricas de córners >= 60%, NO debe figurar Córners
    assert "Córners" not in categories
    assert all(m["probability"] >= 0.60 for m in markets)
    # Verifica que NO existan apuestas de hándicap bajo ninguna circunstancia
    assert not any("hándicap" in m["market"].lower() or "handicap" in m["market"].lower() or "Hándicap" in m["category"] for m in markets)
    # Verifica que cada categoría tenga como máximo 4 apuestas
    from collections import Counter
    cat_counts = Counter(m["category"] for m in markets)
    assert all(count <= 4 for count in cat_counts.values())


def test_uncalculated_fields_do_not_produce_artificial_100_percent():
    home = Team(1, "Local")
    away = Team(2, "Visitante")
    # Instanciación básica con campos de mitad y portería a cero en None
    probs = ProbabilityReport(
        home_win=0.55,
        draw=0.25,
        away_win=0.20,
        over_15=0.70,
        over_25=0.50,
        under_25=0.50,
        btts=0.50,
        expected_home_goals=1.5,
        expected_away_goals=1.0,
        shared_goal_component=0.0,
        score_matrix=[[1.0]],
        first_half_over_15=None,  # No calculado / No disponible
        clean_sheet_away=None,    # No calculado / No disponible
    )
    expected = ExpectedMetrics()

    markets = select_statistical_markets(home, away, probs, expected)
    # No debe existir ninguna apuesta con 100.0% artificial
    assert not any(m["probability"] >= 1.0 for m in markets)
    # "1T Menos de 1.5 goles" no debe generarse falsamente porque su complemento no estaba disponible
    assert not any("1T Menos de 1.5 goles" in m["selection"] for m in markets)
    # "Local Más de 0.5 goles" no debe generarse falsamente desde clean_sheet_away en None
    assert not any(f"{home.name} Más de 0.5 goles" in m["selection"] for m in markets)


def test_corners_1x2_has_no_label_and_requires_valid_metrics():
    home = Team(1, "Local")
    away = Team(2, "Visitante")
    probs = _probabilities()
    expected = ExpectedMetrics(
        corners_home=6.5,
        corners_away=3.2,
        corners_1x2_home=0.64,
        corners_1x2_tie=0.11,
        corners_1x2_away=0.25,
    )
    markets = select_statistical_markets(home, away, probs, expected)
    corner_1x2 = next((m for m in markets if m["market"] == "Córners 1X2"), None)
    assert corner_1x2 is not None
    # Sin etiquetas internas en la selección publicada
    assert corner_1x2["selection"] == "Local saca más córners"
    assert "calibración histórica" in corner_1x2["basis"]


def test_cards_valid_presentation_lines_used_and_trivial_15_excluded():
    """Verifica que Más de 1.5 tarjetas totales quede excluida por trivial y se seleccione una línea válida del catálogo."""
    home = Team(3608, "Racing Club")
    away = Team(9931, "Sarmiento")
    probs = _probabilities()
    # Caso real de Racing vs Sarmiento: 1.67 tarjetas local + 1.53 visitante = 3.20 tarjetas
    expected = ExpectedMetrics(
        cards_home=1.67,
        cards_away=1.53,
        dispersion_cards=0.27,
    )

    markets = select_statistical_markets(home, away, probs, expected)
    card_markets = [m for m in markets if m["category"] == "Tarjetas"]

    assert card_markets, "Debe existir al menos un mercado de tarjetas seleccionado"
    total_card = next((m for m in card_markets if m["market"] == "Tarjetas totales"), None)
    assert total_card is not None, "Debe seleccionarse una línea de Tarjetas totales"
    # No debe ser la línea trivial (+1.5), sino una línea válida del catálogo (Menos de 4.5 tarjetas al ser más segura)
    assert "Más de 1.5 tarjetas" not in total_card["selection"]
    assert "Menos de 4.5 tarjetas" in total_card["selection"]
    assert total_card["probability"] >= 0.60
    assert "3.20" in total_card["explanation"]


def test_metric_families_evaluate_low_medium_high_lines():
    """Verifica que todas las familias de métricas de conteo evalúen líneas bajas, medias y altas."""
    home = Team(1, "Equipo A")
    away = Team(2, "Equipo B")
    probs = _probabilities()
    expected = ExpectedMetrics(
        cards_home=2.5,
        cards_away=2.5,
        corners_home=5.5,
        corners_away=4.5,
        total_shots_home=16.0,
        total_shots_away=12.0,
        shots_on_home=6.0,
        shots_on_away=4.0,
        offsides_home=2.5,
        offsides_away=2.0,
    )

    from deport_ai.statistical_markets import calculate_candidate_markets

    candidates = calculate_candidate_markets(home, away, probs, expected)

    # Tarjetas: debe evaluar +1.5 (baja), +3.5 (media), +5.5 (alta)
    card_lines = {c["selection"] for c in candidates if c["category"] == "Tarjetas" and "totales" in c["market"]}
    assert "Más de 1.5 tarjetas" in card_lines
    assert "Más de 3.5 tarjetas" in card_lines
    assert "Más de 5.5 tarjetas" in card_lines

    # Córners: debe evaluar +3.5 (baja), +7.5 (media), +11.5 (alta)
    corner_lines = {c["selection"] for c in candidates if c["category"] == "Córners" and "totales" in c["market"]}
    assert "Más de 3.5 córners" in corner_lines
    assert "Más de 7.5 córners" in corner_lines
    assert "Más de 11.5 córners" in corner_lines

    # Remates: debe evaluar +15.5 (baja), +21.5 (media), +29.5 (alta)
    shot_lines = {c["selection"] for c in candidates if c["category"] == "Remates" and "totales" in c["market"]}
    assert "Más de 15.5 remates" in shot_lines
    assert "Más de 21.5 remates" in shot_lines
    assert "Más de 29.5 remates" in shot_lines

    # Tiros a puerta: debe evaluar +4.5 (baja), +7.5 (media), +10.5 (alta)
    sot_lines = {c["selection"] for c in candidates if c["category"] == "Tiros a puerta" and "totales" in c["market"]}
    assert "Más de 4.5 tiros a puerta" in sot_lines
    assert "Más de 7.5 tiros a puerta" in sot_lines
    assert "Más de 10.5 tiros a puerta" in sot_lines

    # Offsides: debe evaluar +1.5 (baja), +3.5 (media), +5.5 (alta)
    offside_lines = {c["selection"] for c in candidates if c["category"] == "Fueras de juego" and "totales" in c["market"]}
    assert "Más de 1.5 fueras de juego" in offside_lines
    assert "Más de 3.5 fueras de juego" in offside_lines
    assert "Más de 5.5 fueras de juego" in offside_lines


def test_no_conflicting_or_redundant_markets_in_same_subgroup():
    """Verifica que no aparezcan mercados contradictorios o múltiples en el mismo subgrupo."""
    home = Team(1, "Equipo A")
    away = Team(2, "Equipo B")
    probs = _probabilities()
    expected = ExpectedMetrics(
        cards_home=2.0,
        cards_away=2.0,
        corners_home=6.0,
        corners_away=5.0,
    )

    markets = select_statistical_markets(home, away, probs, expected)

    # Solo una línea de tarjetas totales
    assert sum(m["market"] == "Tarjetas totales" for m in markets) <= 1
    # Solo una línea de córners totales
    assert sum(m["market"] == "Córners totales" for m in markets) <= 1
    # Solo una línea de goles totales
    assert sum(m["market"] == "Goles totales" for m in markets) <= 1
    # Solo una línea de doble oportunidad
    assert sum(m["market"] == "Doble oportunidad" for m in markets) <= 1


def test_complete_independence_from_commercial_bookmakers_and_odds():
    """Verifica que ningún mercado contenga referencias a cuotas, edge, valor o filtros de casas comerciales."""
    home = Team(1, "Local")
    away = Team(2, "Visitante")
    probs = _probabilities()
    expected = ExpectedMetrics(
        cards_home=2.0,
        cards_away=2.0,
        corners_home=5.0,
        corners_away=5.0,
    )

    markets = select_statistical_markets(home, away, probs, expected)

    for m in markets:
        assert "odds" not in m
        assert "cuota" not in m
        assert "edge" not in m
        assert "value" not in m
        assert "betano" not in str(m).lower()
        assert m["probability"] >= 0.60


def test_trivial_lines_blocked_even_with_high_probability():
    """Verifica que líneas triviales (+3.5 córners, +0.5 tarjetas equipo, etc.) no se muestren aunque tengan 90%+."""
    home = Team(1, "Local")
    away = Team(2, "Visitante")
    probs = _probabilities()
    # Métricas altas que generarían altísima probabilidad en líneas triviales
    expected = ExpectedMetrics(
        corners_home=6.0,
        corners_away=5.0,  # Total 11.0 córners -> +3.5 tiene >95%
        cards_home=3.0,
        cards_away=2.5,   # +0.5 tarjetas tiene >90%
        offsides_home=2.5,
        offsides_away=2.0, # +0.5 fueras de juego tiene >90%
        total_shots_home=18.0,
        total_shots_away=12.0, # +7.5 remates tiene >95%
    )

    markets = select_statistical_markets(home, away, probs, expected)
    selections = [m["selection"] for m in markets]

    # Córners totales triviales no permitidos
    assert "Más de 3.5 córners" not in selections
    assert "Más de 4.5 córners" not in selections
    assert "Más de 5.5 córners" not in selections
    assert "Más de 6.5 córners" not in selections

    # Córners de equipo triviales no permitidos (+1.5, +2.5)
    assert not any(s.endswith("Más de 1.5 córners") for s in selections)
    assert not any(s.endswith("Más de 2.5 córners") for s in selections)

    # Tarjetas de equipo triviales (+0.5) no permitidas
    assert not any(s.endswith("Más de 0.5 tarjetas") for s in selections)

    # Tarjetas totales triviales (+1.5, +2.5) no permitidas
    assert "Más de 1.5 tarjetas" not in selections
    assert "Más de 2.5 tarjetas" not in selections

    # Fueras de juego de equipo triviales (+0.5) no permitidas
    assert not any(s.endswith("Más de 0.5 fueras de juego") for s in selections)

    # Fueras de juego totales triviales (+1.5) no permitidas
    assert "Más de 1.5 fueras de juego" not in selections

    # Remates triviales no permitidos
    assert "Más de 7.5 remates" not in selections
    assert "Más de 9.5 remates" not in selections
    assert "Más de 15.5 remates" not in selections
    assert "Más de 17.5 remates" not in selections
    assert "Más de 19.5 remates" not in selections
    assert not any(s.endswith("Más de 7.5 remates") for s in selections)
    assert not any(s.endswith("Más de 9.5 remates") for s in selections)


def test_selector_picks_highest_probability_in_optimal_range():
    """Verifica que entre varias líneas válidas del rango óptimo (60%-88%), el selector elija la de MAYOR PROBABILIDAD (Opción 1: más segura)."""
    home = Team(1, "Local")
    away = Team(2, "Visitante")
    probs = _probabilities()
    # Con 11.5 córners proyectados: +7.5 tiene prob ~72.7% y +8.5 tiene prob ~65.5% (ambas en rango)
    expected = ExpectedMetrics(
        corners_home=6.5,
        corners_away=5.0,
        dispersion_corners=0.18,
    )

    markets = select_statistical_markets(home, away, probs, expected)
    corner_total = next((m for m in markets if m["market"] == "Córners totales"), None)

    assert corner_total is not None
    # Debe escoger Más de 7.5 córners (~72.7%) al ser la de mayor probabilidad dentro del rango óptimo
    assert "Más de 7.5 córners" in corner_total["selection"]
    assert corner_total["probability"] >= 0.70  # Confirma que eligió la línea de mayor probabilidad (~72.7%)


def test_lines_above_maximum_probability_are_excluded_as_near_100_percent():
    """Verifica que selecciones con probabilidad > 88% se descarten por considerarse demasiado cercanas al 100%."""
    home = Team(1, "Local")
    away = Team(2, "Visitante")
    probs = _probabilities()
    # Supongamos una probabilidad excesivamente alta (ej: 92%)
    probs.home_win = 0.92
    probs.draw = 0.05
    probs.away_win = 0.03
    expected = ExpectedMetrics(
        corners_home=8.0,
        corners_away=5.0,
    )

    markets = select_statistical_markets(home, away, probs, expected)
    # Ninguna selección debe superar el 88.0%
    assert all(m["probability"] <= 0.88 for m in markets)


def test_category_hidden_if_no_valid_line_reaches_60_percent():
    """Verifica que si ninguna línea válida de una categoría llega a 60%, la categoría se oculte completamente."""
    home = Team(1, "Local")
    away = Team(2, "Visitante")
    probs = _probabilities()
    # Sin estadísticas de tarjetas en ExpectedMetrics (None), ninguna línea alcanza 60%
    expected = ExpectedMetrics(
        cards_home=None,
        cards_away=None,
        corners_home=6.0,
        corners_away=5.0,
    )

    markets = select_statistical_markets(home, away, probs, expected)
    categories = {m["category"] for m in markets}

    # "Tarjetas" debe quedar totalmente oculta
    assert "Tarjetas" not in categories


def test_uncatalogued_line_with_99_percent_is_discarded():
    """Verifica que una línea con 99% que no esté en MarketPresentationCatalog sea descartada."""
    from deport_ai.presentation_catalog import MarketPresentationCatalog

    # Línea fuera de catálogo con 99% (ej: +2.5 córners totales o +0.5 tarjetas equipo)
    fake_candidate = {
        "id": "uncatalogued_corners_over_25",
        "category": "Córners",
        "group": "corners_total",
        "market": "Córners totales",
        "selection": "Más de 2.5 córners",
        "line": 2.5,
        "side": "over",
        "probability": 0.99,
        "basis": "Test",
        "explanation": "Test",
    }
    assert MarketPresentationCatalog.is_presentable(fake_candidate) is False

    fake_card = {
        "id": "uncatalogued_cards_home_over_05",
        "category": "Tarjetas",
        "group": "cards_home",
        "market": "Tarjetas de Local",
        "selection": "Local Más de 0.5 tarjetas",
        "line": 0.5,
        "side": "over",
        "probability": 0.99,
        "basis": "Test",
        "explanation": "Test",
    }
    assert MarketPresentationCatalog.is_presentable(fake_card) is False


def test_format_adaptive_report_renders_clean_structure_and_omits_empty_categories():
    """Verifica que format_adaptive_report formatee exactamente la estructura adaptativa oficial."""
    from deport_ai.domain import AnalysisReport, ConfidenceScore
    from deport_ai.formatter import format_adaptive_report

    home = Team(1, "Real Madrid")
    away = Team(2, "Atlético Madrid")
    probs = _probabilities()
    expected = ExpectedMetrics(
        corners_home=6.5,
        corners_away=5.0,
        cards_home=2.5,
        cards_away=2.5,
    )
    markets = select_statistical_markets(home, away, probs, expected)
    conf = ConfidenceScore(
        level="MEDIA",
        score=75,
        sample_size=30,
        detailed_matches=25,
        lineups_confirmed=False,
    )

    report = AnalysisReport(
        home=home,
        away=away,
        fixture=None,
        recent_home=[],
        recent_away=[],
        h2h=[],
        probabilities=probs,
        expected=expected,
        elo_home=1850.0,
        elo_away=1780.0,
        injuries=[],
        lineups=[],
        odds={},
        opportunities=[],
        risks=["Rotaciones previstas"],
        sources=[],
        generated_at="2026-09-20",
        statistical_markets=markets,
        confidence=conf,
    )

    formatted = format_adaptive_report(report)

    # Verifica encabezado y confianza
    assert "# ⚽ Real Madrid vs Atlético Madrid" in formatted
    assert "**Confianza:** 🟡 Media" in formatted

    # Verifica que existan categorías con datos
    assert "#### 🥅 Goles y Anotaciones" in formatted
    assert "#### 🚩 Córners" in formatted
    assert "#### 🟨 Tarjetas" in formatted

    # Verifica que NO aparezcan categorías vacías (por ejemplo Especiales o Fueras de Juego si no hubo selecciones >= 60%)
    if not any(m["category"] == "Especiales" for m in markets):
        assert "#### 💥 Especiales" not in formatted

    # Verifica formato de justificación en una sola línea con *Porque ...*
    assert "*Porque " in formatted

    # Verifica proyecciones numéricas finales
    assert "#### 📊 Proyecciones numéricas" in formatted
    assert "• **Goles estimados:**" in formatted
    assert "• **Córners estimados:**" in formatted
    assert "• **Tarjetas estimadas:**" in formatted
    assert "• **Marcador más probable:**" in formatted


def test_analysis_report_llm_payload_prioritizes_adaptive_report():
    """Verifica que llm_payload() incluya adaptive_report y priorice statistical_markets."""
    from deport_ai.domain import AnalysisReport
    home = Team(1, "Real Madrid")
    away = Team(2, "Atlético Madrid")
    probs = _probabilities()
    expected = ExpectedMetrics()
    report = AnalysisReport(
        home=home,
        away=away,
        fixture=None,
        recent_home=[],
        recent_away=[],
        h2h=[],
        probabilities=probs,
        expected=expected,
        elo_home=1850.0,
        elo_away=1780.0,
        injuries=[],
        lineups=[],
        odds={},
        opportunities=[],
        risks=[],
        sources=[],
        generated_at="2026-09-20",
        statistical_markets=[{"category": "Goles", "market": "Goles totales", "selection": "Más de 1.5 goles", "probability": 0.86, "explanation": "test"}],
    )

    payload = report.llm_payload()
    keys = list(payload.keys())

    assert "adaptive_report" in payload
    assert isinstance(payload["adaptive_report"], str)
    assert "# ⚽ Real Madrid vs Atlético Madrid" in payload["adaptive_report"]
    assert keys[0] == "adaptive_report"
    assert keys[1] == "statistical_markets"


def test_creative_markets_generation_and_selection():
    home = Team(1, "Manchester City")
    away = Team(2, "Sunderland")

    # Matriz 3x3 para combos
    matrix = [
        [0.02, 0.01, 0.00],  # 0-0, 0-1, 0-2
        [0.15, 0.05, 0.01],  # 1-0, 1-1, 1-2
        [0.35, 0.20, 0.05],  # 2-0, 2-1, 2-2
        [0.10, 0.05, 0.01],  # 3-0, 3-1, 3-2
    ]
    probs = ProbabilityReport(
        home_win=0.85,
        draw=0.10,
        away_win=0.05,
        over_15=0.76,
        over_25=0.62,
        under_25=0.38,
        btts=0.32,
        expected_home_goals=2.2,
        expected_away_goals=0.4,
        shared_goal_component=0.0,
        score_matrix=matrix,
        first_half_over_05=0.80,
        second_half_over_05=0.82,
    )
    expected = ExpectedMetrics(
        corners_home=6.5,
        corners_away=4.5,
        cards_home=1.8,
        cards_away=2.3,
        shots_on_home=6.8,
        shots_on_away=3.2,
    )

    markets = select_statistical_markets(home, away, probs, expected)

    selections = [m["selection"] for m in markets]

    # Verifica presencia de mercados creativos
    assert any("Ambos equipos reciben al menos 1 tarjeta" in s for s in selections)
    assert any("Ambos equipos sacan 3+ córners" in s for s in selections)
    assert any("Habrá gol en ambas mitades" in s for s in selections)
    assert any("Manchester City o Empate (1X) y Menos de 3.5 goles" in s for s in selections)

    # Verifica que no haya más de una línea Under por equipo en tarjetas
    team_card_unders = [s for s in selections if "tarjetas" in s and "Menos de" in s and ("Manchester City" in s or "Sunderland" in s)]
    assert len(team_card_unders) <= 1

    # Verifica límites de categoría
    from collections import Counter
    cat_counts = Counter(m["category"] for m in markets)
    for cat, count in cat_counts.items():
        assert count <= 4, f"Categoría {cat} excede el límite de 4 selecciones ({count})"



