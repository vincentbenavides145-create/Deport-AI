from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .domain import AnalysisReport, MatchRef, Team
from .errors import LiveMatchError
from .fixture_contract import FINISHED_STATUSES, to_match_ref
from .llm import LLMExplainer
from .odds import normalize_odds, select_opportunities
from .parser import parse_match_query
from .stats_engine import (
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


class AnalysisService:
    def __init__(
        self,
        api: Any,
        explainer: LLMExplainer,
        recent_count: int = 15,
        h2h_count: int = 15,
        detail_count: int = 8,
    ):
        self.api = api
        self.explainer = explainer
        self.recent_count = recent_count
        self.h2h_count = h2h_count
        self.detail_count = max(8, detail_count)

    def analyze(self, question: str) -> AnalysisReport:
        first_name, second_name = parse_match_query(question)
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

        home_league = _primary_league_id(home_rows)
        away_league = _primary_league_id(away_rows)
        elo_home, elo_away = calculate_elo(
            home_matches,
            away_matches,
            home.id,
            away.id,
            home_country=home.country,
            away_country=away.country,
            home_league=home_league,
            away_league=away_league,
        )
        altitude_impact = detect_altitude_impact(home.id, home.name, away.id, away.name)
        probabilities = goal_probabilities(
            home_matches,
            away_matches,
            elo_home,
            elo_away,
            home_season,
            away_season,
            altitude_impact=altitude_impact,
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
        )

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
                    filtered_shots = [
                        p
                        for p in expected.player_shots.get(team_id, [])
                        if any(s in p["name"].lower() or p["name"].lower() in s for s in valid_names)
                    ]
                    if filtered_shots:
                        expected.player_shots[team_id] = filtered_shots

                    filtered_scorers = [
                        p
                        for p in expected.anytime_goalscorers.get(team_id, [])
                        if any(s in p["name"].lower() or p["name"].lower() in s for s in valid_names)
                    ]
                    if filtered_scorers:
                        expected.anytime_goalscorers[team_id] = filtered_scorers

        odds = normalize_odds(self.api.odds(fixture_id)) if odds_supported else {}
        opportunities = select_opportunities(probabilities, odds)
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
        )
        report.narrative = self.explainer.explain(report)
        return report

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

