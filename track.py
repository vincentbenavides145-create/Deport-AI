"""Script CLI de seguimiento, liquidación y aprendizaje dinámico para DEPORT AI.

Permite:
1. Liquidar apuestas pendientes contra resultados reales de Sportmonks (`update`).
2. Visualizar tablero de aciertos, fallos y rentabilidad (`report`).
3. Ejecutar auditoría y post-mortem profundo con IA (`ai-review`).
4. Recalcular y actualizar factores de calibración dinámica (`calibrate`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Añadir src al sys.path
_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from deport_ai.ai_critic import AICritic
from deport_ai.config import Settings
from deport_ai.dynamic_calibration import DynamicCalibrator
from deport_ai.llm import LLMExplainer
from deport_ai.settlement import SettlementEngine
from deport_ai.sportmonks import SportmonksClient
from deport_ai.storage import DatabaseManager


def cmd_update(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    settings.validate()
    api = SportmonksClient(
        settings.sportmonks_api_token or "",
        timeout=settings.timeout_seconds,
        timezone=settings.timezone,
        base_url=settings.sportmonks_base_url,
    )
    db = DatabaseManager()
    engine = SettlementEngine(db, api)

    print("🔍 Buscando partidos pendientes de liquidación en Sportmonks...")
    results = engine.settle_all_pending()

    settled_count = sum(1 for r in results if r.get("status") == "SETTLED")
    pending_count = sum(1 for r in results if r.get("status") == "STILL_PENDING_OR_IN_PLAY")

    print(f"\n✅ Liquidación completada: {settled_count} partidos cerrados, {pending_count} aún pendientes o en juego.")
    for r in results:
        fix_id = r["fixture_id"]
        st = r["status"]
        if st == "SETTLED":
            s = r["summary"]
            print(f"  • Fixture #{fix_id}: {s['won']} ✅ Won | {s['lost']} ❌ Lost | {s['void']} ↩️ Void")
        elif st == "STILL_PENDING_OR_IN_PLAY":
            print(f"  • Fixture #{fix_id}: Aún no finalizado en Sportmonks.")

    # Recalcular automáticamente la calibración tras la liquidación
    if settled_count > 0:
        calibrator = DynamicCalibrator(db)
        updated = calibrator.recompute_calibrations()
        print(f"⚡ Calibración adaptativa actualizada: {updated} factores de liga/categoría sincronizados.")


def cmd_report(args: argparse.Namespace) -> None:
    db = DatabaseManager()
    summary = db.get_summary_stats()
    settled = db.get_settled_predictions(league_id=args.league, limit=args.limit)

    if args.json:
        print(json.dumps({"summary": summary, "settled": settled}, ensure_ascii=False, indent=2))
        return

    print("# 📊 Tablero de Rendimiento Histórico (DEPORT AI)\n")
    print(f"• **Total Predicciones Registradas:** {summary['total_predictions']}")
    print(f"• **Resueltas:** {summary['resolved']} ({summary['won']} ✅ Ganadas | {summary['lost']} ❌ Perdidas | {summary['void']} ↩️ Anuladas)")
    print(f"• **Pendientes:** {summary['pending']}")
    print(f"• **Hit Rate Global:** `{summary['overall_hit_rate'] * 100:.1f}%`\n")

    if summary["by_category"]:
        print("### Rendimiento por Categoría:\n")
        print("| Categoría | Total | Won | Lost | Void | Hit Rate | Prob. Media |")
        print("|:---|:---:|:---:|:---:|:---:|:---:|:---:|")
        for c in summary["by_category"]:
            print(f"| **{c['category']}** | {c['total']} | {c['won']} | {c['lost']} | {c['void']} | **{c['hit_rate']*100:.1f}%** | {c['avg_predicted_prob']*100:.1f}% |")
        print("")

    if settled:
        print("### Últimas Apuestas Liquidadas:\n")
        print("| Partido | Mercado | Selección | Prob. | Resultado |")
        print("|:---|:---|:---|:---:|:---:|")
        for s in settled[:15]:
            badge = "✅ WON" if s["status"] == "WON" else ("❌ LOST" if s["status"] == "LOST" else "↩️ VOID")
            fix = f"{s['home_team_name']} vs {s['away_team_name']}"
            print(f"| {fix} | {s['category']} | {s['selection']} | {s['predicted_prob']*100:.1f}% | {badge} |")


def cmd_ai_review(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    explainer = LLMExplainer(settings.openai_api_key, settings.openai_model) if settings.openai_api_key else None
    db = DatabaseManager()
    critic = AICritic(db, explainer=explainer)

    report_md = critic.generate_diagnostic_report(league_id=args.league, limit=args.limit)
    print("\n" + report_md + "\n")


def cmd_calibrate(args: argparse.Namespace) -> None:
    db = DatabaseManager()
    calibrator = DynamicCalibrator(db)
    updated = calibrator.recompute_calibrations(min_sample=max(30, args.min_sample))
    print(f"⚡ Calibración adaptativa completada: {updated} factores de liga y categorías actualizados en SQLite.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestor de seguimiento y aprendizaje dinámico de DEPORT AI")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # update
    sub_up = subparsers.add_parser("update", help="Consulta Sportmonks y liquida partidos finalizados")
    sub_up.set_defaults(func=cmd_update)

    # report
    sub_rep = subparsers.add_parser("report", help="Muestra el reporte cuantitativo de aciertos y fallos")
    sub_rep.add_argument("--league", type=int, default=None, help="Filtrar por ID de liga")
    sub_rep.add_argument("--limit", type=int, default=50, help="Límite de apuestas a listar")
    sub_rep.add_argument("--json", action="store_true", help="Salida en formato JSON")
    sub_rep.set_defaults(func=cmd_report)

    # ai-review
    sub_rev = subparsers.add_parser("ai-review", help="Ejecuta diagnóstico post-mortem profundo con IA")
    sub_rev.add_argument("--league", type=int, default=None, help="Filtrar por ID de liga")
    sub_rev.add_argument("--limit", type=int, default=100, help="Muestra máxima a evaluar")
    sub_rev.set_defaults(func=cmd_ai_review)

    # calibrate
    sub_cal = subparsers.add_parser("calibrate", help="Recalcula factores de sesgo y contracción empírica")
    sub_cal.add_argument("--min-sample", type=int, default=30, help="Muestra mínima requerida (nunca menor a 30)")
    sub_cal.set_defaults(func=cmd_calibrate)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
