"""Backtest walk-forward y ajuste de parámetros de DEPORT AI.

Ejemplos (Windows / PowerShell):

    # 1) Verificar el pipeline con una liga simulada (no requiere token)
    python backtest.py --synthetic

    # 2) Backtest REAL con Sportmonks: equipos de una misma liga, últimos 40 partidos
    python backtest.py --teams "Real Madrid,Barcelona,Atletico Madrid,Sevilla,Valencia,Villarreal" --count 40

    # 3) Ajustar parámetros por máxima verosimilitud y guardarlos para esa liga
    python backtest.py --teams-file laliga.txt --count 40 --fit --save-params

    # 4) Incluir cuotas históricas (si el plan las tiene) para medir ROI
    python backtest.py --teams-file laliga.txt --with-odds

    # 5) Sembrar la calibración dinámica con resultados walk-forward REALES
    python backtest.py --teams-file laliga.txt --save-calibration

Cada partido se predice solo con partidos anteriores a su fecha. Solo se evalúan
partidos entre equipos de la lista (se necesita el historial de ambos), así que
conviene pasar todos los equipos de una liga.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from deport_ai.backtesting import (  # noqa: E402
    BacktestResult,
    build_fixtures,
    estimate_count_dispersions,
    load_from_sportmonks,
    load_odds_from_sportmonks,
    run_walk_forward,
    scoreline_objective,
    synthetic_league,
)
from deport_ai.model_params import (  # noqa: E402
    DEFAULT_PARAMETERS,
    ModelParameters,
    fit_parameters,
    fitted_fixture_ids,
    load_parameters,
    save_parameters,
)


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def format_report(
    result: BacktestResult,
    title: str,
    params: ModelParameters,
    fitted_from: ModelParameters | None = None,
) -> str:
    summary = result.summary()
    shown, every = summary["shown"], summary["all"]
    lines = [
        f"# 📊 {title}",
        f"**Fecha:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Partidos evaluados (walk-forward):** {summary['evaluated_fixtures']} "
        f"(omitidos por historial insuficiente: {summary['skipped_fixtures']})",
        f"**Log-loss del marcador exacto:** {summary['scoreline_log_loss']}",
        "",
        "## Parámetros usados",
        f"- rho Dixon-Coles: `{params.rho}` · peso Elo: `{params.elo_weight}` · peso sede: `{params.venue_weight}` "
        f"· peso temporada: `{params.season_weight}` · escala tabla de clubes: `{params.club_tier_scale}`",
        f"- Dispersión córners: `{params.dispersion_corners}` · tarjetas: `{params.dispersion_cards}` "
        f"(None = perfil de liga) · ajustado con datos: `{params.fitted}`",
    ]
    if fitted_from is not None and params.log_loss is not None:
        lines.append(
            f"- Ajuste: log-loss {params.baseline_log_loss} → {params.log_loss} "
            f"sobre {params.sample_size} partidos"
        )

    lines += ["", "## 1. Lo que ve el usuario (selecciones mostradas, 60–88 %)"]
    if shown.get("count"):
        verdict = (
            "🟢 bien calibrado" if abs(shown["gap"]) < 0.03
            else "🟡 desviación moderada" if abs(shown["gap"]) < 0.07
            else "🔴 sobreconfianza" if shown["gap"] < 0 else "🔴 infraconfianza"
        )
        lines += [
            f"- Selecciones: **{shown['count']}** · probabilidad media mostrada: **{_pct(shown['mean_predicted'])}** "
            f"· acierto real: **{_pct(shown['hit_rate'])}** · diferencia: **{shown['gap'] * 100:+.1f} pts** ({verdict})",
            f"- Brier: `{shown['brier']}` · Log-loss: `{shown['log_loss']}`",
        ]
        if shown.get("roi") is not None:
            lines.append(f"- ROI plano con cuota ({shown['priced']} apuestas con precio): **{shown['roi'] * 100:+.1f}%**")
        lines += ["", "| Tramo | Muestra | Prob. media | Acierto real |", "|---|:---:|:---:|:---:|"]
        for b in shown["calibration"]:
            lines.append(f"| {b['bin']} | {b['count']} | {_pct(b['predicted'])} | {_pct(b['observed'])} |")
        lines += ["", "| Categoría | Muestra | Prob. media | Acierto real | Diferencia | Brier | ROI |",
                  "|---|:---:|:---:|:---:|:---:|:---:|:---:|"]
        for cat, b in shown["by_category"].items():
            roi = "—" if b["roi"] is None else f"{b['roi'] * 100:+.1f}%"
            lines.append(
                f"| {cat} | {b['count']} | {_pct(b['mean_predicted'])} | {_pct(b['hit_rate'])} "
                f"| {b['gap'] * 100:+.1f} | {b['brier']} | {roi} |"
            )
    else:
        lines.append("- Sin selecciones liquidables.")

    lines += ["", "## 2. Todos los mercados calculados (calibración global)"]
    if every.get("count"):
        lines += [
            f"- Predicciones: {every['count']} · Brier: `{every['brier']}` · Log-loss: `{every['log_loss']}`",
            "",
            "| Tramo | Muestra | Prob. media | Acierto real |",
            "|---|:---:|:---:|:---:|",
        ]
        for b in every["calibration"]:
            lines.append(f"| {b['bin']} | {b['count']} | {_pct(b['predicted'])} | {_pct(b['observed'])} |")

    if summary["unsettled_markets"]:
        lines += ["", "## 3. Mercados no liquidables con estos datos (no cuentan)"]
        for market, count in summary["unsettled_markets"].items():
            lines.append(f"- {market}: {count}")
        lines.append("- *Mitades y córners 1T requieren datos por tiempo; DNB con empate es nulo; jugadores no se evalúan.*")
    return "\n".join(lines)


def storage_conflict(args: argparse.Namespace) -> str | None:
    """Motivo para no ejecutar una combinación que guardaría datos que no valen para producción.

    - Una liga simulada no debe dejar parámetros ni calibración: no tiene número de liga,
      así que el ajuste se guardaba como global y se aplicaba a ligas reales.
    - Con --fit el backtest se evalúa con los mismos partidos del ajuste: sus resultados
      no son independientes y no deben entrar en la calibración.
    """
    if args.synthetic and (args.save_params or args.as_default or args.save_calibration):
        return "Con --synthetic no se guardan parámetros ni calibración: la liga es simulada."
    if args.fit and args.save_calibration:
        return ("--fit y --save-calibration no van juntos: el backtest usaría los mismos partidos del ajuste. "
                "Ajusta con una temporada y guarda la calibración con otra en una ejecución aparte.")
    return None


def save_calibration_from_backtest(
    result: BacktestResult, db: Any = None, excluded: set[int] | frozenset[int] = frozenset()
) -> tuple[int, int]:
    """Registra las selecciones mostradas y liquidadas para la calibración y las exporta
    al histórico del repositorio (si no, se perdían al cerrar la sesión).

    Se guardan como no publicadas (nunca se mostraron a nadie) y con la probabilidad del
    modelo como `model_prob` (el backtest no aplica calibración). Los partidos de
    `excluded` (usados en un ajuste de parámetros) no se guardan. Devuelve
    (predicciones guardadas, partidos omitidos por haberse usado en un ajuste).
    """
    from deport_ai.dynamic_calibration import DynamicCalibrator
    from deport_ai.storage import DatabaseManager

    db = db or DatabaseManager()
    by_fixture: dict[int, list[dict[str, Any]]] = {}
    for record in result.records:
        if record["shown"]:
            by_fixture.setdefault(record["fixture_id"], []).append(
                {**record, "model_prob": record["probability"], "unpublished": True}
            )
    saved = skipped = 0
    for fixture_id, records in by_fixture.items():
        if fixture_id in excluded:
            skipped += 1
            continue
        if db.get_fixture(fixture_id) is not None:
            continue  # ya existe (p. ej. seguido en vivo): no se duplica
        sample = result.samples[fixture_id]
        db.save_fixture_and_predictions(
            fixture_id=fixture_id,
            home_team_id=sample.home.team_id,
            home_team_name=sample.home_name,
            away_team_id=sample.away.team_id,
            away_team_name=sample.away_name,
            league_id=sample.league_id,
            league_name="Backtest walk-forward",
            match_date=sample.date,
            predictions=records,
        )
        db.update_fixture_result(fixture_id, result.actuals[fixture_id], status="FINISHED")
        stored = db.get_predictions_for_fixture(fixture_id)
        outcome = {(r["category"], r["market"], r["selection"]): r["won"] for r in records}
        for pred in stored:
            won = outcome.get((pred["category"], pred["market"], pred["selection"]))
            if won is not None:
                db.update_prediction_status(pred["id"], "WON" if won else "LOST")
        saved += len(records)
    DynamicCalibrator(db).recompute_calibrations()
    db.export_history()
    return saved, skipped


def run_xg_comparison(args: argparse.Namespace, matches_by_team, team_names) -> None:
    """Backtest de los mismos partidos con peso de xG 0 (modelo actual) y con xG de Flashscore."""
    from deport_ai.backtesting import format_xg_comparison, goal_market_summary, xg_coverage
    from deport_ai.flashscore import FlashscoreXG, attach_xg, fixtures_from_matches

    provider = FlashscoreXG(log=print)
    all_matches = [m for ms in matches_by_team.values() for m in ms]
    sm_fixtures = fixtures_from_matches(all_matches, team_names)
    print(f"Buscando xG en Flashscore para {len(sm_fixtures)} partidos (se guardan en {provider.cache_path})...")
    counts = provider.fetch(sm_fixtures, max_new=args.xg_max_new)
    print("Flashscore:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    with_xg = {team_id: attach_xg(ms, provider) for team_id, ms in matches_by_team.items()}

    fixtures = build_fixtures(with_xg, team_names)
    leagues = [f.league_id for f in fixtures if f.league_id is not None]
    league_id = args.league_id if args.league_id is not None else (max(set(leagues), key=leagues.count) if leagues else None)
    params = load_parameters(league_id)
    coverage = xg_coverage(fixtures, with_xg, args.min_history, args.window)
    weights = [float(w) for w in args.xg_weights.split(",") if w.strip()]
    summaries = {}
    for weight in [0.0] + weights:
        label = "Base: sin xG (modelo actual)" if weight == 0 else f"Con xG, peso {weight:.2f}"
        print(f"Backtest — {label}...")
        result = run_walk_forward(
            fixtures, with_xg, params=replace(params, xg_weight=weight),
            min_history=args.min_history, window=args.window,
        )
        summaries[label] = goal_market_summary(result)
    report = format_xg_comparison(summaries, coverage, f"Backtest xG (Flashscore) — liga {league_id}")
    print("\n" + report + "\n")
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Informe guardado en {args.output}")
    if args.json:
        Path(args.json).write_text(json.dumps({"coverage": coverage, "runs": summaries}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"Resumen JSON guardado en {args.json}")


def _run_factor_comparison(args, matches_by_team, team_names, *, field: str, weights: str, select_fixtures,
                           coverage_fn, title: str, coverage_label: str, base_label: str, label: str) -> None:
    """Mismos partidos con el factor en 0 y con cada peso, sobre el modelo actual (con xG guardado)."""
    from deport_ai.backtesting import format_xg_comparison, goal_market_summary
    from deport_ai.flashscore import FlashscoreXG, attach_xg

    # Solo el xG ya guardado: sin lecturas nuevas (no gasta créditos ni escribe la caché).
    provider = FlashscoreXG(fetcher=object())
    with_xg = {team_id: attach_xg(ms, provider) for team_id, ms in matches_by_team.items()}
    fixtures = select_fixtures(build_fixtures(with_xg, team_names))
    leagues = [f.league_id for f in fixtures if f.league_id is not None]
    league_id = args.league_id if args.league_id is not None else (max(set(leagues), key=leagues.count) if leagues else None)
    params = load_parameters(league_id)
    coverage = coverage_fn(fixtures, with_xg, args.min_history, args.window)
    summaries = {}
    for weight in [0.0] + [float(w) for w in weights.split(",") if w.strip()]:
        run_label = base_label if weight == 0 else label.format(weight)
        print(f"Backtest — {run_label}...")
        result = run_walk_forward(
            fixtures, with_xg, params=replace(params, **{field: weight}),
            min_history=args.min_history, window=args.window,
        )
        summaries[run_label] = goal_market_summary(result)
    report = format_xg_comparison(summaries, coverage, title.format(league_id), coverage_label=coverage_label)
    print("\n" + report + "\n")
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Informe guardado en {args.output}")
    if args.json:
        Path(args.json).write_text(json.dumps({"coverage": coverage, "runs": summaries}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"Resumen JSON guardado en {args.json}")


def run_injury_comparison(args: argparse.Namespace, matches_by_team, team_names) -> None:
    """Con y sin el descuento por bajas, en los partidos con lista de bajas."""
    from deport_ai.backtesting import absence_coverage, fixtures_with_injury_data

    _run_factor_comparison(
        args, matches_by_team, team_names, field="absence_weight", weights=args.injury_weights,
        select_fixtures=fixtures_with_injury_data, coverage_fn=absence_coverage,
        title="Backtest bajas — liga {} (partidos con lista de bajas)",
        coverage_label="con alguna baja que pesaba en el ataque",
        base_label="Base: sin ajuste por bajas (modelo actual)", label="Con bajas, peso {:.2f}",
    )


def run_lineup_comparison(args: argparse.Namespace, matches_by_team, team_names) -> None:
    """Con y sin el ajuste por fuerza del once, en los partidos con once publicado."""
    from deport_ai.backtesting import fixtures_with_lineups, lineup_coverage

    _run_factor_comparison(
        args, matches_by_team, team_names, field="lineup_weight", weights=args.lineup_weights,
        select_fixtures=fixtures_with_lineups, coverage_fn=lineup_coverage,
        title="Backtest fuerza del once — liga {} (partidos con once publicado)",
        coverage_label="con un once más débil que de costumbre (déficit ≥ 0.05)",
        base_label="Base: sin ajuste por el once (modelo actual)", label="Con fuerza del once, peso {:.2f}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest walk-forward y ajuste de parámetros de DEPORT AI")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--synthetic", action="store_true", help="Liga simulada (verificación del pipeline)")
    source.add_argument("--teams", type=str, default="", help="Equipos separados por coma (misma liga)")
    source.add_argument("--teams-file", type=str, default="", help="Archivo con un equipo por línea")
    parser.add_argument("--count", type=int, default=40, help="Partidos terminados por equipo a descargar")
    parser.add_argument("--min-history", type=int, default=6, help="Partidos previos mínimos por equipo")
    parser.add_argument("--window", type=int, default=12, help="Partidos previos usados por predicción")
    parser.add_argument("--league-id", type=int, default=None, help="Liga a la que se asocian los parámetros")
    parser.add_argument("--fit", action="store_true", help="Ajusta parámetros por máxima verosimilitud")
    parser.add_argument("--save-params", action="store_true", help="Guarda los parámetros ajustados en model_params.json")
    parser.add_argument("--as-default", action="store_true", help="Guarda los parámetros como globales (todas las ligas)")
    parser.add_argument("--with-odds", action="store_true", help="Descarga cuotas por partido para medir ROI")
    parser.add_argument("--save-calibration", action="store_true", help="Registra los resultados en la BD de calibración")
    parser.add_argument("--output", type=str, default="", help="Guarda el informe en Markdown")
    parser.add_argument("--json", type=str, default="", help="Guarda el resumen en JSON")
    parser.add_argument("--xg", action="store_true",
                        help="Añade el xG de Flashscore y compara el modelo con y sin xG")
    parser.add_argument("--xg-weights", type=str, default="0.35,0.5",
                        help="Pesos del xG a comparar contra 0 (separados por coma)")
    parser.add_argument("--injuries", action="store_true",
                        help="Compara el modelo con y sin el descuento por bajas (usa el xG ya guardado)")
    parser.add_argument("--injury-weights", type=str, default="0.5,1.0",
                        help="Pesos del descuento por bajas a comparar contra 0 (separados por coma)")
    parser.add_argument("--lineups", action="store_true",
                        help="Compara el modelo con y sin el ajuste por fuerza del once (titulares habituales)")
    parser.add_argument("--lineup-weights", type=str, default="0.5,1.0,1.5",
                        help="Pesos del ajuste por el once a comparar contra 0 (separados por coma)")
    parser.add_argument("--xg-max-new", type=int, default=None,
                        help="Máximo de partidos nuevos a leer de Flashscore (créditos de Firecrawl)")
    args = parser.parse_args()
    problem = storage_conflict(args)
    if problem:
        print(f"❌ {problem}")
        sys.exit(2)

    client = None
    if not args.synthetic and not (args.teams or args.teams_file):
        print("Indica los equipos con --teams-file leagues/<liga>.txt (o --teams). "
              "Para probar el pipeline con una liga simulada usa --synthetic.")
        sys.exit(2)
    if args.synthetic:
        print("Liga simulada: sirve para verificar el pipeline, no para medir el modelo real.")
        matches_by_team, team_names = synthetic_league()
        title = "Backtest walk-forward — liga simulada"
    else:
        from deport_ai.config import Settings
        from deport_ai.sportmonks import SportmonksClient

        settings = Settings.from_env()
        settings.validate()
        client = SportmonksClient(
            settings.sportmonks_api_token or "",
            timeout=settings.timeout_seconds,
            timezone=settings.timezone,
            base_url=settings.sportmonks_base_url,
        )
        if args.teams_file:
            queries = [
                line.strip() for line in Path(args.teams_file).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        else:
            queries = [part.strip() for part in args.teams.split(",") if part.strip()]
        print(f"Descargando historial de {len(queries)} equipos desde Sportmonks...")
        matches_by_team, team_names = load_from_sportmonks(client, queries, args.count, log=print)
        title = "Backtest walk-forward — datos reales Sportmonks"

    if args.lineups:
        if client is None:
            print("--lineups necesita datos reales (--teams o --teams-file).")
            sys.exit(1)
        run_lineup_comparison(args, matches_by_team, team_names)
        return

    if args.injuries:
        if client is None:
            print("--injuries necesita datos reales (--teams o --teams-file).")
            sys.exit(1)
        run_injury_comparison(args, matches_by_team, team_names)
        return

    if args.xg:
        if client is None:
            print("--xg necesita datos reales (--teams o --teams-file).")
            sys.exit(1)
        run_xg_comparison(args, matches_by_team, team_names)
        return

    fixtures = build_fixtures(matches_by_team, team_names)
    if not fixtures:
        print("No hay partidos entre los equipos indicados. Usa equipos de una misma liga.")
        sys.exit(1)
    leagues = [f.league_id for f in fixtures if f.league_id is not None]
    league_id = args.league_id if args.league_id is not None else (max(set(leagues), key=leagues.count) if leagues else None)
    print(f"Partidos entre equipos del conjunto: {len(fixtures)} · liga principal: {league_id}")

    params = load_parameters(league_id) if not args.fit else DEFAULT_PARAMETERS
    fitted_from = None
    if args.fit:
        print("Ajustando parámetros (descenso por coordenadas, walk-forward)...")
        objective = scoreline_objective(fixtures, matches_by_team, args.min_history, args.window)
        fitted_from = params
        params = fit_parameters(objective, start=params)
        params = replace(
            params,
            fitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            fitted_fixture_ids=tuple(sorted({f.fixture_id for f in fixtures})),
            **estimate_count_dispersions(fixtures),
        )
        if args.save_params:
            key = "default" if args.as_default or league_id is None else str(league_id)
            path = save_parameters(key, params)
            print(f"Parámetros guardados en {path} (clave '{key}').")
        print(
            "⚠️ El backtest siguiente usa los mismos partidos del ajuste (dentro de muestra). "
            "Para una medición limpia, ajusta con una temporada y evalúa con otra."
        )

    odds_by_fixture = None
    if args.with_odds and client is not None:
        print("Descargando cuotas históricas...")
        odds_by_fixture = load_odds_from_sportmonks(client, fixtures)
        print(f"Partidos con cuotas: {len(odds_by_fixture)}")

    print("Ejecutando backtest de todos los mercados...")
    result = run_walk_forward(
        fixtures,
        matches_by_team,
        params=params,
        min_history=args.min_history,
        window=args.window,
        odds_by_fixture=odds_by_fixture,
    )
    report = format_report(result, title, params, fitted_from)
    print("\n" + report + "\n")

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Informe guardado en {args.output}")
    if args.json:
        Path(args.json).write_text(json.dumps(result.summary(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Resumen JSON guardado en {args.json}")
    if args.save_calibration:
        saved, skipped = save_calibration_from_backtest(result, excluded=fitted_fixture_ids())
        print(f"Calibración actualizada con {saved} predicciones walk-forward reales (no publicadas).")
        if skipped:
            print(f"Omitidos {skipped} partidos ya usados en un ajuste de parámetros (no serían independientes).")
        print("Quedaron en history/predictions.jsonl: súbelas con `python track.py sync`.")


if __name__ == "__main__":
    main()
