from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .domain import AnalysisReport, ConfidenceScore, FactorAttribution, MatchRef, Team
from .dynamic_calibration import DynamicCalibrator
from .errors import LiveMatchError
from .fixture_contract import FINISHED_STATUSES, to_match_ref
from .llm import LLMExplainer
from .model_params import load_parameters
from .odds import normalize_odds, select_opportunities
from .parser import parse_match_query
from .statistical_markets import (
    mark_highlights,
    select_featured_markets,
    select_statistical_markets,
    select_top_recommended_pick,
)
from .storage import DatabaseManager
from .stats_engine import (
    calculate_confidence_score,
    calculate_elo,
    classify_competition,
    detect_altitude_impact,
    expected_metrics,
    extract_common_opponents,
    extract_player_shots,
    extract_team_matches,
    goal_probabilities,
    sample_risks,
)


logger = logging.getLogger(__name__)

class AnalysisService:
    def __init__(
        self,
        api: Any,
        explainer: LLMExplainer,
        recent_count: int = 15,
        h2h_count: int = 15,
        detail_count: int = 8,
        db: DatabaseManager | None = None,
        auto_track: bool = True,
    ):
        self.api = api
        self.explainer = explainer
        self.recent_count = recent_count
        self.h2h_count = h2h_count
        self.detail_count = max(8, detail_count)
        self.db = db if db is not None else DatabaseManager()
        self.calibrator = DynamicCalibrator(self.db)
        self.auto_track = auto_track
        self.xg_provider: Any = None  # FlashscoreXG; se crea al primer uso

    def _attach_xg(self, home: Any, away: Any, home_matches: list[Any], away_matches: list[Any]):
        """Añade el xG de Flashscore a los partidos recientes. Si falla, sigue sin xG."""
        try:
            from .flashscore import FlashscoreXG, attach_xg, fixtures_from_matches

            if self.xg_provider is None:
                self.xg_provider = FlashscoreXG()
            names = {home.id: home.name, away.id: away.name}
            fixtures = fixtures_from_matches(home_matches + away_matches, names)
            self.xg_provider.fetch(fixtures, max_new=XG_MAX_NEW_PER_ANALYSIS)
            return attach_xg(home_matches, self.xg_provider), attach_xg(away_matches, self.xg_provider)
        except Exception as exc:  # sin Firecrawl o sin red: el análisis sigue con goles
            logger.warning("xG de Flashscore no disponible: %s", exc)
            return home_matches, away_matches

    def analyze(self, question: str, track: bool | None = None) -> AnalysisReport:
        first_name, second_name = parse_match_query(question)
        if hasattr(self.api, "resolve_match"):
            first, second = self.api.resolve_match(first_name, second_name)
        else:
            first = self.api.resolve_team(first_name)
            second = self.api.resolve_team(second_name)

        upcoming_row = self.api.upcoming_between(first.id, second.id)
        live_fixture_notice = None
        if upcoming_row:
            status_code = str((upcoming_row.get("fixture", {}).get("status", {}) or {}).get("short") or "").upper()
            state_dev = str((upcoming_row.get("state") or {}).get("developer_name") or "").upper()
            live_terms = {"1H", "2H", "HT", "ET", "PEN_LIVE", "BREAK", "INPLAY", "LIVE"}
            if (
                status_code in live_terms
                or any(term in status_code for term in ("1H", "2H", "HT", "INPLAY", "LIVE"))
                or any(term in state_dev for term in ("INPLAY", "LIVE", "1ST_HALF", "2ND_HALF", "HALF_TIME"))
            ):
                live_fixture_notice = (
                    f"El encuentro entre {first.name} y {second.name} se encuentra en desarrollo en vivo. "
                    "El análisis se generó con base en todos los partidos finalizados previos, "
                    "excluyendo el resultado parcial en juego para preservar la consistencia estadística."
                )

        fixture = to_match_ref(upcoming_row) if upcoming_row else None
        home, away = self._orientation(first, second, fixture)

        home_rows = self.api.recent_fixtures(home.id, self.recent_count)
        away_rows = self.api.recent_fixtures(away.id, self.recent_count)
        # Muestra detallada de mínimo 8 partidos por equipo (siempre >= 8) para métricas robustas.
        fetch_count = max(8, self.detail_count)
        detail_rows = home_rows[:fetch_count] + away_rows[:fetch_count]
        detail_ids = [int(row["fixture"]["id"]) for row in detail_rows]
        details = self.api.fixture_details(detail_ids)
        home_matches = extract_team_matches(home_rows, home.id, details)
        away_matches = extract_team_matches(away_rows, away.id, details)
        if XG_ENABLED:
            home_matches, away_matches = self._attach_xg(home, away, home_matches, away_matches)

        h2h_rows = self.api.h2h(home.id, away.id, self.h2h_count)
        h2h = [to_match_ref(row) for row in h2h_rows if _finished(row)]

        context = _shared_context(home_rows, away_rows) or _latest_context(home_rows, away_rows)
        home_season: dict[str, Any] = {}
        away_season: dict[str, Any] = {}
        coverage: dict[str, Any] = {}
        max_season = getattr(self.api, "max_season", datetime.now().year)
        current_data = max_season >= datetime.now().year - 1
        coverage_checked = False
        if current_data and context and context.league_id and context.season:
            coverage = self.api.coverage(context.league_id, context.season)
            coverage_checked = True
            home_season = self.api.team_season_statistics(home.id, context.league_id, context.season)
            away_season = self.api.team_season_statistics(away.id, context.league_id, context.season)

        fixture_accessible = bool(
            fixture and (fixture.season is None or fixture.season <= max_season)
        )
        fixture_id = fixture.fixture_id if fixture_accessible and fixture else None
        injuries_supported = bool(coverage.get("injuries"))
        fixture_coverage = coverage.get("fixtures", {}) or {}
        lineups_supported = bool(fixture_coverage.get("lineups"))
        odds_supported = bool(coverage.get("odds"))
        injuries = self.api.injuries(fixture_id) if injuries_supported else []
        lineups = self.api.lineups(fixture_id) if lineups_supported else []
        odds = normalize_odds(self.api.odds(fixture_id)) if odds_supported else {}

        # Días de descanso confirmados (cero especulación - regla contextual estricta)
        rest_days_home: float | None = None
        rest_days_away: float | None = None
        if fixture and fixture.date:
            if home_matches and home_matches[0].date:
                try:
                    dt_f = datetime.fromisoformat(fixture.date.replace("Z", "+00:00"))
                    dt_h = datetime.fromisoformat(home_matches[0].date.replace("Z", "+00:00"))
                    diff_h = (dt_f - dt_h).total_seconds() / 86400.0
                    if diff_h >= 0:
                        rest_days_home = round(diff_h, 1)
                except Exception:
                    pass
            if away_matches and away_matches[0].date:
                try:
                    dt_f = datetime.fromisoformat(fixture.date.replace("Z", "+00:00"))
                    dt_a = datetime.fromisoformat(away_matches[0].date.replace("Z", "+00:00"))
                    diff_a = (dt_f - dt_a).total_seconds() / 86400.0
                    if diff_a >= 0:
                        rest_days_away = round(diff_a, 1)
                except Exception:
                    pass

        # Titularidad y minutos esperados desde alineación confirmada
        starter_info: dict[int, dict[str, Any]] = {}
        lineups_confirmed = False
        if lineups:
            # Un once publicado horas antes puede ser solo probable: se toma como oficial
            # únicamente cerca del inicio (ambos equipos y a <= 60 minutos).
            lineups_confirmed = lineups_are_official(lineups, fixture.date if fixture else None)
            for team_info in lineups:
                starters = team_info.get("startXI", [])
                for p in starters:
                    pid = p.get("player", {}).get("id")
                    if pid is not None:
                        starter_info[int(pid)] = {"is_starter": True, "expected_minutes": 75.0}
                for p in team_info.get("substitutes", []):
                    pid = p.get("player", {}).get("id")
                    if pid is not None:
                        starter_info[int(pid)] = {"is_starter": False, "expected_minutes": 22.0}

        home_league = _primary_league_id(home_rows)
        away_league = _primary_league_id(away_rows)
        target_league_id = fixture.league_id if fixture and fixture.league_id else home_league
        target_league_name = fixture.league_name if fixture else None

        model_params = load_parameters(target_league_id)
        elo_home, elo_away = calculate_elo(
            home_matches,
            away_matches,
            home.id,
            away.id,
            home_country=home.country,
            away_country=away.country,
            home_league=home_league,
            away_league=away_league,
            home_name=home.name,
            away_name=away.name,
            club_tier_scale=model_params.club_tier_scale,
        )
        referee_cards = self._referee_cards(fixture_id) if REFEREE_FACTOR_ENABLED else None
        altitude_impact = detect_altitude_impact(home.id, home.name, away.id, away.name, home.country, away.country)
        probabilities = goal_probabilities(
            home_matches,
            away_matches,
            elo_home,
            elo_away,
            home_season,
            away_season,
            altitude_impact=altitude_impact,
            league_id=target_league_id,
            league_name=target_league_name,
            rest_days_home=rest_days_home,
            rest_days_away=rest_days_away,
            params=model_params,
        )
        player_rows = extract_player_shots(details.values())
        expected = expected_metrics(
            home_matches,
            away_matches,
            player_rows,
            home.id,
            away.id,
            elo_home=elo_home,
            elo_away=elo_away,
            altitude_impact=altitude_impact,
            league_id=target_league_id,
            league_name=target_league_name,
            starter_info=starter_info if starter_info else None,
            params=model_params,
            referee_cards=referee_cards,
        )

        if lineups:
            starter_names: dict[int, set[str]] = {
                int(team_info["team"]["id"]): {
                    p["player"]["name"].lower()
                    for p in team_info.get("startXI", [])
                    if p.get("player", {}).get("name")
                }
                for team_info in lineups
                if "team" in team_info and team_info["team"].get("id")
            }
            for team_id in (home.id, away.id):
                if team_id in starter_names and starter_names[team_id]:
                    valid_names = starter_names[team_id]
                    # Solo quedan los titulares del once publicado (aunque la lista quede vacía).
                    # Si el once aún no es oficial, siguen requiriendo confirmar titularidad.
                    starter_flag = True if lineups_confirmed else None
                    expected.player_shots[team_id] = [
                        {**p, "is_starter": starter_flag}
                        for p in expected.player_shots.get(team_id, [])
                        if any(s in p["name"].lower() or p["name"].lower() in s for s in valid_names)
                    ]
                    expected.anytime_goalscorers[team_id] = [
                        {**p, "is_starter": starter_flag}
                        for p in expected.anytime_goalscorers.get(team_id, [])
                        if any(s in p["name"].lower() or p["name"].lower() in s for s in valid_names)
                    ]

        # Calibración dinámica adaptativa basada en resultados empíricos
        calibration = self.calibrator.get_calibration_summary(target_league_id, target_league_name)
        if calibration.active:
            self.calibrator.apply_dynamic_calibration_to_projections(expected, probabilities, calibration)

        confidence = calculate_confidence_score(
            home_matches=home_matches,
            away_matches=away_matches,
            expected=expected,
            lineups_confirmed=lineups_confirmed,
            odds_available=bool(odds),
        )
        opportunities = select_opportunities(probabilities, odds)
        statistical_markets = select_statistical_markets(
            home,
            away,
            probabilities,
            expected,
            calibration=calibration,
            recent_home=home_matches,
            recent_away=away_matches,
            odds=odds,
            exclude_categories=unreliable_categories(home_matches, away_matches, target_league_id),
        )
        top_pick = select_top_recommended_pick(
            statistical_markets,
            recent_home=home_matches,
            recent_away=away_matches,
            probabilities=probabilities,
            expected=expected,
        )
        featured = select_featured_markets(statistical_markets, top_pick)
        mark_highlights(statistical_markets, top_pick, featured)
        risks = sample_risks(home_matches, away_matches, expected)
        if altitude_impact:
            risks.insert(0, f"🏔️ FACTOR ALTITUD ({altitude_impact['home_altitude']} m.s.n.m.): {altitude_impact['description']}")
        risks.extend(
            _availability_risks(
                getattr(self.api, "provider_label", "el proveedor deportivo"),
                fixture,
                injuries,
                lineups,
                odds,
                injuries_supported,
                lineups_supported,
                odds_supported,
                max_season,
                fixture_accessible,
            )
        )
        if live_fixture_notice:
            risks.insert(0, f"Partido en vivo: {live_fixture_notice}")

        report = AnalysisReport(
            home=home,
            away=away,
            fixture=fixture,
            recent_home=home_matches,
            recent_away=away_matches,
            h2h=h2h,
            probabilities=probabilities,
            expected=expected,
            elo_home=elo_home,
            elo_away=elo_away,
            injuries=_compact_injuries(injuries),
            lineups=_compact_lineups(lineups),
            odds=odds,
            opportunities=opportunities,
            statistical_markets=statistical_markets,
            risks=list(dict.fromkeys(risks)),
            sources=_sources(
                getattr(self.api, "provider_label", "Proveedor deportivo"),
                fixture,
                bool(home_season or away_season),
                injuries_supported,
                lineups_supported,
                odds_supported,
                coverage_checked,
            ),
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            common_opponents=extract_common_opponents(home_matches, away_matches),
            confidence=confidence,
            attribution_home=probabilities.attribution_home,
            attribution_away=probabilities.attribution_away,
            dynamic_calibration_info=calibration,
            top_pick=top_pick,
            featured_markets=featured,
        )
        report.narrative = self.explainer.explain(report)

        should_track = self.auto_track if track is None else track
        if should_track and fixture and fixture.fixture_id:
            try:
                self.db.save_fixture_and_predictions(
                    fixture_id=fixture.fixture_id,
                    home_team_id=home.id,
                    home_team_name=home.name,
                    away_team_id=away.id,
                    away_team_name=away.name,
                    league_id=target_league_id,
                    league_name=target_league_name,
                    match_date=fixture.date,
                    predictions=statistical_markets,
                )
                self.db.export_history()
            except Exception:
                pass

        return report

    def _referee_cards(self, fixture_id: int | None) -> tuple[float, int] | None:
        """Promedio de tarjetas del árbitro asignado, si el proveedor lo publica."""
        if not fixture_id or not hasattr(self.api, "fixture_referee"):
            return None
        try:
            referee = self.api.fixture_referee(fixture_id)
            return self.api.referee_card_rate(referee["referee_id"]) if referee else None
        except Exception:
            return None

    @staticmethod
    def _orientation(first: Team, second: Team, fixture: MatchRef | None) -> tuple[Team, Team]:
        if fixture:
            by_id = {first.id: first, second.id: second}
            return by_id.get(fixture.home.id, fixture.home), by_id.get(fixture.away.id, fixture.away)
        return first, second


def _finished(row: dict[str, Any]) -> bool:
    return row.get("fixture", {}).get("status", {}).get("short") in FINISHED_STATUSES


def _latest_context(home_rows: list[dict[str, Any]], away_rows: list[dict[str, Any]]) -> MatchRef | None:
    rows = home_rows + away_rows
    if not rows:
        return None
    rows.sort(key=lambda row: int(row.get("fixture", {}).get("timestamp") or 0), reverse=True)
    return to_match_ref(rows[0])


def _shared_context(
    home_rows: list[dict[str, Any]], away_rows: list[dict[str, Any]]
) -> MatchRef | None:
    def grouped(rows: list[dict[str, Any]]) -> dict[tuple[int, int], list[dict[str, Any]]]:
        result: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in rows:
            league = row.get("league", {})
            if league.get("id") is None or league.get("season") is None:
                continue
            key = (int(league["id"]), int(league["season"]))
            result.setdefault(key, []).append(row)
        return result

    home_groups, away_groups = grouped(home_rows), grouped(away_rows)
    common = set(home_groups) & set(away_groups)
    if not common:
        return None
    key = max(
        common,
        key=lambda item: (item[1], len(home_groups[item]) + len(away_groups[item])),
    )
    candidates = home_groups[key] + away_groups[key]
    candidates.sort(
        key=lambda row: int(row.get("fixture", {}).get("timestamp") or 0), reverse=True
    )
    return to_match_ref(candidates[0])


def _availability_risks(
    provider: str,
    fixture: MatchRef | None,
    injuries: list[dict[str, Any]],
    lineups: list[dict[str, Any]],
    odds: dict[str, float],
    injuries_supported: bool,
    lineups_supported: bool,
    odds_supported: bool,
    max_season: int,
    fixture_accessible: bool,
) -> list[str]:
    risks: list[str] = []
    if fixture is None:
        risks.append(
            "No se encontró un próximo fixture entre ambos equipos: se analiza el cruce hipotético "
            "con el primer equipo como local."
        )
    elif fixture.season and fixture.season > max_season:
        risks.append(
            f"El plan de {provider} está configurado hasta la temporada {max_season}; "
            f"el fixture es {fixture.season}. Forma y modelos usan los datos reales más recientes accesibles."
        )
    if fixture and not fixture_accessible:
        risks.append(
            "Lesiones, alineaciones y cuotas actuales no se consultan porque el fixture está fuera "
            "de las temporadas accesibles del plan."
        )
        return risks
    if not injuries_supported:
        risks.append(f"El plan de {provider} o la competición no incluye cobertura de lesiones.")
    elif injuries:
        risks.append(f"Lesiones/sanciones reportadas por la API: {len(injuries)} registros.")
    else:
        risks.append("Lesiones: sin bajas reportadas a la fecha; no equivale a plantilla completa.")
    if not lineups_supported:
        risks.append(f"El plan de {provider} no incluye alineaciones para esta liga.")
    elif not lineups:
        risks.append("Alineaciones aún no confirmadas por los clubes; el análisis asume onces habituales.")
    if not odds_supported:
        risks.append(f"El plan de {provider} no tiene habilitado el endpoint de cuotas.")
    elif not odds:
        risks.append("Cuotas aún no publicadas en el mercado para este fixture.")
    return risks


def _compact_injuries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        player = row.get("player", {})
        team = row.get("team", {})
        result.append(
            {
                "player": player.get("name", "No informado"),
                "team": team.get("name", "No informado"),
                "type": player.get("type") or row.get("type") or "No informado",
                "reason": player.get("reason") or row.get("reason") or "No informado",
            }
        )
    return result


def _compact_lineups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "team": row.get("team", {}).get("name"),
            "formation": row.get("formation"),
            "starting_xi": [
                player.get("player", {}).get("name") for player in row.get("startXI", []) or []
            ],
        }
        for row in rows
    ]


def _sources(
    provider: str,
    fixture: MatchRef | None,
    has_season_stats: bool,
    injuries_supported: bool,
    lineups_supported: bool,
    odds_supported: bool,
    coverage_checked: bool,
) -> list[str]:
    sources = [
        f"{provider} /teams",
        f"{provider} /fixtures",
        f"{provider} /fixtures/head-to-head",
    ]
    if coverage_checked:
        sources.append(f"{provider} cobertura del plan")
    if has_season_stats:
        sources.append(f"{provider} estadísticas de temporada")
    if fixture:
        if injuries_supported:
            sources.append(f"{provider} sidelined")
        if lineups_supported:
            sources.append(f"{provider} lineups")
        if odds_supported:
            sources.append(f"{provider} odds")
    return sources


# Factor árbitro en tarjetas (validado con backtest walk-forward antes de activarlo).
REFEREE_FACTOR_ENABLED = True

# xG de Flashscore vía Firecrawl (validado con `backtest.py --xg` antes de activarlo).
XG_ENABLED = False
# Tope de partidos nuevos que se leen por análisis (1 crédito de Firecrawl cada uno).
XG_MAX_NEW_PER_ANALYSIS = 30


def lineups_are_confirmed(lineups: list[dict[str, Any]] | None) -> bool:
    """Solo hay alineación confirmada cuando ambos equipos publicaron su once titular."""
    return sum(1 for team_info in lineups or [] if team_info.get("startXI")) >= 2


# Ventana antes del inicio en la que un once publicado se considera oficial.
OFFICIAL_LINEUP_WINDOW_MINUTES = 60


def lineups_are_official(
    lineups: list[dict[str, Any]] | None,
    kickoff_iso: str | None,
    now: datetime | None = None,
    window_minutes: int = OFFICIAL_LINEUP_WINDOW_MINUTES,
) -> bool:
    """Once de ambos equipos publicado y a `window_minutes` o menos del inicio.

    Sportmonks publica onces con horas de anticipación que pueden ser probables; antes de
    la ventana se tratan como no confirmados.
    """
    if not lineups_are_confirmed(lineups) or not kickoff_iso:
        return False
    try:
        kickoff = datetime.fromisoformat(str(kickoff_iso).replace("Z", "+00:00"))
    except ValueError:
        return False
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return (kickoff - current).total_seconds() <= window_minutes * 60


# Cobertura mínima de un dato en la competición para ofrecer sus mercados.
MIN_COVERAGE_SAMPLE = 4
MIN_OFFSIDES_COVERAGE = 0.8


def unreliable_categories(
    home_matches: list[Any], away_matches: list[Any], league_id: int | None
) -> set[str]:
    """Categorías que no conviene ofrecer porque la competición no suele publicar el dato.

    Se mide sobre los partidos recientes de ambos equipos en la misma competición que
    tienen estadísticas completas: si en menos del 80% aparecen los fueras de juego, ese
    mercado no se podría liquidar con fiabilidad.
    """
    if league_id is None:
        # Sin partido programado no se conoce la competición: se usa la más frecuente.
        counts = Counter(m.league_id for m in list(home_matches) + list(away_matches) if getattr(m, "league_id", None))
        if not counts:
            return set()
        league_id = counts.most_common(1)[0][0]
    seen: dict[int, Any] = {}
    for match in list(home_matches) + list(away_matches):
        stats = getattr(match, "stats_for", {}) or {}
        if getattr(match, "league_id", None) == league_id and ("corner_kicks" in stats or "total_shots" in stats):
            seen[match.fixture_id] = match
    if len(seen) < MIN_COVERAGE_SAMPLE:
        return set()
    with_offsides = sum(1 for match in seen.values() if "offsides" in match.stats_for)
    if with_offsides / len(seen) < MIN_OFFSIDES_COVERAGE:
        return {"Fueras de juego"}
    return set()


def _primary_league_id(rows: list[dict[str, Any]]) -> int | None:
    counts: Counter[int] = Counter()
    for row in rows or []:
        league = row.get("league", {})
        lid = league.get("id")
        lname = str(league.get("name", "")).lower()
        cat, weight = classify_competition(lname, lid, league.get("type"), league.get("sub_type"))
        if cat in ("FRIENDLY", "UNKNOWN") or weight < 0.50:
            continue
        if lid:
            counts[int(lid)] += 1
    return counts.most_common(1)[0][0] if counts else None
