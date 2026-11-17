from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any

from .dynamic_calibration import MIN_CALIBRATION_SAMPLE
from .domain import AnalysisReport, TeamMatch
from .stats_engine import detect_altitude_impact, form_line, top_scores



def format_report(report: AnalysisReport) -> str:
    p = report.probabilities
    expected = report.expected
    corner_total = _sum_optional(expected.corners_home, expected.corners_away)
    lines = [
        "",
        "PARTIDO:",
        f"{report.home.name} vs {report.away.name}",
        "",
        "ANÁLISIS:",
        "",
    ]
    if report.fixture:
        lines.extend(
            [
                f"Fixture: {report.fixture.date} | {report.fixture.league_name or 'Competición no informada'}",
                "",
            ]
        )

    if report.confidence:
        c_badge = "🟢" if report.confidence.level == "ALTA" else "🟡" if report.confidence.level == "MEDIA" else "🔴"
        lineup_str = "Once confirmado oficialmente" if report.confidence.lineups_confirmed else "Alineaciones no confirmadas (sujeto a rotación)"
        lines.extend(
            [
                f"{c_badge} CONFIANZA EPISTÉMICA: {report.confidence.level} ({report.confidence.score}/100)",
                f"  • Muestra empírica: {report.confidence.sample_size} partidos analizados | {report.confidence.detailed_matches} con métricas avanzadas completas | {lineup_str}",
                "",
            ]
        )

    lines.extend(_build_statistical_markets_section(report))
    lines.extend(_build_decisive_ticket(report))
    lines.extend(_build_unexploited_section(report))

    lines.extend(
        [
            "Forma reciente:",
            f"- {report.home.name}: {_team_form(report.recent_home)}",
            f"- {report.away.name}: {_team_form(report.recent_away)}",
            f"- H2H: {len(report.h2h)} enfrentamientos directos registrados.",
            "",
            "Rendimiento por sede:",
            f"- Local, {report.home.name}: {_venue_form(report.recent_home, True)}",
            f"- Visitante, {report.away.name}: {_venue_form(report.recent_away, False)}",
            "",
            "Probabilidades 1X2:",
            f"Victoria local: {_pct(p.home_win)}",
            f"Empate: {_pct(p.draw)}",
            f"Victoria visitante: {_pct(p.away_win)}",
            "",
            f"Goles esperados: {report.home.name} {p.expected_home_goals:.2f} — {report.away.name} {p.expected_away_goals:.2f} (Total: {p.expected_home_goals + p.expected_away_goals:.2f})",
        ]
    )
    if report.attribution_home and report.attribution_away:
        ah = report.attribution_home
        aa = report.attribution_away
        lines.extend(
            [
                "Auditoría de Goles Esperados (Waterfall Attribution):",
                f"  • {report.home.name} (xG {ah.final_expected_goals:.2f}): Base Liga {ah.base_league_goals:+.2f} | Ventaja Local {ah.venue_impact:+.2f} | Impacto Elo {ah.elo_impact:+.2f} | Forma {ah.recent_form_impact:+.2f} | Descanso {ah.rest_impact:+.2f}",
                f"  • {report.away.name} (xG {aa.final_expected_goals:.2f}): Base Liga {aa.base_league_goals:+.2f} | Factor Visita {aa.venue_impact:+.2f} | Impacto Elo {aa.elo_impact:+.2f} | Forma {aa.recent_form_impact:+.2f} | Descanso {aa.rest_impact:+.2f}",
            ]
        )
    lines.extend(
        [
            f"Marcador Exacto Oficial (Resultado #1): {top_scores(p)[0][0]} ({_pct(top_scores(p)[0][1])})",
            "",
            "Líneas de Apuesta Destacadas (≥ 60%):",
        ]
    )
    is_heavy_fav = max(p.home_win, p.away_win) >= 0.70
    fav_team = report.home if p.home_win >= 0.70 else (report.away if p.away_win >= 0.70 else None)
    und_team = report.away if p.home_win >= 0.70 else (report.home if p.away_win >= 0.70 else None)

    if p.over_15 is not None and p.over_15 >= 0.60:
        lines.append(f"- Goles Totales: Más de 1.5 goles ({_pct(p.over_15)})")
    if p.over_25 is not None and p.over_25 >= 0.60:
        lines.append(f"- Goles Totales: Más de 2.5 goles ({_pct(p.over_25)})")
    elif p.under_25 is not None and p.under_25 >= 0.60:
        lines.append(f"- Goles Totales: Menos de 2.5 goles ({_pct(p.under_25)})")
    if p.second_half_over_05 is not None and p.second_half_over_05 >= 0.60:
        lines.append(f"- 2do Tiempo: Más de 0.5 goles 2T ({_pct(p.second_half_over_05)})")
    if p.first_half_over_05 is not None and p.first_half_over_05 >= 0.60 and not is_heavy_fav:
        lines.append(f"- 1er Tiempo: Más de 0.5 goles 1T ({_pct(p.first_half_over_05)})")

    # Mercados de Underdog Inteligente y DNB
    if is_heavy_fav and fav_team and und_team:
        und_under_15_goals = p.away_under_15 if und_team == report.away else p.home_under_15
        if und_under_15_goals is not None and und_under_15_goals >= 0.65:
            lines.append(f"- Under Goles Underdog: {und_team.name} Menos de 1.5 goles ({_pct(und_under_15_goals)})")
        und_corners_under_35 = expected.under_35_corners_away if und_team == report.away else expected.under_35_corners_home
        if und_corners_under_35 is not None and und_corners_under_35 >= 0.65:
            lines.append(f"- Córners Underdog: {und_team.name} Menos de 3.5 córners ({_pct(und_corners_under_35)})")
        und_cards_over_15 = expected.over_15_cards_away if und_team == report.away else expected.over_15_cards_home
        if und_cards_over_15 is not None and und_cards_over_15 >= 0.65:
            lines.append(f"- Tarjetas Underdog: {und_team.name} Más de 1.5 tarjetas ({_pct(und_cards_over_15)})")
    else:
        if p.dnb_home is not None and p.dnb_home >= 0.60:
            lines.append(f"- Empate Apuesta No Válida: DNB {report.home.name} ({_pct(p.dnb_home)})")
        elif p.dnb_away is not None and p.dnb_away >= 0.60:
            lines.append(f"- Empate Apuesta No Válida: DNB {report.away.name} ({_pct(p.dnb_away)})")

    if is_heavy_fav and und_team:
        if fav_team == report.home:
            if expected.over_65_corners_home is not None and expected.over_65_corners_home >= 0.60:
                lines.append(f"- Córners Equipo: {report.home.name} Más de 6.5 córners ({_pct(expected.over_65_corners_home)})")
            elif expected.over_55_corners_home is not None and expected.over_55_corners_home >= 0.60:
                lines.append(f"- Córners Equipo: {report.home.name} Más de 5.5 córners ({_pct(expected.over_55_corners_home)})")
            elif expected.over_45_corners_home is not None and expected.over_45_corners_home >= 0.60:
                lines.append(f"- Córners Equipo: {report.home.name} Más de 4.5 córners ({_pct(expected.over_45_corners_home)})")
        elif fav_team == report.away:
            if expected.over_65_corners_away is not None and expected.over_65_corners_away >= 0.60:
                lines.append(f"- Córners Equipo: {report.away.name} Más de 6.5 córners ({_pct(expected.over_65_corners_away)})")
            elif expected.over_55_corners_away is not None and expected.over_55_corners_away >= 0.60:
                lines.append(f"- Córners Equipo: {report.away.name} Más de 5.5 córners ({_pct(expected.over_55_corners_away)})")
            elif expected.over_45_corners_away is not None and expected.over_45_corners_away >= 0.60:
                lines.append(f"- Córners Equipo: {report.away.name} Más de 4.5 córners ({_pct(expected.over_45_corners_away)})")
    else:
        if expected.over_55_corners_home is not None and expected.over_55_corners_home >= 0.60:
            lines.append(f"- Córners Equipo: {report.home.name} Más de 5.5 córners ({_pct(expected.over_55_corners_home)})")
        elif expected.over_45_corners_home is not None and expected.over_45_corners_home >= 0.60:
            lines.append(f"- Córners Equipo: {report.home.name} Más de 4.5 córners ({_pct(expected.over_45_corners_home)})")

        if expected.over_55_corners_away is not None and expected.over_55_corners_away >= 0.60:
            lines.append(f"- Córners Equipo: {report.away.name} Más de 5.5 córners ({_pct(expected.over_55_corners_away)})")
        elif expected.over_45_corners_away is not None and expected.over_45_corners_away >= 0.60:
            lines.append(f"- Córners Equipo: {report.away.name} Más de 4.5 córners ({_pct(expected.over_45_corners_away)})")

    # Fueras de Juego (Tanto Over como Under)
    if expected.over_25_offsides is not None and expected.over_25_offsides >= 0.60:
        lines.append(f"- Fueras de Juego: Más de 2.5 Offsides ({_pct(expected.over_25_offsides)})")
    elif expected.under_35_offsides is not None and expected.under_35_offsides >= 0.60:
        lines.append(f"- Fueras de Juego: Menos de 3.5 Offsides ({_pct(expected.under_35_offsides)})")
    elif expected.under_45_offsides is not None and expected.under_45_offsides >= 0.70:
        lines.append(f"- Fueras de Juego: Menos de 4.5 Offsides ({_pct(expected.under_45_offsides)})")

    # Remates Totales y Tiros al Arco por Equipo y Totales
    if expected.over_295_total_shots is not None and expected.over_295_total_shots >= 0.60:
        lines.append(f"- Remates Totales: Más de 29.5 remates ({_pct(expected.over_295_total_shots)})")
    elif expected.over_275_total_shots is not None and expected.over_275_total_shots >= 0.60:
        lines.append(f"- Remates Totales: Más de 27.5 remates ({_pct(expected.over_275_total_shots)})")
    elif expected.over_235_total_shots is not None and expected.over_235_total_shots >= 0.60:
        lines.append(f"- Remates Totales: Más de 23.5 remates ({_pct(expected.over_235_total_shots)})")
    elif expected.over_215_total_shots is not None and expected.over_215_total_shots >= 0.60:
        lines.append(f"- Remates Totales: Más de 21.5 remates ({_pct(expected.over_215_total_shots)})")
    elif expected.under_245_total_shots is not None and expected.under_245_total_shots >= 0.60:
        lines.append(f"- Remates Totales: Menos de 24.5 remates ({_pct(expected.under_245_total_shots)})")

    if expected.over_175_shots_home is not None and expected.over_175_shots_home >= 0.60:
        lines.append(f"- Remates Equipo: {report.home.name} Más de 17.5 remates ({_pct(expected.over_175_shots_home)})")
    elif expected.over_155_shots_home is not None and expected.over_155_shots_home >= 0.60:
        lines.append(f"- Remates Equipo: {report.home.name} Más de 15.5 remates ({_pct(expected.over_155_shots_home)})")
    elif expected.over_135_shots_home is not None and expected.over_135_shots_home >= 0.60:
        lines.append(f"- Remates Equipo: {report.home.name} Más de 13.5 remates ({_pct(expected.over_135_shots_home)})")
    elif expected.over_115_shots_home is not None and expected.over_115_shots_home >= 0.60:
        lines.append(f"- Remates Equipo: {report.home.name} Más de 11.5 remates ({_pct(expected.over_115_shots_home)})")

    if is_heavy_fav and und_team == report.away:
        if expected.under_85_shots_away is not None and expected.under_85_shots_away >= 0.65:
            lines.append(f"- Remates Equipo: {report.away.name} Menos de 8.5 remates ({_pct(expected.under_85_shots_away)})")
    else:
        if expected.over_135_shots_away is not None and expected.over_135_shots_away >= 0.60:
            lines.append(f"- Remates Equipo: {report.away.name} Más de 13.5 remates ({_pct(expected.over_135_shots_away)})")
        elif expected.under_85_shots_away is not None and expected.under_85_shots_away >= 0.65:
            lines.append(f"- Remates Equipo: {report.away.name} Menos de 8.5 remates ({_pct(expected.under_85_shots_away)})")

    if expected.over_105_shots_on is not None and expected.over_105_shots_on >= 0.60:
        lines.append(f"- Tiros al Arco: Más de 10.5 tiros a puerta ({_pct(expected.over_105_shots_on)})")
    elif expected.over_85_shots_on is not None and expected.over_85_shots_on >= 0.60:
        lines.append(f"- Tiros al Arco: Más de 8.5 tiros a puerta ({_pct(expected.over_85_shots_on)})")
    elif expected.over_75_shots_on is not None and expected.over_75_shots_on >= 0.60:
        lines.append(f"- Tiros al Arco: Más de 7.5 tiros a puerta ({_pct(expected.over_75_shots_on)})")

    if expected.over_65_shots_on_home is not None and expected.over_65_shots_on_home >= 0.60:
        lines.append(f"- Tiros al Arco: {report.home.name} Más de 6.5 al arco ({_pct(expected.over_65_shots_on_home)})")
    elif expected.over_55_shots_on_home is not None and expected.over_55_shots_on_home >= 0.60:
        lines.append(f"- Tiros al Arco: {report.home.name} Más de 5.5 al arco ({_pct(expected.over_55_shots_on_home)})")
    elif expected.over_45_shots_on_home is not None and expected.over_45_shots_on_home >= 0.60:
        lines.append(f"- Tiros al Arco: {report.home.name} Más de 4.5 al arco ({_pct(expected.over_45_shots_on_home)})")

    if is_heavy_fav and und_team == report.away:
        if expected.under_25_shots_on_away is not None and expected.under_25_shots_on_away >= 0.65:
            lines.append(f"- Tiros al Arco: {report.away.name} Menos de 2.5 al arco ({_pct(expected.under_25_shots_on_away)})")
    else:
        if expected.over_35_shots_on_away is not None and expected.over_35_shots_on_away >= 0.60:
            lines.append(f"- Tiros al Arco: {report.away.name} Más de 3.5 al arco ({_pct(expected.over_35_shots_on_away)})")
        elif expected.under_25_shots_on_away is not None and expected.under_25_shots_on_away >= 0.65:
            lines.append(f"- Tiros al Arco: {report.away.name} Menos de 2.5 al arco ({_pct(expected.under_25_shots_on_away)})")

    if expected.over_05_woodwork is not None and expected.over_05_woodwork >= 0.60:
        lines.append(f"- Tiros al Palo: Probabilidad de Tiro al Palo en el partido ({_pct(expected.over_05_woodwork)})")

    cards_total = _sum_optional(expected.cards_home, expected.cards_away)
    tot_shots = _sum_optional(expected.total_shots_home, expected.total_shots_away)
    tot_shots_on = _sum_optional(expected.shots_on_home, expected.shots_on_away)
    tot_woodwork = _sum_optional(expected.woodwork_home, expected.woodwork_away)

    lines.append("")
    if tot_shots is not None:
        lines.append(f"Remates Totales esperados: {_number_or_na(tot_shots)} ({report.home.name}: {_number_or_na(expected.total_shots_home)}, {report.away.name}: {_number_or_na(expected.total_shots_away)})")
    if tot_shots_on is not None:
        lines.append(f"Tiros al Arco esperados: {_number_or_na(tot_shots_on)} ({report.home.name}: {_number_or_na(expected.shots_on_home)}, {report.away.name}: {_number_or_na(expected.shots_on_away)})")
    if tot_woodwork is not None and tot_woodwork > 0:
        wood_prob_str = f" [Prob. ≥1 al palo: {_pct(expected.over_05_woodwork)}]" if expected.over_05_woodwork and expected.over_05_woodwork >= 0.60 else ""
        lines.append(f"Tiros al Palo (Woodwork) esperados: {_number_or_na(tot_woodwork)} ({report.home.name}: {_number_or_na(expected.woodwork_home)}, {report.away.name}: {_number_or_na(expected.woodwork_away)}){wood_prob_str}")
    lines.append(f"Córners esperados: {_number_or_na(corner_total)} ({report.home.name}: {_number_or_na(expected.corners_home)}, {report.away.name}: {_number_or_na(expected.corners_away)})")
    lines.append(f"Tarjetas amarillas esperadas: {_number_or_na(cards_total)} ({report.home.name}: {_number_or_na(expected.cards_home)}, {report.away.name}: {_number_or_na(expected.cards_away)})")
    lines.append(f"Fueras de Juego (Offsides) esperados: {_number_or_na(_sum_optional(expected.offsides_home, expected.offsides_away))}")
    lines.append("")
    lines.append("Jugadores con mayor probabilidad de Tiros Totales (Remates):")
    lines.extend(_player_lines(report))

    goal_lines = _goalscorer_lines(report)
    if goal_lines and "No hay" not in goal_lines[0]:
        lines.extend(["", "Goleadores en cualquier momento (Anytime Goalscorer):"])
        lines.extend(goal_lines)

    lines.extend(_format_common_opponents(report))

    lines.extend(
        [
            "",
            "Riesgos del análisis:",
            f"- Factor clave: {report.risks[0] if report.risks else 'Alineaciones sujetas a confirmación oficial.'}",
            "",
            "Lectura de DEPORT AI:",
            report.narrative or _deterministic_narrative(report),
        ]
    )
    return "\n".join(lines)


def _format_common_opponents(report: AnalysisReport) -> list[str]:
    opps = report.common_opponents
    if not opps:
        return ["", "Comparativa ante Rivales Comunes: No registran rivales compartidos en la muestra reciente."]
    lines = [
        "",
        f"Comparativa ante Rivales Comunes ({len(opps)} rivales compartidos en últimos 15 partidos):",
    ]
    for idx, item in enumerate(opps[:4], start=1):
        opp_name = item["opponent_name"]
        hm = item["home_match"]
        am = item["away_match"]
        h_venue = "L" if hm["is_home"] else "V"
        a_venue = "L" if am["is_home"] else "V"
        adv = item["net_advantage"]
        adv_text = (
            f"Ventaja neta {report.home.name} (+{adv} DG)"
            if adv > 0
            else (
                f"Ventaja neta {report.away.name} (+{abs(adv)} DG)"
                if adv < 0
                else "Desempeño idéntico (0 DG)"
            )
        )
        lines.append(f"- vs. {opp_name}:")
        lines.append(f"  • {report.home.name} ({h_venue}): {hm['score']} ({hm['result']}) | {adv_text}")
        lines.append(f"  • {report.away.name} ({a_venue}): {am['score']} ({am['result']})")

    home_wins = sum(1 for item in opps if item["home_match"]["result"] == "W")
    home_draws = sum(1 for item in opps if item["home_match"]["result"] == "D")
    home_losses = sum(1 for item in opps if item["home_match"]["result"] == "L")
    away_wins = sum(1 for item in opps if item["away_match"]["result"] == "W")
    away_draws = sum(1 for item in opps if item["away_match"]["result"] == "D")
    away_losses = sum(1 for item in opps if item["away_match"]["result"] == "L")
    tot_home_gd = sum(item["home_gd"] for item in opps)
    tot_away_gd = sum(item["away_gd"] for item in opps)

    lines.append(
        f"- Balance ante Rivales Comunes: {report.home.name} {home_wins}V-{home_draws}E-{home_losses}D (Dif: {tot_home_gd:+d}) vs {report.away.name} {away_wins}V-{away_draws}E-{away_losses}D (Dif: {tot_away_gd:+d})"
    )
    return lines


def _team_form(matches: list[TeamMatch]) -> str:
    if not matches:
        return "Sin datos"
    subset = matches[:5]
    return (
        f"{form_line(subset)} | {len(matches)} partidos usados | "
        f"GF {fmean(match.goals_for for match in subset):.2f} | "
        f"GC {fmean(match.goals_against for match in subset):.2f}"
    )


def _venue_form(matches: list[TeamMatch], is_home: bool) -> str:
    subset = [match for match in matches if match.is_home == is_home]
    if not subset:
        return "No disponible"
    wins = sum(match.result == "W" for match in subset)
    draws = sum(match.result == "D" for match in subset)
    losses = sum(match.result == "L" for match in subset)
    return (
        f"{len(subset)} partidos, {wins}V-{draws}E-{losses}D, "
        f"GF {fmean(match.goals_for for match in subset):.2f}, "
        f"GC {fmean(match.goals_against for match in subset):.2f}"
    )


def _observed_stats(matches: list[TeamMatch]) -> str:
    labels = [
        ("total_shots", "tiros"),
        ("shots_on_goal", "al arco"),
        ("corner_kicks", "córners"),
        ("possession", "posesión"),
        ("yellow_cards", "amarillas"),
        ("red_cards", "rojas"),
    ]
    parts: list[str] = []
    for key, label in labels:
        values = [match.stats_for[key] for match in matches if key in match.stats_for]
        if values:
            suffix = "%" if key == "possession" else ""
            parts.append(f"{label} {fmean(values):.2f}{suffix} (n={len(values)})")
    return "; ".join(parts) if parts else "estadísticas detalladas no disponibles"


def _select_smart_player_prop(pl: dict[str, Any], team_name: str) -> dict[str, Any]:
    name = pl["name"]
    p2 = pl.get("probability_two_plus", 0.0)
    p3 = pl.get("probability_three_plus", 0.0)
    p4 = pl.get("probability_four_plus", 0.0)
    p5 = pl.get("probability_five_plus", 0.0)
    sot1 = pl.get("probability_sot_one_plus", 0.0)
    sot2 = pl.get("probability_sot_two_plus", 0.0)
    sot3 = pl.get("probability_sot_three_plus", 0.0)

    # Colectar todas las opciones disponibles de props para este jugador (estrictamente >= 60%)
    candidates: list[dict[str, Any]] = []

    # 1. Tiros al arco (Shots on Target - máxima liquidez y valor)
    if sot3 >= 0.60:
        candidates.append({"desc": "3+ Tiros al Arco (a puerta)", "prob": sot3, "short": f"{name} 3+ Tiros al Arco", "priority": 1})
    if sot2 >= 0.60:
        candidates.append({"desc": "2+ Tiros al Arco (a puerta)", "prob": sot2, "short": f"{name} 2+ Tiros al Arco", "priority": 2})
    if sot1 >= 0.60:
        candidates.append({"desc": "1+ Tiro al Arco (a puerta)", "prob": sot1, "short": f"{name} 1+ Tiro al Arco", "priority": 3})

    # 2. Remates totales escalados (5+, 4+, 3+, 2+)
    if p5 >= 0.60:
        candidates.append({"desc": "5+ Remates Totales", "prob": p5, "short": f"{name} 5+ Remates", "priority": 4})
    if p4 >= 0.60:
        candidates.append({"desc": "4+ Remates Totales", "prob": p4, "short": f"{name} 4+ Remates", "priority": 5})
    if p3 >= 0.60:
        candidates.append({"desc": "3+ Remates Totales", "prob": p3, "short": f"{name} 3+ Remates", "priority": 6})
    if p2 >= 0.60:
        candidates.append({"desc": "2+ Remates Totales", "prob": p2, "short": f"{name} 2+ Remates", "priority": 7})

    # Filtro del Sweet Spot Estricto: 60% <= P <= 79% (Cuotas 1.27 a 1.66)
    sweet_candidates = [c for c in candidates if 0.60 <= c["prob"] <= 0.79]
    if sweet_candidates:
        sweet_candidates.sort(key=lambda c: (c["priority"] > 3, abs(c["prob"] - 0.70)))
        best = sweet_candidates[0]
        return {
            "name": name,
            "team": team_name,
            "prop_desc": best["desc"],
            "probability": best["prob"],
            "short_desc": best["short"],
            "is_escalated": best["desc"] != "2+ Remates Totales",
        }

    # Rango ampliado si no hay en rango estricto: [0.60, 0.82]
    extended = [c for c in candidates if 0.60 <= c["prob"] <= 0.82]
    if extended:
        extended.sort(key=lambda c: (c["priority"] > 3, abs(c["prob"] - 0.70)))
        best = extended[0]
        return {
            "name": name,
            "team": team_name,
            "prop_desc": best["desc"],
            "probability": best["prob"],
            "short_desc": best["short"],
            "is_escalated": best["desc"] != "2+ Remates Totales",
        }

    # Fallback más cercano al 70% (solo si cumple >= 0.60)
    valid_candidates = [c for c in candidates if c["prob"] >= 0.60]
    if valid_candidates:
        valid_candidates.sort(key=lambda c: abs(c["prob"] - 0.70))
        best = valid_candidates[0]
        return {
            "name": name,
            "team": team_name,
            "prop_desc": best["desc"],
            "probability": best["prob"],
            "short_desc": best["short"],
            "is_escalated": best["desc"] != "2+ Remates Totales",
        }

    return {
        "name": name,
        "team": team_name,
        "prop_desc": "2+ Remates Totales",
        "probability": p2,
        "short_desc": f"{name} 2+ Remates",
        "is_escalated": False,
    }


def _market_category(market_name: str) -> str:
    lower = market_name.lower()
    if "fuera" in lower or "offside" in lower:
        return "OFFSIDES"
    if "córner" in lower or "corner" in lower:
        return "CORNERS"
    if "tarjeta" in lower or "amarilla" in lower:
        return "CARDS"
    if "tiro al arco" in lower or "tiros al arco" in lower or "puerta" in lower or "al arco" in lower:
        return "SOT"
    if "remate" in lower:
        return "SHOTS"
    if "gol" in lower or "btts" in lower or "marcan" in lower or "cero" in lower:
        return "GOALS"
    if "hándicap" in lower or "victoria" in lower or "doble" in lower or "dnb" in lower or "empate" in lower:
        return "HANDICAP"
    return "OTHER"


def _build_statistical_markets_section(report: AnalysisReport) -> list[str]:
    """Render the structured model markets without implying bookmaker availability."""
    if not report.statistical_markets:
        return []

    lines = [
        "============================================================",
        "MERCADOS ESTADÍSTICOS AMPLIADOS (proyecciones del modelo):",
        "Sin cuotas, sin comparación con casas y sin afirmar disponibilidad en una casa concreta.",
        "============================================================",
    ]
    for item in report.statistical_markets:
        detail = f"{item['market']}: {item['selection']} ({_pct(item['probability'])})"
        if "projection" in item:
            detail += f" | Proyección: {item['projection']:.2f}"
        if item.get("requires_starter_confirmation"):
            detail += " | Requiere confirmar titularidad"
        lines.append(f"- {item['category']} — {detail}")
    lines.append("")
    return lines


def _build_decisive_ticket(report: AnalysisReport) -> list[str]:
    p = report.probabilities
    expected = report.expected

    alt_impact = detect_altitude_impact(report.home.id, report.home.name, report.away.id, report.away.name)
    disallow_away_ha = bool(alt_impact and alt_impact.get("disallow_away_handicap"))

    is_heavy_fav = max(p.home_win, p.away_win) >= 0.70
    fav_team = report.home if p.home_win >= 0.70 else (report.away if p.away_win >= 0.70 else None)
    und_team = report.away if p.home_win >= 0.70 else (report.home if p.away_win >= 0.70 else None)

    # Sweet Spot Global Estricto (60% <= P <= 80% -> Cuotas 1.25 a 1.66)
    # Ninguna apuesta fuera de este rango puede ser Pick Principal o Pick Secundario
    SWEET_MIN = 0.60
    SWEET_MAX = 0.80

    market_checks: list[tuple[str, float]] = []

    # 1. 1X2, Doble Oportunidad y Hándicaps:
    if is_heavy_fav and fav_team and und_team:
        # Underdog inteligente en partido desbalanceado (NUNCA Over Córners ni Over Remates):
        und_u15 = p.away_under_15 if und_team == report.away else p.home_under_15
        und_u05 = p.clean_sheet_home if und_team == report.away else p.clean_sheet_away
        if und_u15 is not None and SWEET_MIN <= und_u15 <= SWEET_MAX:
            market_checks.append((f"{und_team.name} Menos de 1.5 Goles Totales", und_u15))
        elif und_u05 is not None and SWEET_MIN <= und_u05 <= SWEET_MAX:
            market_checks.append((f"{fav_team.name} Gana a Cero / {und_team.name} No Marca", und_u05))

        und_c_under_35 = expected.under_35_corners_away if und_team == report.away else expected.under_35_corners_home
        und_c_under_45 = expected.under_45_corners_away if und_team == report.away else expected.under_45_corners_home
        if und_c_under_35 is not None and SWEET_MIN <= und_c_under_35 <= SWEET_MAX:
            market_checks.append((f"{und_team.name} Menos de 3.5 Córners", und_c_under_35))
        elif und_c_under_45 is not None and SWEET_MIN <= und_c_under_45 <= SWEET_MAX:
            market_checks.append((f"{und_team.name} Menos de 4.5 Córners", und_c_under_45))

        und_cards_o25 = expected.over_25_cards_away if und_team == report.away else expected.over_25_cards_home
        und_cards_o15 = expected.over_15_cards_away if und_team == report.away else expected.over_15_cards_home
        if und_cards_o25 is not None and SWEET_MIN <= und_cards_o25 <= SWEET_MAX:
            market_checks.append((f"{und_team.name} Más de 2.5 Tarjetas Amarillas", und_cards_o25))
        elif und_cards_o15 is not None and SWEET_MIN <= und_cards_o15 <= SWEET_MAX:
            market_checks.append((f"{und_team.name} Más de 1.5 Tarjetas Amarillas", und_cards_o15))

        und_shots_u85 = expected.under_85_shots_away if und_team == report.away else expected.under_85_shots_home
        if und_shots_u85 is not None and SWEET_MIN <= und_shots_u85 <= SWEET_MAX:
            market_checks.append((f"{und_team.name} Menos de 8.5 Remates Totales", und_shots_u85))

        und_son_u25 = expected.under_25_shots_on_away if und_team == report.away else expected.under_25_shots_on_home
        if und_son_u25 is not None and SWEET_MIN <= und_son_u25 <= SWEET_MAX:
            market_checks.append((f"{und_team.name} Menos de 2.5 Tiros al Arco", und_son_u25))
    else:
        # Partidos equilibrados:
        for name, prob in [
            (f"Victoria {report.home.name}", p.home_win),
            (f"Victoria {report.away.name}", p.away_win),
            (f"Doble Oportunidad 1X ({report.home.name} o empate)", min(1.0, p.home_win + p.draw) if (p.home_win is not None and p.draw is not None) else None),
            (f"Doble Oportunidad X2 ({report.away.name} o empate)", min(1.0, p.away_win + p.draw) if (p.away_win is not None and p.draw is not None) else None),
            (f"Empate Apuesta No Válida (DNB {report.home.name})", p.dnb_home),
            (f"Empate Apuesta No Válida (DNB {report.away.name})", p.dnb_away),
        ]:
            if prob is not None and SWEET_MIN <= prob <= SWEET_MAX:
                market_checks.append((name, prob))

    # 2. Goles Totales (Escalado Dinámico al Sweet Spot):
    if p.over_35 is not None and SWEET_MIN <= p.over_35 <= SWEET_MAX:
        market_checks.append(("Más de 3.5 goles totales", p.over_35))
    elif p.over_25 is not None and SWEET_MIN <= p.over_25 <= SWEET_MAX:
        market_checks.append(("Más de 2.5 goles totales", p.over_25))
    elif p.over_15 is not None and SWEET_MIN <= p.over_15 <= SWEET_MAX:
        market_checks.append(("Más de 1.5 goles totales", p.over_15))

    if p.under_25 is not None and SWEET_MIN <= p.under_25 <= SWEET_MAX:
        market_checks.append(("Menos de 2.5 goles totales", p.under_25))
    elif p.under_35 is not None and SWEET_MIN <= p.under_35 <= SWEET_MAX:
        market_checks.append(("Menos de 3.5 goles totales", p.under_35))

    if p.btts is not None and SWEET_MIN <= p.btts <= SWEET_MAX:
        market_checks.append(("Ambos Equipos Marcan (BTTS)", p.btts))

    # Goles por Mitad:
    if p.second_half_over_05 is not None and SWEET_MIN <= p.second_half_over_05 <= SWEET_MAX:
        market_checks.append(("Más de 0.5 goles en 2do Tiempo", p.second_half_over_05))
    if not is_heavy_fav and p.first_half_over_05 is not None and SWEET_MIN <= p.first_half_over_05 <= SWEET_MAX:
        market_checks.append(("Más de 0.5 goles en 1er Tiempo", p.first_half_over_05))

    # 3. Córners Totales y por Equipo (Escalado Dinámico):
    # Córners por Equipo (Sweet Spot):
    if is_heavy_fav and fav_team:
        fav_c_list = [
            (f"{fav_team.name} Más de 6.5 Córners", expected.over_65_corners_home if fav_team == report.home else expected.over_65_corners_away),
            (f"{fav_team.name} Más de 5.5 Córners", expected.over_55_corners_home if fav_team == report.home else expected.over_55_corners_away),
            (f"{fav_team.name} Más de 4.5 Córners", expected.over_45_corners_home if fav_team == report.home else expected.over_45_corners_away),
        ]
        for c_name, c_prob in fav_c_list:
            if c_prob is not None and SWEET_MIN <= c_prob <= SWEET_MAX:
                market_checks.append((c_name, c_prob))
                break
    else:
        for c_name, c_prob in [
            (f"{report.home.name} Más de 6.5 Córners", expected.over_65_corners_home),
            (f"{report.home.name} Más de 5.5 Córners", expected.over_55_corners_home),
            (f"{report.home.name} Más de 4.5 Córners", expected.over_45_corners_home),
        ]:
            if c_prob is not None and SWEET_MIN <= c_prob <= SWEET_MAX:
                market_checks.append((c_name, c_prob))
                break

        for c_name, c_prob in [
            (f"{report.away.name} Más de 6.5 Córners", expected.over_65_corners_away),
            (f"{report.away.name} Más de 5.5 Córners", expected.over_55_corners_away),
            (f"{report.away.name} Más de 4.5 Córners", expected.over_45_corners_away),
        ]:
            if c_prob is not None and SWEET_MIN <= c_prob <= SWEET_MAX:
                market_checks.append((c_name, c_prob))
                break

    # Córners Totales:
    for c_name, c_prob in [
        ("Más de 11.5 Córners Totales", expected.over_115_corners),
        ("Más de 10.5 Córners Totales", expected.over_105_corners),
        ("Más de 9.5 Córners Totales", expected.over_95_corners),
        ("Más de 8.5 Córners Totales", expected.over_85_corners),
        ("Más de 7.5 Córners Totales", expected.over_75_corners),
    ]:
        if c_prob is not None and SWEET_MIN <= c_prob <= SWEET_MAX:
            market_checks.append((c_name, c_prob))
            break
    if expected.under_105_corners is not None and SWEET_MIN <= expected.under_105_corners <= SWEET_MAX:
        market_checks.append(("Menos de 10.5 Córners Totales", expected.under_105_corners))

    # 4. Tarjetas Dinámicas:
    if expected.over_45_cards is not None and SWEET_MIN <= expected.over_45_cards <= SWEET_MAX:
        market_checks.append(("Más de 4.5 Tarjetas Totales", expected.over_45_cards))
    elif expected.over_35_cards is not None and SWEET_MIN <= expected.over_35_cards <= SWEET_MAX:
        market_checks.append(("Más de 3.5 Tarjetas Totales", expected.over_35_cards))

    # 5. Fueras de Juego Dinámicos:
    for off_name, off_prob in [
        ("Más de 3.5 Fueras de Juego", expected.over_35_offsides),
        ("Más de 2.5 Fueras de Juego", expected.over_25_offsides),
        ("Menos de 3.5 Fueras de Juego", expected.under_35_offsides),
        ("Menos de 4.5 Fueras de Juego", expected.under_45_offsides),
        (f"{report.home.name} Más de 1.5 Fueras de Juego", expected.over_15_offsides_home),
        (f"{report.away.name} Más de 1.5 Fueras de Juego", expected.over_15_offsides_away if not is_heavy_fav else None),
        (f"{report.away.name} Menos de 1.5 Fueras de Juego", expected.under_15_offsides_away),
    ]:
        if off_prob is not None and SWEET_MIN <= off_prob <= SWEET_MAX:
            market_checks.append((off_name, off_prob))

    # 6. Remates Totales y por Equipo (Escalado Dinámico):
    for s_name, s_prob in [
        ("Más de 29.5 Remates Totales", expected.over_295_total_shots),
        ("Más de 27.5 Remates Totales", expected.over_275_total_shots),
        ("Más de 25.5 Remates Totales", expected.over_255_total_shots),
        ("Más de 23.5 Remates Totales", expected.over_235_total_shots),
        ("Más de 21.5 Remates Totales", expected.over_215_total_shots),
    ]:
        if s_prob is not None and SWEET_MIN <= s_prob <= SWEET_MAX:
            market_checks.append((s_name, s_prob))
            break

    # Remates por Equipo (Escalado Dinámico):
    if is_heavy_fav and fav_team:
        if fav_team == report.home:
            for s_name, s_prob in [
                (f"{report.home.name} Más de 17.5 Remates Totales", expected.over_175_shots_home),
                (f"{report.home.name} Más de 15.5 Remates Totales", expected.over_155_shots_home),
                (f"{report.home.name} Más de 13.5 Remates Totales", expected.over_135_shots_home),
                (f"{report.home.name} Más de 11.5 Remates Totales", expected.over_115_shots_home),
            ]:
                if s_prob is not None and SWEET_MIN <= s_prob <= SWEET_MAX:
                    market_checks.append((s_name, s_prob))
                    break
        else:
            for s_name, s_prob in [
                (f"{report.away.name} Más de 13.5 Remates Totales", expected.over_135_shots_away),
                (f"{report.away.name} Más de 11.5 Remates Totales", expected.over_115_shots_away),
            ]:
                if s_prob is not None and SWEET_MIN <= s_prob <= SWEET_MAX:
                    market_checks.append((s_name, s_prob))
                    break
    else:
        for s_name, s_prob in [
            (f"{report.home.name} Más de 17.5 Remates Totales", expected.over_175_shots_home),
            (f"{report.home.name} Más de 15.5 Remates Totales", expected.over_155_shots_home),
            (f"{report.home.name} Más de 13.5 Remates Totales", expected.over_135_shots_home),
            (f"{report.home.name} Más de 11.5 Remates Totales", expected.over_115_shots_home),
        ]:
            if s_prob is not None and SWEET_MIN <= s_prob <= SWEET_MAX:
                market_checks.append((s_name, s_prob))
                break

        for s_name, s_prob in [
            (f"{report.away.name} Más de 13.5 Remates Totales", expected.over_135_shots_away),
            (f"{report.away.name} Más de 11.5 Remates Totales", expected.over_115_shots_away),
        ]:
            if s_prob is not None and SWEET_MIN <= s_prob <= SWEET_MAX:
                market_checks.append((s_name, s_prob))
                break

    # 7. Tiros al Arco Totales y por Equipo:
    for sot_name, sot_prob in [
        ("Más de 10.5 Tiros al Arco Totales", expected.over_105_shots_on),
        ("Más de 9.5 Tiros al Arco Totales", expected.over_95_shots_on),
        ("Más de 8.5 Tiros al Arco Totales", expected.over_85_shots_on),
        ("Más de 7.5 Tiros al Arco Totales", expected.over_75_shots_on),
    ]:
        if sot_prob is not None and SWEET_MIN <= sot_prob <= SWEET_MAX:
            market_checks.append((sot_name, sot_prob))
            break

    # Tiros al Arco por Equipo:
    if is_heavy_fav and fav_team:
        if fav_team == report.home:
            for sot_name, sot_prob in [
                (f"{report.home.name} Más de 7.5 Tiros al Arco", expected.over_75_shots_on_home),
                (f"{report.home.name} Más de 6.5 Tiros al Arco", expected.over_65_shots_on_home),
                (f"{report.home.name} Más de 5.5 Tiros al Arco", expected.over_55_shots_on_home),
                (f"{report.home.name} Más de 4.5 Tiros al Arco", expected.over_45_shots_on_home),
            ]:
                if sot_prob is not None and SWEET_MIN <= sot_prob <= SWEET_MAX:
                    market_checks.append((sot_name, sot_prob))
                    break
        else:
            if expected.over_35_shots_on_away is not None and SWEET_MIN <= expected.over_35_shots_on_away <= SWEET_MAX:
                market_checks.append((f"{report.away.name} Más de 3.5 Tiros al Arco", expected.over_35_shots_on_away))
    else:
        for sot_name, sot_prob in [
            (f"{report.home.name} Más de 7.5 Tiros al Arco", expected.over_75_shots_on_home),
            (f"{report.home.name} Más de 6.5 Tiros al Arco", expected.over_65_shots_on_home),
            (f"{report.home.name} Más de 5.5 Tiros al Arco", expected.over_55_shots_on_home),
            (f"{report.home.name} Más de 4.5 Tiros al Arco", expected.over_45_shots_on_home),
        ]:
            if sot_prob is not None and SWEET_MIN <= sot_prob <= SWEET_MAX:
                market_checks.append((sot_name, sot_prob))
                break

        if expected.over_35_shots_on_away is not None and SWEET_MIN <= expected.over_35_shots_on_away <= SWEET_MAX:
            market_checks.append((f"{report.away.name} Más de 3.5 Tiros al Arco", expected.over_35_shots_on_away))

    # Si por alguna rareza de datos no hay candidatos en [0.60, 0.80], recurrir a líneas con prob >= 0.60
    if not market_checks:
        if p.over_25 >= 0.60:
            market_checks.append(("Más de 2.5 goles totales", p.over_25))
        elif p.under_25 >= 0.60:
            market_checks.append(("Menos de 2.5 goles totales", p.under_25))

    banker_candidates: list[tuple[str, float]] = []
    value_candidates: list[tuple[str, float]] = []

    for name, prob in market_checks:
        if prob >= 0.65:
            banker_candidates.append((name, prob))
        else:
            value_candidates.append((name, prob))

    banker_candidates.sort(key=lambda x: x[1], reverse=True)
    value_candidates.sort(key=lambda x: x[1], reverse=True)

    pick_principal = banker_candidates[0] if banker_candidates else (value_candidates[0] if value_candidates else None)

    pick_secundario = None
    if pick_principal:
        p_cat = _market_category(pick_principal[0])
        for cand in banker_candidates + value_candidates:
            cand_cat = _market_category(cand[0])
            if cand[0] != pick_principal[0] and cand_cat != p_cat:
                pick_secundario = cand
                break
        if not pick_secundario:
            for cand in banker_candidates + value_candidates:
                if cand[0] != pick_principal[0]:
                    pick_secundario = cand
                    break

    best_score, best_score_prob = top_scores(p)[0]

    smart_players: list[dict[str, Any]] = []
    for team_id in (report.home.id, report.away.id):
        team_name = report.home.name if team_id == report.home.id else report.away.name
        for pl in expected.player_shots.get(team_id, []):
            sp = _select_smart_player_prop(pl, team_name)
            if sp.get("probability", 0.0) >= 0.60:
                smart_players.append(sp)

    sweet_players = [p for p in smart_players if SWEET_MIN <= p["probability"] <= SWEET_MAX]
    if is_heavy_fav and fav_team:
        sweet_players.sort(key=lambda x: (x["team"] != fav_team.name, abs(x["probability"] - 0.70)))
    else:
        sweet_players.sort(key=lambda x: abs(x["probability"] - 0.70))
    other_players = [p for p in smart_players if p not in sweet_players]
    if is_heavy_fav and fav_team:
        other_players.sort(key=lambda x: (x["team"] != fav_team.name, abs(x["probability"] - 0.70)))
    else:
        other_players.sort(key=lambda x: x["probability"], reverse=True)
    all_sorted_players = sweet_players + other_players
    top_player = all_sorted_players[0] if all_sorted_players else None

    ticket_lines = [
        "============================================================",
        "🎯 TICKET DIRECTO Y DECISIVO (Picks de Alta Confianza):",
        "============================================================",
        "",
    ]
    if pick_principal:
        ticket_lines.append(f"🟢 1. PICK PRINCIPAL: {pick_principal[0]} — {_pct(pick_principal[1])}")
    if pick_secundario:
        ticket_lines.append(f"🔵 2. PICK SECUNDARIO: {pick_secundario[0]} — {_pct(pick_secundario[1])}")
    ticket_lines.append(f"🎯 3. MARCADOR EXACTO OFICIAL: {best_score} ({_pct(best_score_prob)})")
    if top_player:
        ticket_lines.append(
            f"👟 4. JUGADOR DEL PARTIDO: {top_player['name']} ({top_player['team']}) {top_player['prop_desc']} — {_pct(top_player['probability'])} [⚠️ Sujeto a Titularidad Oficial]"
        )

    builder_items: list[str] = []
    if pick_principal:
        builder_items.append(pick_principal[0])
    if top_player and top_player["probability"] >= 0.60 and top_player["name"] not in str(builder_items):
        builder_items.append(f"{top_player['short_desc']} [⚠️ Titular]")

    if is_heavy_fav and und_team:
        und_c_under_35 = expected.under_35_corners_away if und_team == report.away else expected.under_35_corners_home
        if und_c_under_35 is not None and und_c_under_35 >= 0.65 and "Córners" not in str(builder_items) and len(builder_items) < 3:
            builder_items.append(f"{und_team.name} Menos de 3.5 Córners")
        elif expected.over_45_corners_home is not None and expected.over_45_corners_home >= 0.65 and "Córners" not in str(builder_items) and len(builder_items) < 3:
            builder_items.append(f"{report.home.name} Más de 4.5 Córners")
    else:
        if expected.over_75_corners is not None and expected.over_75_corners >= 0.65 and "Córners" not in str(builder_items) and len(builder_items) < 3:
            builder_items.append("Más de 7.5 Córners Totales")
        elif expected.over_45_corners_home is not None and expected.over_45_corners_home >= 0.65 and "Córners" not in str(builder_items) and len(builder_items) < 3:
            builder_items.append(f"{report.home.name} Más de 4.5 Córners")

    # Remates o Tiros al Arco en Bet Builder
    if len(builder_items) < 3:
        if expected.over_155_shots_home is not None and expected.over_155_shots_home >= 0.60 and "Remates" not in str(builder_items):
            builder_items.append(f"{report.home.name} Más de 15.5 Remates")
        elif expected.over_135_shots_home is not None and expected.over_135_shots_home >= 0.65 and "Remates" not in str(builder_items):
            builder_items.append(f"{report.home.name} Más de 13.5 Remates")
        elif expected.over_55_shots_on_home is not None and expected.over_55_shots_on_home >= 0.65 and "Tiros" not in str(builder_items):
            builder_items.append(f"{report.home.name} Más de 5.5 Tiros al Arco")
        elif expected.over_45_shots_on_home is not None and expected.over_45_shots_on_home >= 0.65 and "Tiros" not in str(builder_items):
            builder_items.append(f"{report.home.name} Más de 4.5 Tiros al Arco")

    if expected.under_35_offsides is not None and expected.under_35_offsides >= 0.65 and "Fueras de Juego" not in str(builder_items) and len(builder_items) < 3:
        builder_items.append("Menos de 3.5 Fueras de Juego")
    elif p.second_half_over_05 >= 0.75 and "goles" not in str(builder_items).lower() and len(builder_items) < 3:
        builder_items.append("Más de 0.5 goles 2T")
    elif p.over_15 >= 0.75 and "goles" not in str(builder_items).lower() and len(builder_items) < 3:
        builder_items.append("Más de 1.5 goles")

    if len(builder_items) >= 2:
        ticket_lines.append(f"🔥 5. BET BUILDER (Estrategia Combinada Correlacionada): {' + '.join(builder_items)}")

    ticket_lines.append("")
    ticket_lines.append("============================================================")
    ticket_lines.append("")
    return ticket_lines


def _build_unexploited_section(report: AnalysisReport) -> list[str]:
    p = report.probabilities
    expected = report.expected
    alt_impact = detect_altitude_impact(report.home.id, report.home.name, report.away.id, report.away.name)
    disallow_away_ha = bool(alt_impact and alt_impact.get("disallow_away_handicap"))

    is_heavy_fav = max(p.home_win, p.away_win) >= 0.70
    fav_team = report.home if p.home_win >= 0.70 else (report.away if p.away_win >= 0.70 else None)
    und_team = report.away if p.home_win >= 0.70 else (report.home if p.away_win >= 0.70 else None)

    lines = [
        "============================================================",
        "💎 JOYAS Y MERCADOS NO EXPLOTADOS (Alta Eficiencia & Baja Varianza):",
        "============================================================",
        "",
    ]

    # 1. Remates / Tiros al Arco de Jugador Clave (Cláusula de Titularidad)
    top_smart_players: list[dict[str, Any]] = []
    for team_id in (report.home.id, report.away.id):
        team_name = report.home.name if team_id == report.home.id else report.away.name
        for pl in expected.player_shots.get(team_id, []):
            sp = _select_smart_player_prop(pl, team_name)
            if sp.get("probability", 0.0) >= 0.60:
                top_smart_players.append(sp)

    sweet_p = [p for p in top_smart_players if 0.60 <= p["probability"] <= 0.84]
    if is_heavy_fav and fav_team:
        sweet_p.sort(key=lambda x: (x["team"] != fav_team.name, abs(x["probability"] - 0.70)))
    else:
        sweet_p.sort(key=lambda x: x["probability"], reverse=True)
    other_p = [p for p in top_smart_players if p not in sweet_p]
    if is_heavy_fav and fav_team:
        other_p.sort(key=lambda x: (x["team"] != fav_team.name, abs(x["probability"] - 0.70)))
    else:
        other_p.sort(key=lambda x: x["probability"], reverse=True)
    sorted_players = sweet_p + other_p

    if sorted_players:
        best_p = sorted_players[0]
        escalated_note = " — Escalado a cuota de valor por alto volumen" if best_p.get("is_escalated") else ""
        lines.append(
            f"1. 👟 Prop de Jugador de Valor: {best_p['name']} ({best_p['team']}) {best_p['prop_desc']} ({_pct(best_p['probability'])}){escalated_note} [⚠️ Sujeto a Titularidad Oficial]"
        )
        if len(sorted_players) > 1 and sorted_players[1]["probability"] >= 0.60:
            alt_p = sorted_players[1]
            lines.append(
                f"   • Alternativa: {alt_p['name']} ({alt_p['team']}) {alt_p['prop_desc']} ({_pct(alt_p['probability'])}) [⚠️ Sujeto a Titularidad Oficial]"
            )
        lines.append("   ℹ️ Cláusula de Titularidad: Apuesta válida únicamente si el futbolista inicia como TITULAR en el XI inicial oficial. Si es suplente o rota, no apostar.")
    else:
        lines.append("1. 👟 Remates de Jugador: Sin jugadores con volumen suficiente (≥60%).")

    # Sub-bullet de Remates y Tiros a Puerta por Equipo (Baja Varianza)
    team_shot_highlights: list[str] = []
    shot_fav = fav_team if (is_heavy_fav and fav_team) else report.home
    if shot_fav == report.home:
        if expected.over_175_shots_home is not None and expected.over_175_shots_home >= 0.60:
            team_shot_highlights.append(f"{report.home.name} >17.5 Remates ({_pct(expected.over_175_shots_home)})")
        elif expected.over_155_shots_home is not None and expected.over_155_shots_home >= 0.60:
            team_shot_highlights.append(f"{report.home.name} >15.5 Remates ({_pct(expected.over_155_shots_home)})")
        elif expected.over_135_shots_home is not None and expected.over_135_shots_home >= 0.60:
            team_shot_highlights.append(f"{report.home.name} >13.5 Remates ({_pct(expected.over_135_shots_home)})")
        elif expected.over_115_shots_home is not None and expected.over_115_shots_home >= 0.60:
            team_shot_highlights.append(f"{report.home.name} >11.5 Remates ({_pct(expected.over_115_shots_home)})")

        if expected.over_65_shots_on_home is not None and expected.over_65_shots_on_home >= 0.60:
            team_shot_highlights.append(f"{report.home.name} >6.5 Tiros al Arco ({_pct(expected.over_65_shots_on_home)})")
        elif expected.over_55_shots_on_home is not None and expected.over_55_shots_on_home >= 0.60:
            team_shot_highlights.append(f"{report.home.name} >5.5 Tiros al Arco ({_pct(expected.over_55_shots_on_home)})")
        elif expected.over_45_shots_on_home is not None and expected.over_45_shots_on_home >= 0.60:
            team_shot_highlights.append(f"{report.home.name} >4.5 Tiros al Arco ({_pct(expected.over_45_shots_on_home)})")
    else:
        if expected.over_135_shots_away is not None and expected.over_135_shots_away >= 0.60:
            team_shot_highlights.append(f"{report.away.name} >13.5 Remates ({_pct(expected.over_135_shots_away)})")
        elif expected.over_115_shots_away is not None and expected.over_115_shots_away >= 0.60:
            team_shot_highlights.append(f"{report.away.name} >11.5 Remates ({_pct(expected.over_115_shots_away)})")

        if expected.over_35_shots_on_away is not None and expected.over_35_shots_on_away >= 0.60:
            team_shot_highlights.append(f"{report.away.name} >3.5 Tiros al Arco ({_pct(expected.over_35_shots_on_away)})")

    if is_heavy_fav and und_team:
        und_s_u85 = expected.under_85_shots_away if und_team == report.away else expected.under_85_shots_home
        if und_s_u85 is not None and und_s_u85 >= 0.65:
            team_shot_highlights.append(f"{und_team.name} <8.5 Remates ({_pct(und_s_u85)})")

    if expected.over_05_woodwork is not None and expected.over_05_woodwork >= 0.60:
        team_shot_highlights.append(f"Tiro al Palo ({_pct(expected.over_05_woodwork)})")

    if team_shot_highlights:
        lines.append(f"   • Remates de Equipo / Tiros a Puerta: {' | '.join(team_shot_highlights)}")

    # 2. Fueras de Juego (Offsides) - Selección Inteligente de Over / Under
    tot_offsides = _sum_optional(expected.offsides_home, expected.offsides_away)
    if expected.over_25_offsides is not None and expected.over_25_offsides >= 0.60:
        lines.append(f"2. 🚩 Fueras de Juego: Más de 2.5 Offsides Totales ({_pct(expected.over_25_offsides)}) [Esperados: {_number_or_na(tot_offsides)}]")
    elif expected.under_35_offsides is not None and expected.under_35_offsides >= 0.60:
        lines.append(f"2. 🚩 Fueras de Juego (Under Inteligente): Menos de 3.5 Offsides Totales ({_pct(expected.under_35_offsides)}) [Esperados: {_number_or_na(tot_offsides)}] — Táctica de repliegue / bloque medio sin caer en trampa de fuera de juego.")
    elif expected.under_45_offsides is not None and expected.under_45_offsides >= 0.70:
        lines.append(f"2. 🚩 Fueras de Juego (Under Inteligente): Menos de 4.5 Offsides Totales ({_pct(expected.under_45_offsides)}) [Esperados: {_number_or_na(tot_offsides)}] — Ritmo pausado y posesión sin rupturas al límite.")
    elif expected.over_15_offsides_home is not None and expected.over_15_offsides_home >= 0.60:
        lines.append(f"2. 🚩 Fueras de Juego: {report.home.name} Más de 1.5 Offsides ({_pct(expected.over_15_offsides_home)}) [Esperados: {_number_or_na(expected.offsides_home)}]")
    elif expected.over_15_offsides_away is not None and expected.over_15_offsides_away >= 0.60:
        lines.append(f"2. 🚩 Fueras de Juego: {report.away.name} Más de 1.5 Offsides ({_pct(expected.over_15_offsides_away)}) [Esperados: {_number_or_na(expected.offsides_away)}]")
    else:
        lines.append(f"2. 🚩 Fueras de Juego: Proyección moderada ({_number_or_na(tot_offsides)} esperados).")

    # 3. Córners Individuales de Equipo y Ángulo Underdog
    best_corner_team = None
    if is_heavy_fav and fav_team:
        if fav_team == report.home:
            if expected.over_65_corners_home is not None and expected.over_65_corners_home >= 0.60:
                best_corner_team = (report.home.name, "6.5", expected.over_65_corners_home, expected.corners_home)
            elif expected.over_55_corners_home is not None and expected.over_55_corners_home >= 0.60:
                best_corner_team = (report.home.name, "5.5", expected.over_55_corners_home, expected.corners_home)
            elif expected.over_45_corners_home is not None and expected.over_45_corners_home >= 0.60:
                best_corner_team = (report.home.name, "4.5", expected.over_45_corners_home, expected.corners_home)
        else:
            if expected.over_65_corners_away is not None and expected.over_65_corners_away >= 0.60:
                best_corner_team = (report.away.name, "6.5", expected.over_65_corners_away, expected.corners_away)
            elif expected.over_55_corners_away is not None and expected.over_55_corners_away >= 0.60:
                best_corner_team = (report.away.name, "5.5", expected.over_55_corners_away, expected.corners_away)
            elif expected.over_45_corners_away is not None and expected.over_45_corners_away >= 0.60:
                best_corner_team = (report.away.name, "4.5", expected.over_45_corners_away, expected.corners_away)
    else:
        if expected.over_55_corners_home is not None and expected.over_55_corners_home >= 0.60:
            best_corner_team = (report.home.name, "5.5", expected.over_55_corners_home, expected.corners_home)
        elif expected.over_55_corners_away is not None and expected.over_55_corners_away >= 0.60:
            best_corner_team = (report.away.name, "5.5", expected.over_55_corners_away, expected.corners_away)
        elif expected.over_45_corners_home is not None and expected.over_45_corners_home >= 0.60:
            best_corner_team = (report.home.name, "4.5", expected.over_45_corners_home, expected.corners_home)
        elif expected.over_45_corners_away is not None and expected.over_45_corners_away >= 0.60:
            best_corner_team = (report.away.name, "4.5", expected.over_45_corners_away, expected.corners_away)

    if is_heavy_fav and und_team:
        und_c_under_35 = expected.under_35_corners_away if und_team == report.away else expected.under_35_corners_home
        und_c_under_45 = expected.under_45_corners_away if und_team == report.away else expected.under_45_corners_home
        und_c_exp = expected.corners_away if und_team == report.away else expected.corners_home

        und_c_prop = None
        if und_c_under_35 is not None and und_c_under_35 >= 0.60:
            und_c_prop = ("3.5", und_c_under_35)
        elif und_c_under_45 is not None and und_c_under_45 >= 0.65:
            und_c_prop = ("4.5", und_c_under_45)

        if best_corner_team and und_c_prop:
            lines.append(
                f"3. 📐 Córners de Equipo: {best_corner_team[0]} Más de {best_corner_team[1]} Córners ({_pct(best_corner_team[2])}) [Promedio: {best_corner_team[3]:.2f}] "
                f"| Alternativa Underdog: {und_team.name} Menos de {und_c_prop[0]} Córners ({_pct(und_c_prop[1])}) [Promedio: {_number_or_na(und_c_exp)}]"
            )
        elif best_corner_team:
            lines.append(f"3. 📐 Córners de Equipo: {best_corner_team[0]} Más de {best_corner_team[1]} Córners ({_pct(best_corner_team[2])}) [Promedio esp: {best_corner_team[3]:.2f}]")
        elif und_c_prop:
            lines.append(f"3. 📐 Córners de Equipo: {und_team.name} Menos de {und_c_prop[0]} Córners ({_pct(und_c_prop[1])}) [Promedio esp: {_number_or_na(und_c_exp)}]")
        elif expected.over_75_corners is not None and expected.over_75_corners >= 0.60:
            lines.append(f"3. 📐 Córners Totales: Más de 7.5 Córners ({_pct(expected.over_75_corners)})")
        else:
            lines.append("3. 📐 Córners de Equipo: Líneas ajustadas sin ventaja clara en volumen individual.")
    else:
        if best_corner_team and best_corner_team[3] is not None:
            lines.append(f"3. 📐 Córners de Equipo: {best_corner_team[0]} Más de {best_corner_team[1]} Córners ({_pct(best_corner_team[2])}) [Promedio esp: {best_corner_team[3]:.2f}]")
        elif expected.over_75_corners is not None and expected.over_75_corners >= 0.60:
            lines.append(f"3. 📐 Córners Totales: Más de 7.5 Córners ({_pct(expected.over_75_corners)})")
        else:
            lines.append("3. 📐 Córners de Equipo: Líneas ajustadas sin ventaja clara en volumen individual.")

    # 4. Hándicap Protector vs Hándicap de Valor / Ángulo Underdog / Veto Altitud
    if disallow_away_ha and alt_impact:
        lines.append("4. 🛡️/🏔️ Hándicap y Factor Altitud Extrema:")
        lines.append(f"   • VETO ESTRATÉGICO: Descartado {report.away.name} (+1.5 HA) debido al choque fisiológico a {alt_impact['home_altitude']:,} m.s.n.m.")
        if p.ah_home_minus_15 is not None and p.ah_home_minus_15 >= 0.60:
            lines.append(f"   • Hándicap Valor Local: {report.home.name} (-1.5 HA) — {_pct(p.ah_home_minus_15)} (Riesgo justificado por asfixia del visitante).")
        else:
            lines.append(f"   • Alternativa Segura: Priorizar mercados de asedio ({report.home.name} Más Córners / Remates) antes que cubrir al visitante.")
    elif is_heavy_fav and fav_team and und_team:
        fav_ah_m15 = p.ah_home_minus_15 if fav_team == report.home else p.ah_away_minus_15
        und_u15 = p.away_under_15 if und_team == report.away else p.home_under_15
        und_cards_o15 = expected.over_15_cards_away if und_team == report.away else expected.over_15_cards_home

        lines.append("4. 🛡️/⚔️ Hándicap de Valor y Props Inteligentes de Underdog:")
        if fav_ah_m15 is not None and fav_ah_m15 >= 0.60:
            lines.append(f"   • Hándicap Valor Favorito: {fav_team.name} (-1.5 HA) — {_pct(fav_ah_m15)} (Evita cuotas ínfimas ~1.02 de victoria directa o +1.5).")
        if und_u15 is not None and und_u15 >= 0.65:
            lines.append(f"   • Prop Inteligente Underdog: {und_team.name} Menos de 1.5 Goles Totales ({_pct(und_u15)}) — Bloqueo ofensivo y contención esperada.")
        elif und_cards_o15 is not None and und_cards_o15 >= 0.65:
            lines.append(f"   • Prop Inteligente Underdog: {und_team.name} Más de 1.5 Tarjetas Amarillas ({_pct(und_cards_o15)}) — Faltas tácticas obligadas ante el asedio.")
    else:
        best_ah = None
        if p.ah_away_plus_15 is not None and p.ah_away_plus_15 >= 0.70:
            best_ah = (report.away.name, "+1.5", p.ah_away_plus_15)
        elif p.ah_home_plus_15 is not None and p.ah_home_plus_15 >= 0.70:
            best_ah = (report.home.name, "+1.5", p.ah_home_plus_15)
        elif p.ah_away_plus_15 is not None and p.ah_away_plus_15 >= 0.60:
            best_ah = (report.away.name, "+1.5", p.ah_away_plus_15)
        elif p.ah_home_plus_15 is not None and p.ah_home_plus_15 >= 0.60:
            best_ah = (report.home.name, "+1.5", p.ah_home_plus_15)

        if best_ah:
            lines.append(f"4. 🛡️ Hándicap Protector: {best_ah[0]} ({best_ah[1]} HA) — {_pct(best_ah[2])} (Cubre victoria, empate y derrota por 1 gol)")
        else:
            lines.append("4. 🛡️ Hándicap Protector: Partido sin sesgo asimétrico claro para +1.5.")

    # 5. Dinámica de 2do Tiempo (2T)
    p_2t = _pct(p.second_half_over_05) if p.second_half_over_05 is not None else "N/D"
    p_1t = _pct(p.first_half_over_05) if p.first_half_over_05 is not None else "N/D"
    lines.append(
        f"5. ⏱️ Dinámica de 2T: Más de 0.5 goles en 2T ({p_2t}) vs 1T ({p_1t}) "
        f"— El 2T presenta mayor seguridad estadística ante repliegues iniciales."
    )

    lines.append("")
    lines.append("============================================================")
    lines.append("")
    return lines


def _player_lines(report: AnalysisReport) -> list[str]:
    lines: list[str] = []
    found = False
    for team in (report.home, report.away):
        for item in report.expected.player_shots.get(team.id, []):
            p2 = item.get("probability_two_plus", item.get("probability_one_plus", 0.0))
            p3 = item.get("probability_three_plus", 0.0)
            p4 = item.get("probability_four_plus", 0.0)
            sot2 = item.get("probability_sot_two_plus", 0.0)
            sot1 = item.get("probability_sot_one_plus", 0.0)

            parts: list[str] = []
            if p2 >= 0.60:
                parts.append(f"2+ Remates Totales {_pct(p2)}")
            if p3 >= 0.60:
                parts.append(f"3+ Remates Totales {_pct(p3)}")
            if p4 >= 0.60:
                parts.append(f"4+ Remates Totales {_pct(p4)}")
            if sot2 >= 0.60:
                parts.append(f"🎯 2+ al Arco {_pct(sot2)}")
            elif sot1 >= 0.60:
                parts.append(f"🎯 1+ al Arco {_pct(sot1)}")

            if parts:
                found = True
                desc = " | ".join(parts)
                lines.append(
                    f"- {item['name']} ({team.name}): {desc} "
                    f"[{item['appearances']} apariciones] [⚠️ Sujeto a Titularidad Oficial]"
                )
    return lines if found else ["- No hay jugadores que superen el umbral de remates totales (≥60%) para este encuentro."]


def _goalscorer_lines(report: AnalysisReport) -> list[str]:
    lines: list[str] = []
    found = False
    for team in (report.home, report.away):
        for item in report.expected.anytime_goalscorers.get(team.id, []):
            prob = item.get("probability_goal", 0.0)
            if prob >= 0.60:
                found = True
                lines.append(
                    f"- {item['name']} ({team.name}): Anota en cualquier momento {_pct(prob)} "
                    f"[{item['appearances']} apariciones]"
                )
    return lines if found else ["- No hay jugadores con alta probabilidad de gol (≥60%) para este encuentro."]


def _deterministic_narrative(report: AnalysisReport) -> str:
    p = report.probabilities
    outcomes = [
        (report.home.name, p.home_win),
        ("el empate", p.draw),
        (report.away.name, p.away_win),
    ]
    label, probability = max(outcomes, key=lambda item: item[1])
    return (
        f"El escenario con mayor probabilidad es {label} ({_pct(probability)}), pero el resultado "
        f"conserva incertidumbre. El modelo estima {p.expected_home_goals + p.expected_away_goals:.2f} "
        "goles totales. Las ausencias, rotaciones y cobertura incompleta de estadísticas pueden "
        "alterar la lectura antes del inicio."
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _sum_optional(first: float | None, second: float | None) -> float | None:
    return first + second if first is not None and second is not None else None


def _number_or_na(value: float | None) -> str:
    return "No disponible" if value is None else f"{value:.2f}"


def _pct_or_na(value: float | None) -> str:
    return "No disponible" if value is None else f"{value * 100:.1f}%"


def format_adaptive_report(report: AnalysisReport) -> str:
    """Genera el reporte oficial de pronósticos deportivos (DEPORT AI) con estructura adaptativa estilo Betano."""
    lines: list[str] = []

    # 1. Título
    lines.append(f"# ⚽ {report.home.name} vs {report.away.name}")

    # 2. Confianza
    cal_info = getattr(report, "dynamic_calibration_info", None)
    cal_str = ""
    if cal_info and getattr(cal_info, "active", False) and getattr(cal_info, "sample_size", 0) >= MIN_CALIBRATION_SAMPLE:
        cal_str = f", ⚡ Calibración Dinámica: {cal_info.sample_size} apuestas auditadas, {cal_info.overall_hit_rate * 100:.1f}% acierto"

    if report.confidence:
        badge = "🟢" if report.confidence.level == "ALTA" else "🟡" if report.confidence.level == "MEDIA" else "🔴"
        lineup_str = "alineación titular confirmada oficialmente" if report.confidence.lineups_confirmed else "alineaciones no confirmadas oficialmente"
        lines.append(f"**Confianza:** {badge} {report.confidence.level.capitalize()} ({report.confidence.sample_size} partidos analizados, {report.confidence.detailed_matches} con estadísticas completas, {lineup_str}{cal_str})")
    else:
        lines.append(f"**Confianza:** 🟡 Media (análisis estadístico preliminar{cal_str})")
    lines.append("")

    # 2.5 Pick Recomendado Oficial
    top_pick = getattr(report, "top_pick", None)
    if top_pick and top_pick.get("probability", 0.0) >= 0.60:
        sel = top_pick.get("selection", "")
        prob = top_pick.get("probability", 0.0)
        expl = top_pick.get("explanation", "").strip()
        if not expl.startswith("*"):
            if not expl.lower().startswith("porque"):
                expl = f"Porque {expl}"
            expl = f"*{expl}*"
        lines.append("### ⭐ PICK RECOMENDADO POR EL MODELO (AI Top Pick)")
        lines.append(f"• **{sel} — {prob * 100:.1f}%**{_value_suffix(top_pick)}  ")
        lines.append(f"  {expl}  ")
        if top_pick.get("requires_starter_confirmation"):
            lines.append("  *(Requiere confirmar titularidad oficial)*.  ")
        lines.append("")

    # 3. Categorías temáticas oficiales
    categories_spec = [
        ("Resultado", "#### 🏆 Resultado"),
        ("Goles", "#### 🥅 Goles y Anotaciones"),
        ("Mitades", "#### ⏱️ Mercados por Mitad"),
        ("Córners", "#### 🚩 Córners"),
        ("Tarjetas", "#### 🟨 Tarjetas"),
        ("Faltas", "#### 🛑 Faltas y Disciplina"),
        ("Remates y Tiros a Puerta", "#### 🎯 Remates y Tiros a Puerta"),
        ("Fueras de juego", "#### 🚩 Fueras de Juego (Offsides)"),
        ("Especiales", "#### 💥 Especiales del Partido"),
        ("Jugadores", "#### 👟 Jugadores"),
    ]

    # Agrupar mercados de report.statistical_markets
    markets_by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in report.statistical_markets:
        cat = m.get("category", "")
        if cat in ("Remates", "Tiros a puerta"):
            markets_by_cat["Remates y Tiros a Puerta"].append(m)
        else:
            markets_by_cat[cat].append(m)

    for cat_name, header in categories_spec:
        items = markets_by_cat.get(cat_name, [])
        if not items:
            continue
        items = sorted(items, key=lambda x: -x.get("probability", 0.0))[:4]
        lines.append(header)
        for item in items:
            sel = item.get("selection", "")
            prob = item.get("probability", 0.0)
            expl = item.get("explanation", "").strip()
            if not expl.startswith("*"):
                if not expl.lower().startswith("porque"):
                    expl = f"Porque {expl}"
                expl = f"*{expl}*"
            lines.append(f"• **{sel} — {prob * 100:.1f}%**{_value_suffix(item)}  ")
            lines.append(f"  {expl}  ")
            if item.get("requires_starter_confirmation"):
                lines.append("  *(Requiere confirmar titularidad oficial)*.  ")
        lines.append("")

    # 4. Proyecciones numéricas
    p = report.probabilities
    exp = report.expected
    total_goals = (p.expected_home_goals + p.expected_away_goals) if (p.expected_home_goals is not None and p.expected_away_goals is not None) else None
    total_corners = _sum_optional(exp.corners_home, exp.corners_away)
    total_cards = _sum_optional(exp.cards_home, exp.cards_away)
    total_shots = _sum_optional(exp.total_shots_home, exp.total_shots_away)

    best_score_str = "1 - 1"
    best_score_prob = 0.10
    if p.score_matrix:
        scores = [
            (f"{h} - {a}", p.score_matrix[h][a])
            for h in range(len(p.score_matrix))
            for a in range(len(p.score_matrix[h]))
        ]
        if scores:
            best_score_str, best_score_prob = max(scores, key=lambda x: x[1])

    lines.append("#### 📊 Proyecciones numéricas")
    if total_goals is not None:
        lines.append(f"• **Goles estimados:** {total_goals:.2f} ({report.home.name}: {p.expected_home_goals:.2f} | {report.away.name}: {p.expected_away_goals:.2f})  ")
    if total_corners is not None:
        lines.append(f"• **Córners estimados:** {total_corners:.2f}  ")
    if total_cards is not None:
        lines.append(f"• **Tarjetas estimadas:** {total_cards:.2f}  ")
    if total_shots is not None:
        lines.append(f"• **Remates estimados:** {total_shots:.1f}  ")
    lines.append(f"• **Marcador más probable:** {best_score_str} ({best_score_prob * 100:.1f}%)")

    return "\n".join(lines)



def _value_suffix(item: dict[str, Any]) -> str:
    """Cuota y valor esperado cuando la selección tiene precio de mercado."""
    price, edge = item.get("odds"), item.get("edge")
    if not price or edge is None:
        return ""
    return f" · cuota {float(price):.2f} · EV {float(edge) * 100:+.1f}%"
