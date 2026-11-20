from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from statistics import fmean, median
from typing import Any, Iterable

from .domain import (
    ConfidenceScore,
    ExpectedMetrics,
    FactorAttribution,
    PlayerShot,
    ProbabilityReport,
    TeamMatch,
)
from .errors import InsufficientDataError
from .model_params import DEFAULT_PARAMETERS, ModelParameters


STAT_KEYS = {
    "Shots on Goal": "shots_on_goal",
    "Total Shots": "total_shots",
    "Hit Woodwork": "hit_woodwork",
    "Corner Kicks": "corner_kicks",
    "Ball Possession": "possession",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Expected Goals": "expected_goals",
    "Offsides": "offsides",
    "Fouls": "fouls",
}


OFFICIAL_LEAGUE_PATTERNS = (
    "premier league",
    "la liga",
    "laliga",
    "serie a",
    "serie b",
    "serie c",
    "bundesliga",
    "ligue 1",
    "ligue 2",
    "eredivisie",
    "primeira liga",
    "liga portugal",
    "brasileir",
    "liga profesional",
    "primera division",
    "primera división",
    "segunda division",
    "segunda división",
    "championship",
    "league one",
    "league two",
    "torneo clausura",
    "torneo apertura",
    "liga betplay",
    "torneo betplay",
    "liga 1",
    "liga 2",
    "liga mx",
    "expansion mx",
    "major league soccer",
    "mls",
    "super lig",
    "super league",
    "pro league",
    "premiership",
    "allsvenskan",
    "eliteserien",
    "superliga",
    "a-league",
    "champions league",
    "europa league",
    "conference league",
    "copa libertadores",
    "copa sudamericana",
    "concacaf",
    "afc champions",
    "caf champions",
    "fifa club world cup",
    "mundial de clubes",
)


def classify_competition(
    league_name: str,
    league_id: int | None = None,
    league_type: str | None = None,
    league_sub_type: str | None = None,
) -> tuple[str, float]:
    """
    Clasificador Zero-Trust Universal de Competiciones.
    - FRIENDLY: 0.20 (Amistosos reconocidos, pretemporada, torneos de exhibición)
    - SUPERCUP: 0.60 (Supercopas oficiales nacionales e internacionales)
    - DOMESTIC_CUP: 0.75 (Copas nacionales oficiales de eliminación directa)
    - OFFICIAL_LEAGUE: 1.00 (Ligas oficiales reconocidas y torneos continentales de élite)
    - UNKNOWN: 0.00 (Competición no verificada; peso 0.0 para no contaminar estadísticas oficiales)
    """
    low = (league_name or "").lower().strip()
    friendly_terms = (
        "friendl", "amistoso", "amical", "preseason", "pre-season", 
        "summer cup", "world club series", "audi cup", "emirates cup", 
        "trofeo joan gamper", "trofeo santiago bernabeu", "international champions cup",
        "torneo de verano", "copa de verano", "challenge cup", "exhibition"
    )
    friendly_ids = {1082, 1101, 1102, 1103, 1104, 1105, 2451, 2452, 2453, 2454, 2455, 2456}

    # 1. Detección de Amistosos / Pretemporada / Exhibición
    if (league_id and int(league_id) in friendly_ids) or any(term in low for term in friendly_terms) or league_sub_type in ("friendly", "friendly_club"):
        return "FRIENDLY", 0.10

    # 2. Supercopas
    supercup_terms = ("supercup", "supercopa", "supercoppa", "super coupe", "recopa", "community shield", "trophée des champions")
    if any(term in low for term in supercup_terms):
        return "SUPERCUP", 0.60

    # 3. Copas Nacionales Oficiales
    cup_terms = ("cup", "copa", "coppa", "coupe", "pokal", "taça", "taca", "beker", "kupa", "trophy")
    if any(term in low for term in cup_terms) or league_type == "cup" or league_sub_type in ("domestic_cup", "cup_international"):
        return "DOMESTIC_CUP", 0.75

    # 4. Ligas Oficiales Reconocidas (Verificación Positiva / Whitelist)
    is_known_league_id = league_id is not None and int(league_id) in LEAGUE_BASE_ELO
    is_known_league_pattern = any(pattern in low for pattern in OFFICIAL_LEAGUE_PATTERNS)
    is_official_type = (league_type == "league" or league_sub_type == "domestic") and len(low) >= 3

    if is_known_league_id or is_known_league_pattern or is_official_type:
        return "OFFICIAL_LEAGUE", 1.00

    # 5. Zero-Trust: Competición Desconocida -> UNKNOWN (Peso 0.00)
    return "UNKNOWN", 0.00


def extract_team_matches(
    recent_rows: Iterable[dict[str, Any]],
    team_id: int,
    details: dict[int, dict[str, Any]],
) -> list[TeamMatch]:
    result: list[TeamMatch] = []
    for row in recent_rows:
        fixture = row.get("fixture", {})
        fixture_id = int(fixture.get("id", -1))
        enriched = details.get(fixture_id, row)
        teams = enriched.get("teams", {}) or row.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        is_home = int(home.get("id", -1)) == team_id
        if not is_home and int(away.get("id", -1)) != team_id:
            continue
        goals = enriched.get("goals", {})
        home_goals = _number(goals.get("home"))
        away_goals = _number(goals.get("away"))
        if home_goals is None or away_goals is None:
            continue
        goals_for, goals_against = (
            (int(home_goals), int(away_goals)) if is_home else (int(away_goals), int(home_goals))
        )
        halftime = enriched.get("halftime") or {}
        ht_home = _number(halftime.get("home"))
        ht_away = _number(halftime.get("away"))
        ht_for: int | None = None
        ht_against: int | None = None
        if ht_home is not None and ht_away is not None:
            ht_for, ht_against = (int(ht_home), int(ht_away)) if is_home else (int(ht_away), int(ht_home))
            if ht_for > goals_for or ht_against > goals_against:
                ht_for = ht_against = None
        stat_blocks = _team_stat_blocks(enriched.get("statistics", []))
        own_id = team_id
        opponent_id = int(away["id"] if is_home else home["id"])
        opponent_name = str(away.get("name") if is_home else home.get("name") or "Rival")
        league_info = enriched.get("league", {}) or row.get("league", {})
        league_name = str(league_info.get("name", "")).lower()
        league_id = league_info.get("id")

        _, comp_weight = classify_competition(
            league_name,
            league_id,
            league_info.get("type"),
            league_info.get("sub_type"),
        )

        result.append(
            TeamMatch(
                fixture_id=fixture_id,
                date=enriched.get("fixture", {}).get("date", ""),
                team_id=team_id,
                opponent_id=opponent_id,
                is_home=is_home,
                goals_for=goals_for,
                goals_against=goals_against,
                result="W" if goals_for > goals_against else "D" if goals_for == goals_against else "L",
                opponent_name=opponent_name,
                stats_for=stat_blocks.get(own_id, {}),
                stats_against=stat_blocks.get(opponent_id, {}),
                competition_weight=comp_weight,
                league_id=league_id,
                goals_for_1h=ht_for,
                goals_against_1h=ht_against,
            )
        )
    result.sort(key=lambda match: match.date, reverse=True)
    return result


def extract_common_opponents(
    home_matches: list[TeamMatch],
    away_matches: list[TeamMatch],
) -> list[dict[str, Any]]:
    """
    Encuentra y compara el desempeño de ambos equipos frente a rivales comunes.
    Calcula la ventaja neta de goles, xG y tiros sobre el mismo baremo de dificultad.
    """
    home_by_opp: dict[int, TeamMatch] = {}
    for m in home_matches:
        if m.opponent_id not in home_by_opp:
            home_by_opp[m.opponent_id] = m

    away_by_opp: dict[int, TeamMatch] = {}
    for m in away_matches:
        if m.opponent_id not in away_by_opp:
            away_by_opp[m.opponent_id] = m

    common_ids = set(home_by_opp.keys()) & set(away_by_opp.keys())
    if not common_ids:
        return []

    comparisons: list[dict[str, Any]] = []
    for opp_id in common_ids:
        hm = home_by_opp[opp_id]
        am = away_by_opp[opp_id]
        opp_name = hm.opponent_name or am.opponent_name or f"Rival #{opp_id}"

        home_gd = hm.goals_for - hm.goals_against
        away_gd = am.goals_for - am.goals_against
        net_advantage = home_gd - away_gd

        comparisons.append({
            "opponent_id": opp_id,
            "opponent_name": opp_name,
            "home_match": {
                "date": hm.date,
                "is_home": hm.is_home,
                "goals_for": hm.goals_for,
                "goals_against": hm.goals_against,
                "result": hm.result,
                "score": f"{hm.goals_for}-{hm.goals_against}",
                "shots_on": hm.stats_for.get("shots_on_goal"),
                "corners": hm.stats_for.get("corner_kicks"),
                "xg": hm.stats_for.get("expected_goals"),
            },
            "away_match": {
                "date": am.date,
                "is_home": am.is_home,
                "goals_for": am.goals_for,
                "goals_against": am.goals_against,
                "result": am.result,
                "score": f"{am.goals_for}-{am.goals_against}",
                "shots_on": am.stats_for.get("shots_on_goal"),
                "corners": am.stats_for.get("corner_kicks"),
                "xg": am.stats_for.get("expected_goals"),
            },
            "home_gd": home_gd,
            "away_gd": away_gd,
            "net_advantage": net_advantage,
        })

    comparisons.sort(key=lambda x: abs(x["net_advantage"]), reverse=True)
    return comparisons


def extract_player_shots(details: Iterable[dict[str, Any]]) -> list[PlayerShot]:
    shots: list[PlayerShot] = []
    for fixture in details:
        for team_block in fixture.get("players", []) or []:
            team_id = int(team_block.get("team", {}).get("id", -1))
            for entry in team_block.get("players", []) or []:
                player = entry.get("player", {})
                stats = (entry.get("statistics") or [{}])[0]
                games = stats.get("games", {})
                shot_data = stats.get("shots", {})
                goal_data = stats.get("goals", {})
                minutes = _number(games.get("minutes")) or 0.0
                on_target = _number(shot_data.get("on")) or 0.0
                total_raw = _number(shot_data.get("total"))
                if total_raw is None:
                    total_raw = _number(shot_data.get("shots"))
                total_shots = float(total_raw) if total_raw is not None else float(max(on_target, round(on_target * 2.2, 1)))
                goals_raw = _number(goal_data.get("scored")) or _number(goal_data.get("total")) or _number(entry.get("goals")) or 0.0
                if player.get("id") is not None and minutes > 0:
                    shots.append(
                        PlayerShot(
                            player_id=int(player["id"]),
                            name=player.get("name", "Jugador"),
                            team_id=team_id,
                            shots_on_target=float(on_target),
                            minutes=float(minutes),
                            total_shots=float(total_shots),
                            goals=float(goals_raw),
                            total_shots_known=total_raw is not None,
                        )
                    )
    return shots


# Ids de país de Sportmonks (verificados con /core/countries). Los anteriores eran de otro
# proveedor y apuntaban a países equivocados (p. ej. "2" es Polonia, "5" es Brasil).
COUNTRY_TIER_ELO: dict[str, float] = {
    # UEFA Top 5
    "462": 1820.0,  # Inglaterra (Premier League)
    "32": 1800.0,   # España (La Liga)
    "251": 1780.0,  # Italia (Serie A)
    "11": 1780.0,   # Alemania (Bundesliga)
    "17": 1730.0,   # Francia (Ligue 1)
    # Tier 2 Europa & Top América
    "5": 1720.0,    # Brasil (Brasileirão)
    "44": 1700.0,   # Argentina (Liga Profesional)
    "20": 1640.0,   # Portugal (Primeira Liga)
    "38": 1620.0,   # Países Bajos (Eredivisie)
    "458": 1580.0,  # México (Liga MX)
    "3483": 1550.0, # EE. UU. (MLS)
    "556": 1540.0,  # Bélgica
    "404": 1530.0,  # Turquía
    "353": 1480.0,  # Colombia (Liga BetPlay)
    "158": 1470.0,  # Uruguay (Primera)
    "80": 1460.0,   # Chile
    "459": 1460.0,  # Ecuador
    "1190": 1460.0, # Paraguay
    "338": 1450.0,  # Perú (Liga 1)
    "7598": 1420.0, # Bolivia
    "275": 1420.0,  # Venezuela
}

LEAGUE_BASE_ELO: dict[int, float] = {
    # Inglaterra
    8: 1840.0,   # Premier League
    9: 1580.0,   # Championship
    12: 1420.0,  # League One
    14: 1320.0,  # League Two
    # España
    564: 1820.0, # La Liga
    567: 1540.0, # La Liga 2 (Segunda División / Hypermotion)
    # Italia
    384: 1790.0, # Serie A
    387: 1520.0, # Serie B
    390: 1600.0, # Coppa Italia
    # Alemania
    82: 1780.0,  # Bundesliga
    85: 1530.0,  # 2. Bundesliga
    88: 1380.0,  # 3. Liga
    109: 1600.0, # DFB Pokal
    # Francia
    301: 1740.0, # Ligue 1
    304: 1490.0, # Ligue 2
    # Portugal / Países Bajos
    462: 1640.0, # Liga Portugal
    72: 1620.0,  # Eredivisie
    # Sudamérica
    648: 1730.0, # Brasileirão Serie A (id Sportmonks)
    651: 1480.0, # Brasileirão Serie B
    636: 1700.0, # Liga Profesional Argentina
    672: 1480.0, # Liga BetPlay Colombia
    764: 1450.0, # Liga 1 Perú (Primera División)
    # Concacaf
    743: 1580.0, # Liga MX
    779: 1550.0, # MLS
}

CLUB_TIER_OFFSETS: dict[str, float] = {
    # Tier 1: Élite mundial / Candidatos a Champions League (+170 a +200)
    "real madrid": 200.0,
    "manchester city": 200.0,
    "bayern munchen": 200.0,
    "bayern munich": 200.0,
    "arsenal": 180.0,
    "liverpool": 180.0,
    "barcelona": 180.0,
    "paris saint germain": 180.0,
    "psg": 180.0,
    "inter": 180.0,
    "inter milan": 180.0,
    "internazionale": 180.0,
    "ac milan": 170.0,
    "milan": 170.0,
    "juventus": 170.0,
    "atletico madrid": 170.0,
    "atletico de madrid": 170.0,
    "bayer leverkusen": 170.0,
    "leverkusen": 170.0,

    # Tier 2: Élite secundaria / Top 4 contendientes / Gigantes continentales (+70 a +115)
    "chelsea": 110.0,
    "tottenham": 100.0,
    "tottenham hotspur": 100.0,
    "manchester united": 100.0,
    "aston villa": 90.0,
    "newcastle": 90.0,
    "newcastle united": 90.0,
    "borussia dortmund": 110.0,
    "dortmund": 110.0,
    "rb leipzig": 100.0,
    "leipzig": 100.0,
    "eintracht frankfurt": 80.0,
    "stuttgart": 80.0,
    "atalanta": 110.0,
    "napoli": 110.0,
    "roma": 90.0,
    "as roma": 90.0,
    "lazio": 90.0,
    "fiorentina": 70.0,
    "monaco": 90.0,
    "as monaco": 90.0,
    "olympique marseille": 85.0,
    "marseille": 85.0,
    "lille": 80.0,
    "lille osc": 80.0,
    "olympique lyonnais": 75.0,
    "lyon": 75.0,
    "sporting cp": 100.0,
    "sporting lisbon": 100.0,
    "benfica": 100.0,
    "porto": 90.0,
    "fc porto": 90.0,
    "psv": 85.0,
    "psv eindhoven": 85.0,
    "feyenoord": 80.0,
    "ajax": 75.0,
    "athletic club": 85.0,
    "athletic bilbao": 85.0,
    "real sociedad": 80.0,
    "villarreal": 80.0,
    "real betis": 75.0,
    "betis": 75.0,
    "flamengo": 100.0,
    "palmeiras": 100.0,
    "botafogo": 90.0,
    "river plate": 90.0,
    "boca juniors": 90.0,

    # Tier 1 Ligas Locales (Perú / Colombia / Sudamérica / MLS):
    "universitario": 120.0,
    "alianza lima": 120.0,
    "sporting cristal": 110.0,
    "melgar": 90.0,
    "fbc melgar": 90.0,
    "millonarios": 90.0,
    "santa fe": 85.0,
    "atletico nacional": 90.0,
    "junior": 85.0,
    "inter miami": 100.0,
    "inter miami cf": 100.0,
    "columbus crew": 70.0,
    "lafc": 70.0,
    "los angeles fc": 70.0,

    # Tier 4: Pequeño presupuesto / Zona descenso / Expansión (-70 a -140)
    "san diego": -70.0,
    "san diego fc": -70.0,
    "lecce": -130.0,
    "us lecce": -130.0,
    "venezia": -140.0,
    "venezia fc": -140.0,
    "monza": -110.0,
    "cagliari": -110.0,
    "empoli": -120.0,
    "hellas verona": -110.0,
    "verona": -110.0,
    "como": -110.0,
    "como 1907": -110.0,
    "pisa": -140.0,
    "salernitana": -140.0,
    "frosinone": -130.0,
    "southampton": -130.0,
    "ipswich": -140.0,
    "ipswich town": -140.0,
    "leicester": -90.0,
    "leicester city": -90.0,
    "espanyol": -110.0,
    "leganes": -130.0,
    "valladolid": -130.0,
    "real valladolid": -130.0,
    "las palmas": -110.0,
    "alaves": -90.0,
    "deportivo alaves": -90.0,
    "st pauli": -130.0,
    "fc st. pauli": -130.0,
    "holstein kiel": -140.0,
    "bochum": -130.0,
    "vfl bochum": -130.0,
    "heidenheim": -90.0,
    "angers": -130.0,
    "le havre": -130.0,
    "saint etienne": -120.0,
    "as saint-etienne": -120.0,
    "auxerre": -110.0,
    "comerciantes unidos": -100.0,
    "union comercio": -120.0,
    "alianza atletico": -80.0,
    "carlos mannucci": -100.0,
}


def get_club_tier_offset(name: str | None, league_id: int | None = None) -> float:
    """
    Estratificación de Clubes (Opción 2):
    Devuelve el desfase Elo base según el estatus competitivo del club dentro de su liga.
    """
    if not name:
        return 0.0
    low = name.lower().strip()
    low = (
        low.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ñ", "n")
    )
    for k in sorted(CLUB_TIER_OFFSETS.keys(), key=len, reverse=True):
        pattern = r"\b" + re.escape(k) + r"\b"
        if re.search(pattern, low):
            return CLUB_TIER_OFFSETS[k]

    # Ids de Sportmonks: 2 Champions League, 5 Europa League (2451/2452 son amistosos).
    if league_id == 2:  # Champions League
        return 120.0
    if league_id == 5:  # Europa League
        return 60.0
    return 0.0


def get_sos_multiplier(opponent_name: str | None, league_id: int | None, attr: str) -> float:
    """
    Strength of Schedule (SoS) Multiplier (Opción 3):
    Ajusta el mérito de goles marcados y encajados según el nivel del rival enfrentado.
    - Anotar frente a rivales de élite (tier > 0) tiene mayor mérito (+10% a +25%).
    - Encajar frente a rivales de élite es previsible y penaliza menos (-10% a -25%).
    - Anotar frente a rivales débiles (tier < 0) reduce el crédito de volumen (-10% a -18%).
    - Encajar frente a rivales débiles penaliza la solidez defensiva (+10% a +18%).
    """
    tier = get_club_tier_offset(opponent_name, league_id)
    if not tier:
        return 1.0
    factor = tier / 800.0
    if attr == "goals_for":
        return max(0.75, min(1.30, 1.0 + factor))
    elif attr == "goals_against":
        return max(0.75, min(1.30, 1.0 - factor))
    return 1.0


@dataclass(frozen=True)
class CompetitionProfile:
    league_id: int | None
    name: str
    home_advantage: float      # Multiplicador ventaja local (ej. 1.09 Premier, 1.24 Libertadores)
    away_advantage: float      # Multiplicador factor visitante (ej. 0.91 Premier, 0.76 Libertadores)
    base_goals: float          # Promedio goles por partido de la competición (ej. 2.85 Premier, 3.15 Bundesliga)
    elo_scale: float           # Factor escala Elo (320 normal, 280 alta varianza)
    recency_decay: float       # Tasa decaimiento temporal (0.86 estándar)
    dispersion_corners: float  # Parámetro alpha Binomial Negativa córners
    dispersion_cards: float    # Parámetro alpha Binomial Negativa tarjetas
    max_lambda_home: float = 5.0          # Tope de goles esperados del local
    max_lambda_away: float = 3.5          # Tope de goles esperados del visitante
    elo_weight_cap: float | None = None   # Peso Elo máximo permitido en la competición


COMPETITION_PROFILES: dict[int, CompetitionProfile] = {
    # Premier League (8): Menor ventaja local, alto volumen de goles
    8: CompetitionProfile(8, "Premier League", 1.09, 0.91, 2.85, 320.0, 0.88, 0.13, 0.20),
    # Championship (9): Mayor fricción, alta competitividad
    9: CompetitionProfile(9, "Championship", 1.12, 0.88, 2.65, 300.0, 0.86, 0.15, 0.24),
    # La Liga (564): Control táctico, promedio moderado de goles
    564: CompetitionProfile(564, "La Liga", 1.12, 0.88, 2.52, 310.0, 0.86, 0.14, 0.25),
    # La Liga 2 (567)
    567: CompetitionProfile(567, "La Liga 2", 1.15, 0.85, 2.25, 290.0, 0.85, 0.15, 0.28),
    # Serie A (384): Disciplina defensiva
    384: CompetitionProfile(384, "Serie A", 1.10, 0.89, 2.58, 310.0, 0.86, 0.14, 0.23),
    # Serie B (387)
    387: CompetitionProfile(387, "Serie B", 1.14, 0.86, 2.35, 290.0, 0.85, 0.15, 0.27),
    # Bundesliga (82): Máximo volumen ofensivo y transiciones rápidas
    82: CompetitionProfile(82, "Bundesliga", 1.10, 0.90, 3.15, 330.0, 0.88, 0.14, 0.20),
    # 2. Bundesliga (85)
    85: CompetitionProfile(85, "2. Bundesliga", 1.11, 0.89, 3.00, 310.0, 0.87, 0.14, 0.22),
    # Ligue 1 (301)
    301: CompetitionProfile(301, "Ligue 1", 1.11, 0.89, 2.70, 320.0, 0.86, 0.14, 0.22),
    # Eredivisie (72): Alto ritmo, abundantes goles
    72: CompetitionProfile(72, "Eredivisie", 1.10, 0.90, 3.05, 310.0, 0.87, 0.14, 0.21),
    # Liga Portugal (462)
    462: CompetitionProfile(462, "Liga Portugal", 1.12, 0.88, 2.65, 310.0, 0.86, 0.14, 0.26),
    # Brasileirão Serie A (648): Marcada ventaja local por logística y clima
    648: CompetitionProfile(648, "Brasileirão", 1.16, 0.84, 2.45, 290.0, 0.85, 0.15, 0.26),
    # Liga Profesional Argentina (636): Partidos muy cerrados, alta fricción
    636: CompetitionProfile(636, "Liga Argentina", 1.16, 0.84, 2.30, 290.0, 0.85, 0.15, 0.27),
    # Liga BetPlay Colombia (672)
    672: CompetitionProfile(672, "Liga BetPlay", 1.18, 0.82, 2.25, 280.0, 0.85, 0.15, 0.27),
    # Liga 1 Perú (764): Gran disparidad costa vs altura
    764: CompetitionProfile(764, "Liga 1 Perú", 1.20, 0.80, 2.48, 280.0, 0.85, 0.16, 0.27),
    # MLS (779)
    779: CompetitionProfile(779, "MLS", 1.15, 0.85, 2.95, 300.0, 0.87, 0.14, 0.22),
    # Liga MX (743)
    743: CompetitionProfile(743, "Liga MX", 1.15, 0.85, 2.70, 300.0, 0.86, 0.15, 0.24),
}

# Amistosos internacionales (1082): rotaciones, sedes a menudo neutrales y ritmo bajo.
# La forma reciente ya refleja el nivel de cada selección, así que el Elo pesa poco
# y los goles esperados se topan para no proyectar goleadas irreales.
FRIENDLY_INTERNATIONAL_PROFILE = CompetitionProfile(
    1082,
    "Amistoso Internacional",
    home_advantage=1.06,
    away_advantage=0.94,
    base_goals=2.55,
    elo_scale=320.0,
    recency_decay=0.86,
    dispersion_corners=0.15,
    dispersion_cards=0.24,
    max_lambda_home=3.5,
    max_lambda_away=3.0,
    elo_weight_cap=0.15,
)
COMPETITION_PROFILES[1082] = FRIENDLY_INTERNATIONAL_PROFILE

DEFAULT_COMPETITION_PROFILE = CompetitionProfile(
    None, "Universal / General", 1.12, 0.90, 2.60, 320.0, 0.86, 0.14, 0.22
)


def get_competition_profile(
    league_id: int | None = None, league_name: str | None = None
) -> CompetitionProfile:
    if league_id is not None and int(league_id) in COMPETITION_PROFILES:
        return COMPETITION_PROFILES[int(league_id)]
    low = (league_name or "").lower()
    if any(k in low for k in ("friendl", "amistos")):
        return replace(FRIENDLY_INTERNATIONAL_PROFILE, league_id=league_id, name="Amistoso")
    if any(k in low for k in ("libertadores", "sudamericana")):
        return CompetitionProfile(
            league_id,
            "Torneo Conmebol",
            home_advantage=1.24,
            away_advantage=0.76,
            base_goals=2.45,
            elo_scale=280.0,
            recency_decay=0.84,
            dispersion_corners=0.16,
            dispersion_cards=0.28,
        )
    if any(k in low for k in ("champions league", "europa league", "conference league")):
        return CompetitionProfile(
            league_id,
            "Torneo UEFA",
            home_advantage=1.10,
            away_advantage=0.90,
            base_goals=2.90,
            elo_scale=320.0,
            recency_decay=0.88,
            dispersion_corners=0.13,
            dispersion_cards=0.22,
        )
    return DEFAULT_COMPETITION_PROFILE


MIN_DETAILED_PER_TEAM = 6


def calculate_confidence_score(
    home_matches: list[TeamMatch],
    away_matches: list[TeamMatch],
    expected: ExpectedMetrics | None = None,
    lineups_confirmed: bool = False,
    odds_available: bool = False,
) -> ConfidenceScore:
    """Calcula la Puntuación de Confianza Epistémica (0 a 100) separada de la probabilidad matemática.
    
    Evalúa la calidad, completitud y frescura de la muestra empírica:
    - Tamaño de muestra (hasta 30 pts)
    - Profundidad de estadísticas avanzadas de tiros/córners (hasta 30 pts)
    - Confirmación oficial de alineaciones XI (hasta 25 pts)
    - Pureza competitiva oficial vs amistosos (hasta 15 pts)
    """
    sample_size = len(home_matches) + len(away_matches)

    # 1. Tamaño muestral
    if sample_size >= 20:
        pts_sample = 30
    elif sample_size >= 14:
        pts_sample = 25
    elif sample_size >= 10:
        pts_sample = 20
    elif sample_size >= 6:
        pts_sample = 12
    else:
        pts_sample = 5

    # 2. Profundidad estadística
    all_matches = home_matches + away_matches
    detailed_matches = sum(
        1 for m in all_matches
        if m.stats_for and ("shots_on_goal" in m.stats_for or "corner_kicks" in m.stats_for)
    )
    ratio_detailed = (detailed_matches / sample_size) if sample_size > 0 else 0.0
    if ratio_detailed >= 0.80:
        pts_detail = 30
    elif ratio_detailed >= 0.60:
        pts_detail = 22
    elif ratio_detailed >= 0.40:
        pts_detail = 15
    else:
        pts_detail = 5

    # 3. Confirmación de Once Titular
    pts_lineup = 25 if lineups_confirmed else 10

    # 4. Pureza de datos de competición oficial
    official_count = sum(1 for m in all_matches if m.competition_weight >= 0.70)
    ratio_official = (official_count / sample_size) if sample_size > 0 else 0.0
    if ratio_official >= 0.85:
        pts_official = 15
    elif ratio_official >= 0.60:
        pts_official = 10
    else:
        pts_official = 5

    total_score = min(100, max(0, pts_sample + pts_detail + pts_lineup + pts_official))

    min_team_detailed = min(
        sum(1 for m in team if m.stats_for and ("shots_on_goal" in m.stats_for or "corner_kicks" in m.stats_for))
        for team in (home_matches, away_matches)
    )
    if total_score >= 75 and min_team_detailed < MIN_DETAILED_PER_TEAM:
        # Con pocas estadísticas de un equipo, los mercados de córners/tarjetas/remates son frágiles.
        total_score = 74

    if total_score >= 75:
        level = "ALTA"
    elif total_score >= 50:
        level = "MEDIA"
    else:
        level = "BAJA"

    reasons: list[str] = [
        f"{sample_size} partidos analizados ({len(home_matches)} local, {len(away_matches)} visitante)",
        f"{detailed_matches}/{sample_size} con estadísticas completas de remates y córners",
        "Alineación titular confirmada oficialmente" if lineups_confirmed else "Alineaciones no confirmadas (proyecciones sujetas a rotación)",
    ]
    if ratio_official < 0.70:
        reasons.append("Muestra con presencia de amistosos o partidos de menor ponderación")
    if min_team_detailed < MIN_DETAILED_PER_TEAM:
        reasons.append(f"Un equipo tiene menos de {MIN_DETAILED_PER_TEAM} partidos con estadísticas completas")

    return ConfidenceScore(
        score=total_score,
        level=level,
        sample_size=sample_size,
        detailed_matches=detailed_matches,
        lineups_confirmed=lineups_confirmed,
        reasons=reasons,
    )


TEAM_ALTITUDES: dict[str, int] = {
    # Altitud en metros sobre el nivel del mar (m.s.n.m.)
    # Perú - Sedes de Altura
    "cienciano": 3400,
    "cusco": 3400,
    "garcilaso": 3400,
    "deportivo garcilaso": 3400,
    "real garcilaso": 3400,
    "binacional": 3825,
    "deportivo binacional": 3825,
    "sport huancayo": 3250,
    "huancayo": 3250,
    "adt": 3050,
    "adt tarma": 3050,
    "tarma": 3050,
    "ayacucho": 2750,
    "utc": 2750,
    "utc cajamarca": 2750,
    "cajamarca": 2750,
    "melgar": 2330,
    "fbc melgar": 2330,
    "arequipa": 2330,
    "comerciantes unidos": 2650,
    "los chankas": 2900,
    "chankas": 2900,
    # Bolivia - Sedes de Altura
    "always ready": 4150,
    "bolivar": 3640,
    "bolívar": 3640,
    "the strongest": 3640,
    "strongest": 3640,
    "san jose": 3735,
    "san josé": 3735,
    "nacional potosi": 4000,
    "nacional potosí": 4000,
    "real potosi": 4000,
    "real potosí": 4000,
    "aurora": 2560,
    "wilstermann": 2560,
    "jorge wilstermann": 2560,
    "universitario de vinto": 2560,
    "real tomayapo": 1850,
    "tomayapo": 1850,
    # Ecuador - Sedes de Altura
    "ldu quito": 2850,
    "liga de quito": 2850,
    "independiente del valle": 2850,
    "universidad catolica ecuador": 2850,
    "aucas": 2850,
    "el nacional": 2850,
    "cumbaya": 2850,
    "cumbayá": 2850,
    "macara": 2570,
    "macará": 2570,
    "tecnico universitario": 2570,
    "técnico universitario": 2570,
    "mushuc runa": 3250,
    "deportivo cuenca": 2550,
    # Colombia - Sedes de Altura
    "millonarios": 2640,
    "santa fe": 2640,
    "independiente santa fe": 2640,
    "la equidad": 2640,
    "fortaleza ceif": 2640,
    "boyaca chico": 2810,
    "boyacá chicó": 2810,
    "patriotas": 2810,
    "patriotas boyaca": 2810,
    "deportivo pasto": 2520,
    "pasto": 2520,
    "once caldas": 2160,
    # México - Sedes de Altura
    "toluca": 2660,
    "puebla": 2135,
    "america": 2240,
    "américa": 2240,
    "club america": 2240,
    "cruz azul": 2240,
    "pumas": 2240,
    "pumas unam": 2240,
    "pachuca": 2400,
}

# Ids de equipo verificados en Sportmonks (los anteriores eran de otro proveedor y
# apuntaban a equipos equivocados: p. ej. 3496 es São Paulo, no Bolívar).
TEAM_ALTITUDE_IDS: dict[int, int] = {
    13264: 3400,   # Cienciano
    10976: 3400,   # Cusco FC
    15743: 3400,   # Deportivo Garcilaso
    208: 2330,     # Melgar
    12562: 3250,   # Sport Huancayo
    239392: 3050,  # ADT
    3992: 2750,    # UTC Cajamarca
    6905: 2900,    # Los Chankas
    234259: 4150,  # Always Ready
    6308: 3640,    # Club Bolívar
    10024: 3640,   # The Strongest
    10779: 2850,   # LDU Quito
    14635: 2850,   # Independiente del Valle
    12402: 2570,   # Macará
    7810: 2640,    # Millonarios
    12506: 2640,   # Santa Fe
    9952: 2640,    # Internacional de Bogotá (ex La Equidad)
    12832: 2520,   # Deportivo Pasto
    3547: 2160,    # Once Caldas
    14615: 2810,   # Boyacá Chicó
}

# Países con sedes de altura (country_id de Sportmonks): la coincidencia por nombre solo
# se aplica a equipos de estos países, para no confundir "San Jose Earthquakes" o
# "Unión de Santa Fe" con San José (Oruro) o Santa Fe (Bogotá).
ALTITUDE_COUNTRY_IDS = frozenset({"338", "7598", "459", "353", "458"})  # Perú, Bolivia, Ecuador, Colombia, México


def get_team_altitude(
    team_id: int | None = None, team_name: str | None = None, country_id: str | int | None = None
) -> int:
    """Obtiene la altitud del estadio/sede del equipo en metros sobre el nivel del mar."""
    if team_id is not None and int(team_id) in TEAM_ALTITUDE_IDS:
        return TEAM_ALTITUDE_IDS[int(team_id)]
    if country_id not in (None, "") and str(country_id) not in ALTITUDE_COUNTRY_IDS:
        return 0
    if team_name:
        clean = team_name.lower().strip()
        for pattern, alt in TEAM_ALTITUDES.items():
            # Solo palabras completas: "utc" no debe coincidir dentro de otra palabra.
            if re.search(r"(?<!\w)" + re.escape(pattern) + r"(?!\w)", clean):
                return alt
    return 0


def detect_altitude_impact(
    home_id: int | None = None,
    home_name: str | None = None,
    away_id: int | None = None,
    away_name: str | None = None,
    home_country: str | int | None = None,
    away_country: str | int | None = None,
) -> dict[str, Any] | None:
    """
    Evalúa el desbalance fisiológico y balístico por altitud extrema.
    Se activa cuando el equipo local juega a >= 2,200 m.s.n.m. y el visitante
    procede de una altitud sustancialmente menor (desnivel >= 1,200 m).
    """
    home_alt = get_team_altitude(home_id, home_name, home_country)
    away_alt = get_team_altitude(away_id, away_name, away_country)
    delta = home_alt - away_alt

    if home_alt < 2200 or delta < 1200:
        return None

    if delta >= 2800 or home_alt >= 3400:
        severity = "EXTREME"
        lambda_home_mult = 1.25
        lambda_away_mult = 0.70
        shots_home_mult = 1.25
        shots_away_mult = 0.80
        corners_home_mult = 1.25
    elif delta >= 1800 or home_alt >= 2600:
        severity = "HIGH"
        lambda_home_mult = 1.18
        lambda_away_mult = 0.78
        shots_home_mult = 1.18
        shots_away_mult = 0.85
        corners_home_mult = 1.18
    else:
        severity = "MODERATE"
        lambda_home_mult = 1.10
        lambda_away_mult = 0.88
        shots_home_mult = 1.10
        shots_away_mult = 0.90
        corners_home_mult = 1.10

    desc = (
        f"Alerta de Altitud {severity}: {home_name or 'Local'} juega a {home_alt:,} m.s.n.m. "
        f"frente a {away_name or 'Visitante'} ({away_alt:,} m.s.n.m.). Desnivel de {delta:,}m provoca "
        "hipoxia aguda en el visitante, merma de resistencia cardiovascular en el 2T y mayor aceleración "
        "del balón en remates de media distancia."
    )

    return {
        "home_altitude": home_alt,
        "away_altitude": away_alt,
        "delta": delta,
        "severity": severity,
        "description": desc,
        "lambda_home_mult": lambda_home_mult,
        "lambda_away_mult": lambda_away_mult,
        "shots_home_mult": shots_home_mult,
        "shots_away_mult": shots_away_mult,
        "corners_home_mult": corners_home_mult,
        "disallow_away_handicap": delta >= 1800,
    }



def calculate_elo(
    home_matches: list[TeamMatch],
    away_matches: list[TeamMatch],
    home_id: int,
    away_id: int,
    home_country: str | None = None,
    away_country: str | None = None,
    home_league: int | None = None,
    away_league: int | None = None,
    home_name: str | None = None,
    away_name: str | None = None,
    club_tier_scale: float = DEFAULT_PARAMETERS.club_tier_scale,
) -> tuple[float, float]:
    def default_rating(
        team_id: int,
        matches: list[TeamMatch] | None = None,
        country: str | None = None,
        league_id: int | None = None,
        team_name: str | None = None,
    ) -> float:
        # 1. Base Universal por División / Liga
        if league_id and int(league_id) in LEAGUE_BASE_ELO:
            base = LEAGUE_BASE_ELO[int(league_id)]
        elif country and str(country) in COUNTRY_TIER_ELO:
            base = COUNTRY_TIER_ELO[str(country)]
        else:
            base = 1550.0

        # 2. Prior por nivel de club (tabla manual), escalado por un parámetro ajustado con datos.
        # No se suma un bonus por diferencia de goles: esos mismos partidos ya actualizan
        # el Elo más abajo y alimentan la forma reciente (sería contarlos dos veces).
        base += club_tier_scale * get_club_tier_offset(team_name, league_id)

        return round(base, 1)

    ratings: dict[int, float] = {}
    ratings[home_id] = default_rating(home_id, home_matches, home_country, home_league, team_name=home_name)
    ratings[away_id] = default_rating(away_id, away_matches, away_country, away_league, team_name=away_name)

    unique: dict[int, TeamMatch] = {}
    for match in home_matches + away_matches:
        unique.setdefault(match.fixture_id, match)

    chronological = sorted(unique.values(), key=lambda item: item.date)
    for position, match in enumerate(chronological, start=1):
        if match.is_home:
            host, visitor = match.team_id, match.opponent_id
            host_goals, visitor_goals = match.goals_for, match.goals_against
            host_name = home_name if host == home_id else (away_name if host == away_id else None)
            vis_name = match.opponent_name if visitor not in (home_id, away_id) else (home_name if visitor == home_id else away_name)
        else:
            host, visitor = match.opponent_id, match.team_id
            host_goals, visitor_goals = match.goals_against, match.goals_for
            host_name = match.opponent_name if host not in (home_id, away_id) else (home_name if host == home_id else away_name)
            vis_name = home_name if visitor == home_id else (away_name if visitor == away_id else None)

        if host not in ratings:
            ratings[host] = default_rating(host, league_id=match.league_id, team_name=host_name)
        if visitor not in ratings:
            ratings[visitor] = default_rating(visitor, league_id=match.league_id, team_name=vis_name)

        expected_host = 1.0 / (1.0 + 10 ** ((ratings[visitor] - (ratings[host] + 60)) / 400))
        actual_host = 1.0 if host_goals > visitor_goals else 0.5 if host_goals == visitor_goals else 0.0
        goal_multiplier = 1.0 + 0.12 * max(0, abs(host_goals - visitor_goals) - 1)
        # Los resultados más recientes pesan más dentro de la ventana disponible.
        recency_weight = 0.55 + 0.45 * position / len(chronological)
        change = 24.0 * recency_weight * goal_multiplier * match.competition_weight * (actual_host - expected_host)
        ratings[host] += change
        ratings[visitor] -= change
    return ratings[home_id], ratings[away_id]


def goal_probabilities(
    home_matches: list[TeamMatch],
    away_matches: list[TeamMatch],
    elo_home: float,
    elo_away: float,
    home_season_stats: dict[str, Any] | None = None,
    away_season_stats: dict[str, Any] | None = None,
    rho: float = -0.08,
    altitude_impact: dict[str, Any] | None = None,
    league_id: int | None = None,
    league_name: str | None = None,
    rest_days_home: float | None = None,
    rest_days_away: float | None = None,
    params: ModelParameters | None = None,
) -> ProbabilityReport:
    if params is None:
        params = DEFAULT_PARAMETERS if rho == -0.08 else ModelParameters(rho=rho)
    rho = params.rho
    use_sos = params.use_sos
    xg_w = params.xg_weight
    if len(home_matches) < 3 or len(away_matches) < 3:
        raise InsufficientDataError(
            "Se necesitan al menos 3 partidos terminados de cada equipo para calcular goles."
        )

    comp_profile = get_competition_profile(league_id, league_name)

    home_venue_for = _goal_signal(home_matches, True, "goals_for", "stats_for", use_sos, xg_w)
    home_venue_against = _goal_signal(home_matches, True, "goals_against", "stats_against", use_sos, xg_w)
    away_venue_for = _goal_signal(away_matches, False, "goals_for", "stats_for", use_sos, xg_w)
    away_venue_against = _goal_signal(away_matches, False, "goals_against", "stats_against", use_sos, xg_w)

    # Señales globales para contracción Bayesiana (Bayesian Shrinkage)
    home_all_for = _goal_signal(home_matches, None, "goals_for", "stats_for", use_sos, xg_w)
    home_all_against = _goal_signal(home_matches, None, "goals_against", "stats_against", use_sos, xg_w)
    away_all_for = _goal_signal(away_matches, None, "goals_for", "stats_for", use_sos, xg_w)
    away_all_against = _goal_signal(away_matches, None, "goals_against", "stats_against", use_sos, xg_w)

    season_home_for = _season_goal_average(home_season_stats, "for", "home")
    season_home_against = _season_goal_average(home_season_stats, "against", "home")
    season_away_for = _season_goal_average(away_season_stats, "for", "away")
    season_away_against = _season_goal_average(away_season_stats, "against", "away")

    sw = params.season_weight
    home_attack_v = _blend_available(home_venue_for, season_home_for, sw)
    home_defence_v = _blend_available(home_venue_against, season_home_against, sw)
    away_attack_v = _blend_available(away_venue_for, season_away_for, sw)
    away_defence_v = _blend_available(away_venue_against, season_away_against, sw)

    # Contracción: muestra de sede frente a rendimiento global (peso ajustado por liga)
    vw = params.venue_weight
    home_attack = home_attack_v * vw + home_all_for * (1.0 - vw)
    home_defence = home_defence_v * vw + home_all_against * (1.0 - vw)
    away_attack = away_attack_v * vw + away_all_for * (1.0 - vw)
    away_defence = away_defence_v * vw + away_all_against * (1.0 - vw)

    raw_home = math.sqrt(max(0.05, home_attack) * max(0.05, away_defence))
    raw_away = math.sqrt(max(0.05, away_attack) * max(0.05, home_defence))

    # Ventaja local y diferencia Elo calibrada por competición
    elo_delta = max(-500.0, min(500.0, elo_home - elo_away))
    h_mult = altitude_impact["lambda_home_mult"] if altitude_impact else 1.0
    a_mult = altitude_impact["lambda_away_mult"] if altitude_impact else 1.0

    # Impacto de descanso (fatiga / falta de ritmo competitivo)
    rest_impact_home = 0.0
    if rest_days_home is not None:
        if rest_days_home < 3.0:
            rest_impact_home = -0.12  # fatiga por partido reciente (< 72h)
        elif rest_days_home > 14.0:
            rest_impact_home = -0.05  # falta de ritmo competitivo

    rest_impact_away = 0.0
    if rest_days_away is not None:
        if rest_days_away < 3.0:
            rest_impact_away = -0.15  # fatiga acumulada + viaje visitante
        elif rest_days_away > 14.0:
            rest_impact_away = -0.05

    # El Elo y la forma reciente se construyen con los mismos partidos: aplicar el factor
    # Elo completo los cuenta dos veces. elo_weight (ajustado con datos) fija su peso.
    elo_weight = params.elo_weight
    if comp_profile.elo_weight_cap is not None:
        elo_weight = min(elo_weight, comp_profile.elo_weight_cap)
    elo_factor_h = math.exp(elo_weight * elo_delta / comp_profile.elo_scale)
    elo_factor_a = math.exp(-elo_weight * elo_delta / comp_profile.elo_scale)

    base_league_half = round(comp_profile.base_goals / 2.0, 2)

    # Descomposición aditiva estricta (Waterfall Telescópico):
    # Base + Ventaja Sede + Forma Reciente + Diferencial Elo + Descanso = Lambda
    venue_impact_h = round(base_league_half * (comp_profile.home_advantage - 1.0), 2)
    form_impact_h = round((raw_home - base_league_half) * comp_profile.home_advantage, 2)
    elo_impact_h = round((raw_home * comp_profile.home_advantage) * (elo_factor_h - 1.0), 2)
    rest_impact_h = round(rest_impact_home, 2)

    raw_lambda_h = base_league_half + venue_impact_h + form_impact_h + elo_impact_h + rest_impact_h
    if altitude_impact and h_mult != 1.0:
        raw_lambda_h *= h_mult
    lambda_home = _clamp(raw_lambda_h, 0.2, comp_profile.max_lambda_home)

    venue_impact_a = round(base_league_half * (comp_profile.away_advantage - 1.0), 2)
    form_impact_a = round((raw_away - base_league_half) * comp_profile.away_advantage, 2)
    elo_impact_a = round((raw_away * comp_profile.away_advantage) * (elo_factor_a - 1.0), 2)
    rest_impact_a = round(rest_impact_away, 2)

    raw_lambda_a = base_league_half + venue_impact_a + form_impact_a + elo_impact_a + rest_impact_a
    if altitude_impact and a_mult != 1.0:
        raw_lambda_a *= a_mult
    lambda_away = _clamp(raw_lambda_a, 0.05, comp_profile.max_lambda_away)

    attr_home = FactorAttribution(
        base_league_goals=base_league_half,
        elo_impact=elo_impact_h,
        venue_impact=venue_impact_h,
        recent_form_impact=form_impact_h,
        rest_impact=rest_impact_h,
        final_expected_goals=round(lambda_home, 2),
    )
    attr_away = FactorAttribution(
        base_league_goals=base_league_half,
        elo_impact=elo_impact_a,
        venue_impact=venue_impact_a,
        recent_form_impact=form_impact_a,
        rest_impact=rest_impact_a,
        final_expected_goals=round(lambda_away, 2),
    )

    shared_component = _estimate_shared_goal_component(
        home_matches, away_matches, lambda_home, lambda_away
    )
    matrix = _bivariate_dixon_coles_matrix(
        lambda_home,
        lambda_away,
        shared_component,
        rho=rho,
        max_goals=10,
    )
    home_win = sum(matrix[h][a] for h in range(11) for a in range(11) if h > a)
    draw = sum(matrix[g][g] for g in range(11))
    away_win = 1.0 - home_win - draw
    over_15 = sum(matrix[h][a] for h in range(11) for a in range(11) if h + a >= 2)
    over_25 = sum(matrix[h][a] for h in range(11) for a in range(11) if h + a >= 3)
    btts = sum(matrix[h][a] for h in range(1, 11) for a in range(1, 11))

    # Hándicap Asiático y Empate Apuesta No Válida (DNB / AH 0.0)
    ah_home_minus_15 = sum(matrix[h][a] for h in range(11) for a in range(11) if h - a >= 2)
    ah_away_plus_15 = 1.0 - ah_home_minus_15
    ah_away_minus_15 = sum(matrix[h][a] for h in range(11) for a in range(11) if a - h >= 2)
    ah_home_plus_15 = 1.0 - ah_away_minus_15
    ah_home_minus_25 = sum(matrix[h][a] for h in range(11) for a in range(11) if h - a >= 3)
    ah_away_plus_25 = 1.0 - ah_home_minus_25
    ah_away_minus_25 = sum(matrix[h][a] for h in range(11) for a in range(11) if a - h >= 3)
    ah_home_plus_25 = 1.0 - ah_away_minus_25
    total_decisive = home_win + away_win
    dnb_home = (home_win / total_decisive) if total_decisive > 0 else 0.5
    dnb_away = (away_win / total_decisive) if total_decisive > 0 else 0.5

    # Goles en el 1er Tiempo (1T / 1H)
    fh_share = params.first_half_share
    first_half_lambda = fh_share * (lambda_home + lambda_away)
    first_half_over_05 = 1.0 - math.exp(-first_half_lambda)
    first_half_over_15 = 1.0 - math.exp(-first_half_lambda) * (1.0 + first_half_lambda)
    first_half_under_15 = 1.0 - first_half_over_15

    # Goles en el 2do Tiempo (2T / 2H) - Mayor volumen histórico (55% de goles)
    second_half_lambda = (1.0 - fh_share) * (lambda_home + lambda_away)
    second_half_over_05 = 1.0 - math.exp(-second_half_lambda)
    second_half_over_15 = 1.0 - math.exp(-second_half_lambda) * (1.0 + second_half_lambda)
    second_half_under_15 = 1.0 - second_half_over_15

    # Goles Over / Under 3.5
    over_35 = sum(matrix[h][a] for h in range(11) for a in range(11) if h + a >= 4)
    under_35 = 1.0 - over_35

    # Goles por Equipo (Individual Team Goals)
    home_over_15 = sum(matrix[h][a] for h in range(2, 11) for a in range(11))
    home_over_25 = sum(matrix[h][a] for h in range(3, 11) for a in range(11))
    away_over_15 = sum(matrix[h][a] for h in range(11) for a in range(2, 11))
    home_under_15 = 1.0 - home_over_15
    away_under_15 = 1.0 - away_over_15

    # Portería a Cero (Clean Sheet)
    clean_sheet_home = sum(matrix[h][0] for h in range(11))
    clean_sheet_away = sum(matrix[0][a] for a in range(11))

    # Multigoles (Rango exacto desde matriz bivariada)
    multigoal_1_3 = sum(matrix[h][a] for h in range(11) for a in range(11) if 1 <= h + a <= 3)
    multigoal_2_4 = sum(matrix[h][a] for h in range(11) for a in range(11) if 2 <= h + a <= 4)
    multigoal_2_5 = sum(matrix[h][a] for h in range(11) for a in range(11) if 2 <= h + a <= 5)

    # Combos 1X2 + Ambos Marcan (BTTS)
    home_win_and_btts = sum(matrix[h][a] for h in range(1, 11) for a in range(1, 11) if h > a)
    away_win_and_btts = sum(matrix[h][a] for h in range(1, 11) for a in range(1, 11) if a > h)
    dc_1x_and_btts = sum(matrix[h][a] for h in range(1, 11) for a in range(1, 11) if h >= a)
    dc_x2_and_btts = sum(matrix[h][a] for h in range(1, 11) for a in range(1, 11) if a >= h)

    # Ambos Marcan en 2do Tiempo (BTTS 2T)
    lambda_h_2t = (1.0 - fh_share) * lambda_home
    lambda_a_2t = (1.0 - fh_share) * lambda_away
    p_h_score_2t = 1.0 - math.exp(-lambda_h_2t)
    p_a_score_2t = 1.0 - math.exp(-lambda_a_2t)
    btts_second_half = p_h_score_2t * p_a_score_2t

    return ProbabilityReport(
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        over_15=over_15,
        over_25=over_25,
        under_25=1.0 - over_25,
        btts=btts,
        expected_home_goals=round(lambda_home, 2),
        expected_away_goals=round(lambda_away, 2),
        over_35=round(over_35, 4),
        under_35=round(under_35, 4),
        shared_goal_component=shared_component,
        score_matrix=matrix,
        ah_home_minus_15=ah_home_minus_15,
        ah_away_plus_15=ah_away_plus_15,
        ah_home_plus_15=ah_home_plus_15,
        ah_away_minus_15=ah_away_minus_15,
        ah_home_minus_25=ah_home_minus_25,
        ah_away_plus_25=ah_away_plus_25,
        ah_home_plus_25=ah_home_plus_25,
        ah_away_minus_25=ah_away_minus_25,
        dnb_home=dnb_home,
        dnb_away=dnb_away,
        first_half_over_05=round(first_half_over_05, 4),
        first_half_over_15=round(first_half_over_15, 4),
        first_half_under_15=round(first_half_under_15, 4),
        second_half_over_05=round(second_half_over_05, 4),
        second_half_over_15=round(second_half_over_15, 4),
        second_half_under_15=round(second_half_under_15, 4),
        home_over_15=round(home_over_15, 4),
        home_over_25=round(home_over_25, 4),
        away_over_15=round(away_over_15, 4),
        home_under_15=round(home_under_15, 4),
        away_under_15=round(away_under_15, 4),
        clean_sheet_home=round(clean_sheet_home, 4),
        clean_sheet_away=round(clean_sheet_away, 4),
        multigoal_1_3=round(multigoal_1_3, 4),
        multigoal_2_4=round(multigoal_2_4, 4),
        multigoal_2_5=round(multigoal_2_5, 4),
        home_win_and_btts=round(home_win_and_btts, 4),
        away_win_and_btts=round(away_win_and_btts, 4),
        dc_1x_and_btts=round(dc_1x_and_btts, 4),
        dc_x2_and_btts=round(dc_x2_and_btts, 4),
        btts_second_half=round(btts_second_half, 4),
        attribution_home=attr_home,
        attribution_away=attr_away,
    )


def expected_metrics(
    home_matches: list[TeamMatch],
    away_matches: list[TeamMatch],
    player_rows: list[PlayerShot],
    home_id: int,
    away_id: int,
    elo_home: float | None = None,
    elo_away: float | None = None,
    altitude_impact: dict[str, Any] | None = None,
    league_id: int | None = None,
    league_name: str | None = None,
    starter_info: dict[int, dict[str, Any]] | None = None,
    params: ModelParameters | None = None,
    referee_cards: tuple[float, int] | None = None,
) -> ExpectedMetrics:
    comp_profile = get_competition_profile(league_id, league_name)
    params = params or DEFAULT_PARAMETERS
    disp_corners = (
        params.dispersion_corners if params.dispersion_corners is not None else comp_profile.dispersion_corners
    )
    disp_cards = params.dispersion_cards if params.dispersion_cards is not None else comp_profile.dispersion_cards
    disp_shots = 0.10
    disp_offsides = 0.16

    corners_home = _expected_count(home_matches, away_matches, True, False, "corner_kicks")
    corners_away = _expected_count(away_matches, home_matches, False, True, "corner_kicks")
    if altitude_impact and corners_home is not None:
        corners_home = round(corners_home * altitude_impact["corners_home_mult"], 2)

    total_corners = (corners_home + corners_away) if (corners_home is not None and corners_away is not None) else None
    over_75_corners = None
    over_85_corners = None
    over_95_corners = None
    over_105_corners = None
    over_115_corners = None
    under_105_corners = None
    if total_corners is not None and total_corners > 0:
        p_corn_under_8 = sum(_negative_binomial(k, total_corners, disp_corners) for k in range(8))
        p_corn_under_9 = sum(_negative_binomial(k, total_corners, disp_corners) for k in range(9))
        p_corn_under_10 = sum(_negative_binomial(k, total_corners, disp_corners) for k in range(10))
        p_corn_under_11 = sum(_negative_binomial(k, total_corners, disp_corners) for k in range(11))
        p_corn_under_12 = sum(_negative_binomial(k, total_corners, disp_corners) for k in range(12))
        over_75_corners = round(1.0 - p_corn_under_8, 4)
        over_85_corners = round(1.0 - p_corn_under_9, 4)
        over_95_corners = round(1.0 - p_corn_under_10, 4)
        over_105_corners = round(1.0 - p_corn_under_11, 4)
        over_115_corners = round(1.0 - p_corn_under_12, 4)
        under_105_corners = round(p_corn_under_11, 4)

    over_45_corners_home = None
    over_55_corners_home = None
    over_65_corners_home = None
    under_35_corners_home = None
    under_45_corners_home = None
    if corners_home is not None and corners_home > 0:
        p_c_h_under_4 = sum(_negative_binomial(k, corners_home, disp_corners) for k in range(4))
        p_c_h_under_5 = sum(_negative_binomial(k, corners_home, disp_corners) for k in range(5))
        p_c_h_under_6 = sum(_negative_binomial(k, corners_home, disp_corners) for k in range(6))
        p_c_h_under_7 = sum(_negative_binomial(k, corners_home, disp_corners) for k in range(7))
        over_45_corners_home = round(1.0 - p_c_h_under_5, 4)
        over_55_corners_home = round(1.0 - p_c_h_under_6, 4)
        over_65_corners_home = round(1.0 - p_c_h_under_7, 4)
        under_35_corners_home = round(p_c_h_under_4, 4)
        under_45_corners_home = round(p_c_h_under_5, 4)

    over_45_corners_away = None
    over_55_corners_away = None
    over_65_corners_away = None
    under_35_corners_away = None
    under_45_corners_away = None
    if corners_away is not None and corners_away > 0:
        p_c_a_under_4 = sum(_negative_binomial(k, corners_away, disp_corners) for k in range(4))
        p_c_a_under_5 = sum(_negative_binomial(k, corners_away, disp_corners) for k in range(5))
        p_c_a_under_6 = sum(_negative_binomial(k, corners_away, disp_corners) for k in range(6))
        p_c_a_under_7 = sum(_negative_binomial(k, corners_away, disp_corners) for k in range(7))
        over_45_corners_away = round(1.0 - p_c_a_under_5, 4)
        over_55_corners_away = round(1.0 - p_c_a_under_6, 4)
        over_65_corners_away = round(1.0 - p_c_a_under_7, 4)
        under_35_corners_away = round(p_c_a_under_4, 4)
        under_45_corners_away = round(p_c_a_under_5, 4)

    # Córners 1X2 mediante convolución discreta de la distribución binomial negativa
    corners_1x2_home = None
    corners_1x2_tie = None
    corners_1x2_away = None
    if corners_home is not None and corners_away is not None and corners_home > 0 and corners_away > 0:
        p_c_h = sum(
            _negative_binomial(h, corners_home, disp_corners) *
            sum(_negative_binomial(a, corners_away, disp_corners) for a in range(h))
            for h in range(1, 30)
        )
        p_c_tie = sum(
            _negative_binomial(k, corners_home, disp_corners) *
            _negative_binomial(k, corners_away, disp_corners)
            for k in range(30)
        )
        p_c_a = sum(
            _negative_binomial(a, corners_away, disp_corners) *
            sum(_negative_binomial(h, corners_home, disp_corners) for h in range(a))
            for a in range(1, 30)
        )
        corners_1x2_home = round(p_c_h, 4)
        corners_1x2_tie = round(p_c_tie, 4)
        corners_1x2_away = round(p_c_a, 4)

    # Remates Totales (Total Shots)
    total_shots_home = _expected_count(home_matches, away_matches, True, False, "total_shots")
    total_shots_away = _expected_count(away_matches, home_matches, False, True, "total_shots")
    if altitude_impact:
        if total_shots_home is not None:
            total_shots_home = round(total_shots_home * altitude_impact["shots_home_mult"], 2)
        if total_shots_away is not None:
            total_shots_away = round(total_shots_away * altitude_impact["shots_away_mult"], 2)

    tot_shots = (
        round(total_shots_home + total_shots_away, 2)
        if (total_shots_home is not None and total_shots_away is not None)
        else None
    )
    over_215_total_shots = None
    over_235_total_shots = None
    over_255_total_shots = None
    over_275_total_shots = None
    over_295_total_shots = None
    under_245_total_shots = None
    under_265_total_shots = None
    if tot_shots is not None and tot_shots > 0:
        over_215_total_shots = round(1.0 - sum(_negative_binomial(k, tot_shots, disp_shots) for k in range(22)), 4)
        over_235_total_shots = round(1.0 - sum(_negative_binomial(k, tot_shots, disp_shots) for k in range(24)), 4)
        over_255_total_shots = round(1.0 - sum(_negative_binomial(k, tot_shots, disp_shots) for k in range(26)), 4)
        over_275_total_shots = round(1.0 - sum(_negative_binomial(k, tot_shots, disp_shots) for k in range(28)), 4)
        over_295_total_shots = round(1.0 - sum(_negative_binomial(k, tot_shots, disp_shots) for k in range(30)), 4)
        under_245_total_shots = round(sum(_negative_binomial(k, tot_shots, disp_shots) for k in range(25)), 4)
        under_265_total_shots = round(sum(_negative_binomial(k, tot_shots, disp_shots) for k in range(27)), 4)

    over_115_shots_home = None
    over_135_shots_home = None
    over_155_shots_home = None
    over_175_shots_home = None
    under_85_shots_home = None
    under_95_shots_home = None
    if total_shots_home is not None and total_shots_home > 0:
        over_115_shots_home = round(1.0 - sum(_negative_binomial(k, total_shots_home, disp_shots) for k in range(12)), 4)
        over_135_shots_home = round(1.0 - sum(_negative_binomial(k, total_shots_home, disp_shots) for k in range(14)), 4)
        over_155_shots_home = round(1.0 - sum(_negative_binomial(k, total_shots_home, disp_shots) for k in range(16)), 4)
        over_175_shots_home = round(1.0 - sum(_negative_binomial(k, total_shots_home, disp_shots) for k in range(18)), 4)
        under_85_shots_home = round(sum(_negative_binomial(k, total_shots_home, disp_shots) for k in range(9)), 4)
        under_95_shots_home = round(sum(_negative_binomial(k, total_shots_home, disp_shots) for k in range(10)), 4)

    over_115_shots_away = None
    over_135_shots_away = None
    under_85_shots_away = None
    under_95_shots_away = None
    if total_shots_away is not None and total_shots_away > 0:
        over_115_shots_away = round(1.0 - sum(_negative_binomial(k, total_shots_away, disp_shots) for k in range(12)), 4)
        over_135_shots_away = round(1.0 - sum(_negative_binomial(k, total_shots_away, disp_shots) for k in range(14)), 4)
        under_85_shots_away = round(sum(_negative_binomial(k, total_shots_away, disp_shots) for k in range(9)), 4)
        under_95_shots_away = round(sum(_negative_binomial(k, total_shots_away, disp_shots) for k in range(10)), 4)

    # Tiros al Arco (Shots on Goal)
    shots_home = _expected_count(home_matches, away_matches, True, False, "shots_on_goal")
    shots_away = _expected_count(away_matches, home_matches, False, True, "shots_on_goal")
    if altitude_impact:
        if shots_home is not None:
            shots_home = round(shots_home * altitude_impact["shots_home_mult"], 2)
        if shots_away is not None:
            shots_away = round(shots_away * altitude_impact["shots_away_mult"], 2)
    tot_shots_on = (
        round(shots_home + shots_away, 2)
        if (shots_home is not None and shots_away is not None)
        else None
    )
    over_75_shots_on = None
    over_85_shots_on = None
    over_95_shots_on = None
    over_105_shots_on = None
    under_85_shots_on = None
    under_95_shots_on = None
    if tot_shots_on is not None and tot_shots_on > 0:
        over_75_shots_on = round(1.0 - sum(_negative_binomial(k, tot_shots_on, disp_shots) for k in range(8)), 4)
        over_85_shots_on = round(1.0 - sum(_negative_binomial(k, tot_shots_on, disp_shots) for k in range(9)), 4)
        over_95_shots_on = round(1.0 - sum(_negative_binomial(k, tot_shots_on, disp_shots) for k in range(10)), 4)
        over_105_shots_on = round(1.0 - sum(_negative_binomial(k, tot_shots_on, disp_shots) for k in range(11)), 4)
        under_85_shots_on = round(sum(_negative_binomial(k, tot_shots_on, disp_shots) for k in range(9)), 4)
        under_95_shots_on = round(sum(_negative_binomial(k, tot_shots_on, disp_shots) for k in range(10)), 4)

    over_45_shots_on_home = None
    over_55_shots_on_home = None
    over_65_shots_on_home = None
    over_75_shots_on_home = None
    under_25_shots_on_home = None
    under_35_shots_on_home = None
    if shots_home is not None and shots_home > 0:
        over_45_shots_on_home = round(1.0 - sum(_negative_binomial(k, shots_home, disp_shots) for k in range(5)), 4)
        over_55_shots_on_home = round(1.0 - sum(_negative_binomial(k, shots_home, disp_shots) for k in range(6)), 4)
        over_65_shots_on_home = round(1.0 - sum(_negative_binomial(k, shots_home, disp_shots) for k in range(7)), 4)
        over_75_shots_on_home = round(1.0 - sum(_negative_binomial(k, shots_home, disp_shots) for k in range(8)), 4)
        under_25_shots_on_home = round(sum(_negative_binomial(k, shots_home, disp_shots) for k in range(3)), 4)
        under_35_shots_on_home = round(sum(_negative_binomial(k, shots_home, disp_shots) for k in range(4)), 4)

    over_35_shots_on_away = None
    over_45_shots_on_away = None
    under_25_shots_on_away = None
    under_35_shots_on_away = None
    if shots_away is not None and shots_away > 0:
        over_35_shots_on_away = round(1.0 - sum(_negative_binomial(k, shots_away, disp_shots) for k in range(4)), 4)
        over_45_shots_on_away = round(1.0 - sum(_negative_binomial(k, shots_away, disp_shots) for k in range(5)), 4)
        under_25_shots_on_away = round(sum(_negative_binomial(k, shots_away, disp_shots) for k in range(3)), 4)
        under_35_shots_on_away = round(sum(_negative_binomial(k, shots_away, disp_shots) for k in range(4)), 4)

    # Tiros al Palo (Hit Woodwork)
    woodwork_home = _expected_count(home_matches, away_matches, True, False, "hit_woodwork")
    woodwork_away = _expected_count(away_matches, home_matches, False, True, "hit_woodwork")
    tot_woodwork = (
        round(woodwork_home + woodwork_away, 2)
        if (woodwork_home is not None and woodwork_away is not None)
        else None
    )
    over_05_woodwork = None
    if tot_woodwork is not None and tot_woodwork > 0:
        over_05_woodwork = round(1.0 - math.exp(-tot_woodwork), 4)

    cards_home = _expected_count(home_matches, away_matches, True, False, CARDS_KEY)
    cards_away = _expected_count(away_matches, home_matches, False, True, CARDS_KEY)
    team_cards = (cards_home, cards_away)
    cards_home, cards_away = apply_referee_factor(cards_home, cards_away, referee_cards)
    if params.dispersion_cards is None:
        referee_applied = (cards_home, cards_away) != team_cards
        disp_cards = min(
            disp_cards, CARDS_DISPERSION_WITH_REFEREE if referee_applied else CARDS_DISPERSION_WITHOUT_REFEREE
        )
    total_cards = (cards_home + cards_away) if (cards_home is not None and cards_away is not None) else None
    over_15_cards = None
    over_25_cards = None
    over_35_cards = None
    over_45_cards = None
    if total_cards is not None and total_cards > 0:
        p_under_2 = sum(_negative_binomial(k, total_cards, disp_cards) for k in range(2))
        p_under_3 = sum(_negative_binomial(k, total_cards, disp_cards) for k in range(3))
        p_under_4 = sum(_negative_binomial(k, total_cards, disp_cards) for k in range(4))
        p_under_5 = sum(_negative_binomial(k, total_cards, disp_cards) for k in range(5))
        over_15_cards = round(1.0 - p_under_2, 4)
        over_25_cards = round(1.0 - p_under_3, 4)
        over_35_cards = round(1.0 - p_under_4, 4)
        over_45_cards = round(1.0 - p_under_5, 4)

    over_15_cards_home = None
    over_25_cards_home = None
    if cards_home is not None and cards_home > 0:
        p_card_h_under_2 = sum(_negative_binomial(k, cards_home, disp_cards) for k in range(2))
        p_card_h_under_3 = sum(_negative_binomial(k, cards_home, disp_cards) for k in range(3))
        over_15_cards_home = round(1.0 - p_card_h_under_2, 4)
        over_25_cards_home = round(1.0 - p_card_h_under_3, 4)

    over_15_cards_away = None
    over_25_cards_away = None
    if cards_away is not None and cards_away > 0:
        p_card_a_under_2 = sum(_negative_binomial(k, cards_away, disp_cards) for k in range(2))
        p_card_a_under_3 = sum(_negative_binomial(k, cards_away, disp_cards) for k in range(3))
        over_15_cards_away = round(1.0 - p_card_a_under_2, 4)
        over_25_cards_away = round(1.0 - p_card_a_under_3, 4)

    offsides_home = _expected_count(home_matches, away_matches, True, False, "offsides")
    offsides_away = _expected_count(away_matches, home_matches, False, True, "offsides")

    total_offsides = (
        round(offsides_home + offsides_away, 2)
        if (offsides_home is not None and offsides_away is not None)
        else None
    )
    over_25_offsides = None
    over_35_offsides = None
    under_25_offsides = None
    under_35_offsides = None
    under_45_offsides = None
    if total_offsides is not None and total_offsides > 0:
        p_off_under_3 = sum(_negative_binomial(k, total_offsides, disp_offsides) for k in range(3))
        p_off_under_4 = sum(_negative_binomial(k, total_offsides, disp_offsides) for k in range(4))
        p_off_under_5 = sum(_negative_binomial(k, total_offsides, disp_offsides) for k in range(5))
        over_25_offsides = round(1.0 - p_off_under_3, 4)
        over_35_offsides = round(1.0 - p_off_under_4, 4)
        under_25_offsides = round(p_off_under_3, 4)
        under_35_offsides = round(p_off_under_4, 4)
        under_45_offsides = round(p_off_under_5, 4)

    over_15_offsides_home = None
    under_15_offsides_home = None
    if offsides_home is not None and offsides_home > 0:
        p_off_h_under_2 = sum(_negative_binomial(k, offsides_home, disp_offsides) for k in range(2))
        over_15_offsides_home = round(1.0 - p_off_h_under_2, 4)
        under_15_offsides_home = round(p_off_h_under_2, 4)

    over_15_offsides_away = None
    under_15_offsides_away = None
    if offsides_away is not None and offsides_away > 0:
        p_off_a_under_2 = sum(_negative_binomial(k, offsides_away, disp_offsides) for k in range(2))
        over_15_offsides_away = round(1.0 - p_off_a_under_2, 4)
        under_15_offsides_away = round(p_off_a_under_2, 4)

    home_baseline = _team_baseline_stat(home_matches, "shots_on_goal")
    away_baseline = _team_baseline_stat(away_matches, "shots_on_goal")

    scale_home = (shots_home / home_baseline) if (shots_home and home_baseline and home_baseline > 0) else 1.0
    scale_away = (shots_away / away_baseline) if (shots_away and away_baseline and away_baseline > 0) else 1.0

    if elo_home is not None and elo_away is not None:
        elo_diff = max(-400.0, min(400.0, elo_home - elo_away))
        scale_home *= math.exp(elo_diff / 2_000)
        scale_away *= math.exp(-elo_diff / 2_000)

    if altitude_impact:
        scale_home *= altitude_impact["shots_home_mult"]
        scale_away *= altitude_impact["shots_away_mult"]

    scale_home = _clamp(scale_home, 0.45, 1.65)
    scale_away = _clamp(scale_away, 0.45, 1.65)

    fouls_home = _expected_count(home_matches, away_matches, True, False, "fouls")
    fouls_away = _expected_count(away_matches, home_matches, False, True, "fouls")
    corners_first_half = round(total_corners * 0.45, 2) if total_corners is not None else None

    return ExpectedMetrics(
        corners_home=corners_home,
        corners_away=corners_away,
        corners_first_half=corners_first_half,
        fouls_home=fouls_home,
        fouls_away=fouls_away,
        dispersion_fouls=0.12,
        corners_1x2_home=corners_1x2_home,
        corners_1x2_tie=corners_1x2_tie,
        corners_1x2_away=corners_1x2_away,
        over_75_corners=over_75_corners,
        over_85_corners=over_85_corners,
        over_95_corners=over_95_corners,
        over_105_corners=over_105_corners,
        over_115_corners=over_115_corners,
        under_105_corners=under_105_corners,
        over_45_corners_home=over_45_corners_home,
        over_45_corners_away=over_45_corners_away,
        under_35_corners_home=under_35_corners_home,
        under_35_corners_away=under_35_corners_away,
        under_45_corners_home=under_45_corners_home,
        under_45_corners_away=under_45_corners_away,
        over_55_corners_home=over_55_corners_home,
        over_55_corners_away=over_55_corners_away,
        over_65_corners_home=over_65_corners_home,
        over_65_corners_away=over_65_corners_away,
        total_shots_home=total_shots_home,
        total_shots_away=total_shots_away,
        over_215_total_shots=over_215_total_shots,
        over_235_total_shots=over_235_total_shots,
        over_255_total_shots=over_255_total_shots,
        over_275_total_shots=over_275_total_shots,
        over_295_total_shots=over_295_total_shots,
        under_245_total_shots=under_245_total_shots,
        under_265_total_shots=under_265_total_shots,
        over_115_shots_home=over_115_shots_home,
        over_135_shots_home=over_135_shots_home,
        over_155_shots_home=over_155_shots_home,
        over_175_shots_home=over_175_shots_home,
        over_115_shots_away=over_115_shots_away,
        over_135_shots_away=over_135_shots_away,
        under_85_shots_home=under_85_shots_home,
        under_95_shots_home=under_95_shots_home,
        under_85_shots_away=under_85_shots_away,
        under_95_shots_away=under_95_shots_away,
        shots_on_home=shots_home,
        shots_on_away=shots_away,
        over_75_shots_on=over_75_shots_on,
        over_85_shots_on=over_85_shots_on,
        over_95_shots_on=over_95_shots_on,
        over_105_shots_on=over_105_shots_on,
        under_85_shots_on=under_85_shots_on,
        under_95_shots_on=under_95_shots_on,
        over_45_shots_on_home=over_45_shots_on_home,
        over_55_shots_on_home=over_55_shots_on_home,
        over_65_shots_on_home=over_65_shots_on_home,
        over_75_shots_on_home=over_75_shots_on_home,
        under_25_shots_on_home=under_25_shots_on_home,
        under_35_shots_on_home=under_35_shots_on_home,
        over_35_shots_on_away=over_35_shots_on_away,
        over_45_shots_on_away=over_45_shots_on_away,
        under_25_shots_on_away=under_25_shots_on_away,
        under_35_shots_on_away=under_35_shots_on_away,
        woodwork_home=woodwork_home,
        woodwork_away=woodwork_away,
        over_05_woodwork=over_05_woodwork,
        cards_home=cards_home,
        cards_away=cards_away,
        over_15_cards=over_15_cards,
        over_25_cards=over_25_cards,
        over_35_cards=over_35_cards,
        over_45_cards=over_45_cards,
        over_15_cards_home=over_15_cards_home,
        over_15_cards_away=over_15_cards_away,
        over_25_cards_home=over_25_cards_home,
        over_25_cards_away=over_25_cards_away,
        dispersion_corners=disp_corners,
        dispersion_cards=disp_cards,
        dispersion_shots=disp_shots,
        dispersion_offsides=disp_offsides,
        offsides_home=offsides_home,
        offsides_away=offsides_away,
        over_25_offsides=over_25_offsides,
        over_35_offsides=over_35_offsides,
        under_25_offsides=under_25_offsides,
        under_35_offsides=under_35_offsides,
        under_45_offsides=under_45_offsides,
        over_15_offsides_home=over_15_offsides_home,
        over_15_offsides_away=over_15_offsides_away,
        under_15_offsides_home=under_15_offsides_home,
        under_15_offsides_away=under_15_offsides_away,
        player_shots={
            home_id: _player_probabilities(player_rows, home_id, scale_factor=scale_home, starter_info=starter_info),
            away_id: _player_probabilities(player_rows, away_id, scale_factor=scale_away, starter_info=starter_info),
        },
        anytime_goalscorers={
            home_id: _anytime_goalscorer_probabilities(player_rows, home_id, scale_factor=scale_home, starter_info=starter_info),
            away_id: _anytime_goalscorer_probabilities(player_rows, away_id, scale_factor=scale_away, starter_info=starter_info),
        },
    )


def _bivariate_dixon_coles_matrix(
    lambda_home: float,
    lambda_away: float,
    shared_component: float,
    rho: float,
    max_goals: int,
) -> list[list[float]]:
    """Poisson bivariado con Dixon-Coles para dependencia adicional en marcadores bajos.

    X = U + W e Y = V + W; W representa el componente compartido de goles.
    Las tasas marginales de local y visitante se mantienen en lambda_home/lambda_away.
    """
    matrix: list[list[float]] = []
    for home_goals in range(max_goals + 1):
        row: list[float] = []
        for away_goals in range(max_goals + 1):
            probability = _bivariate_poisson(
                home_goals, away_goals, lambda_home, lambda_away, shared_component
            )
            probability *= _dc_tau(home_goals, away_goals, lambda_home, lambda_away, rho)
            row.append(max(0.0, probability))
        matrix.append(row)
    total = sum(map(sum, matrix))
    return [[value / total for value in row] for row in matrix]


def _bivariate_poisson(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    shared_component: float,
) -> float:
    shared = _clamp(shared_component, 0.0, min(lambda_home, lambda_away) - 1e-9)
    independent_home = lambda_home - shared
    independent_away = lambda_away - shared
    probability = 0.0
    for common_goals in range(min(home_goals, away_goals) + 1):
        probability += (
            independent_home ** (home_goals - common_goals)
            * independent_away ** (away_goals - common_goals)
            * shared**common_goals
            / (
                math.factorial(home_goals - common_goals)
                * math.factorial(away_goals - common_goals)
                * math.factorial(common_goals)
            )
        )
    return math.exp(-(independent_home + independent_away + shared)) * probability


def _dc_tau(home: int, away: int, lh: float, la: float, rho: float) -> float:
    if home == 0 and away == 0:
        return 1.0 - lh * la * rho
    if home == 0 and away == 1:
        return 1.0 + lh * rho
    if home == 1 and away == 0:
        return 1.0 + la * rho
    if home == 1 and away == 1:
        return 1.0 - rho
    return 1.0


def _negative_binomial(k: int, rate: float, alpha: float = 0.0) -> float:
    """Distribución Binomial Negativa parametrizada por media (rate) y dispersión (alpha).
    
    Var = rate + alpha * rate^2.
    Para alpha <= 1e-6, converge de forma exacta a Poisson estándar.
    Utiliza math.lgamma para garantizar estabilidad numérica ante recuentos elevados.
    """
    if rate <= 0.0 or k < 0:
        return 1.0 if (rate <= 0.0 and k == 0) else 0.0
    if alpha <= 1e-6:
        log_p = -rate + k * math.log(rate) - math.lgamma(k + 1)
        return math.exp(log_p)
    r = 1.0 / alpha
    p = 1.0 / (1.0 + alpha * rate)
    log_p = (
        math.lgamma(k + r)
        - math.lgamma(k + 1)
        - math.lgamma(r)
        + r * math.log(p)
        + k * math.log(1.0 - p)
    )
    return math.exp(log_p)


negative_binomial_pmf = _negative_binomial


def _poisson(k: int, rate: float) -> float:
    """Alias retrocompatible para Poisson estándar."""
    return _negative_binomial(k, rate, 0.0)


# Estadísticas de evento raro que Sportmonks solo publica cuando ocurren: en un partido
# con estadísticas completas, su ausencia significa 0 (no "dato faltante"). Promediar
# solo los partidos donde aparecen infla la proyección (p. ej. tiros al palo).
# Las tarjetas también se omiten cuando un equipo no recibe ninguna.
SPARSE_EVENT_KEYS = frozenset({"hit_woodwork", "yellow_cards", "red_cards"})
# Clave compuesta: tarjetas totales = amarillas + rojas, como liquidan las casas de apuestas.
CARDS_KEY = "cards"
_DETAIL_MARKER_KEYS = ("total_shots", "shots_on_goal", "corner_kicks")


def stat_value(stats: dict[str, float], key: str) -> float | None:
    """Valor de una estadística, tratando como 0 los eventos raros ausentes en partidos detallados."""
    if key == CARDS_KEY:
        yellow = stat_value(stats, "yellow_cards")
        red = stat_value(stats, "red_cards")
        if yellow is None and red is None:
            return None
        return (yellow or 0.0) + (red or 0.0)
    if key in stats:
        return float(stats[key])
    if key in SPARSE_EVENT_KEYS and any(marker in stats for marker in _DETAIL_MARKER_KEYS):
        return 0.0
    return None


def _expected_count(
    attacking: list[TeamMatch],
    defending: list[TeamMatch],
    attacking_home: bool,
    defending_home: bool,
    key: str,
) -> float | None:
    # 1. Priorizar partidos oficiales sobre amistosos
    with_att = [m for m in attacking if stat_value(m.stats_for, key) is not None]
    official_att = [m for m in with_att if m.competition_weight >= 0.70]
    att_base = official_att if len(official_att) >= 3 else with_att
    att_venue = [m for m in att_base if m.is_home == attacking_home]
    attack_pool = att_venue if len(att_venue) >= 3 else att_base

    with_def = [m for m in defending if stat_value(m.stats_against, key) is not None]
    official_def = [m for m in with_def if m.competition_weight >= 0.70]
    def_base = official_def if len(official_def) >= 3 else with_def
    def_venue = [m for m in def_base if m.is_home == defending_home]
    defence_pool = def_venue if len(def_venue) >= 3 else def_base

    if len(attack_pool) < 2 or len(defence_pool) < 2:
        return None

    # Ponderación temporal + peso de competición (atenúa amistosos a 0.35)
    att_values = [stat_value(m.stats_for, key) or 0.0 for m in attack_pool]
    att_weights = [(0.86**i) * m.competition_weight for i, m in enumerate(attack_pool)]
    total_att_w = sum(att_weights)
    attack_mean = (
        sum(v * w for v, w in zip(att_values, att_weights)) / total_att_w
        if total_att_w > 0
        else _robust_count_mean(att_values)
    )

    def_values = [stat_value(m.stats_against, key) or 0.0 for m in defence_pool]
    def_weights = [(0.86**i) * m.competition_weight for i, m in enumerate(defence_pool)]
    total_def_w = sum(def_weights)
    allowed_mean = (
        sum(v * w for v, w in zip(def_values, def_weights)) / total_def_w
        if total_def_w > 0
        else _robust_count_mean(def_values)
    )

    return round((attack_mean + allowed_mean) / 2.0, 2)


def _team_baseline_stat(matches: list[TeamMatch], key: str) -> float | None:
    official = [m for m in matches if m.competition_weight >= 0.70 and key in m.stats_for]
    pool = official if len(official) >= 3 else [m for m in matches if key in m.stats_for]
    if len(pool) < 2:
        return None
    values = [float(m.stats_for[key]) for m in pool]
    weights = [(0.86**i) * m.competition_weight for i, m in enumerate(pool)]
    total_w = sum(weights)
    return round(sum(v * w for v, w in zip(values, weights)) / total_w, 2) if total_w > 0 else _robust_count_mean(values)


# Minutos mínimos para contar un partido como titular en el historial del jugador.
PLAYER_START_MINUTES = 45.0


# Peso máximo del árbitro en la proyección de tarjetas y partidos de "prior" para encogerlo.
# Validado walk-forward en 543 partidos (Brasileirão, Liga MX, Argentina, Bundesliga, LaLiga;
# árbitro medido sin la temporada del partido): Brier de líneas de tarjetas 0.2075 -> 0.1935,
# mejora en las 5 ligas.
REFEREE_MAX_WEIGHT = 0.75
REFEREE_PRIOR_MATCHES = 15
REFEREE_MIN_MATCHES = 5
# Dispersión binomial negativa de tarjetas validada: con árbitro las tarjetas son casi
# Poisson (0.05); sin árbitro, 0.15 (los perfiles de liga usaban 0.20-0.28 y sobreestimaban
# la variación, inflando los "Menos de").
CARDS_DISPERSION_WITH_REFEREE = 0.05
CARDS_DISPERSION_WITHOUT_REFEREE = 0.15


def apply_referee_factor(
    cards_home: float | None,
    cards_away: float | None,
    referee_cards: tuple[float, int] | None,
) -> tuple[float | None, float | None]:
    """Mezcla la proyección de tarjetas de los equipos con el promedio del árbitro asignado.

    Las tarjetas dependen mucho del árbitro. Su promedio (amarillas + rojas por partido)
    pesa más cuantos más partidos dirigió, hasta REFEREE_MAX_WEIGHT; el reparto entre
    local y visitante se mantiene.
    """
    if cards_home is None or cards_away is None or not referee_cards:
        return cards_home, cards_away
    referee_avg, matches = referee_cards
    team_total = cards_home + cards_away
    if matches < REFEREE_MIN_MATCHES or team_total <= 0 or referee_avg <= 0:
        return cards_home, cards_away
    weight = REFEREE_MAX_WEIGHT * matches / (matches + REFEREE_PRIOR_MATCHES)
    scale = ((1.0 - weight) * team_total + weight * referee_avg) / team_total
    return round(cards_home * scale, 2), round(cards_away * scale, 2)


def _player_probabilities(
    rows: list[PlayerShot],
    team_id: int,
    scale_factor: float = 1.0,
    starter_info: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    grouped: defaultdict[int, list[PlayerShot]] = defaultdict(list)
    for row in rows:
        if row.team_id == team_id:
            grouped[row.player_id].append(row)
    result: list[dict[str, Any]] = []
    for entries in grouped.values():
        if len(entries) < 2 or sum(item.minutes for item in entries) < 90:
            continue
        shots_sum = sum(
            item.total_shots if item.total_shots > 0 else max(item.shots_on_target, item.shots_on_target * 2.2)
            for item in entries
        )
        total_minutes = sum(item.minutes for item in entries)
        per90 = shots_sum / total_minutes * 90
        sot_sum = sum(item.shots_on_target for item in entries)
        sot_per90 = sot_sum / total_minutes * 90
        # Historial real partido a partido (solo como titular y con remates publicados),
        # que justifica y valida las props del jugador.
        starts = [item for item in entries if item.minutes >= PLAYER_START_MINUTES]
        history_shots = [item.total_shots for item in starts if item.total_shots_known]
        history_sot = [item.shots_on_target for item in starts]

        # Titularidad y minutos esperados
        p_info = starter_info.get(entries[0].player_id) if starter_info else None
        if p_info:
            is_starter = p_info.get("is_starter", True)
            expected_mins = float(p_info.get("expected_minutes", 75.0 if is_starter else 22.0))
        else:
            avg_hist_mins = total_minutes / len(entries)
            expected_mins = float(max(20.0, min(90.0, avg_hist_mins)))
            is_starter = None

        min_scale = expected_mins / 90.0

        # Ajuste dinámico por volumen esperado del equipo, titularidad y dificultad del rival.
        expected = min(8.0, per90 * min_scale * 0.82 * scale_factor)
        expected_sot = min(5.0, sot_per90 * min_scale * 0.82 * scale_factor)

        # Probabilidades Poisson para Tiros Totales (Remates)
        p0 = math.exp(-expected)
        p1 = expected * p0
        p2 = (expected**2 / 2.0) * p0
        p3 = (expected**3 / 6.0) * p0
        p4 = (expected**4 / 24.0) * p0

        prob_1_plus = max(0.0, min(1.0, 1.0 - p0))
        prob_2_plus = max(0.0, min(1.0, 1.0 - (p0 + p1)))
        prob_3_plus = max(0.0, min(1.0, 1.0 - (p0 + p1 + p2)))
        prob_4_plus = max(0.0, min(1.0, 1.0 - (p0 + p1 + p2 + p3)))
        prob_5_plus = max(0.0, min(1.0, 1.0 - (p0 + p1 + p2 + p3 + p4)))

        # Probabilidades Poisson para Tiros al Arco (Shots on Target)
        s0 = math.exp(-expected_sot)
        s1 = expected_sot * s0
        s2 = (expected_sot**2 / 2.0) * s0

        prob_sot_1 = max(0.0, min(1.0, 1.0 - s0))
        prob_sot_2 = max(0.0, min(1.0, 1.0 - (s0 + s1)))
        prob_sot_3 = max(0.0, min(1.0, 1.0 - (s0 + s1 + s2)))

        result.append(
            {
                "player_id": entries[0].player_id,
                "name": entries[0].name,
                "appearances": len(entries),
                "is_starter": is_starter,
                "expected_minutes": round(expected_mins, 1),
                "expected_total_shots": round(expected, 2),
                "expected_shots_on_target": round(expected_sot, 2),
                "probability_one_plus": round(prob_1_plus, 4),
                "probability_two_plus": round(prob_2_plus, 4),
                "probability_three_plus": round(prob_3_plus, 4),
                "probability_four_plus": round(prob_4_plus, 4),
                "probability_five_plus": round(prob_5_plus, 4),
                "probability_sot_one_plus": round(prob_sot_1, 4),
                "probability_sot_two_plus": round(prob_sot_2, 4),
                "probability_sot_three_plus": round(prob_sot_3, 4),
                "history_shots": history_shots,
                "history_sot": history_sot,
            }
        )
    result.sort(key=lambda item: item["probability_two_plus"], reverse=True)
    return result[:3]


def _anytime_goalscorer_probabilities(
    rows: list[PlayerShot],
    team_id: int,
    scale_factor: float = 1.0,
    starter_info: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    grouped: defaultdict[int, list[PlayerShot]] = defaultdict(list)
    for row in rows:
        if row.team_id == team_id:
            grouped[row.player_id].append(row)
    result: list[dict[str, Any]] = []
    for entries in grouped.values():
        if len(entries) < 2 or sum(item.minutes for item in entries) < 90:
            continue
        goals_sum = sum(item.goals for item in entries)
        shots_sum = sum(item.total_shots for item in entries)
        shots_on = sum(item.shots_on_target for item in entries)

        # Si el jugador no ha tenido ni tiros ni goles en la muestra, no se le inventa probabilidad
        if goals_sum == 0 and shots_sum == 0 and shots_on == 0:
            continue

        total_minutes = sum(item.minutes for item in entries)
        effective_shots = shots_sum if shots_sum > 0 else shots_on * 2.2

        if goals_sum > 0:
            base_rate = (goals_sum / total_minutes * 90.0) * 0.70 + (effective_shots / total_minutes * 90.0 * 0.12) * 0.30
        else:
            base_rate = (effective_shots / total_minutes * 90.0 * 0.12)

        p_info = starter_info.get(entries[0].player_id) if starter_info else None
        if p_info:
            is_starter = p_info.get("is_starter", True)
            expected_mins = float(p_info.get("expected_minutes", 75.0 if is_starter else 22.0))
        else:
            avg_hist_mins = total_minutes / len(entries)
            expected_mins = float(max(20.0, min(90.0, avg_hist_mins)))
            is_starter = None

        min_scale = expected_mins / 90.0
        expected_goals = min(1.25, base_rate * min_scale * 0.85 * scale_factor)
        if expected_goals < 0.05:
            continue

        prob_goal = min(0.92, 1.0 - math.exp(-expected_goals))
        result.append(
            {
                "player_id": entries[0].player_id,
                "name": entries[0].name,
                "appearances": len(entries),
                "is_starter": is_starter,
                "expected_minutes": round(expected_mins, 1),
                "goals_observed": goals_sum,
                "expected_goals": round(expected_goals, 2),
                "probability_goal": round(prob_goal, 4),
                "history_goals": [item.goals for item in entries if item.minutes >= PLAYER_START_MINUTES],
            }
        )
    result.sort(key=lambda item: item["probability_goal"], reverse=True)
    return result[:3]


def _team_stat_blocks(blocks: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    result: dict[int, dict[str, float]] = {}
    for block in blocks or []:
        team_id = block.get("team", {}).get("id")
        if team_id is None:
            continue
        values: dict[str, float] = {}
        for item in block.get("statistics", []) or []:
            mapped = STAT_KEYS.get(item.get("type"))
            value = _number(item.get("value"))
            if mapped and value is not None:
                values[mapped] = value
        result[int(team_id)] = values
    return result


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _venue_or_all(
    matches: list[TeamMatch], home: bool | None, attr: str, use_sos: bool = False
) -> float:
    official = [m for m in matches if m.competition_weight >= 0.70]
    base_pool = official if len(official) >= 3 else matches
    if home is not None:
        venue_matches = [m for m in base_pool if m.is_home == home]
        pool = venue_matches if len(venue_matches) >= 3 else base_pool
    else:
        pool = base_pool
    values = [
        float(getattr(match, attr))
        * (get_sos_multiplier(match.opponent_name, match.league_id, attr) if use_sos else 1.0)
        for match in pool
    ]
    weights = [(0.86**i) * match.competition_weight for i, match in enumerate(pool)]
    total_w = sum(weights)
    if total_w > 0:
        return sum(v * w for v, w in zip(values, weights)) / total_w
    return _weighted_mean(values)


def _goal_signal(
    matches: list[TeamMatch],
    home: bool | None,
    goals_attribute: str,
    stats_attribute: str,
    use_sos: bool = False,
    xg_weight: float = 0.35,
) -> float:
    """Mezcla goles observados y xG cuando hay xG para una muestra suficiente (3+ partidos).

    El xG llega de Flashscore (``deport_ai.flashscore``); el plan de Sportmonks no lo trae.
    ``xg_weight`` = 0 reproduce el modelo solo con goles.
    """
    goals = _venue_or_all(matches, home, goals_attribute, use_sos)
    if xg_weight <= 0:
        return goals
    if home is not None:
        xg = _venue_stat_or_none(matches, home, stats_attribute, "expected_goals")
    else:
        xg = _stat_or_none(matches, stats_attribute, "expected_goals")
    return goals if xg is None else goals * (1.0 - xg_weight) + xg * xg_weight


def _stat_or_none(matches: list[TeamMatch], attribute: str, key: str) -> float | None:
    """Media ponderada por recencia de una estadística en todos los partidos que la tienen."""
    pool = [match for match in matches if key in getattr(match, attribute)]
    if len(pool) < 3:
        return None
    values = [getattr(match, attribute)[key] for match in pool]
    weights = [(0.86**i) * match.competition_weight for i, match in enumerate(pool)]
    total_w = sum(weights)
    if total_w > 0:
        return sum(v * w for v, w in zip(values, weights)) / total_w
    return _weighted_mean(values)


def _venue_stat_or_none(
    matches: list[TeamMatch], home: bool, attribute: str, key: str
) -> float | None:
    venue_matches = [
        match
        for match in matches
        if match.is_home == home and key in getattr(match, attribute)
    ]
    pool = venue_matches if len(venue_matches) >= 3 else [
        match for match in matches if key in getattr(match, attribute)
    ]
    if len(pool) < 3:
        return None
    values = [getattr(match, attribute)[key] for match in pool]
    weights = [(0.86**i) * match.competition_weight for i, match in enumerate(pool)]
    total_w = sum(weights)
    if total_w > 0:
        return sum(v * w for v, w in zip(values, weights)) / total_w
    return _weighted_mean(values)


def _estimate_shared_goal_component(
    home_matches: list[TeamMatch],
    away_matches: list[TeamMatch],
    lambda_home: float,
    lambda_away: float,
) -> float:
    """Estima la covarianza de goles desde la apertura observada de los partidos recientes."""
    mutual_goals = [
        float(min(match.goals_for, match.goals_against)) for match in home_matches + away_matches
    ]
    observed_openness = _weighted_mean(mutual_goals)
    unconstrained = 0.04 + 0.12 * observed_openness
    return round(_clamp(unconstrained, 0.0, min(0.30, min(lambda_home, lambda_away) * 0.30)), 4)


def _weighted_mean(values: list[float], decay: float = 0.86) -> float:
    if not values:
        raise InsufficientDataError("No hay valores suficientes para calcular el promedio.")
    weights = [decay**index for index in range(len(values))]
    return sum(value * weight for value, weight in zip(values, weights)) / sum(weights)


def _robust_count_mean(values: list[float]) -> float:
    """Evita que un único partido extremo domine muestras pequeñas."""
    if len(values) <= 4:
        return float(median(values))
    center = float(median(values))
    deviations = [abs(value - center) for value in values]
    mad = float(median(deviations))
    if mad <= 0:
        return _weighted_mean(values)
    low, high = max(0.0, center - 2.5 * mad), center + 2.5 * mad
    clipped = [max(low, min(high, value)) for value in values]
    return _weighted_mean(clipped)


def _season_goal_average(data: dict[str, Any] | None, side: str, venue: str) -> float | None:
    if not data:
        return None
    value = data.get("goals", {}).get(side, {}).get("average", {}).get(venue)
    return _number(value)


def _blend_available(recent: float, season: float | None, season_weight: float = 0.35) -> float:
    return recent if season is None else recent * (1.0 - season_weight) + season * season_weight


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sample_risks(
    home_matches: list[TeamMatch], away_matches: list[TeamMatch], expected: ExpectedMetrics
) -> list[str]:
    risks: list[str] = []
    unknown_count = sum(1 for m in home_matches + away_matches if m.competition_weight == 0.0)
    if unknown_count > 0:
        risks.append(
            f"Se detectaron {unknown_count} partidos de competiciones no verificadas (excluidos con peso 0.00 para evitar distorsiones)."
        )
    if min(len(home_matches), len(away_matches)) < 6:
        risks.append("Baja muestra estadística: menos de 6 partidos recientes por equipo.")
    if expected.corners_home is None or expected.corners_away is None:
        risks.append("La API no aportó suficientes estadísticas de córners comparables.")
    if expected.shots_on_home is None or expected.shots_on_away is None:
        risks.append("La API no aportó suficientes estadísticas de tiros al arco.")
    if not any(expected.player_shots.values()):
        risks.append("Sin muestra suficiente de tiros por jugador; no se publica esa predicción.")
    detailed_sample = min(
        sum("corner_kicks" in match.stats_for for match in home_matches),
        sum("corner_kicks" in match.stats_for for match in away_matches),
    )
    if 0 < detailed_sample < 5:
        risks.append(
            f"Córners y tiros se basan en {detailed_sample} partidos detallados por equipo; "
            "se usa una mediana robusta para limitar valores extremos."
        )
    return risks


def form_line(matches: list[TeamMatch], maximum: int = 5) -> str:
    return "-".join(match.result for match in matches[:maximum]) or "Sin datos"


def top_scores(report: ProbabilityReport, count: int = 3) -> list[tuple[str, float]]:
    scores = [
        (f"{home}-{away}", report.score_matrix[home][away])
        for home in range(len(report.score_matrix))
        for away in range(len(report.score_matrix[home]))
    ]
    return sorted(scores, key=lambda item: item[1], reverse=True)[:count]
