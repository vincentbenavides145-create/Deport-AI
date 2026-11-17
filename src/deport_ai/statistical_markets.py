from __future__ import annotations

import math
from collections import defaultdict
from statistics import fmean
from typing import Any

from .domain import ExpectedMetrics, ProbabilityReport, Team, TeamMatch
from .markets_catalog import (
    MINIMUM_INFORMATIVE_LINES,
    MarketDefinition,
    build_declarative_catalog,
)
from .dynamic_calibration import MIN_CALIBRATION_SAMPLE
from .odds import MIN_EDGE, expected_value, odds_key_for_candidate
from .presentation_catalog import MarketPresentationCatalog, get_exigence_score
from .stats_engine import negative_binomial_pmf


MINIMUM_PROBABILITY = 0.60
MAXIMUM_PROBABILITY = 0.88


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


def _generate_dynamic_explanation(
    defn: MarketDefinition,
    home: Team,
    away: Team,
    proj_val: float | None,
    prob: float,
    recent_home: list[TeamMatch] | None = None,
    recent_away: list[TeamMatch] | None = None,
) -> str:
    """Genera explicaciones dinámicas y fundamentadas en los resultados empíricos recientes de los equipos."""
    if not recent_home and not recent_away:
        try:
            return defn.explanation_template.format(projection=proj_val, probability=prob) if proj_val is not None else defn.explanation_template
        except Exception:
            return defn.explanation_template

    grp = defn.group
    line = defn.line
    side = defn.side
    sel = defn.selection_template

    combined = (recent_home or []) + (recent_away or [])
    n_h = len(recent_home or [])
    n_a = len(recent_away or [])
    n_comb = len(combined)

    # 1. Goles Totales
    if grp == "total_goals" and line is not None and n_comb > 0:
        if side == "over":
            hits = sum(1 for m in combined if (m.goals_for + m.goals_against) > line)
            avg_g = fmean(m.goals_for + m.goals_against for m in combined)
            return f"Porque en {hits} de los últimos {n_comb} partidos de ambos equipos se superó la línea de {line} goles (promedio: {avg_g:.2f})."
        elif side == "under":
            hits = sum(1 for m in combined if (m.goals_for + m.goals_against) < line)
            avg_g = fmean(m.goals_for + m.goals_against for m in combined)
            return f"Porque en {hits} de los últimos {n_comb} encuentros de ambos se registraron menos de {line} goles (promedio: {avg_g:.2f})."

    # 2. Goles de Equipo
    if grp == "home_goals" and line is not None and recent_home:
        hits = sum(1 for m in recent_home if (m.goals_for > line if side == "over" else m.goals_for < line))
        avg_hg = fmean(m.goals_for for m in recent_home)
        comp = "más" if side == "over" else "menos"
        return f"Porque {home.name} anotó {comp} de {line} goles en {hits} de sus últimos {n_h} compromisos (promedia {avg_hg:.2f} goles)."

    if grp == "away_goals" and line is not None and recent_away:
        hits = sum(1 for m in recent_away if (m.goals_for > line if side == "over" else m.goals_for < line))
        avg_ag = fmean(m.goals_for for m in recent_away)
        comp = "más" if side == "over" else "menos"
        return f"Porque {away.name} anotó {comp} de {line} goles en {hits} de sus últimos {n_a} compromisos (promedia {avg_ag:.2f} goles)."

    # 3. Ambos Marcan (BTTS)
    if grp == "both_score" and n_comb > 0:
        if sel == "Sí":
            hits = sum(1 for m in combined if m.goals_for > 0 and m.goals_against > 0)
            return f"Porque ambos equipos anotaron y recibieron gol en {hits} de sus últimos {n_comb} encuentros."
        else:
            hits = sum(1 for m in combined if m.goals_for == 0 or m.goals_against == 0)
            return f"Porque al menos uno de los rivales se quedó sin anotar en {hits} de sus últimos {n_comb} partidos."

    # 4. Resultado (1X2, Doble Oportunidad, DNB)
    if grp in ("1x2", "double_chance", "dnb", "win_to_nil"):
        if home.name in sel and recent_home:
            wins_h = sum(1 for m in recent_home if m.result == "W")
            unbeaten_h = sum(1 for m in recent_home if m.result in ("W", "D"))
            if "(1X)" in sel or sel.startswith("DNB"):
                return f"Porque {home.name} evitó la derrota en {unbeaten_h} de sus últimos {n_h} partidos con fuerte solidez de local."
            if "gana a cero" in sel:
                cs_h = sum(1 for m in recent_home if m.result == "W" and m.goals_against == 0)
                return f"Porque {home.name} ganó manteniendo su arco a cero en {cs_h} de sus últimos {n_h} partidos."
            return f"Porque {home.name} suma {wins_h} victorias en sus últimos {n_h} partidos con clara superioridad de campo."
        if away.name in sel and recent_away:
            wins_a = sum(1 for m in recent_away if m.result == "W")
            unbeaten_a = sum(1 for m in recent_away if m.result in ("W", "D"))
            if "(X2)" in sel or sel.startswith("DNB"):
                return f"Porque {away.name} sumó puntos en {unbeaten_a} de sus últimos {n_a} partidos como visitante."
            return f"Porque {away.name} llega con {wins_a} victorias en sus últimos {n_a} encuentros oficiales."

    # 5. Córners
    if grp.startswith("corners_"):
        h_c = [m.stats_for.get("corner_kicks") for m in (recent_home or []) if m.stats_for.get("corner_kicks") is not None]
        a_c = [m.stats_for.get("corner_kicks") for m in (recent_away or []) if m.stats_for.get("corner_kicks") is not None]
        if grp == "corners_home" and h_c and line is not None:
            hits = sum(1 for c in h_c if (c > line if side == "over" else c < line))
            avg_c = fmean(h_c)
            comp = "superó" if side == "over" else "estuvo por debajo de"
            return f"Porque {home.name} promedia {avg_c:.1f} saques de esquina y {comp} los {line} córners en {hits} de sus últimos {len(h_c)} partidos."
        if grp == "corners_away" and a_c and line is not None:
            hits = sum(1 for c in a_c if (c > line if side == "over" else c < line))
            avg_c = fmean(a_c)
            comp = "superó" if side == "over" else "estuvo por debajo de"
            return f"Porque {away.name} promedia {avg_c:.1f} saques de esquina y {comp} los {line} córners en {hits} de sus últimos {len(a_c)} partidos."
        if grp == "corners_total" and line is not None and (h_c or a_c):
            avg_tot = (fmean(h_c) if h_c else 4.5) + (fmean(a_c) if a_c else 4.5)
            comp = "alta generación" if side == "over" else "volumen contenido"
            return f"Porque la combinación de ambos equipos promedia {avg_tot:.1f} saques de esquina totales en sus fechas recientes ({comp})."

    # 6. Tarjetas
    if grp.startswith("cards_"):
        h_t = [m.stats_for.get("yellow_cards") for m in (recent_home or []) if m.stats_for.get("yellow_cards") is not None]
        a_t = [m.stats_for.get("yellow_cards") for m in (recent_away or []) if m.stats_for.get("yellow_cards") is not None]
        if grp == "cards_total" and line is not None and (h_t or a_t):
            avg_tot = (fmean(h_t) if h_t else 2.0) + (fmean(a_t) if a_t else 2.0)
            comp = "disciplinado con apenas" if side == "under" else "de alta fricción con"
            return f"Porque ambos equipos registran un promedio {comp} {avg_tot:.1f} tarjetas por partido en sus fechas previas."
        if grp == "cards_home" and h_t and line is not None:
            avg_t = fmean(h_t)
            hits = sum(1 for t in h_t if (t > line if side == "over" else t < line))
            comp = "más" if side == "over" else "menos"
            return f"Porque {home.name} promedia {avg_t:.1f} tarjetas y registró {comp} de {line} en {hits} de sus últimos {len(h_t)} partidos."
        if grp == "cards_away" and a_t and line is not None:
            avg_t = fmean(a_t)
            hits = sum(1 for t in a_t if (t > line if side == "over" else t < line))
            comp = "más" if side == "over" else "menos"
            return f"Porque {away.name} promedia {avg_t:.1f} tarjetas y registró {comp} de {line} en {hits} de sus últimos {len(a_t)} partidos."

    # 7. Remates
    if grp.startswith("shots_"):
        h_s = [m.stats_for.get("total_shots") for m in (recent_home or []) if m.stats_for.get("total_shots") is not None]
        a_s = [m.stats_for.get("total_shots") for m in (recent_away or []) if m.stats_for.get("total_shots") is not None]
        if grp == "shots_home" and h_s and line is not None:
            avg_s = fmean(h_s)
            comp = "más" if side == "over" else "menos"
            return f"Porque {home.name} promedia {avg_s:.1f} remates y registró {comp} de {line} en {len(h_s)} partidos analizados."
        if grp == "shots_away" and a_s and line is not None:
            avg_s = fmean(a_s)
            comp = "más" if side == "over" else "menos"
            return f"Porque {away.name} promedia {avg_s:.1f} remates y registró {comp} de {line} en {len(a_s)} partidos analizados."
        if grp == "shots_total" and line is not None and (h_s or a_s):
            avg_tot = (fmean(h_s) if h_s else 12.0) + (fmean(a_s) if a_s else 10.0)
            comp = "elevado volumen ofensivo" if side == "over" else "volumen ofensivo contenido"
            return f"Porque ambos clubes combinan {avg_tot:.1f} remates promedio por encuentro ({comp})."

    # 8. Mercados Creativos (Tarjetas mutuas, 1X2, Córners mutuos, Gol en ambas mitades, Combos)
    if grp in ("both_teams_card", "both_teams_2_cards") and n_comb > 0:
        min_c = 1 if grp == "both_teams_card" else 2
        hits = 0
        tot = 0
        for m in combined:
            yf = m.stats_for.get("yellow_cards")
            ya = m.stats_against.get("yellow_cards")
            if yf is not None and ya is not None:
                tot += 1
                if yf >= min_c and ya >= min_c:
                    hits += 1
        if tot > 0:
            return f"Porque ambos equipos recibieron {min_c}+ tarjeta(s) en {hits} de sus últimos {tot} partidos disputados."
        return f"Porque el promedio de tarjetas conjuntas ({proj_val:.2f}) proyecta alta probabilidad de amonestaciones mutuas." if proj_val else defn.explanation_template

    if grp == "cards_1x2":
        t_name = home.name if home.name in sel else away.name
        rec = recent_home if home.name in sel else recent_away
        if rec:
            hits = sum(1 for m in rec if (m.stats_for.get("yellow_cards") or 0) > (m.stats_against.get("yellow_cards") or 0))
            return f"Porque {t_name} recibió más tarjetas que su adversario en {hits} de sus últimos {len(rec)} compromisos."

    if grp == "both_teams_corners" and n_comb > 0:
        thresh = 4 if "4+" in sel else 3
        hits = 0
        tot = 0
        for m in combined:
            cf = m.stats_for.get("corner_kicks")
            ca = m.stats_against.get("corner_kicks")
            if cf is not None and ca is not None:
                tot += 1
                if cf >= thresh and ca >= thresh:
                    hits += 1
        if tot > 0:
            return f"Porque ambos clubes alcanzaron al menos {thresh} saques de esquina en {hits} de sus últimos {tot} partidos."

    if grp == "goal_both_halves" and n_comb > 0:
        hits = sum(1 for m in combined if (m.goals_for + m.goals_against) >= 2)
        return f"Porque en {hits} de los últimos {n_comb} partidos hubo un desarrollo dinámico con ritmo goleador en ambas etapas."

    if grp == "team_score_both_halves":
        t_name = home.name if home.name in sel else away.name
        rec = recent_home if home.name in sel else recent_away
        if rec:
            hits = sum(1 for m in rec if m.goals_for >= 2)
            return f"Porque {t_name} anotó 2 o más goles en {hits} de sus últimos {len(rec)} partidos demostrando constancia ofensiva."

    if grp == "combo_result_goals":
        if "(1X)" in sel and recent_home:
            hits = sum(1 for m in recent_home if m.result in ("W", "D") and (m.goals_for + m.goals_against > 1 if "Más de 1.5" in sel else m.goals_for + m.goals_against < 4))
            return f"Porque {home.name} evitó la derrota y cumplió el margen de goles en {hits} de sus últimos {n_h} partidos."
        if "(X2)" in sel and recent_away:
            hits = sum(1 for m in recent_away if m.result in ("W", "D") and (m.goals_for + m.goals_against > 1 if "Más de 1.5" in sel else m.goals_for + m.goals_against < 4))
            return f"Porque {away.name} sumó puntos y cumplió el margen de goles en {hits} de sus últimos {n_a} partidos."
        if "gana y Más de 1.5" in sel:
            t_name = home.name if home.name in sel else away.name
            rec = recent_home if home.name in sel else recent_away
            if rec:
                hits = sum(1 for m in rec if m.result == "W" and (m.goals_for + m.goals_against) > 1)
                return f"Porque {t_name} triunfó en partidos de múltiples goles en {hits} de sus últimos {len(rec)} encuentros."
        if "Ambos marcan y Más de 2.5" in sel and n_comb > 0:
            hits = sum(1 for m in combined if m.goals_for > 0 and m.goals_against > 0 and (m.goals_for + m.goals_against) > 2)
            return f"Porque ambos anotaron y se superaron los 2.5 goles en {hits} de sus últimos {n_comb} partidos."

    if grp == "both_teams_shots_on" and n_comb > 0:
        hits = 0
        tot = 0
        for m in combined:
            sf = m.stats_for.get("shots_on_target")
            sa = m.stats_against.get("shots_on_target")
            if sf is not None and sa is not None:
                tot += 1
                if sf >= 3 and sa >= 3:
                    hits += 1
        if tot > 0:
            return f"Porque ambos equipos alcanzaron 3+ tiros a puerta en {hits} de sus últimos {tot} encuentros."

    if grp == "shots_on_1x2":
        t_name = home.name if home.name in sel else away.name
        rec = recent_home if home.name in sel else recent_away
        if rec:
            hits = sum(1 for m in rec if (m.stats_for.get("shots_on_target") or 0) > (m.stats_against.get("shots_on_target") or 0))
            return f"Porque {t_name} superó a sus rivales en tiros a puerta en {hits} de sus últimos {len(rec)} compromisos."

    # 9. Multigoles y Combos 1X2 + Ambos Marcan
    if grp == "multigoals" and n_comb > 0:
        min_g, max_g = (1, 3) if "1 a 3" in sel else ((2, 4) if "2 a 4" in sel else (2, 5))
        hits = sum(1 for m in combined if min_g <= (m.goals_for + m.goals_against) <= max_g)
        return f"Porque en {hits} de los últimos {n_comb} partidos de ambos se registró un total de {sel}."

    if grp == "combo_1x2_btts":
        if home.name in sel and recent_home:
            hits = sum(1 for m in recent_home if (m.result == "W" if "gana" in sel else m.result in ("W", "D")) and m.goals_for > 0 and m.goals_against > 0)
            return f"Porque {home.name} cumplió este patrón de resultado con goles de ambos lados en {hits} de sus últimos {n_h} partidos."
        if away.name in sel and recent_away:
            hits = sum(1 for m in recent_away if (m.result == "W" if "gana" in sel else m.result in ("W", "D")) and m.goals_for > 0 and m.goals_against > 0)
            return f"Porque {away.name} sumó con goles en ambas porterías en {hits} de sus últimos {n_a} compromisos como visitante."

    if grp == "btts_second_half":
        return "Porque la dinámica táctica y necesidad de puntos en el complemento suele forzar anotaciones en ambos arcos."

    if grp == "corners_first_half" and line is not None:
        comp = "alta generación ofensiva inicial" if side == "over" else "estudio táctico cerrado en los primeros 45 minutos"
        return f"Porque la proyección de córners en la primera mitad ({proj_val:.2f}) refleja {comp}."

    # 10. Faltas
    if grp.startswith("fouls_"):
        h_f = [m.stats_for.get("fouls") for m in (recent_home or []) if m.stats_for.get("fouls") is not None]
        a_f = [m.stats_for.get("fouls") for m in (recent_away or []) if m.stats_for.get("fouls") is not None]
        if grp == "fouls_total" and line is not None and (h_f or a_f):
            avg_tot = (fmean(h_f) if h_f else 12.0) + (fmean(a_f) if a_f else 12.0)
            comp = "intensa fricción" if side == "over" else "fútbol fluido y limpio"
            return f"Porque ambos equipos combinan {avg_tot:.1f} faltas por partido en sus fechas recientes ({comp})."
        if grp == "fouls_home" and h_f and line is not None:
            avg_f = fmean(h_f)
            hits = sum(1 for f in h_f if (f > line if side == "over" else f < line))
            comp = "más" if side == "over" else "menos"
            return f"Porque {home.name} promedia {avg_f:.1f} faltas y registró {comp} de {line} en {hits} de sus últimos {len(h_f)} partidos."
        if grp == "fouls_away" and a_f and line is not None:
            avg_f = fmean(a_f)
            hits = sum(1 for f in a_f if (f > line if side == "over" else f < line))
            comp = "más" if side == "over" else "menos"
            return f"Porque {away.name} promedia {avg_f:.1f} faltas y registró {comp} de {line} en {hits} de sus últimos {len(a_f)} partidos."
        if grp == "fouls_1x2":
            t_name = home.name if home.name in sel else away.name
            rec = recent_home if home.name in sel else recent_away
            if rec:
                hits = sum(1 for m in rec if (m.stats_for.get("fouls") or 0) > (m.stats_against.get("fouls") or 0))
                return f"Porque {t_name} cometió más faltas que su adversario en {hits} de sus últimos {len(rec)} compromisos."

    # Fallback
    try:
        return defn.explanation_template.format(projection=proj_val, probability=prob) if proj_val is not None else defn.explanation_template
    except Exception:
        return defn.explanation_template


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

        # 9. Mercados Creativos (Tarjetas mutuas, Córners mutuos, Tiros a puerta mutuos, Combos)
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

        explanation = _generate_dynamic_explanation(
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
    return group


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
    """
    candidates = calculate_candidate_markets(
        home, away, probabilities, expected, recent_home=recent_home, recent_away=recent_away
    )

    # 1. Filtro estricto por MarketPresentationCatalog y rango de probabilidad óptimo
    eligible: list[dict[str, Any]] = []
    cat_factors = getattr(calibration, "category_factors", {}) if calibration else {}

    for c in candidates:
        if not MarketPresentationCatalog.is_presentable(c):
            continue

        prob = c.get("probability")
        if prob is None:
            continue

        cat = c.get("category", "")
        # Si existe calibración dinámica activa para esta categoría, aplicar factor empírico
        if cat in cat_factors:
            f_info = cat_factors[cat]
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

        if prob < minimum_probability:
            continue

        if prob > maximum_probability:
            continue

        price = (odds or {}).get(odds_key_for_candidate(c.get("id")) or "")
        if price and price > 1.0:
            edge = round(expected_value(prob, price), 4)
            if edge < min_edge:
                # La cuota no paga el riesgo: valor esperado insuficiente o negativo.
                continue
            c["odds"] = price
            c["edge"] = edge

        eligible.append(c)

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

