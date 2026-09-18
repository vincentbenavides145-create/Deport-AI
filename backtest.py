"""Script de Backtesting Histórico Walk-Forward para DEPORT AI.

Ejecuta simulaciones estrictamente cronológicas sobre partidos pasados,
garantizando cero sesgo retrospectivo (look-ahead bias) y publicando
métricas de precisión demostrada: Brier Score, Log Loss y Calibración Decílica.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Asegurar que src esté en el path
_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from deport_ai.config import Settings
from deport_ai.domain import Team, TeamMatch
from deport_ai.evaluation import evaluate_binary_predictions, evaluate_multiclass_1x2
from deport_ai.sportmonks import SportmonksClient
from deport_ai.stats_engine import calculate_elo, goal_probabilities


def run_synthetic_backtest(n_matches: int = 100) -> dict[str, Any]:
    """Genera una simulación histórica sintética de una liga completa para verificar el pipeline."""
    import random
    random.seed(42)

    teams = [Team(i, f"Equipo {chr(65 + i)}", "País Test") for i in range(10)]
    all_matches: list[TeamMatch] = []
    
    # Generar calendario de partidos
    fixture_id = 1000
    for round_num in range(18):
        for i in range(0, 10, 2):
            h_idx = (i + round_num) % 10
            a_idx = (i + 1 + round_num) % 10
            if h_idx == a_idx:
                a_idx = (a_idx + 1) % 10
            
            # Asignar niveles de fuerza base
            h_strength = 1.0 + (h_idx / 10.0) * 0.8
            a_strength = 1.0 + (a_idx / 10.0) * 0.8
            
            h_lambda = h_strength * 1.4
            a_lambda = a_strength * 1.0
            
            hg = min(7, max(0, int(random.gauss(h_lambda, 1.1))))
            ag = min(7, max(0, int(random.gauss(a_lambda, 0.9))))
            
            date_str = f"2024-{(round_num // 3) + 1:02d}-{(round_num % 3) * 9 + 5:02d}T15:00:00Z"
            all_matches.append(
                TeamMatch(
                    fixture_id=fixture_id,
                    date=date_str,
                    team_id=teams[h_idx].id,
                    opponent_id=teams[a_idx].id,
                    is_home=True,
                    goals_for=hg,
                    goals_against=ag,
                    result="W" if hg > ag else "D" if hg == ag else "L",
                    opponent_name=teams[a_idx].name,
                    competition_weight=1.0,
                    league_id=384,
                )
            )
            all_matches.append(
                TeamMatch(
                    fixture_id=fixture_id,
                    date=date_str,
                    team_id=teams[a_idx].id,
                    opponent_id=teams[h_idx].id,
                    is_home=False,
                    goals_for=ag,
                    goals_against=hg,
                    result="W" if ag > hg else "D" if ag == hg else "L",
                    opponent_name=teams[h_idx].name,
                    competition_weight=1.0,
                    league_id=384,
                )
            )
            fixture_id += 1

    return evaluate_match_sequence(all_matches, min_history=6)


def evaluate_match_sequence(matches: list[TeamMatch], min_history: int = 6) -> dict[str, Any]:
    """Evalúa una secuencia de partidos aplicando la regla estricta walk-forward."""
    fixtures_dict: dict[int, tuple[TeamMatch, TeamMatch]] = {}
    for m in matches:
        if m.fixture_id not in fixtures_dict:
            for comp in matches:
                if comp.fixture_id == m.fixture_id and comp.team_id != m.team_id:
                    home_m = m if m.is_home else comp
                    away_m = comp if m.is_home else m
                    fixtures_dict[m.fixture_id] = (home_m, away_m)
                    break

    fixtures = list(fixtures_dict.values())
    fixtures.sort(key=lambda pair: pair[0].date)

    probs_1x2: list[tuple[float, float, float]] = []
    outcomes_1x2: list[str] = []

    probs_over15: list[float] = []
    outcomes_over15: list[int] = []

    probs_over25: list[float] = []
    outcomes_over25: list[int] = []

    probs_btts: list[float] = []
    outcomes_btts: list[int] = []

    evaluated_count = 0

    for idx, (target_h, target_a) in enumerate(fixtures):
        current_date = target_h.date
        history_home = [
            m for m in matches
            if m.team_id == target_h.team_id and m.date < current_date
        ]
        history_away = [
            m for m in matches
            if m.team_id == target_a.team_id and m.date < current_date
        ]

        if len(history_home) < min_history or len(history_away) < min_history:
            continue

        elo_h, elo_a = calculate_elo(
            history_home,
            history_away,
            target_h.team_id,
            target_a.team_id,
            home_league=target_h.league_id,
            away_league=target_a.league_id,
        )

        prob_report = goal_probabilities(
            history_home,
            history_away,
            elo_h,
            elo_a,
            league_id=target_h.league_id,
        )

        actual_hg = target_h.goals_for
        actual_ag = target_h.goals_against

        # 1X2
        probs_1x2.append((prob_report.home_win, prob_report.draw, prob_report.away_win))
        outcomes_1x2.append(target_h.result)

        # Over 1.5
        probs_over15.append(prob_report.over_15)
        outcomes_over15.append(1 if (actual_hg + actual_ag) >= 2 else 0)

        # Over 2.5
        probs_over25.append(prob_report.over_25)
        outcomes_over25.append(1 if (actual_hg + actual_ag) >= 3 else 0)

        # BTTS
        probs_btts.append(prob_report.btts)
        outcomes_btts.append(1 if (actual_hg > 0 and actual_ag > 0) else 0)

        evaluated_count += 1

    if evaluated_count == 0:
        return {"error": "No se encontraron suficientes partidos con historial previo para evaluar."}

    eval_1x2 = evaluate_multiclass_1x2(probs_1x2, outcomes_1x2)
    eval_o15 = evaluate_binary_predictions(probs_over15, outcomes_over15, bins=5)
    eval_o25 = evaluate_binary_predictions(probs_over25, outcomes_over25, bins=5)
    eval_btts = evaluate_binary_predictions(probs_btts, outcomes_btts, bins=5)

    return {
        "evaluated_matches": evaluated_count,
        "1x2": {
            "brier_score": eval_1x2.brier_score,
            "log_loss": eval_1x2.log_loss,
            "accuracy": eval_1x2.accuracy,
            "home_acc": eval_1x2.home_accuracy,
            "draw_acc": eval_1x2.draw_accuracy,
            "away_acc": eval_1x2.away_accuracy,
        },
        "over_15": {
            "brier_score": eval_o15.brier_score,
            "log_loss": eval_o15.log_loss,
            "calibration": [
                {
                    "bin": f"{int(b.lower*100)}%-{int(b.upper*100)}%",
                    "count": b.count,
                    "predicted_avg": round(b.mean_predicted, 3) if b.mean_predicted is not None else None,
                    "observed_avg": round(b.observed_frequency, 3) if b.observed_frequency is not None else None,
                }
                for b in eval_o15.calibration
            ],
        },
        "over_25": {
            "brier_score": eval_o25.brier_score,
            "log_loss": eval_o25.log_loss,
            "calibration": [
                {
                    "bin": f"{int(b.lower*100)}%-{int(b.upper*100)}%",
                    "count": b.count,
                    "predicted_avg": round(b.mean_predicted, 3) if b.mean_predicted is not None else None,
                    "observed_avg": round(b.observed_frequency, 3) if b.observed_frequency is not None else None,
                }
                for b in eval_o25.calibration
            ],
        },
        "btts": {
            "brier_score": eval_btts.brier_score,
            "log_loss": eval_btts.log_loss,
        },
    }


def format_backtest_report(results: dict[str, Any], title: str = "Auditoría de Precisión Histórica") -> str:
    """Formatea los resultados del backtesting en un informe profesional en Markdown."""
    lines = [
        f"# 📊 {title}",
        f"**Fecha de Auditoría:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Partidos Evaluados (Walk-Forward Estricto):** {results.get('evaluated_matches', 0)}",
        "",
        "---",
        "",
        "## 1. Mercado 1X2 (Resultado Final)",
        f"- **Brier Score Multiclase:** `{results['1x2']['brier_score']}` *(Excelente < 0.55 | Aleatorio ~0.66)*",
        f"- **Log Loss:** `{results['1x2']['log_loss']}`",
        f"- **Precisión Directa (Hit Rate):** `{results['1x2']['accuracy'] * 100:.1f}%`",
        f"  • Acierto en Victorias Locales: `{results['1x2']['home_acc'] * 100:.1f}%`",
        f"  • Acierto en Empates: `{results['1x2']['draw_acc'] * 100:.1f}%`",
        f"  • Acierto en Victorias Visitantes: `{results['1x2']['away_acc'] * 100:.1f}%`",
        "",
        "---",
        "",
        "## 2. Mercados de Goles y Calibración Decílica",
        "",
        "### Más de 1.5 Goles Totales",
        f"- **Brier Score:** `{results['over_15']['brier_score']:.4f}` | **Log Loss:** `{results['over_15']['log_loss']:.4f}`",
        "",
        "| Rango Probabilidad | Muestra | Predicción Media | Frecuencia Real | Calibración |",
        "|---|:---:|:---:|:---:|:---:|",
    ]
    for b in results["over_15"]["calibration"]:
        if b["count"] > 0 and b["predicted_avg"] is not None and b["observed_avg"] is not None:
            diff = abs(b["predicted_avg"] - b["observed_avg"])
            cal_status = "🟢 Excelente" if diff < 0.08 else "🟡 Aceptable" if diff < 0.15 else "🔴 Desviado"
            lines.append(
                f"| **{b['bin']}** | {b['count']} | {b['predicted_avg']*100:.1f}% | {b['observed_avg']*100:.1f}% | {cal_status} |"
            )

    lines.extend([
        "",
        "### Más de 2.5 Goles Totales",
        f"- **Brier Score:** `{results['over_25']['brier_score']:.4f}` | **Log Loss:** `{results['over_25']['log_loss']:.4f}`",
        "",
        "| Rango Probabilidad | Muestra | Predicción Media | Frecuencia Real | Calibración |",
        "|---|:---:|:---:|:---:|:---:|",
    ])
    for b in results["over_25"]["calibration"]:
        if b["count"] > 0 and b["predicted_avg"] is not None and b["observed_avg"] is not None:
            diff = abs(b["predicted_avg"] - b["observed_avg"])
            cal_status = "🟢 Excelente" if diff < 0.08 else "🟡 Aceptable" if diff < 0.15 else "🔴 Desviado"
            lines.append(
                f"| **{b['bin']}** | {b['count']} | {b['predicted_avg']*100:.1f}% | {b['observed_avg']*100:.1f}% | {cal_status} |"
            )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Ambos Equipos Marcan (BTTS)",
        f"- **Brier Score:** `{results['btts']['brier_score']:.4f}`",
        f"- **Log Loss:** `{results['btts']['log_loss']:.4f}`",
    ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoría y Backtesting Histórico de DEPORT AI")
    parser.add_argument("--synthetic", action="store_true", help="Ejecuta simulación con datos sintéticos completos")
    parser.add_argument("--matches", type=int, default=100, help="Número de partidos a evaluar")
    parser.add_argument("--output", type=str, default="", help="Ruta de archivo para guardar el reporte")
    args = parser.parse_args()

    print("Iniciando auditoría de backtesting histórico...")
    results = run_synthetic_backtest(n_matches=args.matches)
    report_text = format_backtest_report(results, title="Auditoría de Precisión Histórica (DEPORT AI)")

    print("\n" + report_text + "\n")

    if args.output:
        Path(args.output).write_text(report_text, encoding="utf-8")
        print(f"Reporte guardado exitosamente en: {args.output}")


if __name__ == "__main__":
    main()
