from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .domain import ExpectedMetrics, ProbabilityReport, Team


MINIMUM_PROBABILITY = 0.60


def _safe_complement(p: float | None) -> float | None:
    """Calcula el complemento (1.0 - p) distinguiendo estrictamente 'no disponible' (None) de 0.0.

    Evita que valores no calculados o ausentes se transformen artificialmente en 100.0%.
    """
    if p is None:
        return None
    return round(max(0.0, min(1.0, 1.0 - p)), 4)


def select_statistical_markets(
    home: Team,
    away: Team,
    probabilities: ProbabilityReport,
    expected: ExpectedMetrics,
    minimum_probability: float = MINIMUM_PROBABILITY,
) -> list[dict[str, Any]]:
    """Return model-only markets, without bookmaker prices or value assertions.

    Each logical market contributes only its highest-probability eligible line.
    This keeps the output useful without filling it with overlapping alternatives
    such as every consecutive total-goals or total-corners line.
    """

    candidates: list[dict[str, Any]] = []

    def add(
        category: str,
        group: str,
        market: str,
        selection: str,
        probability: float | None,
        projection: float | None = None,
        *,
        starter_confirmation: bool = False,
        basis: str | None = None,
    ) -> None:
        if probability is None or probability < minimum_probability:
            return
        item: dict[str, Any] = {
            "category": category,
            "group": group,
            "market": market,
            "selection": selection,
            "probability": round(probability, 4),
            "basis": basis or "Proyección del modelo estadístico; no incluye cuota ni valoración frente a una casa.",
        }
        if projection is not None:
            item["projection"] = round(projection, 2)
        if starter_confirmation:
            item["requires_starter_confirmation"] = True
        candidates.append(item)

    matrix = probabilities.score_matrix if getattr(probabilities, "score_matrix", None) and len(probabilities.score_matrix) > 1 else None
    total_goals = probabilities.expected_home_goals + probabilities.expected_away_goals

    # 1. Resultado y Gana a Cero (máximo 1 de cada subtipo)
    add("Resultado", "1x2", "Resultado del partido", home.name, probabilities.home_win)
    add("Resultado", "1x2", "Resultado del partido", "Empate", probabilities.draw)
    add("Resultado", "1x2", "Resultado del partido", away.name, probabilities.away_win)

    # Doble Oportunidad (solo la más probable: 1X, X2 o 12)
    p_1x = min(1.0, probabilities.home_win + probabilities.draw) if (probabilities.home_win is not None and probabilities.draw is not None) else None
    p_x2 = min(1.0, probabilities.away_win + probabilities.draw) if (probabilities.away_win is not None and probabilities.draw is not None) else None
    p_12 = min(1.0, probabilities.home_win + probabilities.away_win) if (probabilities.home_win is not None and probabilities.away_win is not None) else None
    add("Resultado", "double_chance", "Doble oportunidad", f"{home.name} o Empate (1X)", p_1x)
    add("Resultado", "double_chance", "Doble oportunidad", f"{away.name} o Empate (X2)", p_x2)
    add("Resultado", "double_chance", "Doble oportunidad", f"{home.name} o {away.name} (12)", p_12)

    # Empate Apuesta No Válida (DNB - solo la más probable)
    add("Resultado", "dnb", "Empate apuesta no válida", f"DNB {home.name}", probabilities.dnb_home)
    add("Resultado", "dnb", "Empate apuesta no válida", f"DNB {away.name}", probabilities.dnb_away)

    if matrix:
        win_to_nil_h = sum(matrix[h][0] for h in range(1, len(matrix)))
        win_to_nil_a = sum(matrix[0][a] for a in range(1, len(matrix[0])))
        add("Resultado", "win_to_nil", "Gana a cero", f"{home.name} gana a cero", win_to_nil_h)
        add("Resultado", "win_to_nil", "Gana a cero", f"{away.name} gana a cero", win_to_nil_a)

    # 2. Goles Totales y Ambos Marcan (solo 1 línea de goles totales)
    add("Goles", "total_goals", "Goles totales", "Más de 1.5 goles", probabilities.over_15, total_goals)
    add("Goles", "total_goals", "Goles totales", "Más de 2.5 goles", probabilities.over_25, total_goals)
    add("Goles", "total_goals", "Goles totales", "Más de 3.5 goles", probabilities.over_35, total_goals)
    add("Goles", "total_goals", "Goles totales", "Menos de 2.5 goles", probabilities.under_25, total_goals)
    add("Goles", "total_goals", "Goles totales", "Menos de 3.5 goles", probabilities.under_35, total_goals)

    if matrix:
        over_05 = 1.0 - matrix[0][0]
        over_45 = sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h + a >= 5)
        add("Goles", "total_goals", "Goles totales", "Más de 0.5 goles", over_05, total_goals)
        add("Goles", "total_goals", "Goles totales", "Menos de 4.5 goles", 1.0 - over_45, total_goals)

    add("Goles", "both_score", "Ambos equipos marcan", "Sí", probabilities.btts)
    add("Goles", "both_score", "Ambos equipos marcan", "No (BTTS No)", _safe_complement(probabilities.btts))

    # 3. Mercados por Mitad (1T y 2T - solo 1 línea por mitad)
    p_1h_u15 = probabilities.first_half_under_15 if getattr(probabilities, "first_half_under_15", None) is not None else _safe_complement(probabilities.first_half_over_15)
    p_2h_u15 = probabilities.second_half_under_15 if getattr(probabilities, "second_half_under_15", None) is not None else _safe_complement(probabilities.second_half_over_15)

    add("Mitades", "first_half", "Primer tiempo", "1T Más de 0.5 goles", probabilities.first_half_over_05)
    add("Mitades", "first_half", "Primer tiempo", "1T Menos de 1.5 goles", p_1h_u15)
    add("Mitades", "first_half", "Primer tiempo", "1T Más de 1.5 goles", probabilities.first_half_over_15)
    add("Mitades", "second_half", "Segundo tiempo", "2T Más de 0.5 goles", probabilities.second_half_over_05)
    add("Mitades", "second_half", "Segundo tiempo", "2T Menos de 1.5 goles", p_2h_u15)
    add("Mitades", "second_half", "Segundo tiempo", "2T Más de 1.5 goles", probabilities.second_half_over_15)

    # 4. Goles por Equipo y Portería a Cero (solo 1 línea por equipo)
    p_home_o05 = _safe_complement(probabilities.clean_sheet_away)
    p_away_o05 = _safe_complement(probabilities.clean_sheet_home)

    add("Goles", "home_goals", f"Goles de {home.name}", f"{home.name} Más de 0.5 goles", p_home_o05, probabilities.expected_home_goals)
    add("Goles", "home_goals", f"Goles de {home.name}", f"{home.name} Más de 1.5 goles", probabilities.home_over_15, probabilities.expected_home_goals)
    add("Goles", "home_goals", f"Goles de {home.name}", f"{home.name} Menos de 1.5 goles", probabilities.home_under_15, probabilities.expected_home_goals)
    add("Goles", "home_goals", f"Goles de {home.name}", f"{home.name} Más de 2.5 goles", getattr(probabilities, "home_over_25", None), probabilities.expected_home_goals)

    add("Goles", "away_goals", f"Goles de {away.name}", f"{away.name} Más de 0.5 goles", p_away_o05, probabilities.expected_away_goals)
    add("Goles", "away_goals", f"Goles de {away.name}", f"{away.name} Menos de 1.5 goles", probabilities.away_under_15, probabilities.expected_away_goals)
    add("Goles", "away_goals", f"Goles de {away.name}", f"{away.name} Más de 1.5 goles", probabilities.away_over_15, probabilities.expected_away_goals)

    add("Goles", "clean_sheet", f"Portería a cero de {home.name}", f"{home.name} no recibe gol", probabilities.clean_sheet_home)
    add("Goles", "clean_sheet", f"Portería a cero de {away.name}", f"{away.name} no recibe gol", probabilities.clean_sheet_away)

    # 5. Especiales / Postes
    if expected.over_05_woodwork is not None:
        add("Especiales", "woodwork", "Tiros al palo", "Tiro al palo en el partido", expected.over_05_woodwork)

    # 6. Córners 1X2 (Experimental - mediante convolución discreta binomial negativa con probabilidad explícita de empate)
    p_c_home = getattr(expected, "corners_1x2_home", None)
    p_c_away = getattr(expected, "corners_1x2_away", None)
    if p_c_home is not None:
        add(
            "Córners",
            "corners_1x2",
            "Córners 1X2",
            f"{home.name} saca más córners (Experimental)",
            p_c_home,
            expected.corners_home,
            basis="Proyección experimental sujeta a calibración histórica; calculada con distribución binomial negativa y probabilidad explícita de empate.",
        )
    if p_c_away is not None:
        add(
            "Córners",
            "corners_1x2",
            "Córners 1X2",
            f"{away.name} saca más córners (Experimental)",
            p_c_away,
            expected.corners_away,
            basis="Proyección experimental sujeta a calibración histórica; calculada con distribución binomial negativa y probabilidad explícita de empate.",
        )

    corner_total = _total(expected.corners_home, expected.corners_away)
    _add_lines(
        add,
        "Córners",
        "corners_total",
        "Córners totales",
        corner_total,
        [
            ("Más de 7.5 córners", expected.over_75_corners),
            ("Más de 8.5 córners", expected.over_85_corners),
            ("Más de 9.5 córners", expected.over_95_corners),
            ("Más de 10.5 córners", expected.over_105_corners),
            ("Más de 11.5 córners", expected.over_115_corners),
            ("Menos de 10.5 córners", expected.under_105_corners),
        ],
    )
    _add_lines(
        add,
        "Córners",
        "corners_home",
        f"Córners de {home.name}",
        expected.corners_home,
        [
            ("Más de 4.5 córners", expected.over_45_corners_home),
            ("Más de 5.5 córners", expected.over_55_corners_home),
            ("Más de 6.5 córners", expected.over_65_corners_home),
            ("Menos de 3.5 córners", expected.under_35_corners_home),
            ("Menos de 4.5 córners", expected.under_45_corners_home),
        ],
    )
    _add_lines(
        add,
        "Córners",
        "corners_away",
        f"Córners de {away.name}",
        expected.corners_away,
        [
            ("Más de 4.5 córners", expected.over_45_corners_away),
            ("Más de 5.5 córners", expected.over_55_corners_away),
            ("Más de 6.5 córners", expected.over_65_corners_away),
            ("Menos de 3.5 córners", expected.under_35_corners_away),
            ("Menos de 4.5 córners", expected.under_45_corners_away),
        ],
    )

    cards_total = _total(expected.cards_home, expected.cards_away)
    _add_lines(
        add,
        "Tarjetas",
        "cards_total",
        "Tarjetas totales",
        cards_total,
        [("Más de 3.5 tarjetas", expected.over_35_cards), ("Más de 4.5 tarjetas", expected.over_45_cards)],
    )
    _add_lines(add, "Tarjetas", "cards_home", f"Tarjetas de {home.name}", expected.cards_home, [
        ("Más de 1.5 tarjetas", expected.over_15_cards_home),
        ("Más de 2.5 tarjetas", expected.over_25_cards_home),
    ])
    _add_lines(add, "Tarjetas", "cards_away", f"Tarjetas de {away.name}", expected.cards_away, [
        ("Más de 1.5 tarjetas", expected.over_15_cards_away),
        ("Más de 2.5 tarjetas", expected.over_25_cards_away),
    ])

    shot_total = _total(expected.total_shots_home, expected.total_shots_away)
    _add_lines(add, "Remates", "shots_total", "Remates totales", shot_total, [
        ("Más de 21.5 remates", expected.over_215_total_shots),
        ("Más de 23.5 remates", expected.over_235_total_shots),
        ("Más de 25.5 remates", expected.over_255_total_shots),
        ("Más de 27.5 remates", expected.over_275_total_shots),
        ("Más de 29.5 remates", expected.over_295_total_shots),
        ("Menos de 24.5 remates", expected.under_245_total_shots),
        ("Menos de 26.5 remates", expected.under_265_total_shots),
    ])
    _add_lines(add, "Remates", "shots_home", f"Remates de {home.name}", expected.total_shots_home, [
        ("Más de 11.5 remates", expected.over_115_shots_home),
        ("Más de 13.5 remates", expected.over_135_shots_home),
        ("Más de 15.5 remates", expected.over_155_shots_home),
        ("Más de 17.5 remates", expected.over_175_shots_home),
        ("Menos de 8.5 remates", expected.under_85_shots_home),
        ("Menos de 9.5 remates", expected.under_95_shots_home),
    ])
    _add_lines(add, "Remates", "shots_away", f"Remates de {away.name}", expected.total_shots_away, [
        ("Más de 11.5 remates", expected.over_115_shots_away),
        ("Más de 13.5 remates", expected.over_135_shots_away),
        ("Menos de 8.5 remates", expected.under_85_shots_away),
        ("Menos de 9.5 remates", expected.under_95_shots_away),
    ])

    shots_on_total = _total(expected.shots_on_home, expected.shots_on_away)
    _add_lines(add, "Tiros a puerta", "shots_on_total", "Tiros a puerta totales", shots_on_total, [
        ("Más de 7.5 tiros a puerta", expected.over_75_shots_on),
        ("Más de 8.5 tiros a puerta", expected.over_85_shots_on),
        ("Más de 9.5 tiros a puerta", expected.over_95_shots_on),
        ("Más de 10.5 tiros a puerta", expected.over_105_shots_on),
        ("Menos de 8.5 tiros a puerta", expected.under_85_shots_on),
        ("Menos de 9.5 tiros a puerta", expected.under_95_shots_on),
    ])
    _add_lines(add, "Tiros a puerta", "shots_on_home", f"Tiros a puerta de {home.name}", expected.shots_on_home, [
        ("Más de 4.5 tiros a puerta", expected.over_45_shots_on_home),
        ("Más de 5.5 tiros a puerta", expected.over_55_shots_on_home),
        ("Más de 6.5 tiros a puerta", expected.over_65_shots_on_home),
        ("Más de 7.5 tiros a puerta", expected.over_75_shots_on_home),
        ("Menos de 2.5 tiros a puerta", expected.under_25_shots_on_home),
        ("Menos de 3.5 tiros a puerta", expected.under_35_shots_on_home),
    ])
    _add_lines(add, "Tiros a puerta", "shots_on_away", f"Tiros a puerta de {away.name}", expected.shots_on_away, [
        ("Más de 3.5 tiros a puerta", expected.over_35_shots_on_away),
        ("Más de 4.5 tiros a puerta", expected.over_45_shots_on_away),
        ("Menos de 2.5 tiros a puerta", expected.under_25_shots_on_away),
        ("Menos de 3.5 tiros a puerta", expected.under_35_shots_on_away),
    ])

    offsides_total = _total(expected.offsides_home, expected.offsides_away)
    _add_lines(add, "Fueras de juego", "offsides_total", "Fueras de juego totales", offsides_total, [
        ("Más de 2.5 fueras de juego", expected.over_25_offsides),
        ("Más de 3.5 fueras de juego", expected.over_35_offsides),
        ("Menos de 2.5 fueras de juego", expected.under_25_offsides),
        ("Menos de 3.5 fueras de juego", expected.under_35_offsides),
        ("Menos de 4.5 fueras de juego", expected.under_45_offsides),
    ])
    _add_lines(add, "Fueras de juego", "offsides_home", f"Fueras de juego de {home.name}", expected.offsides_home, [
        ("Más de 1.5 fueras de juego", expected.over_15_offsides_home),
        ("Menos de 1.5 fueras de juego", expected.under_15_offsides_home),
    ])
    _add_lines(add, "Fueras de juego", "offsides_away", f"Fueras de juego de {away.name}", expected.offsides_away, [
        ("Más de 1.5 fueras de juego", expected.over_15_offsides_away),
        ("Menos de 1.5 fueras de juego", expected.under_15_offsides_away),
    ])

    _add_player_markets(add, home, expected.player_shots.get(home.id, []), minimum_probability)
    _add_player_markets(add, away, expected.player_shots.get(away.id, []), minimum_probability)
    _add_scorer_markets(add, home, expected.anytime_goalscorers.get(home.id, []), minimum_probability)
    _add_scorer_markets(add, away, expected.anytime_goalscorers.get(away.id, []), minimum_probability)

    best_by_group: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        previous = best_by_group.get(candidate["group"])
        if previous is None or candidate["probability"] > previous["probability"]:
            best_by_group[candidate["group"]] = candidate

    # Agrupar por categoría y limitar a máximo 4 apuestas por categoría
    # en estricto orden de mayor probabilidad a menor (probabilidad >= 60%)
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in best_by_group.values():
        by_cat[item["category"]].append(item)

    selected: list[dict[str, Any]] = []
    for cat, items in by_cat.items():
        items.sort(key=lambda x: -x["probability"])
        selected.extend(items[:4])

    selected.sort(key=lambda item: (-item["probability"], item["category"], item["market"]))
    for item in selected:
        item.pop("group", None)
    return selected


def _add_lines(
    add: Any,
    category: str,
    group: str,
    market: str,
    projection: float | None,
    lines: list[tuple[str, float | None]],
) -> None:
    for selection, probability in lines:
        add(category, group, market, selection, probability, projection)


def _add_player_markets(
    add: Any,
    team: Team,
    players: list[dict[str, Any]],
    minimum_probability: float,
) -> None:
    for player in players:
        name = str(player.get("name") or "").strip()
        if not name:
            continue
        group = f"player_shots:{team.id}:{name.lower()}"
        projection = _number(player.get("expected_per_match"))
        for selection, probability in (
            ("2+ remates", _number(player.get("probability_two_plus"))),
            ("3+ remates", _number(player.get("probability_three_plus"))),
            ("4+ remates", _number(player.get("probability_four_plus"))),
            ("1+ tiro a puerta", _number(player.get("probability_sot_one_plus"))),
            ("2+ tiros a puerta", _number(player.get("probability_sot_two_plus"))),
        ):
            if probability is not None and probability >= minimum_probability:
                add("Jugadores", group, f"Remates de {name} ({team.name})", selection, probability, projection, starter_confirmation=True)


def _add_scorer_markets(
    add: Any,
    team: Team,
    players: list[dict[str, Any]],
    minimum_probability: float,
) -> None:
    for player in players:
        name = str(player.get("name") or "").strip()
        probability = _number(player.get("probability_goal"))
        if name and probability is not None and probability >= minimum_probability:
            add("Jugadores", f"player_goal:{team.id}:{name.lower()}", f"Gol de {name} ({team.name})", "Anota en cualquier momento", probability, starter_confirmation=True)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _total(first: float | None, second: float | None) -> float | None:
    return first + second if first is not None and second is not None else None

