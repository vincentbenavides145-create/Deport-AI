from __future__ import annotations

from typing import Any

from .domain import MatchRef, Team


FINISHED_STATUSES = {"FT", "AET", "PEN"}
# Partidos que no se jugarán (o se resolvieron en mesa): sus apuestas se anulan.
VOID_FIXTURE_STATUSES = {"CANCELLED", "ABANDONED", "DELETED", "AWARDED", "WO", "WALKOVER"}


def to_match_ref(row: dict[str, Any]) -> MatchRef:
    teams = row.get("teams", {})
    fixture = row.get("fixture", {})
    league = row.get("league", {})
    goals = row.get("goals", {})
    home = teams.get("home", {})
    away = teams.get("away", {})
    return MatchRef(
        fixture_id=int(fixture["id"]),
        home=Team(int(home["id"]), home["name"], home.get("country")),
        away=Team(int(away["id"]), away["name"], away.get("country")),
        date=fixture.get("date", ""),
        league_id=_int_or_none(league.get("id")),
        league_name=league.get("name"),
        season=_int_or_none(league.get("season")),
        status=fixture.get("status", {}).get("short", ""),
        home_goals=_int_or_none(goals.get("home")),
        away_goals=_int_or_none(goals.get("away")),
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None

