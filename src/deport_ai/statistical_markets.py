from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .domain import ExpectedMetrics, ProbabilityReport, Team
from .markets_catalog import (
    MINIMUM_INFORMATIVE_LINES,
    MarketDefinition,
    build_declarative_catalog,
)
from .presentation_catalog import MarketPresentationCatalog, get_exigence_score
from .stats_engine import negative_binomial_pmf


MINIMUM_PROBABILITY = 0.60


def _safe_complement(p: float | None) -> float | None:
    """Calcula el complemento (1.0 - p) distinguiendo estrictamente 'no disponible' (None) de 0.0.

    Evita que valores no calculados o ausentes se transformen artificialmente en 100.0%.
    """
    if p is None:
        return None
    return round(max(0.0, min(1.0, 1.0 - p)), 4)


def _calc_count_over(rate: float | None, alpha: float, line: float) -> float | None:
    """Calcula P(Conteo > line) mediante distribución Binomial Negativa: 1 - sum(P(k) para k <= line)."""
    if rate is None or rate <= 0.0:
        return None
    k_max = int(math.floor(line))
    p_under = sum(negative_binomial_pmf(k, rate, alpha) for k in range(k_max + 1))
    return round(max(0.0, min(1.0, 1.0 - p_under)), 4)


def _calc_count_under(rate: float | None, alpha: float, line: float) -> float | None:
    """Calcula P(Conteo < line) mediante distribución Binomial Negativa: sum(P(k) para k <= line)."""
    if rate is None or rate <= 0.0:
        return None
    k_max = int(math.floor(line))
    p_under = sum(negative_binomial_pmf(k, rate, alpha) for k in range(k_max + 1))
    return round(max(0.0, min(1.0, p_under)), 4)


def calculate_candidate_markets(
    home: Team,
    away: Team,
    probabilities: ProbabilityReport,
    expected: ExpectedMetrics,
) -> list[dict[str, Any]]:
    """Genera sistemáticamente todos los mercados declarativos evaluados por las distribuciones del modelo."""
    catalog = build_declarative_catalog(home.name, away.name)
    candidates: list[dict[str, Any]] = []

    # Métricas agregadas y dispersiones
    disp_cards = getattr(expected, "dispersion_cards", 0.27)
    disp_corners = getattr(expected, "dispersion_corners", 0.18)
    disp_shots = getattr(expected, "dispersion_shots", 0.10)
    disp_offsides = getattr(expected, "dispersion_offsides", 0.16)

    total_cards = (
        expected.cards_home + expected.cards_away
        if (expected.cards_home is not None and expected.cards_away is not None)
        else None
    )
    total_corners = (
        expected.corners_home + expected.corners_away
        if (expected.corners_home is not None and expected.corners_away is not None)
        else None
    )
    total_shots = (
        expected.total_shots_home + expected.total_shots_away
        if (expected.total_shots_home is not None and expected.total_shots_away is not None)
        else None
    )
    total_shots_on = (
        expected.shots_on_home + expected.shots_on_away
        if (expected.shots_on_home is not None and expected.shots_on_away is not None)
        else None
    )
    total_offsides = (
        expected.offsides_home + expected.offsides_away
        if (expected.offsides_home is not None and expected.offsides_away is not None)
        else None
    )
    total_goals = (
        (probabilities.expected_home_goals + probabilities.expected_away_goals)
        if (probabilities.expected_home_goals is not None and probabilities.expected_away_goals is not None)
        else None
    )
    tot_woodwork = (
        expected.woodwork_home + expected.woodwork_away
        if (expected.woodwork_home is not None and expected.woodwork_away is not None)
        else None
    )

    matrix = (
        probabilities.score_matrix
        if getattr(probabilities, "score_matrix", None) and len(probabilities.score_matrix) > 1
        else None
    )

    projections_map: dict[str, float | None] = {
        "total_cards": total_cards,
        "cards_home": expected.cards_home,
        "cards_away": expected.cards_away,
        "total_corners": total_corners,
        "corners_home": expected.corners_home,
        "corners_away": expected.corners_away,
        "total_shots": total_shots,
        "total_shots_home": expected.total_shots_home,
        "total_shots_away": expected.total_shots_away,
        "total_shots_on": total_shots_on,
        "shots_on_home": expected.shots_on_home,
        "shots_on_away": expected.shots_on_away,
        "total_offsides": total_offsides,
        "offsides_home": expected.offsides_home,
        "offsides_away": expected.offsides_away,
        "total_goals": total_goals,
        "expected_home_goals": probabilities.expected_home_goals,
        "expected_away_goals": probabilities.expected_away_goals,
        "tot_woodwork": tot_woodwork,
    }

    for defn in catalog:
        prob: float | None = None
        proj_val = projections_map.get(defn.projection_source) if defn.projection_source else None

        # 1. Tarjetas
        if defn.probability_source == "neg_bin_cards_total":
            if total_cards is not None and total_cards > 0:
                prob = _calc_count_over(total_cards, disp_cards, defn.line) if defn.side == "over" else _calc_count_under(total_cards, disp_cards, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_cards"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_cards_home":
            if expected.cards_home is not None and expected.cards_home > 0:
                prob = _calc_count_over(expected.cards_home, disp_cards, defn.line) if defn.side == "over" else _calc_count_under(expected.cards_home, disp_cards, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_cards_home"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_cards_away":
            if expected.cards_away is not None and expected.cards_away > 0:
                prob = _calc_count_over(expected.cards_away, disp_cards, defn.line) if defn.side == "over" else _calc_count_under(expected.cards_away, disp_cards, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_cards_away"
                prob = getattr(expected, attr_name, None)

        # 2. Córners
        elif defn.probability_source == "neg_bin_corners_total":
            if total_corners is not None and total_corners > 0:
                prob = _calc_count_over(total_corners, disp_corners, defn.line) if defn.side == "over" else _calc_count_under(total_corners, disp_corners, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_corners"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_corners_home":
            if expected.corners_home is not None and expected.corners_home > 0:
                prob = _calc_count_over(expected.corners_home, disp_corners, defn.line) if defn.side == "over" else _calc_count_under(expected.corners_home, disp_corners, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_corners_home"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_corners_away":
            if expected.corners_away is not None and expected.corners_away > 0:
                prob = _calc_count_over(expected.corners_away, disp_corners, defn.line) if defn.side == "over" else _calc_count_under(expected.corners_away, disp_corners, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_corners_away"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "corners_1x2_home":
            prob = getattr(expected, "corners_1x2_home", None)
        elif defn.probability_source == "corners_1x2_away":
            prob = getattr(expected, "corners_1x2_away", None)

        # 3. Remates
        elif defn.probability_source == "neg_bin_shots_total":
            if total_shots is not None and total_shots > 0:
                prob = _calc_count_over(total_shots, disp_shots, defn.line) if defn.side == "over" else _calc_count_under(total_shots, disp_shots, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_total_shots"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_shots_home":
            if expected.total_shots_home is not None and expected.total_shots_home > 0:
                prob = _calc_count_over(expected.total_shots_home, disp_shots, defn.line) if defn.side == "over" else _calc_count_under(expected.total_shots_home, disp_shots, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_shots_home"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_shots_away":
            if expected.total_shots_away is not None and expected.total_shots_away > 0:
                prob = _calc_count_over(expected.total_shots_away, disp_shots, defn.line) if defn.side == "over" else _calc_count_under(expected.total_shots_away, disp_shots, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_shots_away"
                prob = getattr(expected, attr_name, None)

        # 4. Tiros a puerta
        elif defn.probability_source == "neg_bin_shots_on_total":
            if total_shots_on is not None and total_shots_on > 0:
                prob = _calc_count_over(total_shots_on, disp_shots, defn.line) if defn.side == "over" else _calc_count_under(total_shots_on, disp_shots, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_shots_on"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_shots_on_home":
            if expected.shots_on_home is not None and expected.shots_on_home > 0:
                prob = _calc_count_over(expected.shots_on_home, disp_shots, defn.line) if defn.side == "over" else _calc_count_under(expected.shots_on_home, disp_shots, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_shots_on_home"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_shots_on_away":
            if expected.shots_on_away is not None and expected.shots_on_away > 0:
                prob = _calc_count_over(expected.shots_on_away, disp_shots, defn.line) if defn.side == "over" else _calc_count_under(expected.shots_on_away, disp_shots, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_shots_on_away"
                prob = getattr(expected, attr_name, None)

        # 5. Fueras de juego
        elif defn.probability_source == "neg_bin_offsides_total":
            if total_offsides is not None and total_offsides > 0:
                prob = _calc_count_over(total_offsides, disp_offsides, defn.line) if defn.side == "over" else _calc_count_under(total_offsides, disp_offsides, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_offsides"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_offsides_home":
            if expected.offsides_home is not None and expected.offsides_home > 0:
                prob = _calc_count_over(expected.offsides_home, disp_offsides, defn.line) if defn.side == "over" else _calc_count_under(expected.offsides_home, disp_offsides, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_offsides_home"
                prob = getattr(expected, attr_name, None)
        elif defn.probability_source == "neg_bin_offsides_away":
            if expected.offsides_away is not None and expected.offsides_away > 0:
                prob = _calc_count_over(expected.offsides_away, disp_offsides, defn.line) if defn.side == "over" else _calc_count_under(expected.offsides_away, disp_offsides, defn.line)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}_offsides_away"
                prob = getattr(expected, attr_name, None)

        # 6. Goles
        elif defn.probability_source == "matrix_goals_total":
            if matrix:
                k_line = int(math.floor(defn.line))
                if defn.side == "over":
                    prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h + a > k_line), 4)
                else:
                    prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h + a <= k_line), 4)
            else:
                attr_name = f"{'over' if defn.side == 'over' else 'under'}_{int(defn.line * 10)}"
                prob = getattr(probabilities, attr_name, None)
        elif defn.probability_source == "btts_yes":
            prob = probabilities.btts
        elif defn.probability_source == "btts_no":
            prob = _safe_complement(probabilities.btts)
        elif defn.probability_source == "matrix_home_goals":
            if matrix:
                k_line = int(math.floor(defn.line))
                if defn.side == "over":
                    prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h > k_line), 4)
                else:
                    prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h <= k_line), 4)
            else:
                if defn.line == 0.5 and defn.side == "over":
                    prob = _safe_complement(probabilities.clean_sheet_away)
                elif defn.line == 1.5 and defn.side == "over":
                    prob = probabilities.home_over_15
                elif defn.line == 1.5 and defn.side == "under":
                    prob = probabilities.home_under_15
                elif defn.line == 2.5 and defn.side == "over":
                    prob = getattr(probabilities, "home_over_25", None)
        elif defn.probability_source == "matrix_away_goals":
            if matrix:
                k_line = int(math.floor(defn.line))
                if defn.side == "over":
                    prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if a > k_line), 4)
                else:
                    prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if a <= k_line), 4)
            else:
                if defn.line == 0.5 and defn.side == "over":
                    prob = _safe_complement(probabilities.clean_sheet_home)
                elif defn.line == 1.5 and defn.side == "over":
                    prob = probabilities.away_over_15
                elif defn.line == 1.5 and defn.side == "under":
                    prob = probabilities.away_under_15
        elif defn.probability_source == "clean_sheet_home":
            prob = probabilities.clean_sheet_home
        elif defn.probability_source == "clean_sheet_away":
            prob = probabilities.clean_sheet_away

        # 7. Mitades
        elif defn.probability_source == "first_half_over_05":
            prob = probabilities.first_half_over_05
        elif defn.probability_source == "first_half_under_15":
            prob = probabilities.first_half_under_15 if getattr(probabilities, "first_half_under_15", None) is not None else _safe_complement(probabilities.first_half_over_15)
        elif defn.probability_source == "first_half_over_15":
            prob = probabilities.first_half_over_15
        elif defn.probability_source == "second_half_over_05":
            prob = probabilities.second_half_over_05
        elif defn.probability_source == "second_half_under_15":
            prob = probabilities.second_half_under_15 if getattr(probabilities, "second_half_under_15", None) is not None else _safe_complement(probabilities.second_half_over_15)
        elif defn.probability_source == "second_half_over_15":
            prob = probabilities.second_half_over_15

        # 8. Resultado
        elif defn.probability_source == "match_1x2_home":
            prob = probabilities.home_win
        elif defn.probability_source == "match_1x2_draw":
            prob = probabilities.draw
        elif defn.probability_source == "match_1x2_away":
            prob = probabilities.away_win
        elif defn.probability_source == "double_chance_1x":
            prob = min(1.0, round(probabilities.home_win + probabilities.draw, 4)) if (probabilities.home_win is not None and probabilities.draw is not None) else None
        elif defn.probability_source == "double_chance_x2":
            prob = min(1.0, round(probabilities.away_win + probabilities.draw, 4)) if (probabilities.away_win is not None and probabilities.draw is not None) else None
        elif defn.probability_source == "double_chance_12":
            prob = min(1.0, round(probabilities.home_win + probabilities.away_win, 4)) if (probabilities.home_win is not None and probabilities.away_win is not None) else None
        elif defn.probability_source == "dnb_home":
            prob = probabilities.dnb_home
        elif defn.probability_source == "dnb_away":
            prob = probabilities.dnb_away
        elif defn.probability_source == "win_to_nil_home":
            if matrix:
                prob = round(sum(matrix[h][0] for h in range(1, len(matrix))), 4)
        elif defn.probability_source == "win_to_nil_away":
            if matrix:
                prob = round(sum(matrix[0][a] for a in range(1, len(matrix[0]))), 4)

        # 9. Especiales
        elif defn.probability_source == "hit_woodwork":
            prob = expected.over_05_woodwork

        if prob is None:
            continue

        prob = round(prob, 4)
        basis = (
            "Proyección experimental sujeta a calibración histórica; calculada con distribución binomial negativa y probabilidad explícita de empate."
            if defn.is_experimental
            else "Proyección del modelo estadístico; no incluye cuota ni valoración frente a una casa."
        )

        try:
            explanation = defn.explanation_template.format(projection=proj_val, probability=prob) if proj_val is not None else defn.explanation_template
        except Exception:
            explanation = defn.explanation_template

        item: dict[str, Any] = {
            "id": defn.id,
            "category": defn.category,
            "group": defn.group,
            "market": defn.market_template,
            "selection": defn.selection_template,
            "line": defn.line,
            "side": defn.side,
            "probability": prob,
            "basis": basis,
            "explanation": explanation,
        }
        if proj_val is not None:
            item["projection"] = round(proj_val, 2)
        if defn.requires_starter_confirmation:
            item["requires_starter_confirmation"] = True

        candidates.append(item)

    # 10. Jugadores (Props de remates y goleadores)
    _add_player_candidates(candidates, home, expected.player_shots.get(home.id, []))
    _add_player_candidates(candidates, away, expected.player_shots.get(away.id, []))
    _add_scorer_candidates(candidates, home, expected.anytime_goalscorers.get(home.id, []))
    _add_scorer_candidates(candidates, away, expected.anytime_goalscorers.get(away.id, []))

    return candidates


def _get_subfamily_key(candidate: dict[str, Any]) -> str:
    """Identifica la subfamilia homogénea de una selección (ej: corners_total:over vs corners_total:under)."""
    group = str(candidate.get("group", ""))
    side = str(candidate.get("side", ""))
    selection = str(candidate.get("selection", ""))

    if group.startswith("player_shots"):
        if "tiro a puerta" in selection:
            return f"{group}:sot"
        return f"{group}:shots"
    if group.startswith("player_goal"):
        return f"{group}:goal"
    if side in ("over", "under"):
        return f"{group}:{side}"
    return group


def _get_concept_group(candidate: dict[str, Any]) -> str:
    """Identifica el concepto global del mercado para deduplicar a una única selección por concepto."""
    group = str(candidate.get("group", ""))
    if group.startswith("player_shots:") or group.startswith("player_goal:"):
        parts = group.split(":")
        if len(parts) >= 3:
            return f"player:{parts[1]}:{parts[2]}"
        return group
    return group


def _candidate_rank_key(c: dict[str, Any]) -> tuple[float, float]:
    """Calcula el orden de prioridad entre campeones de subfamilias del mismo concepto.

    Para mercados de conteo con línea y proyección:
    Prioriza el margen direccional proyectado (projection - line para over, line - projection para under).
    Desempata con la probabilidad de la selección.
    """
    side = c.get("side")
    line = c.get("line")
    proj = c.get("projection")
    if proj is not None and line is not None:
        if side == "over":
            directional_margin = round(float(proj) - float(line), 2)
            return (directional_margin, float(c.get("probability", 0.0)))
        if side == "under":
            directional_margin = round(float(line) - float(proj), 2)
            return (directional_margin, float(c.get("probability", 0.0)))
    return (0.0, float(c.get("probability", 0.0)))


def select_statistical_markets(
    home: Team,
    away: Team,
    probabilities: ProbabilityReport,
    expected: ExpectedMetrics,
    minimum_probability: float = MINIMUM_PROBABILITY,
    max_per_category: int = 4,
) -> list[dict[str, Any]]:
    """Aplica la capa de presentación:
    1. Filtra candidatos estrictamente según MarketPresentationCatalog (excluye triviales y no catalogados).
    2. Conserva selecciones con probabilidad >= minimum_probability (0.60).
    3. Para cada subfamilia, elige la línea válida MÁS EXIGENTE.
    4. Deduplica por concepto/grupo priorizando margen direccional proyectado y probabilidad.
    5. Agrupa por categoría, limitando a un máximo de 4 selecciones (orden descendente).
    6. Oculta cualquier categoría sin selecciones válidas.
    """
    candidates = calculate_candidate_markets(home, away, probabilities, expected)

    # 1. Filtro estricto por MarketPresentationCatalog y probabilidad mínima
    eligible: list[dict[str, Any]] = []
    for c in candidates:
        prob = c.get("probability")
        if prob is None or prob < minimum_probability:
            continue
        if not MarketPresentationCatalog.is_presentable(c):
            continue
        eligible.append(c)

    # 2. Agrupación por subfamilia para escoger la línea MÁS EXIGENTE de cada una
    by_subfamily: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in eligible:
        subfamily_key = _get_subfamily_key(c)
        by_subfamily[subfamily_key].append(c)

    # 3. Dentro de cada subfamilia, elegir la selección con mayor puntaje de exigencia
    subfamily_champions: list[dict[str, Any]] = []
    for sub_items in by_subfamily.values():
        champion = max(sub_items, key=lambda x: (get_exigence_score(x), x["probability"]))
        subfamily_champions.append(champion)

    # 4. Deduplicación por concepto global / grupo único
    best_by_group: dict[str, dict[str, Any]] = {}
    for c in subfamily_champions:
        concept_key = _get_concept_group(c)
        previous = best_by_group.get(concept_key)
        if previous is None or _candidate_rank_key(c) > _candidate_rank_key(previous):
            best_by_group[concept_key] = c

    # 5. Agrupación por categoría y limitación a máximo configurado (orden descendente)
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in best_by_group.values():
        by_cat[item["category"]].append(item)

    selected: list[dict[str, Any]] = []
    for cat, items in by_cat.items():
        items.sort(key=lambda x: -x["probability"])
        selected.extend(items[:max_per_category])

    # 6. Orden final descendente y limpieza de campos internos
    selected.sort(key=lambda item: (-item["probability"], item["category"], item["market"]))
    for item in selected:
        item.pop("group", None)
        item.pop("id", None)
        item.pop("line", None)
        item.pop("side", None)

    return selected


def _add_player_candidates(
    candidates: list[dict[str, Any]],
    team: Team,
    players: list[dict[str, Any]],
) -> None:
    for player in players:
        name = str(player.get("name") or "").strip()
        if not name:
            continue
        group = f"player_shots:{team.id}:{name.lower()}"
        projection = _number(player.get("expected_per_match"))
        for selection, prob in (
            ("2+ remates", _number(player.get("probability_two_plus"))),
            ("3+ remates", _number(player.get("probability_three_plus"))),
            ("4+ remates", _number(player.get("probability_four_plus"))),
            ("1+ tiro a puerta", _number(player.get("probability_sot_one_plus"))),
            ("2+ tiros a puerta", _number(player.get("probability_sot_two_plus"))),
        ):
            if prob is not None:
                item: dict[str, Any] = {
                    "id": f"player_shot_{team.id}_{name.lower()}_{selection.replace('+', 'plus').replace(' ', '_')}",
                    "category": "Jugadores",
                    "group": group,
                    "market": f"Remates de {name} ({team.name})",
                    "selection": f"{name} {selection}",
                    "line": None,
                    "side": "player",
                    "probability": round(prob, 4),
                    "basis": "Proyección del modelo estadístico; no incluye cuota ni valoración frente a una casa.",
                    "explanation": f"Porque {name} registra un promedio de {projection:.2f} remates esperados por partido." if projection else f"Porque {name} mantiene una alta frecuencia ofensiva.",
                    "requires_starter_confirmation": True,
                }
                if projection is not None:
                    item["projection"] = round(projection, 2)
                candidates.append(item)


def _add_scorer_candidates(
    candidates: list[dict[str, Any]],
    team: Team,
    players: list[dict[str, Any]],
) -> None:
    for player in players:
        name = str(player.get("name") or "").strip()
        prob = _number(player.get("probability_goal"))
        if name and prob is not None:
            candidates.append({
                "id": f"player_goal_{team.id}_{name.lower()}",
                "category": "Jugadores",
                "group": f"player_goal:{team.id}:{name.lower()}",
                "market": f"Gol de {name} ({team.name})",
                "selection": f"{name} anota en cualquier momento",
                "line": None,
                "side": "player",
                "probability": round(prob, 4),
                "basis": "Proyección del modelo estadístico; no incluye cuota ni valoración frente a una casa.",
                "explanation": f"Porque {name} es la principal referencia ofensiva de {team.name}.",
                "requires_starter_confirmation": True,
            })


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
