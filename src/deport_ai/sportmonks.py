from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher, get_close_matches
from statistics import fmean
from typing import Any, Iterable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from .domain import Team
from .errors import APIError, AmbiguousTeamError, TeamNotFoundError
from .fixture_contract import FINISHED_STATUSES


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


DEFAULT_BASE_URL = "https://api.sportmonks.com/v3/football"
# Valor de SPORTMONKS_API_TOKEN cuando un proxy de red inyecta el token real.
PROXY_INJECTED_TOKEN = "proxy-injected"
DETAIL_INCLUDES = (
    "participants;scores;statistics.type;lineups.details.type;"
    "league;season;state;formations"
)
FIXTURE_INCLUDES = "participants;scores;league;season;state;lineups;formations;sidelined.sideline"


TEAM_ALIASES: dict[str, str] = {
    "arsenal": "Arsenal",
    "arsenal fc": "Arsenal",
    "gales": "Wales",
    "noruega": "Norway",
    "nooruega": "Norway",
    "dinamarca": "Denmark",
    "alemania": "Germany",
    "inglaterra": "England",
    "espana": "Spain",
    "españa": "Spain",
    "francia": "France",
    "italia": "Italy",
    "paises bajos": "Netherlands",
    "holanda": "Netherlands",
    "croacia": "Croatia",
    "belgica": "Belgium",
    "bélgica": "Belgium",
    "suiza": "Switzerland",
    "suecia": "Sweden",
    "polonia": "Poland",
    "turquia": "Turkey",
    "turquía": "Turkey",
    "austria": "Austria",
    "escocia": "Scotland",
    "irlanda": "Republic of Ireland",
    "islandia": "Iceland",
    "grecia": "Greece",
    "brasil": "Brazil",
    "estados unidos": "USA",
    "eeuu": "USA",
    "japon": "Japan",
    "japón": "Japan",
    "marruecos": "Morocco",
    "sunderland": "Sunderland",
    "sunderland afc": "Sunderland",
    "udinese": "Udinese",
    "udinese calcio": "Udinese",
    "udinense": "Udinese",
    "udinense calcio": "Udinese",
    "villarreal": "Villarreal",
    "villarreal cf": "Villarreal",
    "virrareal": "Villarreal",
    "virrareal cf": "Villarreal",
    "villareal": "Villarreal",
    "villareal cf": "Villarreal",
    "real betis": "Real Betis",
    "betis": "Real Betis",
    "real betis balompie": "Real Betis",
    "real betis balompié": "Real Betis",
    "betis balompie": "Real Betis",
    "betis balompié": "Real Betis",
    "inter": "Inter",
    "inter milan": "Inter",
    "inter de milan": "Inter",
    "internazionale": "Inter",
    "athletic bilbao": "Athletic Club",
    "athletic de bilbao": "Athletic Club",
    "bilbao": "Athletic Club",
    "real madrid": "Real Madrid",
    "rela madrid": "Real Madrid",
    "real madrid cf": "Real Madrid",
    "elche": "Elche",
    "elche cf": "Elche",
    "elche fc": "Elche",
    "corinthians": "Corinthians",
    "corinthians sp": "Corinthians",
    "sc corinthians": "Corinthians",
    "sc corinthians paulista": "Corinthians",
    "corinthians paulista": "Corinthians",
    "estudiantes": "Estudiantes",
    "estudiantes de la plata": "Estudiantes",
    "estudiantes lp": "Estudiantes",
    "flamengo": "Flamengo",
    "flamengo rj": "Flamengo",
    "independiente del valle": "Independiente del Valle",
    "independinete del valle": "Independiente del Valle",
    "idv": "Independiente del Valle",
    "inter milan": "Inter",
    "inter de milan": "Inter",
    "internazionale": "Inter",
    "sporting lisboa": "Sporting CP",
    "sporting de lisboa": "Sporting CP",
    "bayern munich": "Bayern München",
    "bayern de munich": "Bayern München",
    "bayern munchen": "Bayern München",
    "bayer munchen": "Bayern München",
    "fk bodo": "Bodø / Glimt",
    "bodo": "Bodø / Glimt",
    "bodo glimt": "Bodø / Glimt",
    "bodø glimt": "Bodø / Glimt",
    "psg": "Paris Saint Germain",
    "paris sg": "Paris Saint Germain",
    "atletico madrid": "Atlético Madrid",
    "atletico de madrid": "Atlético Madrid",
    "manchester utd": "Manchester United",
    "man utd": "Manchester United",
    "man united": "Manchester United",
    "tottenham hotspurs": "Tottenham Hotspur",
    "spurs": "Tottenham Hotspur",
    "wolves": "Wolverhampton Wanderers",
    "independiente santa fe": "Santa Fe",
    "santa fe": "Santa Fe",
    "club america": "América",
    "club américa": "América",
    "america": "América",
    "columbus": "Columbus Crew",
    "brighton": "Brighton & Hove Albion",
    "brighton & hove albion": "Brighton & Hove Albion",
    "fulham": "Fulham",
    "chelsea": "Chelsea",
    "ca lanus": "Lanús",
    "ca lanús": "Lanús",
    "lanus": "Lanús",
    "club atletico lanus": "Lanús",
    "boca": "Boca Juniors",
    "boca juniors": "Boca Juniors",
    "gremio novorizontino": "Novorizontino",
    "novorizontino": "Novorizontino",
    "deportes recife": "Sport Recife",
    "sport recife": "Sport Recife",
    "juventus fc": "Juventus",
    "juventus": "Juventus",
    "parma calcio 1913": "Parma",
    "parma calcio": "Parma",
    "parma": "Parma",
    "utc de cajamarca": "UTC Cajamarca",
    "utc cajamarca": "UTC Cajamarca",
    "utc": "UTC Cajamarca",
    "universitario deportes": "Universitario",
    "universitario de deportes": "Universitario",
    "la u": "Universitario",
    "soprting cristal": "Sporting Cristal",
    "sport boys association": "Sport Boys",
    "fortaleza ce": "Fortaleza",
    "fortaleza ec": "Fortaleza",
    "operario pr": "Operário PR",
    "operario ferroviario": "Operário PR",
    "cucuta deportiva": "Cúcuta Deportivo",
    "cucuta deportivo": "Cúcuta Deportivo",
    "tolima": "Deportes Tolima",
    "deportes tolima": "Deportes Tolima",
    "lille": "LOSC Lille",
    "lille osc": "LOSC Lille",
    "losc lille": "LOSC Lille",
    "toulouse fc": "Toulouse",
    "feyenoord": "Feyenoord",
    "feyenoord rotterdam": "Feyenoord",
    "feyornoorrd": "Feyenoord",
    "feyornoorrd rotterdam": "Feyenoord",
    "fc sabah": "Sabah",
    "sabah fc": "Sabah",
    "sabah fk": "Sabah",
    "psv eindhoven": "PSV",
    "psv": "PSV",
    "shakhtar": "Shakhtar Donetsk",
    "shakhtar donetsk": "Shakhtar Donetsk",
    "club cienciano": "Cienciano",
    "cienciano": "Cienciano",
    "montevideo city torque": "Montevideo City Torque",
    "city torque": "Montevideo City Torque",
    "torque": "Montevideo City Torque",
    "arsenal": "Arsenal",
    "arsenal fc": "Arsenal",
    "sunderland": "Sunderland",
    "sunderland afc": "Sunderland",
}

TEAM_ID_OVERRIDES: dict[str, int] = {
    "arsenal": 19,
    "arsenal fc": 19,
    "sunderland": 3,
    "sunderland afc": 3,
    "udinese": 346,
    "udinese calcio": 346,
    "udinense": 346,
    "udinense calcio": 346,
    "villarreal": 3477,
    "villarreal cf": 3477,
    "virrareal": 3477,
    "virrareal cf": 3477,
    "villareal": 3477,
    "villareal cf": 3477,
    "real betis": 485,
    "betis": 485,
    "real betis balompie": 485,
    "real betis balompié": 485,
    "betis balompie": 485,
    "betis balompié": 485,
    "cienciano": 13264,
    "club cienciano": 13264,
    "montevideo city torque": 5479,
    "city torque": 5479,
    "torque": 5479,
    "psv": 682,
    "psv eindhoven": 682,
    "shakhtar": 621,
    "shakhtar donetsk": 621,
    "sabah": 138649,
    "fc sabah": 138649,
    "sabah fc": 138649,
    "sabah fk": 138649,
    "bayer munchen": 503,
    "bayern munchen": 503,
    "bayern munich": 503,
    "bodo": 1668,
    "fk bodo": 1668,
    "bodo glimt": 1668,
    "bodø glimt": 1668,
    "bodø / glimt": 1668,
    "feyenoord": 73,
    "feyenoord rotterdam": 73,
    "feyornoorrd": 73,
    "feyornoorrd rotterdam": 73,
    "inter": 2930,
    "inter milan": 2930,
    "inter de milan": 2930,
    "internazionale": 2930,
    "inter miami": 239235,
    "inter miami cf": 239235,
    "inter de miami": 239235,
    "san diego": 275650,
    "san diego fc": 275650,
    "lille": 690,
    "lille osc": 690,
    "losc lille": 690,
    "toulouse": 289,
    "toulouse fc": 289,
    "cucuta": 14645,
    "cúcuta": 14645,
    "cucuta deportivo": 14645,
    "cúcuta deportivo": 14645,
    "cucuta deportiva": 14645,
    "cúcuta deportiva": 14645,
    "tolima": 10204,
    "deportes tolima": 10204,
    "fortaleza": 3621,
    "fortaleza ce": 3621,
    "fortaleza ec": 3621,
    "operario": 14710,
    "operario pr": 14710,
    "operário": 14710,
    "operário pr": 14710,
    "operario ferroviario": 14710,
    "operário ferroviário": 14710,
    "sport boys": 15644,
    "sport boys association": 15644,
    "sporting cristal": 10661,
    "soprting cristal": 10661,
    "river plate": 10002,
    "river": 10002,
    "flamengo": 1024,
    "flamengo rj": 1024,
    "cr flamengo": 1024,
    "bragantino": 7808,
    "bragantino sp": 7808,
    "red bull bragantino": 7808,
    "rb bragantino": 7808,
    "santa fe": 12506,
    "independiente santa fe": 12506,
    "union santa fe": 7228,
    "barcelona": 83,
    "liverpool": 8,
    "arsenal": 19,
    "chelsea": 18,
    "chelsea fc": 18,
    "brighton": 78,
    "brighton & hove albion": 78,
    "brighton and hove albion": 78,
    "swansea": 30,
    "swansea city": 30,
    "atletico madrid": 7980,
    "atletico de madrid": 7980,
    "atlético madrid": 7980,
    "atlético de madrid": 7980,
    "atletico": 7980,
    "sevilla": 676,
    "sevilla fc": 676,
    "los sevilla": 676,
    "los sevilla fc": 676,
    "fulham": 11,
    "club america": 2687,
    "club américa": 2687,
    "america": 2687,
    "columbus crew": 577,
    "real madrid": 3468,
    "rela madrid": 3468,
    "real madrid cf": 3468,
    "elche": 1099,
    "elche cf": 1099,
    "elche fc": 1099,
    "corinthians": 303,
    "corinthians sp": 303,
    "sc corinthians": 303,
    "sc corinthians paulista": 303,
    "corinthians paulista": 303,
    "estudiantes": 9335,
    "estudiantes de la plata": 9335,
    "estudiantes lp": 9335,
    "flamengo": 1024,
    "flamengo rj": 1024,
    "independiente del valle": 14635,
    "independinete del valle": 14635,
    "idv": 14635,
    "independiente medellin": 332,
    "independiente medellín": 332,
    "medellin": 332,
    "medellín": 332,
    "dim": 332,
    "independiente de medellin": 332,
    "independiente de medellín": 332,
    "independiente": 10840,
    "independiente avellaneda": 10840,
    "independiente de avellaneda": 10840,
    "independiente rivadavia": 812,
    "jaguares de cordoba": 12488,
    "jaguares de córdoba": 12488,
    "jaguares": 12488,
    "asociacion deportiva de tarma": 239392,
    "asociacion deportiva tarma": 239392,
    "asociación deportiva de tarma": 239392,
    "asociación deportiva tarma": 239392,
    "ad tarma": 239392,
    "tarma": 239392,
    "adt": 239392,
    "adt tarma": 239392,
    "cienciano": 13264,
    "club cienciano": 13264,
    "club cienciano del cusco": 13264,
    "cienciano del cusco": 13264,
}


TEAM_SEARCH_PAGE_SIZE = 50
MAIN_REFEREE_TYPE = 6  # Sportmonks: 6 árbitro principal, 7-8 asistentes, 9 cuarto árbitro


class SportmonksClient:
    """Adaptador Sportmonks v3 al contrato interno usado por DEPORT AI."""

    provider_label = "Sportmonks"

    def __init__(
        self,
        api_token: str,
        timeout: float = 20,
        timezone: str = "America/Lima",
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.api_token = api_token
        self.timeout = timeout
        self.timezone = timezone
        self.base_url = base_url.rstrip("/")
        self.max_season = datetime.now().year
        self.requests_used = 0
        self.requests_remaining: int | None = None
        self._cache: dict[str, Any] = {}
        self._raw_fixtures: dict[int, dict[str, Any]] = {}
        self._fixtures: dict[int, dict[str, Any]] = {}
        self._plan_capabilities: dict[str, bool] = {}
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "DEPORT-AI/0.1"})

    def _get(self, path: str, **params: Any) -> Any:
        clean = {key: value for key, value in params.items() if value is not None}
        cache_key = path + "?" + json.dumps(clean, sort_keys=True, default=str)
        if cache_key in self._cache:
            return self._cache[cache_key]
        request_params = {**clean, "timezone": self.timezone}
        if self.api_token and self.api_token != PROXY_INJECTED_TOKEN:
            request_params["api_token"] = self.api_token
        # Con PROXY_INJECTED_TOKEN el token lo añade un proxy (encabezado Authorization),
        # así que no se envía en la URL.
        response = None
        for attempt in range(3):
            try:
                response = self.session.get(
                    f"{self.base_url}/{path.lstrip('/')}",
                    params=request_params,
                    timeout=self.timeout,
                )
                break
            except requests.RequestException as exc:
                if attempt == 2:
                    raise APIError(f"No se pudo conectar con Sportmonks: {exc}") from exc
                time.sleep(1.0 * (attempt + 1))
        self.requests_used += 1
        try:
            payload = response.json()
        except ValueError as exc:
            raise APIError(f"Sportmonks devolvió una respuesta inválida ({response.status_code}).") from exc
        rate = payload.get("rate_limit") or {}
        if rate.get("remaining") is not None:
            self.requests_remaining = int(rate["remaining"])
        if response.status_code in {401, 403}:
            message = payload.get("message") or "Token inválido o función fuera del plan."
            raise APIError(f"Sportmonks rechazó la consulta: {message}")
        if response.status_code == 429:
            raise APIError("Se alcanzó el límite temporal de Sportmonks.")
        if response.status_code >= 400:
            raise APIError(payload.get("message") or f"Error HTTP {response.status_code} de Sportmonks.")
        data = payload.get("data", [])
        self._cache[cache_key] = data
        return data

    def resolve_team(self, query: str) -> Team:
        return self._resolve_team(query)[0]

    def _search_has_exact_name(self, query: str) -> bool:
        try:
            rows = self._get(f"teams/search/{quote(query, safe='')}", per_page=TEAM_SEARCH_PAGE_SIZE) or []
        except Exception:
            return False
        target = _normalize(query)
        return any(_normalize(str(row.get("name") or "")) == target for row in rows)

    def _resolve_team(self, query: str) -> tuple[Team, list[Team]]:
        """Equipo elegido y, si hubo homónimos exactos, los equipos empatados con él."""
        cleaned = re.sub(r"\s+", " ", query).strip()
        norm = _normalize(cleaned)
        override_id = TEAM_ID_OVERRIDES.get(norm)
        if not override_id:
            close = get_close_matches(norm, TEAM_ID_OVERRIDES.keys(), n=1, cutoff=0.88)
            # Una coincidencia aproximada con la lista de alias no debe ganarle a un equipo
            # que Sportmonks tiene con ese nombre exacto ("Internacional" no es "Internazionale").
            if close and not self._search_has_exact_name(cleaned):
                override_id = TEAM_ID_OVERRIDES[close[0]]
        if override_id:
            try:
                team_data = self._get(f"teams/{override_id}")
                if team_data:
                    return Team(override_id, team_data.get("name", cleaned), str(team_data.get("country_id") or "")), []
            except Exception:
                pass
        effective_query = TEAM_ALIASES.get(norm, cleaned)
        rows = self._get(f"teams/search/{quote(effective_query, safe='')}", per_page=TEAM_SEARCH_PAGE_SIZE)
        if not rows and effective_query != cleaned:
            rows = self._get(f"teams/search/{quote(cleaned, safe='')}", per_page=TEAM_SEARCH_PAGE_SIZE)
        if not rows:
            stripped = re.sub(r"\b(fc|cf|afc|sc|cd|fk|ec|ac|ca|club|calcio|sp|rj|mg|rs|pr|ba|go)\b", "", cleaned, flags=re.IGNORECASE).strip()
            stripped = re.sub(r"\s+", " ", stripped).strip()
            if stripped and stripped.lower() != cleaned.lower():
                stripped_norm = _normalize(stripped)
                if stripped_norm in TEAM_ID_OVERRIDES:
                    override_id = TEAM_ID_OVERRIDES[stripped_norm]
                else:
                    close_stripped = get_close_matches(stripped_norm, TEAM_ID_OVERRIDES.keys(), n=1, cutoff=0.88)
                    if close_stripped:
                        override_id = TEAM_ID_OVERRIDES[close_stripped[0]]
                if override_id:
                    try:
                        team_data = self._get(f"teams/{override_id}")
                        if team_data:
                            return Team(override_id, team_data.get("name", cleaned), str(team_data.get("country_id") or "")), []
                    except Exception:
                        pass
                effective_stripped = TEAM_ALIASES.get(stripped_norm, stripped)
                rows = self._get(f"teams/search/{quote(effective_stripped, safe='')}", per_page=TEAM_SEARCH_PAGE_SIZE)
        if not rows:
            raise TeamNotFoundError(f"No encontré el equipo '{cleaned}' en Sportmonks.")
        if override_id:
            for row in rows:
                if int(row.get("id", -1)) == override_id:
                    return Team(override_id, row.get("name", cleaned), str(row.get("country_id") or "")), []
        ranked = _rank_team_rows(cleaned, effective_query, rows)
        best_score, best = ranked[0]
        if best_score < 0.48:
            raise TeamNotFoundError(f"No pude identificar con seguridad '{cleaned}'.")
        if len(ranked) > 1:
            second_score, second = ranked[1]
            if best_score < 0.94 and best_score - second_score < 0.035:
                raise AmbiguousTeamError(
                    f"'{cleaned}' es ambiguo: {best.name} o {second.name}. "
                    "Escribe el país o el nombre completo.",
                    candidates=[team for score, team in ranked if best_score - score < 0.035][:3],
                )
        # Homónimos exactos (p. ej. dos "Nacional"): se conserva el primero, pero se
        # informan los empatados para que resolve_match pueda desempatar por calendario.
        ties = [team for score, team in ranked[1:] if score >= 1.0] if best_score >= 1.0 else []
        return best, ties

    def resolve_match(self, first_query: str, second_query: str) -> tuple[Team, Team]:
        """Resuelve ambos equipos; si uno es ambiguo, desempata con el partido programado.

        Cuando un nombre admite varios equipos, se busca cuál de los candidatos tiene un
        partido próximo contra el otro equipo. Si exactamente uno lo tiene, se elige ese.
        """
        first = second = None
        first_ties: list[Team] = []
        second_ties: list[Team] = []
        first_error = second_error = None
        try:
            first, first_ties = self._resolve_team(first_query)
        except AmbiguousTeamError as exc:
            first_error = exc
        try:
            second, second_ties = self._resolve_team(second_query)
        except AmbiguousTeamError as exc:
            second_error = exc
        if first_error and second_error:
            raise first_error
        if first_error:
            first = self._pick_by_fixture(first_error.candidates, second, error=first_error)
        elif first_ties:
            first = self._pick_by_fixture([first, *first_ties], second, default=first)
        if second_error:
            second = self._pick_by_fixture(second_error.candidates, first, error=second_error)
        elif second_ties:
            second = self._pick_by_fixture([second, *second_ties], first, default=second)
        return first, second

    def _pick_by_fixture(
        self,
        candidates: list[Team],
        rival: Team,
        error: AmbiguousTeamError | None = None,
        default: Team | None = None,
    ) -> Team:
        with_fixture = []
        for candidate in candidates:
            try:
                if self.upcoming_between(candidate.id, rival.id):
                    with_fixture.append(candidate)
            except Exception:
                continue
        if len(with_fixture) == 1:
            return with_fixture[0]
        if default is not None:
            return default
        raise error

    def recent_fixtures(self, team_id: int, count: int) -> list[dict[str, Any]]:
        completed: list[dict[str, Any]] = []
        end = date.today()
        for _ in range(8):
            start = end - timedelta(days=99)
            rows = self._get(
                f"fixtures/between/{start.isoformat()}/{end.isoformat()}/{team_id}",
                include=FIXTURE_INCLUDES,
                order="desc",
                per_page=50,
            )
            converted = self._remember_many(rows)
            completed.extend(row for row in converted if _status(row) in FINISHED_STATUSES)
            if len(completed) >= count:
                break
            end = start - timedelta(days=1)
        unique = {int(row["fixture"]["id"]): row for row in completed}
        result = list(unique.values())
        result.sort(key=lambda row: int(row["fixture"].get("timestamp") or 0), reverse=True)
        return result[:count]

    def upcoming_between(self, first_id: int, second_id: int) -> dict[str, Any] | None:
        start = date.today()
        end = start + timedelta(days=99)
        rows = self._get(
            f"fixtures/between/{start.isoformat()}/{end.isoformat()}/{first_id}",
            include=FIXTURE_INCLUDES,
            order="asc",
            per_page=50,
        )
        candidates = [
            row
            for row in rows
            if second_id in {int(p.get("id", -1)) for p in row.get("participants", [])}
            and _sportmonks_status(row) not in FINISHED_STATUSES
        ]
        candidates.sort(key=lambda row: int(row.get("starting_at_timestamp") or 0))
        if not candidates:
            return None
        return self._remember(candidates[0])

    def h2h(self, first_id: int, second_id: int, count: int) -> list[dict[str, Any]]:
        rows = self._get(
            f"fixtures/head-to-head/{first_id}/{second_id}",
            include="participants;scores;league;season;state",
            order="desc",
            per_page=min(50, max(count, 10)),
        )
        converted = [self._remember(row) for row in rows]
        completed = [row for row in converted if _status(row) in FINISHED_STATUSES]
        completed.sort(key=lambda row: int(row["fixture"].get("timestamp") or 0), reverse=True)
        return completed[:count]

    def fixture_details(self, fixture_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for fixture_id in dict.fromkeys(int(value) for value in fixture_ids):
            if fixture_id not in self._fixtures or not self._fixtures[fixture_id].get("statistics"):
                try:
                    raw = self._get(f"fixtures/{fixture_id}", include=DETAIL_INCLUDES)
                    self._remember(raw)
                except Exception:
                    try:
                        raw = self._get(f"fixtures/{fixture_id}", include="participants;scores;statistics.type")
                        self._remember(raw)
                    except Exception:
                        pass
            if fixture_id in self._fixtures:
                result[fixture_id] = self._fixtures[fixture_id]
        return result

    def fixture_referee(self, fixture_id: int | None) -> dict[str, Any] | None:
        """Árbitro principal asignado al partido (tipo 6 de Sportmonks) y la temporada."""
        if not fixture_id:
            return None
        try:
            raw = self._get(f"fixtures/{fixture_id}", include="referees")
        except Exception:
            return None
        for row in (raw or {}).get("referees") or []:
            if int(row.get("type_id") or -1) == MAIN_REFEREE_TYPE and row.get("referee_id"):
                return {"referee_id": int(row["referee_id"]), "season_id": (raw or {}).get("season_id")}
        return None

    def referee_card_rate(self, referee_id: int, exclude_season: int | None = None) -> tuple[float, int] | None:
        """Tarjetas a jugadores (amarillas + rojas) por partido del árbitro y partidos dirigidos.

        Suma todas sus temporadas registradas; `exclude_season` permite medir sin la
        temporada del partido evaluado (backtest sin mirar el futuro).
        """
        try:
            raw = self._get(f"referees/{referee_id}", include="statistics.details.type")
        except Exception:
            return None
        cards = 0.0
        matches = 0
        for season in (raw or {}).get("statistics") or []:
            if exclude_season is not None and season.get("season_id") == exclude_season:
                continue
            details = {
                (item.get("type") or {}).get("developer_name"): item.get("value") or {}
                for item in season.get("details") or []
            }
            played = int((details.get("MATCHES") or {}).get("count") or 0)
            if played <= 0:
                continue
            for key in ("YELLOWCARDS", "REDCARDS"):
                block = (details.get(key) or {}).get("all") or {}
                cards += float(block.get("on_pitch", block.get("count")) or 0)
            matches += played
        if matches <= 0:
            return None
        return round(cards / matches, 3), matches

    def first_half_corners(self, fixture_id: int) -> dict[int, int] | None:
        """Córners del primer tiempo por equipo (id -> córners), desde las estadísticas por periodo."""
        try:
            raw = self._get(f"fixtures/{fixture_id}", include="periods.statistics.type")
        except Exception:
            return None
        for period in (raw or {}).get("periods") or []:
            if str(period.get("description") or "").lower() not in {"1st-half", "1st half", "first half"}:
                continue
            corners: dict[int, int] = {}
            for row in period.get("statistics") or []:
                if (row.get("type") or {}).get("developer_name") != "CORNERS":
                    continue
                value = (row.get("data") or {}).get("value")
                if row.get("participant_id") is not None and value is not None:
                    corners[int(row["participant_id"])] = int(value)
            return corners or None
        return None

    def coverage(self, league_id: int, season: int) -> dict[str, Any]:
        """Verifica dinámicamente qué características están soportadas por plan y liga."""
        return {
            "fixtures": {
                "lineups": self._plan_capabilities.get("lineups", True),
                "statistics_fixtures": True,
                "statistics_players": True,
            },
            "injuries": self._plan_capabilities.get("injuries", True),
            "odds": self._plan_capabilities.get("odds", True),
        }

    def team_season_statistics(self, team_id: int, league_id: int, season: int) -> dict[str, Any]:
        """Extrae estadísticas consolidadas de la temporada para el prior macro Bayesiano."""
        cache_key = f"season_stats_{team_id}_{league_id}_{season}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            raw = self._get(f"teams/{team_id}", include="statistics.details;seasons")
            # Extraer promedios oficiales si existen en la respuesta
            stats = raw.get("statistics", []) if isinstance(raw, dict) else []
            if stats:
                parsed = self._parse_season_stats(stats)
                if parsed:
                    self._cache[cache_key] = parsed
                    return parsed
        except Exception:
            pass

        # Fallback de alta precisión: calcular macro de temporada a partir de fixtures de la temporada
        season_matches = [
            m for m in self._fixtures.values()
            if int(m.get("league_id") or (m.get("league") or {}).get("id") or -1) == league_id
            and (int((m.get("season") or {}).get("id") or m.get("season_id") or -1) == season or not season)
        ]
        if season_matches:
            parsed = self._aggregate_season_matches(season_matches, team_id)
            self._cache[cache_key] = parsed
            return parsed

        return {}

    def _parse_season_stats(self, stats: list[dict[str, Any]]) -> dict[str, Any]:
        goals_for_home, goals_for_away = None, None
        goals_ag_home, goals_ag_away = None, None
        for item in stats:
            name = str(item.get("type", {}).get("name") or "").lower()
            val = item.get("value", {})
            if "goals scored" in name or "goals for" in name:
                goals_for_home = _number(val.get("home"))
                goals_for_away = _number(val.get("away"))
            elif "goals conceded" in name or "goals against" in name:
                goals_ag_home = _number(val.get("home"))
                goals_ag_away = _number(val.get("away"))
        if goals_for_home is not None and goals_ag_home is not None:
            return {
                "goals": {
                    "for": {"average": {"home": goals_for_home, "away": goals_for_away or goals_for_home}},
                    "against": {"average": {"home": goals_ag_home, "away": goals_ag_away or goals_ag_home}},
                }
            }
        return {}

    def _aggregate_season_matches(self, matches: list[dict[str, Any]], team_id: int) -> dict[str, Any]:
        home_gf, home_ga, away_gf, away_ga = [], [], [], []
        for m in matches:
            teams = m.get("teams", {})
            goals = m.get("goals", {})
            h_id = int(teams.get("home", {}).get("id", -1))
            a_id = int(teams.get("away", {}).get("id", -1))
            hg = _number(goals.get("home"))
            ag = _number(goals.get("away"))
            if hg is None or ag is None:
                continue
            if h_id == team_id:
                home_gf.append(hg)
                home_ga.append(ag)
            elif a_id == team_id:
                away_gf.append(ag)
                away_ga.append(hg)
        
        h_gf_avg = fmean(home_gf) if home_gf else None
        h_ga_avg = fmean(home_ga) if home_ga else None
        a_gf_avg = fmean(away_gf) if away_gf else None
        a_ga_avg = fmean(away_ga) if away_ga else None

        if h_gf_avg is not None and h_ga_avg is not None:
            return {
                "goals": {
                    "for": {"average": {"home": h_gf_avg, "away": a_gf_avg or h_gf_avg}},
                    "against": {"average": {"home": h_ga_avg, "away": a_ga_avg or h_ga_avg}},
                },
                "matches_played": len(home_gf) + len(away_gf),
            }
        return {}

    def injuries(self, fixture_id: int | None) -> list[dict[str, Any]]:
        if not fixture_id:
            return []
        raw = self._raw_fixtures.get(fixture_id)
        if raw is None or "sidelined" not in raw:
            try:
                raw = self._get(f"fixtures/{fixture_id}", include="participants;sidelined.sideline")
                self._remember(raw)
                self._plan_capabilities["injuries"] = True
            except APIError as exc:
                if "fuera del plan" in str(exc).lower() or "403" in str(exc):
                    self._plan_capabilities["injuries"] = False
                return []
        teams = {int(item["id"]): item.get("name") for item in raw.get("participants", [])}
        result: list[dict[str, Any]] = []
        for item in raw.get("sidelined", []) or []:
            sideline = item.get("sideline") or {}
            result.append(
                {
                    "player": {
                        "name": item.get("player_name") or sideline.get("name") or "No informado",
                        "type": sideline.get("category") or sideline.get("name") or "Baja",
                        "reason": sideline.get("description") or sideline.get("name") or "No informado",
                    },
                    "team": {"name": teams.get(int(item.get("team_id") or -1), "No informado")},
                }
            )
        return result

    def lineups(self, fixture_id: int | None) -> list[dict[str, Any]]:
        if not fixture_id:
            return []
        raw = self._raw_fixtures.get(fixture_id)
        if raw is None or "lineups" not in raw:
            try:
                raw = self._get(f"fixtures/{fixture_id}", include="participants;lineups;formations")
                self._remember(raw)
                self._plan_capabilities["lineups"] = True
            except APIError as exc:
                if "fuera del plan" in str(exc).lower() or "403" in str(exc):
                    self._plan_capabilities["lineups"] = False
                return []
        teams = {int(item["id"]): item.get("name") for item in raw.get("participants", [])}
        formations = {
            int(item["participant_id"]): item.get("formation")
            for item in raw.get("formations", []) or []
            if item.get("participant_id") is not None
        }
        starters: dict[int, list[dict[str, Any]]] = {}
        for item in raw.get("lineups", []) or []:
            if int(item.get("type_id") or -1) != 11:
                continue
            team_id = int(item.get("team_id") or -1)
            starters.setdefault(team_id, []).append(
                {"player": {"id": item.get("player_id"), "name": item.get("player_name")}}
            )
        return [
            {
                "team": {"id": team_id, "name": teams.get(team_id, "No informado")},
                "formation": formations.get(team_id),
                "startXI": players,
            }
            for team_id, players in starters.items()
        ]

    def odds(self, fixture_id: int | None) -> list[dict[str, Any]]:
        if not fixture_id:
            return []
        raw = self._raw_fixtures.get(fixture_id)
        if raw is not None and "odds" in raw and raw["odds"]:
            return raw["odds"]
        try:
            data = self._get(f"odds/pre-match/fixtures/{fixture_id}") or []
            self._plan_capabilities["odds"] = True
            return data
        except APIError as exc:
            if "fuera del plan" in str(exc).lower() or "403" in str(exc):
                self._plan_capabilities["odds"] = False
            return []
        except Exception:
            return []

    def _remember_many(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._remember(row) for row in rows]

    def _remember(self, raw: dict[str, Any]) -> dict[str, Any]:
        fixture_id = int(raw["id"])
        self._raw_fixtures[fixture_id] = raw
        converted = _convert_fixture(raw, self.timezone)
        self._fixtures[fixture_id] = converted
        return converted


def _convert_fixture(raw: dict[str, Any], timezone_name: str = "UTC") -> dict[str, Any]:
    participants = raw.get("participants", []) or []
    home_raw = next((p for p in participants if (p.get("meta") or {}).get("location") == "home"), {})
    away_raw = next((p for p in participants if (p.get("meta") or {}).get("location") == "away"), {})
    home_id = int(home_raw.get("id") or -1)
    away_id = int(away_raw.get("id") or -1)
    league = raw.get("league") or {}
    season = raw.get("season") or {}
    starting_at = raw.get("starting_at") or ""
    return {
        "fixture": {
            "id": int(raw["id"]),
            "date": _iso_date(starting_at, timezone_name),
            "timestamp": int(raw.get("starting_at_timestamp") or 0),
            "status": {"short": _sportmonks_status(raw)},
        },
        "league": {
            "id": raw.get("league_id"),
            "name": league.get("name"),
            "season": _season_year(season, starting_at),
        },
        "teams": {
            "home": {"id": home_id, "name": home_raw.get("name", "Local")},
            "away": {"id": away_id, "name": away_raw.get("name", "Visitante")},
        },
        "goals": {
            "home": _current_score(raw.get("scores", []), home_id),
            "away": _current_score(raw.get("scores", []), away_id),
        },
        "halftime": {
            "home": _period_score(raw.get("scores", []), home_id, "1ST_HALF"),
            "away": _period_score(raw.get("scores", []), away_id, "1ST_HALF"),
        },
        # En Sportmonks "2ND_HALF" es el marcador acumulado; solo el 2T es "2ND_HALF_ONLY".
        "second_half": {
            "home": _period_score(raw.get("scores", []), home_id, "2ND_HALF_ONLY"),
            "away": _period_score(raw.get("scores", []), away_id, "2ND_HALF_ONLY"),
        },
        "statistics": _convert_statistics(raw.get("statistics", []), participants),
        "players": _convert_players(raw.get("lineups", []), participants),
    }


def _convert_statistics(
    rows: list[dict[str, Any]], participants: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    names = {int(item["id"]): item.get("name") for item in participants}
    mapped_names = {
        "CORNERS": "Corner Kicks",
        "SHOTS_TOTAL": "Total Shots",
        "SHOTS_ON_TARGET": "Shots on Goal",
        "HIT_WOODWORK": "Hit Woodwork",
        "WOODWORK": "Hit Woodwork",
        "EXPECTED_GOALS": "Expected Goals",
        "XG": "Expected Goals",
        "X_G": "Expected Goals",
        "BALL_POSSESSION": "Ball Possession",
        "YELLOWCARDS": "Yellow Cards",
        "YELLOW_CARDS": "Yellow Cards",
        "REDCARDS": "Red Cards",
        "RED_CARDS": "Red Cards",
        "OFFSIDES": "Offsides",
        "OFFSIDE": "Offsides",
        "OFF_SIDES": "Offsides",
        "FOULS": "Fouls",
        "FOULS_COMMITTED": "Fouls",
        "FOULS_TOTAL": "Fouls",
    }
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows or []:
        team_id = row.get("participant_id")
        developer_name = (row.get("type") or {}).get("developer_name")
        mapped = mapped_names.get(str(developer_name))
        value = (row.get("data") or {}).get("value")
        if team_id is None or not mapped or value is None:
            continue
        grouped.setdefault(int(team_id), []).append({"type": mapped, "value": value})
    return [
        {"team": {"id": team_id, "name": names.get(team_id)}, "statistics": stats}
        for team_id, stats in grouped.items()
    ]


def _convert_players(
    rows: list[dict[str, Any]], participants: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    names = {int(item["id"]): item.get("name") for item in participants}
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows or []:
        team_id = int(row.get("team_id") or -1)
        details = {
            (item.get("type") or {}).get("developer_name"): (item.get("data") or {}).get("value")
            for item in row.get("details", []) or []
        }
        minutes = details.get("MINUTES_PLAYED")
        if minutes is None:
            continue
        total_shots = (
            details.get("SHOTS_TOTAL")
            or details.get("TOTAL_SHOTS")
            or details.get("SHOTS")
            or details.get("SHOTS_ON_TARGET")
            or 0
        )
        shots_on = details.get("SHOTS_ON_TARGET") or 0
        goals_val = details.get("GOALS") or details.get("GOALS_SCORED") or details.get("GOALS_TOTAL") or 0
        grouped.setdefault(team_id, []).append(
            {
                "player": {"id": row.get("player_id"), "name": row.get("player_name")},
                "statistics": [
                    {
                        "games": {"minutes": minutes},
                        "shots": {"on": shots_on, "total": total_shots},
                        "goals": {"total": goals_val},
                    }
                ],
            }
        )
    return [
        {"team": {"id": team_id, "name": names.get(team_id)}, "players": players}
        for team_id, players in grouped.items()
    ]


def _current_score(scores: list[dict[str, Any]], participant_id: int) -> int | None:
    priorities = ("CURRENT", "EXTRA_TIME", "PENALTIES", "2ND_HALF", "1ST_HALF")
    by_description = {
        row.get("description"): (row.get("score") or {}).get("goals")
        for row in scores or []
        if int(row.get("participant_id") or -1) == participant_id
    }
    for description in priorities:
        if by_description.get(description) is not None:
            return int(by_description[description])
    return None


def _period_score(scores: list[dict[str, Any]], participant_id: int, description: str) -> int | None:
    for row in scores or []:
        if int(row.get("participant_id") or -1) == participant_id and row.get("description") == description:
            goals = (row.get("score") or {}).get("goals")
            return int(goals) if goals is not None else None
    return None


def _sportmonks_status(raw: dict[str, Any]) -> str:
    value = str((raw.get("state") or {}).get("developer_name") or "").upper()
    if value in {"FT", "AET", "PEN"}:
        return value
    if "PEN" in value:
        return "PEN"
    if "EXTRA" in value or value == "AET":
        return "AET"
    if "FINISH" in value or value in {"ENDED", "AFTER_FULL_TIME"}:
        return "FT"
    if value in {"NS", "POSTPONED", "CANCELLED"}:
        return value
    if value.startswith("INPLAY"):
        return "1H" if "1ST" in value else "2H"
    return value or "NS"


def _status(row: dict[str, Any]) -> str:
    return row.get("fixture", {}).get("status", {}).get("short", "")


def _season_year(season: dict[str, Any], starting_at: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", str(season.get("name") or ""))
    if match:
        return int(match.group(1))
    match = re.match(r"(20\d{2})", starting_at)
    return int(match.group(1)) if match else None


def _iso_date(value: str, timezone_name: str) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.isoformat()


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _name_score(query: str, candidate: str) -> float:
    left, right = _normalize(query), _normalize(candidate)
    if left == right:
        return 1.0
    if right in {f"fc {left}", f"{left} fc", f"cf {left}", f"{left} cf"}:
        return 0.98
    sequence = SequenceMatcher(None, left, right).ratio()
    # Contención solo por palabras completas: "russia" está en "russia u21" pero no en
    # "borussia dortmund"; "iran" no está en "mirandela" ni en "partizani tirana".
    left_tokens, right_tokens = left.split(), right.split()
    containment = 0.93 if left_tokens and right_tokens and (
        _contains_tokens(right_tokens, left_tokens) or _contains_tokens(left_tokens, right_tokens)
    ) else 0.0
    overlap = len(set(left_tokens) & set(right_tokens)) / max(1, len(set(left_tokens) | set(right_tokens)))
    return max(sequence, containment, overlap)


def _contains_tokens(haystack: list[str], needle: list[str]) -> bool:
    """True si `needle` aparece como secuencia contigua de palabras completas en `haystack`."""
    size = len(needle)
    return any(haystack[i : i + size] == needle for i in range(len(haystack) - size + 1))


# Marcadores de equipos juveniles, filiales o femeninos: no deben ganarle al equipo
# absoluto salvo que el usuario los escriba.
_SECONDARY_TEAM_TOKENS = frozenset(
    {"u15", "u16", "u17", "u18", "u19", "u20", "u21", "u22", "u23", "ii", "iii", "b", "reserves", "reservas", "women", "w", "femenino", "feminino"}
)
_SECONDARY_PENALTY = 0.06


def _rank_team_rows(cleaned: str, effective_query: str, rows: list[dict[str, Any]]) -> list[tuple[float, Team]]:
    """Ordena los resultados de búsqueda de Sportmonks por afinidad con el nombre pedido.

    1. Un nombre idéntico (normalizado) a lo escrito gana directamente.
    2. Los equipos juveniles/filiales se penalizan si el usuario no los pidió.
    3. Ante igualdad, la selección nacional precede a un club (p. ej. "Venezuela").
    """
    query_tokens = set(_normalize(cleaned).split()) | set(_normalize(effective_query).split())
    ranked: list[tuple[float, int, Team]] = []
    for row in rows:
        name = row.get("name", "") or ""
        score = max(_name_score(cleaned, name), _name_score(effective_query, name))
        secondary = (set(_normalize(name).split()) & _SECONDARY_TEAM_TOKENS) - query_tokens
        if secondary and score < 1.0:
            score -= _SECONDARY_PENALTY
        national = 1 if str(row.get("type") or "").lower() == "national" else 0
        ranked.append((round(score, 4), national, Team(int(row["id"]), name or cleaned, str(row.get("country_id") or ""))))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

    exact = [item for item in ranked if item[0] >= 1.0]
    if len(exact) > 1:
        nationals = [item for item in exact if item[1] == 1]
        if len(nationals) == 1:
            # Varios equipos con el mismo nombre: la selección absoluta va primero
            # y el resto se separa para que no se declare ambigüedad.
            others = [(score - 0.05, nat, team) for score, nat, team in ranked if team.id != nationals[0][2].id]
            return [(nationals[0][0], nationals[0][2])] + [(score, team) for score, _, team in others]
    return [(score, team) for score, _, team in ranked]
