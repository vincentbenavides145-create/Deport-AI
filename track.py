"""Script CLI de seguimiento, liquidación y aprendizaje dinámico para DEPORT AI.

Permite:
1. Liquidar apuestas pendientes contra resultados reales de Sportmonks (`update`).
2. Visualizar tablero de aciertos, fallos y rentabilidad (`report`).
3. Ejecutar auditoría y post-mortem profundo con IA (`ai-review`).
4. Recalcular y actualizar factores de calibración dinámica (`calibrate`).
5. Subir el histórico de predicciones al repositorio (`sync`): commit + push a main.

El histórico permanente es `history/predictions.jsonl` (dentro del repositorio). La base
SQLite local se reconstruye desde ese archivo al iniciar una sesión nueva.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
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

    highlights = summary.get("highlights") or {}
    if highlights:
        print("### ⭐ Lo que se recomienda (formato corto):\n")
        for key, label in (("pick", "Pick Recomendado"), ("top5", "Las más seguras")):
            h = highlights.get(key)
            if not h:
                continue
            rate = f"{h['hit_rate'] * 100:.1f}%" if h["hit_rate"] is not None else "sin liquidar"
            print(f"• **{label}:** {h['won']} ✅ | {h['lost']} ❌ | {h['pending']} pendientes · acierto `{rate}` · prob. media {h['avg_predicted_prob'] * 100:.1f}%")
        print("")

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
    db = DatabaseManager()
    critic = AICritic(db, api_key=settings.openai_api_key, model=settings.openai_model)

    report_md = critic.generate_diagnostic_report(league_id=args.league, limit=args.limit)
    print("\n" + report_md + "\n")


def cmd_calibrate(args: argparse.Namespace) -> None:
    db = DatabaseManager()
    calibrator = DynamicCalibrator(db)
    updated = calibrator.recompute_calibrations(min_sample=max(30, args.min_sample))
    print(f"⚡ Calibración adaptativa completada: {updated} factores de liga y categorías actualizados en SQLite.")


HISTORY_FILE = "history/predictions.jsonl"
XG_FILE = "history/flashscore_xg.json"


def _git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=check)


def merge_xg_caches(local: dict, remote: dict) -> dict:
    """Une dos cachés de xG de Flashscore; ante el mismo partido manda la local."""
    return {"version": 1, "matches": {**remote.get("matches", {}), **local.get("matches", {})}}


def _merge_remote_history(repo: Path, db: DatabaseManager) -> None:
    """Trae main y fusiona su histórico antes de exportar, para no pisar liquidaciones."""
    if _git(repo, "fetch", "origin", "main").returncode != 0:
        print("⚠️ No se pudo leer main remoto: se sube solo el histórico local.")
        return
    remote_history = _git(repo, "show", f"FETCH_HEAD:{HISTORY_FILE}")
    if remote_history.returncode == 0:
        merged = db.merge_history(remote_history.stdout)
        if merged:
            print(f"🔄 {merged} partidos actualizados desde el histórico remoto.")
    xg_path = repo / XG_FILE
    local_xg = json.loads(xg_path.read_text(encoding="utf-8")) if xg_path.exists() else {}
    remote_xg_raw = _git(repo, "show", f"FETCH_HEAD:{XG_FILE}")
    remote_xg = json.loads(remote_xg_raw.stdout) if remote_xg_raw.returncode == 0 else {}
    # Si esta copia va por detrás de main, avanza: el histórico se reescribe enseguida
    # desde la base (que ya incluye lo remoto) y la caché de xG se vuelve a unir.
    behind = _git(repo, "merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD").returncode == 0
    if behind and _git(repo, "rev-parse", "HEAD").stdout != _git(repo, "rev-parse", "FETCH_HEAD").stdout:
        _git(repo, "checkout", "--", HISTORY_FILE, XG_FILE)
        if _git(repo, "merge", "--ff-only", "FETCH_HEAD").returncode != 0:
            print("⚠️ No se pudo avanzar a main remoto (hay otros cambios locales).")
    if local_xg or remote_xg:
        merged_xg = merge_xg_caches(local_xg, remote_xg)
        merged_xg["matches"] = dict(sorted(merged_xg["matches"].items(), key=lambda kv: int(kv[0])))
        xg_path.write_text(json.dumps(merged_xg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def cmd_sync(args: argparse.Namespace) -> None:
    repo = Path(__file__).resolve().parent
    db = DatabaseManager()
    _merge_remote_history(repo, db)
    path = db.export_history()
    rel = path.relative_to(repo)
    _git(repo, "add", str(rel), check=True)
    if (repo / XG_FILE).exists():  # xG de Flashscore ya leído: se conserva para no gastar créditos otra vez
        _git(repo, "add", XG_FILE, check=True)
    if _git(repo, "diff", "--cached", "--quiet").returncode == 0:
        print("El histórico ya está al día en git.")
        return
    _git(repo, "commit", "-m", f"Histórico de predicciones {date.today().isoformat()}", check=True)
    push = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=repo)
    if push.returncode != 0:
        sys.exit(push.returncode)
    print(f"📒 Histórico subido a main ({rel}).")


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

    # sync
    sub_sync = subparsers.add_parser("sync", help="Sube el histórico de predicciones al repositorio (main)")
    sub_sync.set_defaults(func=cmd_sync)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
