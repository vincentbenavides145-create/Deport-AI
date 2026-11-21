from __future__ import annotations

from collections import defaultdict
from typing import Any

from .dynamic_calibration import MIN_CALIBRATION_SAMPLE
from .domain import AnalysisReport
from .statistical_markets import MINIMUM_PROBABILITY
from .stats_engine import REFEREE_MIN_MATCHES


def _referee_suffix(report: AnalysisReport) -> str:
    """Árbitro cuyo promedio entra en la proyección de tarjetas (si dirigió lo suficiente)."""
    referee = getattr(report, "referee", None)
    if not referee or referee.get("matches", 0) < REFEREE_MIN_MATCHES:
        return ""
    name = referee.get("name") or "asignado"
    return f" (árbitro {name}: {referee['cards_per_match']:.2f} por partido en {referee['matches']})"


def _sum_optional(first: float | None, second: float | None) -> float | None:
    return first + second if first is not None and second is not None else None


def format_adaptive_report(report: AnalysisReport, full: bool = False) -> str:
    """Genera el reporte oficial de pronósticos deportivos (DEPORT AI).

    Por defecto es el formato corto: Pick Recomendado + las selecciones más seguras +
    proyecciones. Con `full=True` muestra todas las categorías (estructura adaptativa).
    """
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
    if top_pick and top_pick.get("probability", 0.0) >= MINIMUM_PROBABILITY:
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
        ("Remates y Tiros al Arco", "#### 🎯 Remates y Tiros al Arco"),
        ("Fueras de juego", "#### 🚩 Fueras de Juego (Offsides)"),
        ("Especiales", "#### 💥 Especiales del Partido"),
        ("Jugadores", "#### 👟 Jugadores"),
    ]

    # Agrupar mercados de report.statistical_markets
    markets_by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in report.statistical_markets:
        cat = m.get("category", "")
        if cat in ("Remates", "Tiros al arco"):
            markets_by_cat["Remates y Tiros al Arco"].append(m)
        else:
            markets_by_cat[cat].append(m)

    # El Pick Recomendado ya se muestra arriba: no se repite dentro de su categoría.
    top_selection = top_pick.get("selection") if top_pick and top_pick.get("probability", 0.0) >= MINIMUM_PROBABILITY else None

    if not full:
        featured = list(getattr(report, "featured_markets", None) or [])
        if featured:
            lines.append("#### 🔒 Las más seguras")
            for item in featured:
                expl = item.get("explanation", "").strip()
                if not expl.startswith("*"):
                    if not expl.lower().startswith("porque"):
                        expl = f"Porque {expl}"
                    expl = f"*{expl}*"
                lines.append(f"• **{item.get('selection', '')} — {item.get('probability', 0.0) * 100:.1f}%**{_value_suffix(item)}  ")
                lines.append(f"  {expl}  ")
            lines.append("")
        categories_spec = []

    for cat_name, header in categories_spec:
        items = [m for m in markets_by_cat.get(cat_name, []) if m.get("selection") != top_selection]
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
        lines.append(f"• **Tarjetas estimadas:** {total_cards:.2f}{_referee_suffix(report)}  ")
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
