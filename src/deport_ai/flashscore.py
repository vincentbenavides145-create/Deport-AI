"""Goles esperados (xG) de Flashscore a través de Firecrawl.

El plan de Sportmonks no incluye xG. Flashscore sí lo publica en la pestaña de
estadísticas de cada partido. Este módulo:

1. Descarga (renderizada por Firecrawl) la lista de resultados de una temporada.
2. Empareja cada partido de Sportmonks con su fila de Flashscore por fecha
   (±1 día), marcador exacto y parecido de los nombres de ambos equipos.
3. Lee la pestaña de estadísticas y guarda xG, xGOT, xA, toques en el área y
   ocasiones claras.
4. Guarda todo en ``history/flashscore_xg.json`` (dentro del repositorio) para no
   volver a gastar créditos: cada partido terminado se lee una sola vez.

Las cifras se inyectan en ``TeamMatch.stats_for/against["expected_goals"]``, la
clave que el modelo de goles ya sabe mezclar con los goles reales.
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable

from .domain import TeamMatch

FIRECRAWL_URL = "https://api.firecrawl.dev/v2"
FLASHSCORE_BASE = "https://www.flashscore.com"
DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "history" / "flashscore_xg.json"
XG_KEY = "expected_goals"

# league_id de Sportmonks -> (ruta de Flashscore, tipo de temporada).
# "split": temporada agosto-mayo (2025-2026); "calendar": año natural (2026).
FLASHSCORE_LEAGUES: dict[int, tuple[str, str]] = {
    944: ("saudi-arabia/saudi-professional-league", "split"),
    72: ("netherlands/eredivisie", "split"),
    648: ("brazil/serie-a", "calendar"),
    8: ("england/premier-league", "split"),
    564: ("spain/laliga", "split"),
    384: ("italy/serie-a", "split"),
    82: ("germany/bundesliga", "split"),
    301: ("france/ligue-1", "split"),
    462: ("portugal/liga-portugal", "split"),
    208: ("belgium/jupiler-pro-league", "split"),
    600: ("turkey/super-lig", "split"),
    779: ("usa/mls", "calendar"),
    636: ("argentina/liga-profesional", "calendar"),
    959: ("united-arab-emirates/uae-league", "split"),
    743: ("mexico/liga-mx", "split"),
}

# Estadísticas que se leen de la pestaña "Stats" (etiqueta en inglés -> clave).
STAT_LABELS: dict[str, str] = {
    "Expected goals (xG)": "xg",
    "xG on target (xGOT)": "xgot",
    "Expected assists (xA)": "xa",
    "Touches in opposition box": "box_touches",
    "Big chances": "big_chances",
}

# Días tras el partido en los que se deja de buscarlo si no aparece en la lista.
UNMATCHED_GIVE_UP_DAYS = 7
SHOW_MORE_SELECTOR = "div[data-testid='wcl-section-footer'] button"
SHOW_MORE_MARKER = 'data-testid="wcl-section-footer"'
# Clics acumulados que se prueban (cada intento es 1 crédito de Firecrawl).
SHOW_MORE_STEPS = (0, 1, 2, 3, 5, 7, 10)
NAME_STOPWORDS = {
    "fc", "sc", "cf", "club", "ac", "afc", "sv", "bv", "de", "the", "cd", "ec", "se",
    "fk", "sk", "cr", "ca", "esporte", "clube", "futebol", "saudi", "kv", "vv",
}


# ---------------------------------------------------------------------------
# Cliente Firecrawl
# ---------------------------------------------------------------------------


class FirecrawlError(RuntimeError):
    pass


class FirecrawlFetcher:
    """Llamadas mínimas a la API REST de Firecrawl (scrape y batch scrape).

    La clave se lee de ``FIRECRAWL_API_KEY``. En las sesiones en la nube el proxy
    la inyecta, así que basta un valor de relleno.
    """

    def __init__(self, api_key: str | None = None, timeout: int = 150, session: Any = None) -> None:
        import requests

        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY") or "proxy-injected"
        self.timeout = timeout
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def scrape(self, url: str, formats: list[str], actions: list[dict[str, Any]] | None = None,
               wait_for: int = 3000) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url, "formats": formats, "onlyMainContent": False, "timeout": 120000}
        if actions:
            body["actions"] = actions
        else:
            body["waitFor"] = wait_for
        response = self.session.post(f"{FIRECRAWL_URL}/scrape", headers=self._headers(), json=body,
                                     timeout=self.timeout)
        payload = response.json() if response.content else {}
        if response.status_code != 200 or not payload.get("success"):
            raise FirecrawlError(f"HTTP {response.status_code}: {payload.get('error') or payload}")
        return payload.get("data") or {}

    def batch_markdown(self, urls: list[str], wait_for: int = 4000, poll_seconds: float = 5.0,
                       max_wait: float = 900.0) -> dict[str, str]:
        """Devuelve {url: markdown} para varias páginas (Firecrawl gestiona la concurrencia)."""
        if not urls:
            return {}
        body = {"urls": urls, "formats": ["markdown"], "waitFor": wait_for, "onlyMainContent": True}
        response = self.session.post(f"{FIRECRAWL_URL}/batch/scrape", headers=self._headers(), json=body,
                                     timeout=self.timeout)
        payload = response.json() if response.content else {}
        if response.status_code != 200 or not payload.get("id"):
            raise FirecrawlError(f"HTTP {response.status_code}: {payload.get('error') or payload}")
        job_id = payload["id"]
        results: dict[str, str] = {}
        started = time.monotonic()
        next_url: str | None = f"{FIRECRAWL_URL}/batch/scrape/{job_id}"
        while True:
            status = self.session.get(next_url, headers=self._headers(), timeout=self.timeout).json()
            if status.get("status") == "completed":
                for item in status.get("data") or []:
                    meta = item.get("metadata") or {}
                    source = meta.get("sourceURL") or meta.get("url")
                    if source:
                        results[source] = item.get("markdown") or ""
                if status.get("next"):
                    next_url = status["next"]
                    continue
                return results
            if status.get("status") == "failed":
                raise FirecrawlError(f"Batch {job_id} falló: {status.get('error')}")
            if time.monotonic() - started > max_wait:
                raise FirecrawlError(f"Batch {job_id} no terminó en {max_wait:.0f} s")
            time.sleep(poll_seconds)


# ---------------------------------------------------------------------------
# Parsers (sin red: se prueban con HTML/markdown guardado)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlashscoreRow:
    mid: str
    url: str
    day: int
    month: int
    year: int | None
    home: str
    away: str
    home_score: int | None
    away_score: int | None


_ROW_RE = re.compile(r'<div id="g_1_([A-Za-z0-9]{8})"[^>]*class="event__match')


def _text(fragment: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def parse_results_html(raw_html: str) -> list[FlashscoreRow]:
    """Filas de la lista de resultados de una temporada."""
    rows: list[FlashscoreRow] = []
    starts = [(m.start(), m.group(1)) for m in _ROW_RE.finditer(raw_html)]
    for index, (start, mid) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else start + 20000
        chunk = raw_html[start:end]
        url_match = re.search(r'href="(https://www\.flashscore\.com/match/football/[^"]+)"', chunk)
        date_match = re.search(r'wcl-dateContent[^>]*>([^<]+)<', chunk) or re.search(
            r'event__time[^>]*>([^<]+)<', chunk
        )
        names = re.findall(r'wcl-name_[^"]*"[^>]*>([^<]+)<', chunk)
        home_score = re.search(r'data-side="home"[^>]*>(\d+)<', chunk)
        away_score = re.search(r'data-side="away"[^>]*>(\d+)<', chunk)
        if not (url_match and date_match and len(names) >= 2):
            continue
        parts = re.match(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{4})?", date_match.group(1))
        if not parts:
            continue
        rows.append(
            FlashscoreRow(
                mid=mid,
                url=html_lib.unescape(url_match.group(1)),
                day=int(parts.group(1)),
                month=int(parts.group(2)),
                year=int(parts.group(3)) if parts.group(3) else None,
                home=html_lib.unescape(names[0]).strip(),
                away=html_lib.unescape(names[1]).strip(),
                home_score=int(home_score.group(1)) if home_score else None,
                away_score=int(away_score.group(1)) if away_score else None,
            )
        )
    return rows


def _number(text: str) -> float | None:
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)", text.replace(",", "."))
    return float(match.group(1)) if match else None


def parse_match_stats(markdown: str) -> dict[str, float] | None:
    """Lee xG y afines de la pestaña de estadísticas. None si el partido no publica xG.

    El formato renderizado es "valor local / etiqueta / valor visitante", una línea cada uno.
    """
    lines = [re.sub(r"^#+\s*", "", line).strip() for line in markdown.splitlines()]
    lines = [line for line in lines if line]
    stats: dict[str, float] = {}
    for index in range(1, len(lines) - 1):
        key = STAT_LABELS.get(lines[index])
        if not key or f"{key}_home" in stats:
            continue
        home, away = _number(lines[index - 1]), _number(lines[index + 1])
        if home is None or away is None:
            continue
        stats[f"{key}_home"] = home
        stats[f"{key}_away"] = away
    if "xg_home" not in stats:
        return None
    return stats


def stats_url(match_url: str) -> str:
    """URL de la pestaña de estadísticas a partir de la URL del partido."""
    base, _, query = match_url.partition("?")
    base = base.rstrip("/")
    return f"{base}/summary/stats/" + (f"?{query}" if query else "")


# ---------------------------------------------------------------------------
# Emparejamiento Sportmonks <-> Flashscore
# ---------------------------------------------------------------------------


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    tokens = [t for t in text.split() if t not in NAME_STOPWORDS]
    return " ".join(tokens) or text.strip()


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if ta <= tb or tb <= ta:
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


def season_label(day: date, season_type: str) -> str:
    if season_type == "calendar":
        return str(day.year)
    start = day.year if day.month >= 7 else day.year - 1
    return f"{start}-{start + 1}"


def _row_dates(row: FlashscoreRow, season: str) -> list[date]:
    years = [row.year] if row.year else sorted({int(y) for y in season.split("-")})
    out: list[date] = []
    for year in years:
        try:
            out.append(date(year, row.month, row.day))
        except ValueError:
            continue
    return out


@dataclass(frozen=True)
class SportmonksFixture:
    fixture_id: int
    date: date
    home: str
    away: str
    home_goals: int
    away_goals: int
    league_id: int | None


def match_fixture(fixture: SportmonksFixture, rows: Iterable[FlashscoreRow], season: str) -> FlashscoreRow | None:
    """Fila de Flashscore del mismo partido: fecha ±1 día, mismo marcador y nombres parecidos."""
    best: tuple[float, FlashscoreRow] | None = None
    tied = False
    for row in rows:
        if not any(abs((d - fixture.date).days) <= 1 for d in _row_dates(row, season)):
            continue
        if (row.home_score, row.away_score) != (fixture.home_goals, fixture.away_goals):
            continue
        sim_home = name_similarity(fixture.home, row.home)
        sim_away = name_similarity(fixture.away, row.away)
        if max(sim_home, sim_away) < 0.75 or sim_home + sim_away < 1.0:
            continue
        score = sim_home + sim_away
        if best is None or score > best[0] + 1e-9:
            best, tied = (score, row), False
        elif abs(score - best[0]) <= 1e-9:
            tied = True
    if best is None or tied:
        return None
    return best[1]


# ---------------------------------------------------------------------------
# Proveedor con caché
# ---------------------------------------------------------------------------


class FlashscoreXG:
    """Obtiene y guarda el xG por partido de Sportmonks (clave: fixture_id)."""

    def __init__(self, fetcher: Any = None, cache_path: Path | str | None = None,
                 log: Callable[[str], None] = lambda _msg: None, today: date | None = None) -> None:
        self.fetcher = fetcher or FirecrawlFetcher()
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self.log = log
        self.today = today or date.today()
        self._listings: dict[tuple[int, str], list[FlashscoreRow]] = {}
        self.cache = self._load()

    # -- caché ---------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                data.setdefault("matches", {})
                return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"version": 1, "matches": {}}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        ordered = {"version": 1, "matches": dict(sorted(self.cache["matches"].items(), key=lambda kv: int(kv[0])))}
        self.cache_path.write_text(json.dumps(ordered, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def get(self, fixture_id: int) -> dict[str, Any] | None:
        entry = self.cache["matches"].get(str(fixture_id))
        return entry if entry and entry.get("xg_home") is not None else None

    # -- listas de resultados ------------------------------------------------
    def _listing_urls(self, league_id: int, season: str) -> list[str]:
        path, _ = FLASHSCORE_LEAGUES[league_id]
        current = season_label(self.today, FLASHSCORE_LEAGUES[league_id][1])
        archive = f"{FLASHSCORE_BASE}/football/{path}-{season}/results/"
        plain = f"{FLASHSCORE_BASE}/football/{path}/results/"
        return [plain, archive] if season == current else [archive]

    def listing(self, league_id: int, season: str) -> list[FlashscoreRow]:
        key = (league_id, season)
        if key in self._listings:
            return self._listings[key]
        rows: list[FlashscoreRow] = []
        for url in self._listing_urls(league_id, season):
            rows = self._read_listing(url)
            if rows:
                self.log(f"  Flashscore {league_id} {season}: {len(rows)} partidos en la lista")
                break
        self._listings[key] = rows
        return rows

    def _read_listing(self, url: str) -> list[FlashscoreRow]:
        """Lista completa: pulsa "mostrar más" mientras exista el botón.

        Firecrawl aborta toda la lectura si un clic no encuentra el botón, así que se
        prueba sin clics y, mientras la página siga mostrando el botón, con más clics.
        """
        best: list[FlashscoreRow] = []
        for clicks in SHOW_MORE_STEPS:
            actions = [{"type": "wait", "milliseconds": 3000}]
            for _ in range(clicks):
                actions += [{"type": "click", "selector": SHOW_MORE_SELECTOR},
                            {"type": "wait", "milliseconds": 2000}]
            try:
                data = self.fetcher.scrape(url, ["rawHtml"], actions=actions)
            except FirecrawlError as exc:
                self.log(f"  Flashscore: {url} ({clicks} clics en 'mostrar más') -> {exc}")
                break  # con este número de clics el botón ya no existe: vale lo leído antes
            raw = data.get("rawHtml") or ""
            rows = parse_results_html(raw)
            if len(rows) > len(best):
                best = rows
            if not rows or SHOW_MORE_MARKER not in raw:
                break
        return best

    # -- proceso principal ---------------------------------------------------
    def fetch(self, fixtures: Iterable[SportmonksFixture], max_new: int | None = None) -> dict[str, int]:
        """Completa la caché para los partidos dados. Devuelve contadores."""
        counts = {"cached": 0, "unsupported": 0, "unmatched": 0, "new": 0, "no_xg": 0}
        pending: dict[str, tuple[SportmonksFixture, FlashscoreRow]] = {}
        gave_up = False
        for fixture in fixtures:
            entry = self.cache["matches"].get(str(fixture.fixture_id))
            if entry is not None:
                counts["cached"] += 1
                continue
            if fixture.league_id not in FLASHSCORE_LEAGUES:
                counts["unsupported"] += 1
                continue
            season = season_label(fixture.date, FLASHSCORE_LEAGUES[fixture.league_id][1])
            row = match_fixture(fixture, self.listing(fixture.league_id, season), season)
            if row is None:
                counts["unmatched"] += 1
                if (self.today - fixture.date).days > UNMATCHED_GIVE_UP_DAYS:
                    # La lista ya es definitiva: no se vuelve a buscar (ahorra créditos).
                    self.cache["matches"][str(fixture.fixture_id)] = {
                        "mid": None, "date": fixture.date.isoformat(), "home": fixture.home,
                        "away": fixture.away, "xg_home": None, "xg_away": None, "unmatched": True,
                    }
                    gave_up = True
                continue
            pending[stats_url(row.url)] = (fixture, row)
        if gave_up and not pending:
            self.save()
        urls = list(pending)
        if max_new is not None:
            urls = urls[:max_new]
        for start in range(0, len(urls), 100):
            chunk = urls[start:start + 100]
            self.log(f"  Flashscore: leyendo estadísticas de {len(chunk)} partidos...")
            pages = self.fetcher.batch_markdown(chunk)
            by_mid = {self._mid(url): md for url, md in pages.items()}
            for url in chunk:
                fixture, row = pending[url]
                markdown = pages.get(url) or by_mid.get(row.mid)
                if markdown is None:
                    continue  # se reintenta en la próxima ejecución
                stats = parse_match_stats(markdown)
                entry: dict[str, Any] = {"mid": row.mid, "date": fixture.date.isoformat(),
                                         "home": fixture.home, "away": fixture.away}
                if stats:
                    entry.update(stats)
                    counts["new"] += 1
                else:
                    entry.update({"xg_home": None, "xg_away": None})
                    counts["no_xg"] += 1
                self.cache["matches"][str(fixture.fixture_id)] = entry
            self.save()
        return counts

    @staticmethod
    def _mid(url: str) -> str | None:
        match = re.search(r"mid=([A-Za-z0-9]{8})", url)
        return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Integración con TeamMatch
# ---------------------------------------------------------------------------


def fixtures_from_matches(matches: Iterable[TeamMatch], team_names: dict[int, str]) -> list[SportmonksFixture]:
    """Partidos únicos (vistos desde el local) a partir de los registros por equipo."""
    seen: dict[int, SportmonksFixture] = {}
    for match in matches:
        if match.fixture_id in seen:
            continue
        home_id, away_id = (match.team_id, match.opponent_id) if match.is_home else (match.opponent_id, match.team_id)
        home_goals, away_goals = (
            (match.goals_for, match.goals_against) if match.is_home else (match.goals_against, match.goals_for)
        )
        own = team_names.get(match.team_id, "")
        other = match.opponent_name or team_names.get(match.opponent_id, "")
        home_name, away_name = (own, other) if match.is_home else (other, own)
        try:
            day = datetime.fromisoformat(match.date.replace("Z", "+00:00")[:19]).date()
        except ValueError:
            continue
        seen[match.fixture_id] = SportmonksFixture(
            match.fixture_id, day, home_name, away_name, home_goals, away_goals, match.league_id
        )
    return list(seen.values())


def attach_xg(matches: list[TeamMatch], provider: FlashscoreXG) -> list[TeamMatch]:
    """Copia de los partidos con ``expected_goals`` a favor y en contra cuando hay xG guardado."""
    out: list[TeamMatch] = []
    for match in matches:
        entry = provider.get(match.fixture_id)
        if entry is None:
            out.append(match)
            continue
        xg_for, xg_against = (
            (entry["xg_home"], entry["xg_away"]) if match.is_home else (entry["xg_away"], entry["xg_home"])
        )
        out.append(
            replace(
                match,
                stats_for={**match.stats_for, XG_KEY: float(xg_for)},
                stats_against={**match.stats_against, XG_KEY: float(xg_against)},
            )
        )
    return out


def strip_xg(matches: list[TeamMatch]) -> list[TeamMatch]:
    """Copia sin xG (para comparar contra el modelo actual)."""
    out: list[TeamMatch] = []
    for match in matches:
        if XG_KEY not in match.stats_for and XG_KEY not in match.stats_against:
            out.append(match)
            continue
        out.append(
            replace(
                match,
                stats_for={k: v for k, v in match.stats_for.items() if k != XG_KEY},
                stats_against={k: v for k, v in match.stats_against.items() if k != XG_KEY},
            )
        )
    return out
