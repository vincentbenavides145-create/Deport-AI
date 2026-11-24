from __future__ import annotations

import math
from collections import defaultdict
from statistics import fmean
from typing import Any

from .domain import ExpectedMetrics, ProbabilityReport, Team, TeamMatch
from .markets_catalog import (
    MarketDefinition,
    build_declarative_catalog,
)
from .dynamic_calibration import (
    MATCH_TOTAL_CATEGORIES,
    MIN_CALIBRATION_SAMPLE,
    band_factor,
    factor_for,
    is_match_total,
    selection_side,
    side_key,
    total_side_key,
)
from .odds import MIN_EDGE, expected_value, odds_key_for_candidate
from .presentation_catalog import MarketPresentationCatalog, get_exigence_score
from .stats_engine import CARDS_KEY, negative_binomial_pmf, stat_value


# Mínimo publicado: en resultados reales (17-21/11/2026) el acierto siguió a la probabilidad
# (73 % prometido, 73 % acertado); solo desde el 75 % se acercaba al 80 % de acierto.
MINIMUM_PROBABILITY = 0.75
MAXIMUM_PROBABILITY = 0.88
# Filtro de coherencia: muestra mínima para citar un historial y desvío máximo tolerado
# entre la probabilidad del modelo y la tasa histórica que se cita como justificación.
MIN_EVIDENCE_SAMPLE = 6
MAX_MODEL_GAP = 0.20
# Categorías suspendidas tras medir resultados reales: props de jugador (54 % de acierto
# con 70 % prometido), fueras de juego (54 % con 73 %) y mitades (61 % con 67 %). Se siguen
# calculando para el backtest, pero no se publican hasta que el modelo demuestre acierto.
SUSPENDED_CATEGORIES: frozenset[str] = frozenset({"Jugadores", "Fueras de juego", "Mitades"})
# Conteos cuyos "Menos de" salieron sobreconfiados en resultados reales: solo se publican
# cuando ese lado tiene su propia calibración (30+ predicciones liquidadas).
UNDER_NEEDS_OWN_CALIBRATION: frozenset[str] = frozenset({"Córners", "Tarjetas", "Tiros al arco", "Remates", "Faltas"})
# Mercados suspendidos dentro de categorías que sí se publican: córners del 1T (63 % de
# acierto con 74 % prometido; son de mitades aunque se registren como Córners) y "quién
# saca más córners" (63 % con 74 %).
SUSPENDED_GROUPS: frozenset[str] = frozenset({"corners_first_half", "corners_1x2"})
# Córners Más/Menos: solo con 2+ córners de distancia entre la proyección y la línea
# (80 % de acierto con ese margen frente a 62 % por debajo).
MIN_CORNER_MARGIN = 2.0


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


def _calc_comparison_1x2(rate_a: float | None, rate_b: float | None, alpha: float) -> tuple[float | None, float | None]:
    """Calcula P(A > B) y P(B > A) usando convolución de dos distribuciones Binomial Negativa independientes."""
    if rate_a is None or rate_b is None or rate_a <= 0.0 or rate_b <= 0.0:
        return None, None
    max_val = 18
    pmf_a = [negative_binomial_pmf(k, rate_a, alpha) for k in range(max_val + 1)]
    pmf_b = [negative_binomial_pmf(k, rate_b, alpha) for k in range(max_val + 1)]
    p_a_win = sum(pmf_a[k] * sum(pmf_b[j] for j in range(k)) for k in range(1, max_val + 1))
    p_b_win = sum(pmf_b[k] * sum(pmf_a[j] for j in range(k)) for k in range(1, max_val + 1))
    return round(max(0.0, min(1.0, p_a_win)), 4), round(max(0.0, min(1.0, p_b_win)), 4)


# Etiquetas de estadísticas por equipo usadas en justificaciones y evidencia empírica.
_STAT_LABELS: dict[str, str] = {
    "corner_kicks": "saques de esquina",
    "yellow_cards": "tarjetas",
    "cards": "tarjetas",
    "fouls": "faltas",
    "total_shots": "remates",
    "shots_on_goal": "tiros al arco",
    "offsides": "fueras de juego",
}
# group -> (lado del equipo, clave de estadística)
_TEAM_STAT_GROUPS: dict[str, tuple[str, str]] = {
    "corners_home": ("home", "corner_kicks"),
    "corners_away": ("away", "corner_kicks"),
    "cards_home": ("home", CARDS_KEY),
    "cards_away": ("away", CARDS_KEY),
    "fouls_home": ("home", "fouls"),
    "fouls_away": ("away", "fouls"),
    "shots_home": ("home", "total_shots"),
    "shots_away": ("away", "total_shots"),
    "shots_on_home": ("home", "shots_on_goal"),
    "shots_on_away": ("away", "shots_on_goal"),
    "offsides_home": ("home", "offsides"),
    "offsides_away": ("away", "offsides"),
}
_TOTAL_STAT_GROUPS: dict[str, str] = {
    "corners_total": "corner_kicks",
    "cards_total": CARDS_KEY,
    "fouls_total": "fouls",
    "shots_total": "total_shots",
    "shots_on_total": "shots_on_goal",
    "offsides_total": "offsides",
}
_STAT_1X2_GROUPS: dict[str, tuple[str, str]] = {
    "corners_1x2": ("corner_kicks", "sacó más córners"),
    "cards_1x2": (CARDS_KEY, "recibió más tarjetas"),
    "shots_on_1x2": ("shots_on_goal", "tuvo más tiros al arco"),
    "fouls_1x2": ("fouls", "cometió más faltas"),
}
# Mercados que dependen de estadísticas de partido (no de goles): exigen muestra mínima.
STAT_EVIDENCE_GROUPS: frozenset[str] = frozenset(
    set(_TEAM_STAT_GROUPS) | set(_TOTAL_STAT_GROUPS) | set(_STAT_1X2_GROUPS)
    | {"woodwork", "both_teams_card", "both_teams_2_cards", "both_teams_corners", "both_teams_shots_on"}
)


def _fmt_line(line: float | None) -> str:
    return f"{line:g}" if line is not None else ""


def _selection_team(
    sel: str, home: Team, away: Team, recent_home: list[TeamMatch], recent_away: list[TeamMatch]
) -> tuple[Team, list[TeamMatch]]:
    text = sel[4:] if sel.startswith("DNB ") else sel
    if text.startswith(home.name):
        return home, recent_home
    if text.startswith(away.name):
        return away, recent_away
    if home.name in text:
        return home, recent_home
    return away, recent_away


def _hit(value: float, line: float, side: str) -> bool:
    return value > line if side == "over" else value < line


def _evidence(hits: int, n: int, avg: float | None = None, line: float | None = None, side: str | None = None) -> dict[str, Any]:
    return {"hits": hits, "n": n, "avg": None if avg is None else round(avg, 2), "line": line, "side": side}


def _half_split(m: TeamMatch) -> tuple[int, int, int, int] | None:
    """(1T a favor, 1T en contra, 2T a favor, 2T en contra) si hay marcador al descanso."""
    if m.goals_for_1h is None or m.goals_against_1h is None:
        return None
    return (
        m.goals_for_1h,
        m.goals_against_1h,
        m.goals_for - m.goals_for_1h,
        m.goals_against - m.goals_against_1h,
    )


def _explain_market(
    defn: MarketDefinition,
    home: Team,
    away: Team,
    proj_val: float | None,
    prob: float,
    recent_home: list[TeamMatch] | None = None,
    recent_away: list[TeamMatch] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Justificación de una línea y la evidencia empírica exacta que cita.

    La evidencia (aciertos, muestra, promedio) es la misma que aparece en el texto, de
    modo que el filtro de coherencia nunca deja pasar una justificación que contradiga
    la probabilidad publicada.
    """
    recent_home = recent_home or []
    recent_away = recent_away or []
    grp = defn.group
    line = defn.line
    side = defn.side or ""
    sel = defn.selection_template
    combined = recent_home + recent_away
    n_comb = len(combined)

    def fallback() -> tuple[str, None]:
        try:
            text = defn.explanation_template.format(projection=proj_val, probability=prob) if proj_val is not None else defn.explanation_template
        except Exception:
            text = defn.explanation_template
        return text, None

    if not recent_home and not recent_away:
        return fallback()

    # 1. Goles totales
    if grp == "total_goals" and line is not None and n_comb:
        hits = sum(1 for m in combined if _hit(m.goals_for + m.goals_against, line, side))
        avg = fmean(m.goals_for + m.goals_against for m in combined)
        verb = "se superó" if side == "over" else "no se alcanzó"
        return (
            f"Porque en {hits} de los últimos {n_comb} partidos de ambos equipos {verb} la línea de {_fmt_line(line)} goles (promedio: {avg:.2f}).",
            _evidence(hits, n_comb, avg, line, side),
        )

    # 2. Goles de equipo
    if grp in ("home_goals", "away_goals") and line is not None:
        team, rec = (home, recent_home) if grp == "home_goals" else (away, recent_away)
        if rec:
            hits = sum(1 for m in rec if _hit(m.goals_for, line, side))
            avg = fmean(m.goals_for for m in rec)
            comp = "más" if side == "over" else "menos"
            return (
                f"Porque {team.name} anotó {comp} de {_fmt_line(line)} goles en {hits} de sus últimos {len(rec)} partidos (promedia {avg:.2f} goles).",
                _evidence(hits, len(rec), avg, line, side),
            )

    # 3. Ambos marcan
    if grp == "both_score" and n_comb:
        if sel == "Sí":
            hits = sum(1 for m in combined if m.goals_for > 0 and m.goals_against > 0)
            return f"Porque ambos equipos anotaron y recibieron gol en {hits} de sus últimos {n_comb} encuentros.", _evidence(hits, n_comb)
        hits = sum(1 for m in combined if m.goals_for == 0 or m.goals_against == 0)
        return f"Porque al menos uno de los rivales se quedó sin anotar en {hits} de sus últimos {n_comb} partidos.", _evidence(hits, n_comb)

    # 4. Portería a cero y resultado
    if grp == "clean_sheet":
        team, rec = _selection_team(sel, home, away, recent_home, recent_away)
        if rec:
            hits = sum(1 for m in rec if m.goals_against == 0)
            return f"Porque {team.name} dejó su arco en cero en {hits} de sus últimos {len(rec)} partidos.", _evidence(hits, len(rec))

    if grp == "win_to_nil":
        team, rec = _selection_team(sel, home, away, recent_home, recent_away)
        if rec:
            hits = sum(1 for m in rec if m.result == "W" and m.goals_against == 0)
            return f"Porque {team.name} ganó sin recibir goles en {hits} de sus últimos {len(rec)} partidos.", _evidence(hits, len(rec))

    if grp == "1x2":
        if sel == "Empate" and n_comb:
            hits = sum(1 for m in combined if m.result == "D")
            return f"Porque {hits} de los últimos {n_comb} partidos de ambos equipos terminaron en empate.", _evidence(hits, n_comb)
        team, rec = _selection_team(sel, home, away, recent_home, recent_away)
        if rec:
            hits = sum(1 for m in rec if m.result == "W")
            return f"Porque {team.name} ganó {hits} de sus últimos {len(rec)} partidos.", _evidence(hits, len(rec))

    if grp == "double_chance":
        if "(12)" in sel and n_comb:
            hits = sum(1 for m in combined if m.result != "D")
            return f"Porque {hits} de los últimos {n_comb} partidos de ambos equipos tuvieron un ganador.", _evidence(hits, n_comb)
        team, rec = _selection_team(sel, home, away, recent_home, recent_away)
        if rec:
            hits = sum(1 for m in rec if m.result in ("W", "D"))
            return f"Porque {team.name} evitó la derrota en {hits} de sus últimos {len(rec)} partidos.", _evidence(hits, len(rec))

    if grp == "dnb":
        team, rec = _selection_team(sel, home, away, recent_home, recent_away)
        decided = [m for m in rec if m.result != "D"]
        if decided:
            hits = sum(1 for m in decided if m.result == "W")
            return (
                f"Porque {team.name} ganó {hits} de sus últimos {len(decided)} partidos que no terminaron en empate.",
                _evidence(hits, len(decided)),
            )

    if grp == "combo_result_goals":
        if sel.startswith("Ambos marcan") and n_comb:
            hits = sum(1 for m in combined if m.goals_for > 0 and m.goals_against > 0 and (m.goals_for + m.goals_against) > 2)
            return f"Porque ambos anotaron y se superaron los 2.5 goles en {hits} de sus últimos {n_comb} partidos.", _evidence(hits, n_comb)
        team, rec = _selection_team(sel, home, away, recent_home, recent_away)
        if rec:
            outcome_ok = (lambda m: m.result == "W") if " gana " in f" {sel} " else (lambda m: m.result in ("W", "D"))
            if "Menos de 3.5" in sel:
                goals_ok = lambda m: (m.goals_for + m.goals_against) < 3.5  # noqa: E731
            elif "Más de 2.5" in sel:
                goals_ok = lambda m: (m.goals_for + m.goals_against) > 2.5  # noqa: E731
            else:
                goals_ok = lambda m: (m.goals_for + m.goals_against) > 1.5  # noqa: E731
            hits = sum(1 for m in rec if outcome_ok(m) and goals_ok(m))
            return (
                f"Porque {team.name} cumplió el resultado y la línea de goles en {hits} de sus últimos {len(rec)} partidos.",
                _evidence(hits, len(rec)),
            )

    if grp == "combo_1x2_btts":
        team, rec = _selection_team(sel, home, away, recent_home, recent_away)
        if rec:
            outcome_ok = (lambda m: m.result == "W") if " gana " in f" {sel} " else (lambda m: m.result in ("W", "D"))
            hits = sum(1 for m in rec if outcome_ok(m) and m.goals_for > 0 and m.goals_against > 0)
            return (
                f"Porque {team.name} cumplió este resultado con goles en ambos arcos en {hits} de sus últimos {len(rec)} partidos.",
                _evidence(hits, len(rec)),
            )

    if grp == "multigoals" and n_comb:
        min_g, max_g = (1, 3) if "1 a 3" in sel else ((2, 4) if "2 a 4" in sel else (2, 5))
        hits = sum(1 for m in combined if min_g <= (m.goals_for + m.goals_against) <= max_g)
        return f"Porque en {hits} de los últimos {n_comb} partidos de ambos equipos hubo un total de {sel}.", _evidence(hits, n_comb)

    # 5. Mercados por mitad (requieren marcador al descanso)
    if grp in ("goal_both_halves", "team_score_both_halves", "first_half", "second_half", "btts_second_half"):
        if grp == "team_score_both_halves":
            team, rec = _selection_team(sel, home, away, recent_home, recent_away)
            halves = [h for h in (_half_split(m) for m in rec) if h is not None]
            if len(halves) >= MIN_EVIDENCE_SAMPLE:
                hits = sum(1 for h in halves if h[0] > 0 and h[2] > 0)
                return f"Porque {team.name} marcó en ambos tiempos en {hits} de sus últimos {len(halves)} partidos.", _evidence(hits, len(halves))
            if proj_val is not None:
                return f"Porque el modelo proyecta {proj_val:.2f} goles de {team.name}, repartidos entre ambos tiempos.", None
            return fallback()
        halves = [h for h in (_half_split(m) for m in combined) if h is not None]
        if len(halves) >= MIN_EVIDENCE_SAMPLE:
            n = len(halves)
            if grp == "goal_both_halves":
                hits = sum(1 for h in halves if (h[0] + h[1]) > 0 and (h[2] + h[3]) > 0)
                return f"Porque hubo gol en ambos tiempos en {hits} de los últimos {n} partidos de ambos equipos.", _evidence(hits, n)
            if grp == "btts_second_half":
                hits = sum(1 for h in halves if h[2] > 0 and h[3] > 0)
                return f"Porque ambos equipos marcaron en el 2T en {hits} de los últimos {n} partidos.", _evidence(hits, n)
            if line is not None:
                period = "1T" if grp == "first_half" else "2T"
                totals = [(h[0] + h[1]) if grp == "first_half" else (h[2] + h[3]) for h in halves]
                hits = sum(1 for t in totals if _hit(t, line, side))
                comp = "más" if side == "over" else "menos"
                return (
                    f"Porque hubo {comp} de {_fmt_line(line)} goles en el {period} en {hits} de los últimos {n} partidos de ambos equipos.",
                    _evidence(hits, n, fmean(totals), line, side),
                )
        if grp == "goal_both_halves" and proj_val is not None:
            return f"Porque el modelo proyecta {proj_val:.2f} goles en el partido, con margen para marcar en ambos tiempos.", None
        return fallback()

    # 6. Estadísticas por equipo (córners, tarjetas, faltas, remates, tiros al arco, offsides)
    if grp in _TEAM_STAT_GROUPS and line is not None:
        team_side, key = _TEAM_STAT_GROUPS[grp]
        team, rec = (home, recent_home) if team_side == "home" else (away, recent_away)
        values = [v for v in (stat_value(m.stats_for, key) for m in rec) if v is not None]
        if values:
            hits = sum(1 for v in values if _hit(v, line, side))
            avg = fmean(values)
            comp = "más" if side == "over" else "menos"
            return (
                f"Porque {team.name} promedia {avg:.1f} {_STAT_LABELS[key]} y registró {comp} de {_fmt_line(line)} en {hits} de sus últimos {len(values)} partidos.",
                _evidence(hits, len(values), avg, line, side),
            )
        return fallback()

    if grp in _TOTAL_STAT_GROUPS and line is not None:
        key = _TOTAL_STAT_GROUPS[grp]
        totals = []
        for m in combined:
            own, opp = stat_value(m.stats_for, key), stat_value(m.stats_against, key)
            if own is not None and opp is not None:
                totals.append(own + opp)
        if totals:
            hits = sum(1 for t in totals if _hit(t, line, side))
            avg = fmean(totals)
            comp = "más" if side == "over" else "menos"
            return (
                f"Porque los partidos recientes de ambos equipos promedian {avg:.1f} {_STAT_LABELS[key]} y registraron {comp} de {_fmt_line(line)} en {hits} de {len(totals)}.",
                _evidence(hits, len(totals), avg, line, side),
            )
        return fallback()

    if grp in _STAT_1X2_GROUPS:
        key, verb = _STAT_1X2_GROUPS[grp]
        team, rec = _selection_team(sel, home, away, recent_home, recent_away)
        pairs = [
            (own, opp)
            for own, opp in ((stat_value(m.stats_for, key), stat_value(m.stats_against, key)) for m in rec)
            if own is not None and opp is not None
        ]
        if pairs:
            hits = sum(1 for own, opp in pairs if own > opp)
            return f"Porque {team.name} {verb} que su rival en {hits} de sus últimos {len(pairs)} partidos.", _evidence(hits, len(pairs))
        return fallback()

    if grp in ("both_teams_card", "both_teams_2_cards", "both_teams_corners", "both_teams_shots_on"):
        if grp == "both_teams_card":
            key, thresh, label = CARDS_KEY, 1, "1+ tarjeta"
        elif grp == "both_teams_2_cards":
            key, thresh, label = CARDS_KEY, 2, "2+ tarjetas"
        elif grp == "both_teams_corners":
            key, thresh = "corner_kicks", (4 if "4+" in sel else 3)
            label = f"{thresh}+ córners"
        else:
            key, thresh, label = "shots_on_goal", 3, "3+ tiros al arco"
        pairs = [
            (own, opp)
            for own, opp in ((stat_value(m.stats_for, key), stat_value(m.stats_against, key)) for m in combined)
            if own is not None and opp is not None
        ]
        if pairs:
            hits = sum(1 for own, opp in pairs if own >= thresh and opp >= thresh)
            return f"Porque ambos equipos registraron {label} en {hits} de los últimos {len(pairs)} partidos.", _evidence(hits, len(pairs))
        return fallback()

    if grp == "woodwork":
        totals = []
        for m in combined:
            own, opp = stat_value(m.stats_for, "hit_woodwork"), stat_value(m.stats_against, "hit_woodwork")
            if own is not None and opp is not None:
                totals.append(own + opp)
        if totals:
            hits = sum(1 for t in totals if t >= 1)
            return (
                f"Porque hubo al menos un tiro al palo en {hits} de los últimos {len(totals)} partidos de ambos equipos (promedio {fmean(totals):.2f}).",
                _evidence(hits, len(totals), fmean(totals)),
            )
        return fallback()

    if grp == "corners_first_half" and line is not None and proj_val is not None:
        comp = "por encima" if side == "over" else "por debajo"
        return f"Porque el modelo proyecta {proj_val:.2f} córners en el 1T, {comp} de la línea de {_fmt_line(line)}.", None

    return fallback()


def evidence_contradicts(probability: float, evidence: dict[str, Any] | None, stat_market: bool) -> bool:
    """True si la evidencia citada no respalda la probabilidad publicada.

    - Mercados de estadísticas con menos de MIN_EVIDENCE_SAMPLE partidos: muestra insuficiente.
    - Tasa de acierto histórica < 50% o más de MAX_MODEL_GAP por debajo del modelo.
    - Promedio citado del lado contrario de la línea (p. ej. "Menos de 4.5" con promedio 4.9).
    """
    if evidence is None:
        return False
    n = int(evidence.get("n") or 0)
    if n < MIN_EVIDENCE_SAMPLE:
        return stat_market
    rate = evidence["hits"] / n
    if rate < 0.5 or probability - rate > MAX_MODEL_GAP:
        return True
    avg, line, side = evidence.get("avg"), evidence.get("line"), evidence.get("side")
    if avg is not None and line is not None and side in ("over", "under"):
        if (side == "over" and avg <= line) or (side == "under" and avg >= line):
            return True
    return False


def calculate_candidate_markets(
    home: Team,
    away: Team,
    probabilities: ProbabilityReport,
    expected: ExpectedMetrics,
    recent_home: list[TeamMatch] | None = None,
    recent_away: list[TeamMatch] | None = None,
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
    disp_fouls = getattr(expected, "dispersion_fouls", 0.12)
    total_fouls = (
        expected.fouls_home + expected.fouls_away
        if (expected.fouls_home is not None and expected.fouls_away is not None)
        else None
    )
    corners_1h = getattr(expected, "corners_first_half", None)

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
        "total_fouls": total_fouls,
        "fouls_home": expected.fouls_home,
        "fouls_away": expected.fouls_away,
        "corners_first_half": corners_1h,
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

        # 4. Tiros al arco
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

        # 9. Mercados Creativos (Tarjetas mutuas, Córners mutuos, Tiros al arco mutuos, Combos)
        elif defn.probability_source == "both_teams_card":
            if expected.cards_home is not None and expected.cards_away is not None:
                p_h_0 = negative_binomial_pmf(0, expected.cards_home, disp_cards)
                p_a_0 = negative_binomial_pmf(0, expected.cards_away, disp_cards)
                prob = round((1.0 - p_h_0) * (1.0 - p_a_0), 4)
        elif defn.probability_source == "both_teams_2_cards":
            if expected.cards_home is not None and expected.cards_away is not None:
                p_h_under2 = negative_binomial_pmf(0, expected.cards_home, disp_cards) + negative_binomial_pmf(1, expected.cards_home, disp_cards)
                p_a_under2 = negative_binomial_pmf(0, expected.cards_away, disp_cards) + negative_binomial_pmf(1, expected.cards_away, disp_cards)
                prob = round(max(0.0, 1.0 - p_h_under2) * max(0.0, 1.0 - p_a_under2), 4)
        elif defn.probability_source == "cards_1x2_home":
            p_h_win, _ = _calc_comparison_1x2(expected.cards_home, expected.cards_away, disp_cards)
            prob = p_h_win
        elif defn.probability_source == "cards_1x2_away":
            _, p_a_win = _calc_comparison_1x2(expected.cards_home, expected.cards_away, disp_cards)
            prob = p_a_win

        elif defn.probability_source == "both_teams_corners_3":
            if expected.corners_home is not None and expected.corners_away is not None:
                p_h_under3 = sum(negative_binomial_pmf(k, expected.corners_home, disp_corners) for k in range(3))
                p_a_under3 = sum(negative_binomial_pmf(k, expected.corners_away, disp_corners) for k in range(3))
                prob = round(max(0.0, 1.0 - p_h_under3) * max(0.0, 1.0 - p_a_under3), 4)
        elif defn.probability_source == "both_teams_corners_4":
            if expected.corners_home is not None and expected.corners_away is not None:
                p_h_under4 = sum(negative_binomial_pmf(k, expected.corners_home, disp_corners) for k in range(4))
                p_a_under4 = sum(negative_binomial_pmf(k, expected.corners_away, disp_corners) for k in range(4))
                prob = round(max(0.0, 1.0 - p_h_under4) * max(0.0, 1.0 - p_a_under4), 4)

        elif defn.probability_source == "both_teams_shots_on_3":
            if expected.shots_on_home is not None and expected.shots_on_away is not None:
                p_h_under3 = sum(negative_binomial_pmf(k, expected.shots_on_home, disp_shots) for k in range(3))
                p_a_under3 = sum(negative_binomial_pmf(k, expected.shots_on_away, disp_shots) for k in range(3))
                prob = round(max(0.0, 1.0 - p_h_under3) * max(0.0, 1.0 - p_a_under3), 4)
        elif defn.probability_source == "shots_on_1x2_home":
            p_h_win, _ = _calc_comparison_1x2(expected.shots_on_home, expected.shots_on_away, disp_shots)
            prob = p_h_win
        elif defn.probability_source == "shots_on_1x2_away":
            _, p_a_win = _calc_comparison_1x2(expected.shots_on_home, expected.shots_on_away, disp_shots)
            prob = p_a_win

        elif defn.probability_source == "goal_both_halves":
            p_1t = probabilities.first_half_over_05
            p_2t = probabilities.second_half_over_05
            if p_1t is not None and p_2t is not None:
                prob = round(p_1t * p_2t, 4)
            elif total_goals is not None and total_goals > 0:
                p1 = 1.0 - math.exp(-0.45 * total_goals)
                p2 = 1.0 - math.exp(-0.55 * total_goals)
                prob = round(p1 * p2, 4)
        elif defn.probability_source == "team_score_both_halves_home":
            lambda_h = probabilities.expected_home_goals
            if lambda_h is not None and lambda_h > 0:
                prob = round((1.0 - math.exp(-0.45 * lambda_h)) * (1.0 - math.exp(-0.55 * lambda_h)), 4)
        elif defn.probability_source == "team_score_both_halves_away":
            lambda_a = probabilities.expected_away_goals
            if lambda_a is not None and lambda_a > 0:
                prob = round((1.0 - math.exp(-0.45 * lambda_a)) * (1.0 - math.exp(-0.55 * lambda_a)), 4)

        elif defn.probability_source == "combo_1x_over_15":
            if matrix:
                prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h >= a and (h + a) >= 2), 4)
        elif defn.probability_source == "combo_x2_over_15":
            if matrix:
                prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if a >= h and (h + a) >= 2), 4)
        elif defn.probability_source == "combo_1x_under_35":
            if matrix:
                prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h >= a and (h + a) <= 3), 4)
        elif defn.probability_source == "combo_x2_under_35":
            if matrix:
                prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if a >= h and (h + a) <= 3), 4)
        elif defn.probability_source == "combo_1_over_15":
            if matrix:
                prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h > a and (h + a) >= 2), 4)
        elif defn.probability_source == "combo_2_over_15":
            if matrix:
                prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if a > h and (h + a) >= 2), 4)
        elif defn.probability_source == "combo_btts_over_25":
            if matrix:
                prob = round(sum(matrix[h][a] for h in range(len(matrix)) for a in range(len(matrix[h])) if h >= 1 and a >= 1 and (h + a) >= 3), 4)

        # 10. Especiales
        elif defn.probability_source == "hit_woodwork":
            prob = expected.over_05_woodwork

        # 11. Multigoles
        elif defn.probability_source == "multigoal_1_3":
            prob = probabilities.multigoal_1_3
        elif defn.probability_source == "multigoal_2_4":
            prob = probabilities.multigoal_2_4
        elif defn.probability_source == "multigoal_2_5":
            prob = probabilities.multigoal_2_5

        # 12. Combos 1X2 + Ambos Marcan
        elif defn.probability_source == "combo_1_btts":
            prob = probabilities.home_win_and_btts
        elif defn.probability_source == "combo_2_btts":
            prob = probabilities.away_win_and_btts
        elif defn.probability_source == "combo_1x_btts":
            prob = probabilities.dc_1x_and_btts
        elif defn.probability_source == "combo_x2_btts":
            prob = probabilities.dc_x2_and_btts

        # 13. BTTS 2do Tiempo
        elif defn.probability_source == "btts_second_half":
            prob = probabilities.btts_second_half

        # 14. Córners 1er Tiempo
        elif defn.probability_source == "neg_bin_corners_1h":
            if corners_1h is not None and corners_1h > 0 and defn.line is not None:
                prob = _calc_count_over(corners_1h, disp_corners, defn.line) if defn.side == "over" else _calc_count_under(corners_1h, disp_corners, defn.line)

        # 15. Faltas
        elif defn.probability_source == "neg_bin_fouls_total":
            if total_fouls is not None and total_fouls > 0 and defn.line is not None:
                prob = _calc_count_over(total_fouls, disp_fouls, defn.line) if defn.side == "over" else _calc_count_under(total_fouls, disp_fouls, defn.line)
        elif defn.probability_source == "neg_bin_fouls_home":
            if expected.fouls_home is not None and expected.fouls_home > 0 and defn.line is not None:
                prob = _calc_count_over(expected.fouls_home, disp_fouls, defn.line) if defn.side == "over" else _calc_count_under(expected.fouls_home, disp_fouls, defn.line)
        elif defn.probability_source == "neg_bin_fouls_away":
            if expected.fouls_away is not None and expected.fouls_away > 0 and defn.line is not None:
                prob = _calc_count_over(expected.fouls_away, disp_fouls, defn.line) if defn.side == "over" else _calc_count_under(expected.fouls_away, disp_fouls, defn.line)
        elif defn.probability_source == "fouls_1x2_home":
            p_h_win, _ = _calc_comparison_1x2(expected.fouls_home, expected.fouls_away, disp_fouls)
            prob = p_h_win
        elif defn.probability_source == "fouls_1x2_away":
            _, p_a_win = _calc_comparison_1x2(expected.fouls_home, expected.fouls_away, disp_fouls)
            prob = p_a_win

        if prob is None:
            continue

        prob = round(prob, 4)
        basis = (
            "Proyección experimental sujeta a calibración histórica; calculada con distribución binomial negativa y probabilidad explícita de empate."
            if defn.is_experimental
            else "Proyección del modelo estadístico; no incluye cuota ni valoración frente a una casa."
        )

        explanation, evidence = _explain_market(
            defn, home, away, proj_val, prob, recent_home=recent_home, recent_away=recent_away
        )

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
            "evidence": evidence,
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
        if "tiro al arco" in selection:
            return f"{group}:sot"
        return f"{group}:shots"
    if group.startswith("player_goal"):
        return f"{group}:goal"
    if group in ("both_teams_card", "both_teams_2_cards"):
        return "both_teams_card"
    if group == "both_teams_corners":
        return "both_teams_corners"
    if group == "combo_result_goals":
        return "combo_result_goals"
    if group == "cards_1x2":
        return "cards_1x2"
    if group == "shots_on_1x2":
        return "shots_on_1x2"
    if group == "team_score_both_halves":
        return "team_score_both_halves"
    if group in ("multigoals", "combo_1x2_btts", "btts_second_half", "fouls_1x2"):
        return group
    if side in ("over", "under"):
        return f"{group}:{side}"
    return group


def _get_concept_group(candidate: dict[str, Any]) -> str:
    """Identifica el concepto global del mercado para deduplicar a una única selección por concepto."""
    group = str(candidate.get("group", ""))
    side = str(candidate.get("side", ""))
    if group.startswith("player_shots:") or group.startswith("player_goal:"):
        parts = group.split(":")
        if len(parts) >= 3:
            return f"player:{parts[1]}:{parts[2]}"
        return group
    # Evitar saturación de líneas 'Menos de' individuales por equipo cuando hay mercados mutuos
    if group in ("cards_home", "cards_away") and side == "under":
        return "team_cards_under"
    if group in ("corners_home", "corners_away") and side == "under":
        return "team_corners_under"
    if group in ("fouls_home", "fouls_away") and side == "under":
        return "team_fouls_under"
    if group in ("both_teams_card", "both_teams_2_cards"):
        return "both_teams_card"
    if group == "both_teams_corners":
        return "both_teams_corners"
    # Familias de mercados correlacionados: una sola selección por familia (regla 5).
    if group in RESULT_FAMILY:
        return "family:result"
    if group in CLEAN_SHEET_FAMILY:
        return "family:clean_sheet"
    if group in TOTAL_GOALS_FAMILY:
        return "family:total_goals"
    return group


# 1X2, doble oportunidad, DNB y combinadas de resultado expresan la misma apuesta de fondo.
RESULT_FAMILY = frozenset({"1x2", "double_chance", "dnb", "combo_result_goals", "combo_1x2_btts"})
# "Ambos marcan: No", "X no recibe gol" y "X gana a cero" dependen de la misma portería a cero.
CLEAN_SHEET_FAMILY = frozenset({"both_score", "clean_sheet", "win_to_nil"})
# Goles totales y multigoles son la misma distribución de goles del partido.
TOTAL_GOALS_FAMILY = frozenset({"total_goals", "multigoals"})


def _candidate_rank_key(c: dict[str, Any]) -> tuple[float, float, float, float]:
    """Calcula el orden de prioridad entre campeones de subfamilias del mismo concepto.

    Con cuota disponible manda el valor esperado (EV): una selección con valor demostrado
    frente al mercado precede a una sin cuota. Sin cuotas, prioriza la probabilidad más
    alta y desempata con el margen direccional.
    """
    prob = float(c.get("probability", 0.0))
    side = c.get("side")
    line = c.get("line")
    proj = c.get("projection")
    directional_margin = 0.0
    if proj is not None and line is not None:
        if side == "over":
            directional_margin = round(float(proj) - float(line), 2)
        elif side == "under":
            directional_margin = round(float(line) - float(proj), 2)
    edge = c.get("edge")
    has_edge = 1.0 if edge is not None else 0.0
    return (has_edge, float(edge) if edge is not None else 0.0, prob, directional_margin)


def _corner_margin(candidate: dict[str, Any]) -> float:
    """Córners de distancia entre la proyección y la línea, a favor del lado elegido."""
    projection, line = candidate.get("projection"), candidate.get("line")
    if projection is None or line is None:
        return 0.0
    return projection - line if selection_side(candidate) == "over" else line - projection


def select_statistical_markets(
    home: Team,
    away: Team,
    probabilities: ProbabilityReport,
    expected: ExpectedMetrics,
    minimum_probability: float = MINIMUM_PROBABILITY,
    maximum_probability: float = MAXIMUM_PROBABILITY,
    max_per_category: int = 4,
    calibration: Any = None,
    recent_home: list[TeamMatch] | None = None,
    recent_away: list[TeamMatch] | None = None,
    odds: dict[str, float] | None = None,
    min_edge: float = MIN_EDGE,
    exclude_categories: set[str] | frozenset[str] | None = None,
    suspended_categories: set[str] | frozenset[str] = SUSPENDED_CATEGORIES,
    suspended_groups: set[str] | frozenset[str] = SUSPENDED_GROUPS,
    unpublished: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Aplica la capa de presentación:
    1. Filtra candidatos estrictamente según MarketPresentationCatalog (excluye triviales y no catalogados).
    2. Aplica calibración adaptativa si está activa (contracción empírica y filtro dinámico).
    3. Conserva selecciones con probabilidad dentro del rango óptimo (>= minimum_probability y <= maximum_probability).
    4. Para cada subfamilia, elige la selección de MAYOR PROBABILIDAD (Opción 1: más segura en el rango).
    5. Deduplica por concepto/grupo priorizando probabilidad y margen direccional proyectado.
    6. Agrupa por categoría, limitando a un máximo de 4 selecciones (orden descendente).
    7. Oculta cualquier categoría sin selecciones válidas.

    Si hay cuotas (`odds`, claves de `normalize_odds`), cada selección con precio recibe
    `odds` y `edge` (EV = prob × cuota − 1). Las de EV < `min_edge` se descartan aunque
    sean muy probables, y dentro de cada subfamilia se elige la de mayor EV.

    Las categorías frenadas en la liga (`calibration.frozen_categories`) no se devuelven;
    si se pasa la lista `unpublished`, sus selecciones válidas se agregan ahí para
    registrarlas sin publicar.
    """
    candidates = calculate_candidate_markets(
        home, away, probabilities, expected, recent_home=recent_home, recent_away=recent_away
    )

    # 1. Filtro estricto por MarketPresentationCatalog y rango de probabilidad óptimo
    excluded = set(exclude_categories or ()) | set(suspended_categories)
    eligible: list[dict[str, Any]] = []
    cat_factors = getattr(calibration, "category_factors", {}) if calibration else {}
    # Categorías frenadas en esta liga por su acierto real (ver FREEZE_MAX_HIT_RATE).
    frozen = getattr(calibration, "frozen_categories", ()) if calibration else ()
    frozen_eligible: list[dict[str, Any]] = []

    for c in candidates:
        if not MarketPresentationCatalog.is_presentable(c):
            continue

        prob = c.get("probability")
        if prob is None:
            continue

        cat = c.get("category", "")
        if c.get("group") in suspended_groups:
            continue
        c["model_prob"] = prob
        side = selection_side(c)
        if cat in UNDER_NEEDS_OWN_CALIBRATION and side == "under" and side_key(cat, side) not in cat_factors:
            continue
        if (cat in MATCH_TOTAL_CATEGORIES and side == "under" and is_match_total(c)
                and total_side_key(cat, side) not in cat_factors):
            continue
        if cat == "Córners" and side in ("over", "under") and _corner_margin(c) < MIN_CORNER_MARGIN:
            continue
        # Factor empírico del lado de la categoría (o de la categoría) si hay calibración activa.
        f_info = factor_for(cat_factors, cat, side, match_total=is_match_total(c))
        if f_info:
            shrinkage = f_info.get("shrinkage_factor", 1.0)
            hit_rate = f_info.get("hit_rate", 0.0)
            sample_size = f_info.get("sample_size", 0)

            if shrinkage != 1.0:
                prob = round(min(0.99, prob * shrinkage), 4)
                c["probability"] = prob

            if sample_size >= MIN_CALIBRATION_SAMPLE and hit_rate >= 0.70:
                c["dynamic_verified"] = True
                if not c.get("explanation", "").endswith("."):
                    c["explanation"] = c.get("explanation", "") + "."
                c["explanation"] += (
                    f" (Categoría con {hit_rate * 100:.1f}% de acierto real en {sample_size} predicciones liquidadas)."
                )

        c["prob_before_band"] = prob
        # Por encima del 88 % no se publica (sin valor en la cuota ni datos para calibrar).
        if prob > maximum_probability:
            continue
        # Calibración por tramo: lleva cada probabilidad al acierto real de su tramo.
        f_band = band_factor(cat_factors, prob)
        if f_band and f_band.get("shrinkage_factor", 1.0) != 1.0:
            prob = round(min(0.99, prob * f_band["shrinkage_factor"]), 4)
            c["probability"] = prob

        if prob < minimum_probability:
            continue

        # Filtro de coherencia: la justificación citada debe respaldar la probabilidad.
        if c.get("category") in excluded:
            continue
        group = str(c.get("group") or "")
        is_player = group.startswith("player_")
        # Las props de jugador exigen siempre historial real (sin él no se publican).
        evidence = c.get("evidence") if not is_player else (c.get("evidence") or {"hits": 0, "n": 0})
        if evidence_contradicts(prob, evidence, group in STAT_EVIDENCE_GROUPS or is_player):
            continue

        price = (odds or {}).get(odds_key_for_candidate(c.get("id")) or "")
        if price and price > 1.0:
            edge = round(expected_value(prob, price), 4)
            if edge < min_edge:
                # La cuota no paga el riesgo: valor esperado insuficiente o negativo.
                continue
            c["odds"] = price
            c["edge"] = edge

        (frozen_eligible if cat in frozen else eligible).append(c)

    if unpublished is not None:
        unpublished.extend(_choose_markets(frozen_eligible, max_per_category))
    return _choose_markets(eligible, max_per_category)


def _choose_markets(eligible: list[dict[str, Any]], max_per_category: int) -> list[dict[str, Any]]:
    """De los candidatos válidos, el mejor por subfamilia y concepto, y hasta
    `max_per_category` por categoría, en orden descendente de probabilidad."""
    # 2. Agrupación por subfamilia
    by_subfamily: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in eligible:
        subfamily_key = _get_subfamily_key(c)
        by_subfamily[subfamily_key].append(c)

    # 3. Dentro de cada subfamilia, elegir la selección de MAYOR PROBABILIDAD (Opción 1: más segura dentro del rango)
    subfamily_champions: list[dict[str, Any]] = []
    for sub_items in by_subfamily.values():
        priced = [x for x in sub_items if x.get("edge") is not None]
        if priced:
            champion = max(priced, key=lambda x: (x["edge"], x["probability"]))
        else:
            champion = max(sub_items, key=lambda x: (x["probability"], -abs(get_exigence_score(x))))
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
        # line/side se conservan: el seguimiento los necesita para liquidar Más/Menos.
        item.pop("evidence", None)

    return selected


def _player_evidence(history: list[float], threshold: int) -> tuple[dict[str, Any], float | None]:
    values = [float(v) for v in history or []]
    hits = sum(1 for v in values if v >= threshold)
    return _evidence(hits, len(values)), (fmean(values) if values else None)


def _player_explanation(name: str, label: str, evidence: dict[str, Any], avg: float | None, unit: str) -> str:
    if not evidence["n"]:
        return f"Porque {name} no tiene historial suficiente como titular."
    return (
        f"Porque {name} registró {label} en {evidence['hits']} de sus últimos {evidence['n']} partidos "
        f"como titular (promedio {avg:.1f} {unit})."
    )


def _add_player_candidates(
    candidates: list[dict[str, Any]],
    team: Team,
    players: list[dict[str, Any]],
) -> None:
    for player in players:
        name = str(player.get("name") or "").strip()
        if not name or player.get("is_starter") is False:
            # Un suplente confirmado no tiene minutos garantizados para la prop.
            continue
        needs_confirmation = player.get("is_starter") is not True
        group = f"player_shots:{team.id}:{name.lower()}"
        projection = _number(player.get("expected_total_shots"))
        for selection, prob, history_key, threshold, unit in (
            ("2+ remates", _number(player.get("probability_two_plus")), "history_shots", 2, "remates"),
            ("3+ remates", _number(player.get("probability_three_plus")), "history_shots", 3, "remates"),
            ("4+ remates", _number(player.get("probability_four_plus")), "history_shots", 4, "remates"),
            ("1+ tiro al arco", _number(player.get("probability_sot_one_plus")), "history_sot", 1, "tiros al arco"),
            ("2+ tiros al arco", _number(player.get("probability_sot_two_plus")), "history_sot", 2, "tiros al arco"),
        ):
            if prob is None:
                continue
            evidence, avg = _player_evidence(player.get(history_key) or [], threshold)
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
                "explanation": _player_explanation(name, selection, evidence, avg, unit),
                "evidence": evidence,
            }
            if needs_confirmation:
                item["requires_starter_confirmation"] = True
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
        if name and prob is not None and player.get("is_starter") is not False:
            evidence, avg = _player_evidence(player.get("history_goals") or [], 1)
            item = {
                "id": f"player_goal_{team.id}_{name.lower()}",
                "category": "Jugadores",
                "group": f"player_goal:{team.id}:{name.lower()}",
                "market": f"Gol de {name} ({team.name})",
                "selection": f"{name} anota en cualquier momento",
                "line": None,
                "side": "player",
                "probability": round(prob, 4),
                "basis": "Proyección del modelo estadístico; no incluye cuota ni valoración frente a una casa.",
                "explanation": _player_explanation(name, "gol", evidence, avg, "goles"),
                "evidence": evidence,
            }
            if player.get("is_starter") is not True:
                item["requires_starter_confirmation"] = True
            candidates.append(item)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def select_top_recommended_pick(
    selected_markets: list[dict[str, Any]],
    recent_home: list[TeamMatch] | None = None,
    recent_away: list[TeamMatch] | None = None,
    probabilities: ProbabilityReport | None = None,
    expected: ExpectedMetrics | None = None,
) -> dict[str, Any] | None:
    """Selecciona la mejor recomendación global del partido (AI Top Pick).

    Evalúa todas las selecciones filtradas del catálogo (rango 60.0% - 88.0%),
    priorizando selecciones con alta probabilidad, consistencia en la muestra empírica
    y menor varianza estructural.
    """
    if not selected_markets:
        return None

    # Si hay selecciones sin sujeción a titularidad oficial, preferirlas para el Top Pick
    stable_pool = [m for m in selected_markets if not m.get("requires_starter_confirmation")]
    pool = stable_pool if stable_pool else selected_markets

    # Con cuotas, el pick recomendado es el de mayor valor esperado (no el más probable).
    priced_pool = [m for m in pool if m.get("edge") is not None]
    if priced_pool:
        pool = priced_pool

    def score_candidate(item: dict[str, Any]) -> float:
        prob = float(item.get("probability", 0.0))
        bonus = 0.0
        cat = str(item.get("category", ""))
        # Ponderación por estabilidad de mercado
        cat_weight = 1.0
        if cat in ("Córners", "Goles", "Resultado"):
            cat_weight = 1.05
        elif cat in ("Fueras de juego", "Especiales"):
            cat_weight = 0.95
        return (prob + bonus) * cat_weight

    if priced_pool:
        best = max(pool, key=lambda item: (item["edge"], item["probability"]))
    else:
        best = max(pool, key=score_candidate)

    return {
        "market": best.get("market"),
        "selection": best.get("selection"),
        "category": best.get("category"),
        "probability": best.get("probability"),
        "explanation": best.get("explanation"),
        "requires_starter_confirmation": best.get("requires_starter_confirmation", False),
        **({"odds": best["odds"], "edge": best["edge"]} if best.get("edge") is not None else {}),
    }


# Selecciones destacadas ("las más seguras"): las categorías que mejor rindieron en
# resultados reales, sin mercados por mitad. En 20 partidos reales, las 5 más probables de
# estas categorías acertaron 91% frente a 78% del reporte completo.
FEATURED_CATEGORIES: frozenset[str] = frozenset(
    {"Goles", "Faltas", "Remates", "Tiros al arco", "Córners", "Resultado"}
)
FEATURED_LIMIT = 5
FEATURED_MIN_PROBABILITY = 0.75
FEATURED_MAX_PER_CATEGORY = 2


# Máximo de selecciones publicadas (y registradas) por partido, contando el Pick. Las de un
# mismo partido dependen del mismo guion: si sale distinto (un favorito que pierde, un 0-0
# esperado abierto) caen juntas. En resultados reales, 5 por partido acertó ~2 puntos más.
MAX_SELECTIONS_PER_MATCH = 5
# Selecciones de categorías frenadas que se registran sin publicar, por partido: bastan
# para medir si la categoría se recuperó sin inflar el histórico.
MAX_UNPUBLISHED_PER_MATCH = 2


def cap_selections(
    markets: list[dict[str, Any]],
    top_pick: dict[str, Any] | None = None,
    limit: int = MAX_SELECTIONS_PER_MATCH,
) -> list[dict[str, Any]]:
    """El Pick y las selecciones más probables hasta `limit`, en el orden original."""
    pick = (top_pick or {}).get("selection")
    others = sorted(
        (m for m in markets if m.get("selection") != pick),
        key=lambda m: -float(m.get("probability") or 0.0),
    )
    keep = {id(m) for m in others[: max(0, limit - (1 if pick else 0))]}
    return [m for m in markets if id(m) in keep or (pick and m.get("selection") == pick)]


def select_featured_markets(
    markets: list[dict[str, Any]],
    top_pick: dict[str, Any] | None = None,
    limit: int = FEATURED_LIMIT,
    min_probability: float = FEATURED_MIN_PROBABILITY,
    max_per_category: int = FEATURED_MAX_PER_CATEGORY,
) -> list[dict[str, Any]]:
    """Las selecciones más seguras del partido, sin repetir el Pick Recomendado."""
    pick = (top_pick or {}).get("selection")
    pool = [
        m for m in markets
        if m.get("category") in FEATURED_CATEGORIES
        and float(m.get("probability") or 0.0) >= min_probability
        and m.get("selection") != pick
        and not str(m.get("selection") or "").startswith(("1T ", "2T "))
    ]
    pool.sort(key=lambda m: -float(m.get("probability") or 0.0))
    featured: list[dict[str, Any]] = []
    per_category: dict[str, int] = defaultdict(int)
    for market in pool:
        if per_category[market["category"]] >= max_per_category:
            continue
        featured.append(market)
        per_category[market["category"]] += 1
        if len(featured) >= limit:
            break
    return featured


def mark_highlights(
    markets: list[dict[str, Any]], top_pick: dict[str, Any] | None, featured: list[dict[str, Any]]
) -> None:
    """Marca en cada selección si es el Pick ('pick') o una de las más seguras ('top5')."""
    pick = (top_pick or {}).get("selection")
    featured_selections = {m.get("selection") for m in featured}
    for market in markets:
        if pick and market.get("selection") == pick:
            market["highlight"] = "pick"
        elif market.get("selection") in featured_selections:
            market["highlight"] = "top5"
