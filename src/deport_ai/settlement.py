from __future__ import annotations

import json
import logging
import re
from typing import Any

from .fixture_contract import FINISHED_STATUSES
from .storage import DatabaseManager

logger = logging.getLogger("deport_ai.settlement")

# Resultado de `evaluate_prediction` para mercados que el liquidador no sabe evaluar.
UNSUPPORTED = "UNSUPPORTED"
_LINE_RE = re.compile(r"\b(Más|Menos) de (\d+(?:\.\d+)?)", re.IGNORECASE)


def extract_match_actual_stats(fixture_detail: dict[str, Any]) -> dict[str, Any] | None:
    """Extrae las estadísticas finales consolidadas a partir del payload enriquecido de Sportmonks."""
    status_short = fixture_detail.get("fixture", {}).get("status", {}).get("short") or ""
    if status_short not in FINISHED_STATUSES:
        return None

    teams = fixture_detail.get("teams", {})
    home_id = int((teams.get("home") or {}).get("id") or -1)
    away_id = int((teams.get("away") or {}).get("id") or -1)

    goals = fixture_detail.get("goals", {})
    home_goals = goals.get("home")
    away_goals = goals.get("away")

    # Estadísticas de equipo
    stats_by_team: dict[int, dict[str, float]] = {}
    for block in fixture_detail.get("statistics", []):
        t_id = int((block.get("team") or {}).get("id") or -1)
        st_dict: dict[str, float] = {}
        for s in block.get("statistics", []):
            st_type = s.get("type")
            st_val = s.get("value")
            if st_type and st_val is not None:
                try:
                    st_dict[st_type] = float(st_val)
                except (ValueError, TypeError):
                    pass
        if t_id != -1:
            stats_by_team[t_id] = st_dict

    home_stats = stats_by_team.get(home_id, {})
    away_stats = stats_by_team.get(away_id, {})

    def _get_stat(d: dict[str, float], keys: tuple[str, ...]) -> int | None:
        for k in keys:
            if k in d:
                return int(d[k])
        return None

    corners_home = _get_stat(home_stats, ("Corner Kicks", "CORNERS"))
    corners_away = _get_stat(away_stats, ("Corner Kicks", "CORNERS"))

    cards_home = _get_stat(home_stats, ("Yellow Cards", "YELLOW_CARDS", "YELLOWCARDS"))
    cards_away = _get_stat(away_stats, ("Yellow Cards", "YELLOW_CARDS", "YELLOWCARDS"))
    # Sportmonks omite las tarjetas cuando un equipo no recibió ninguna: en un partido con
    # estadísticas completas, su ausencia es 0 y no un dato faltante.
    if cards_home is None and _is_detailed(home_stats):
        cards_home = 0
    if cards_away is None and _is_detailed(away_stats):
        cards_away = 0
    reds_home = _get_stat(home_stats, ("Red Cards", "RED_CARDS", "REDCARDS")) or 0
    reds_away = _get_stat(away_stats, ("Red Cards", "RED_CARDS", "REDCARDS")) or 0
    # En casas de apuestas estándar, total tarjetas suele ser amarillas + rojas (o amarillas)
    tot_cards_home = (cards_home + reds_home) if cards_home is not None else None
    tot_cards_away = (cards_away + reds_away) if cards_away is not None else None

    shots_home = _get_stat(home_stats, ("Total Shots", "SHOTS_TOTAL"))
    shots_away = _get_stat(away_stats, ("Total Shots", "SHOTS_TOTAL"))

    shots_on_home = _get_stat(home_stats, ("Shots on Goal", "SHOTS_ON_TARGET"))
    shots_on_away = _get_stat(away_stats, ("Shots on Goal", "SHOTS_ON_TARGET"))

    fouls_home = _get_stat(home_stats, ("Fouls", "FOULS"))
    fouls_away = _get_stat(away_stats, ("Fouls", "FOULS"))

    offsides_home = _get_stat(home_stats, ("Offsides", "OFFSIDES"))
    offsides_away = _get_stat(away_stats, ("Offsides", "OFFSIDES"))

    woodwork_h = _get_stat(home_stats, ("Hit Woodwork", "HIT_WOODWORK", "WOODWORK")) or 0
    woodwork_a = _get_stat(away_stats, ("Hit Woodwork", "HIT_WOODWORK", "WOODWORK")) or 0
    total_woodwork = woodwork_h + woodwork_a

    # Goles por mitad. El cliente entrega "halftime" (1T) y "second_half" (solo 2T);
    # un payload crudo trae "scores", donde "2ND_HALF" es acumulado y "2ND_HALF_ONLY" es el 2T.
    halftime = fixture_detail.get("halftime") or {}
    second = fixture_detail.get("second_half") or {}
    first_half_home = _int_or_none(halftime.get("home"))
    first_half_away = _int_or_none(halftime.get("away"))
    second_half_home = _int_or_none(second.get("home"))
    second_half_away = _int_or_none(second.get("away"))
    for sc in fixture_detail.get("scores", []) or []:
        desc = str(sc.get("description") or "").upper()
        p_id = int(sc.get("participant_id") or -1)
        g_val = _int_or_none((sc.get("score") or {}).get("goals"))
        if g_val is None or p_id not in (home_id, away_id):
            continue
        is_home = p_id == home_id
        if desc == "1ST_HALF":
            if is_home and first_half_home is None:
                first_half_home = g_val
            elif not is_home and first_half_away is None:
                first_half_away = g_val
        elif desc == "2ND_HALF_ONLY":
            if is_home and second_half_home is None:
                second_half_home = g_val
            elif not is_home and second_half_away is None:
                second_half_away = g_val

    # Si hay 1T y final pero no 2T específico, 2T = final - 1T
    if home_goals is not None and first_half_home is not None and second_half_home is None:
        second_half_home = max(0, home_goals - first_half_home)
    if away_goals is not None and first_half_away is not None and second_half_away is None:
        second_half_away = max(0, away_goals - first_half_away)

    # Jugadores
    player_stats: dict[str, dict[str, Any]] = {}
    for team_block in fixture_detail.get("players", []):
        for p in team_block.get("players", []):
            p_data = p.get("player") or {}
            p_name = str(p_data.get("name") or "").strip().lower()
            p_id = p_data.get("id")
            stats_list = p.get("statistics") or []
            if stats_list:
                s0 = stats_list[0]
                minutes = (s0.get("games") or {}).get("minutes") or 0
                shots = (s0.get("shots") or {}).get("total") or 0
                shots_on = (s0.get("shots") or {}).get("on") or 0
                p_goals = (s0.get("goals") or {}).get("total") or 0
                entry = {
                    "id": p_id,
                    "name": p_data.get("name"),
                    "minutes": minutes,
                    "shots": shots,
                    "shots_on": shots_on,
                    "goals": p_goals,
                }
                player_stats[p_name] = entry
                if p_id is not None:
                    player_stats[str(p_id)] = entry

    return {
        "home_goals": home_goals,
        "away_goals": away_goals,
        "first_half_home_goals": first_half_home,
        "first_half_away_goals": first_half_away,
        "second_half_home_goals": second_half_home,
        "second_half_away_goals": second_half_away,
        "corners_home": corners_home,
        "corners_away": corners_away,
        "cards_home": tot_cards_home,
        "cards_away": tot_cards_away,
        "shots_home": shots_home,
        "shots_away": shots_away,
        "shots_on_home": shots_on_home,
        "shots_on_away": shots_on_away,
        "offsides_home": offsides_home,
        "offsides_away": offsides_away,
        "fouls_home": fouls_home,
        "fouls_away": fouls_away,
        "woodwork_hit": total_woodwork,
        "player_stats": player_stats,
        # Si el partido tiene estadísticas completas pero no publica un dato, no se registró:
        # esas selecciones se anulan en vez de quedar pendientes para siempre.
        "detailed": _is_detailed(home_stats) and _is_detailed(away_stats),
    }


def _is_detailed(stats: dict[str, float]) -> bool:
    return any(key in stats for key in ("Corner Kicks", "Total Shots", "Shots on Goal", "CORNERS", "SHOTS_TOTAL"))


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def evaluate_prediction(
    prediction: dict[str, Any],
    actual: dict[str, Any],
    home_name: str,
    away_name: str,
) -> str:
    """Evalúa una predicción contra los resultados reales. Devuelve 'WON', 'LOST' o 'VOID'."""
    category = prediction.get("category", "")
    selection = prediction.get("selection", "")
    side = prediction.get("side")
    line = prediction.get("line")
    if line is None or side not in ("over", "under"):
        # Predicciones antiguas se guardaron sin línea: se deduce del texto ("Más de 2.5 goles").
        parsed = _LINE_RE.search(selection)
        if parsed:
            side = "over" if parsed.group(1).lower() == "más" else "under"
            line = float(parsed.group(2))

    hg = actual.get("home_goals")
    ag = actual.get("away_goals")

    # 1. CATEGORÍA: RESULTADO (1X2, Doble Oportunidad, DNB, Gana a cero)
    if category == "Resultado":
        if hg is None or ag is None:
            return "PENDING"

        # 1X2: el catálogo usa el nombre del equipo como selección.
        if selection in (home_name, f"Victoria {home_name}"):
            return "WON" if hg > ag else "LOST"
        if selection in (away_name, f"Victoria {away_name}"):
            return "WON" if ag > hg else "LOST"
        if selection == "Empate":
            return "WON" if hg == ag else "LOST"

        # Doble oportunidad
        if "(1X)" in selection:
            return "WON" if hg >= ag else "LOST"
        if "(X2)" in selection:
            return "WON" if ag >= hg else "LOST"
        if "(12)" in selection:
            return "WON" if hg != ag else "LOST"

        # DNB
        if selection.startswith("DNB"):
            if home_name in selection:
                if hg > ag:
                    return "WON"
                if hg < ag:
                    return "LOST"
                return "VOID"
            if away_name in selection:
                if ag > hg:
                    return "WON"
                if ag < hg:
                    return "LOST"
                return "VOID"

        if "gana a cero" in selection:
            if home_name in selection:
                return "WON" if hg > ag and ag == 0 else "LOST"
            if away_name in selection:
                return "WON" if ag > hg and hg == 0 else "LOST"

        # Combos Resultado + Goles
        if "(1X) y Más de 1.5" in selection:
            return "WON" if hg >= ag and (hg + ag) > 1.5 else "LOST"
        if "(X2) y Más de 1.5" in selection:
            return "WON" if ag >= hg and (hg + ag) > 1.5 else "LOST"
        if "(1X) y Menos de 3.5" in selection:
            return "WON" if hg >= ag and (hg + ag) < 3.5 else "LOST"
        if "(X2) y Menos de 3.5" in selection:
            return "WON" if ag >= hg and (hg + ag) < 3.5 else "LOST"
        if selection.endswith("y Ambos Marcan"):
            both = hg > 0 and ag > 0
            if "(1X)" in selection:
                return "WON" if both and hg >= ag else "LOST"
            if "(X2)" in selection:
                return "WON" if both and ag >= hg else "LOST"
            if selection == f"{home_name} gana y Ambos Marcan":
                return "WON" if both and hg > ag else "LOST"
            if selection == f"{away_name} gana y Ambos Marcan":
                return "WON" if both and ag > hg else "LOST"
        if "gana y Más de 1.5" in selection:
            if home_name in selection:
                return "WON" if hg > ag and (hg + ag) > 1.5 else "LOST"
            if away_name in selection:
                return "WON" if ag > hg and (hg + ag) > 1.5 else "LOST"

    # 2. CATEGORÍA: GOLES Y ANOTACIONES
    if category in ("Goles", "Goles y Anotaciones"):
        if hg is None or ag is None:
            return "PENDING"
        total_goals = hg + ag

        # Multigoles (rango cerrado de goles totales)
        multigoal = re.fullmatch(r"(\d+) a (\d+) goles", selection.strip())
        if multigoal:
            low, high = int(multigoal.group(1)), int(multigoal.group(2))
            return "WON" if low <= total_goals <= high else "LOST"

        # Combos BTTS + Over
        if "Ambos marcan y Más de 2.5" in selection:
            return "WON" if hg > 0 and ag > 0 and total_goals > 2.5 else "LOST"

        # Ambos marcan
        if selection == "Sí" or "ambos marcan: sí" in selection.lower():
            return "WON" if hg > 0 and ag > 0 else "LOST"
        if selection == "No (BTTS No)" or "ambos marcan: no" in selection.lower():
            return "WON" if hg == 0 or ag == 0 else "LOST"

        # Clean sheet
        if "no recibe gol" in selection:
            if home_name in selection:
                return "WON" if ag == 0 else "LOST"
            if away_name in selection:
                return "WON" if hg == 0 else "LOST"

        # Goles por equipo
        if home_name in selection and line is not None:
            if side == "over":
                return "WON" if hg > line else "LOST"
            if side == "under":
                return "WON" if hg < line else "LOST"
        if away_name in selection and line is not None:
            if side == "over":
                return "WON" if ag > line else "LOST"
            if side == "under":
                return "WON" if ag < line else "LOST"

        # Goles totales
        if line is not None:
            if side == "over":
                return "WON" if total_goals > line else "LOST"
            if side == "under":
                return "WON" if total_goals < line else "LOST"

    # 3. CATEGORÍA: MITADES
    if category in ("Mitades", "Mercados por Mitad"):
        fh_h = actual.get("first_half_home_goals")
        fh_a = actual.get("first_half_away_goals")
        sh_h = actual.get("second_half_home_goals")
        sh_a = actual.get("second_half_away_goals")

        if "gol en ambas mitades" in selection.lower():
            if fh_h is None or fh_a is None or sh_h is None or sh_a is None:
                return "PENDING"
            return "WON" if ((fh_h + fh_a) >= 1 and (sh_h + sh_a) >= 1) else "LOST"

        if "anota en ambas mitades" in selection.lower() or "marca en ambas mitades" in selection.lower():
            if home_name in selection:
                if fh_h is None or sh_h is None:
                    return "PENDING"
                return "WON" if (fh_h >= 1 and sh_h >= 1) else "LOST"
            if away_name in selection:
                if fh_a is None or sh_a is None:
                    return "PENDING"
                return "WON" if (fh_a >= 1 and sh_a >= 1) else "LOST"

        if "1t" in selection.lower() or "primer tiempo" in selection.lower() or "1er tiempo" in selection.lower():
            if fh_h is None or fh_a is None:
                return "PENDING"
            fh_tot = fh_h + fh_a
            if line is not None:
                return "WON" if (fh_tot > line if side == "over" else fh_tot < line) else "LOST"

        if "2t" in selection.lower() or "segundo tiempo" in selection.lower() or "2do tiempo" in selection.lower():
            if sh_h is None or sh_a is None:
                return "PENDING"
            sh_tot = sh_h + sh_a
            if line is not None:
                return "WON" if (sh_tot > line if side == "over" else sh_tot < line) else "LOST"

    # 4. CATEGORÍA: CÓRNERS
    if category == "Córners" and selection.startswith("1T "):
        # Córners del primer tiempo: sin el dato por mitad no se puede liquidar.
        c1h = actual.get("corners_first_half")
        if line is None:
            return "PENDING"
        if c1h is None:
            return "VOID" if actual.get("detailed") else "PENDING"
        return "WON" if (c1h > line if side == "over" else c1h < line) else "LOST"

    if category == "Córners":
        ch = actual.get("corners_home")
        ca = actual.get("corners_away")
        if ch is None or ca is None:
            return "PENDING"
        tot_corners = ch + ca

        if "ambos equipos sacan 3+ córners" in selection.lower():
            return "WON" if ch >= 3 and ca >= 3 else "LOST"
        if "ambos equipos sacan 4+ córners" in selection.lower():
            return "WON" if ch >= 4 and ca >= 4 else "LOST"

        if "saca más córners" in selection:
            if home_name in selection:
                return "WON" if ch > ca else "LOST"
            if away_name in selection:
                return "WON" if ca > ch else "LOST"

        if home_name in selection and line is not None:
            return "WON" if (ch > line if side == "over" else ch < line) else "LOST"
        if away_name in selection and line is not None:
            return "WON" if (ca > line if side == "over" else ca < line) else "LOST"

        if line is not None:
            return "WON" if (tot_corners > line if side == "over" else tot_corners < line) else "LOST"

    # 5. CATEGORÍA: TARJETAS
    if category == "Tarjetas":
        cards_h = actual.get("cards_home")
        cards_a = actual.get("cards_away")
        if cards_h is None or cards_a is None:
            return "PENDING"
        tot_cards = cards_h + cards_a

        if "al menos 1 tarjeta" in selection or "reciben tarjeta" in selection:
            return "WON" if cards_h >= 1 and cards_a >= 1 else "LOST"
        if "2+ tarjetas" in selection:
            return "WON" if cards_h >= 2 and cards_a >= 2 else "LOST"
        if "recibe más tarjetas" in selection:
            if home_name in selection:
                return "WON" if cards_h > cards_a else "LOST"
            if away_name in selection:
                return "WON" if cards_a > cards_h else "LOST"

        if home_name in selection and line is not None:
            return "WON" if (cards_h > line if side == "over" else cards_h < line) else "LOST"
        if away_name in selection and line is not None:
            return "WON" if (cards_a > line if side == "over" else cards_a < line) else "LOST"

        if line is not None:
            return "WON" if (tot_cards > line if side == "over" else tot_cards < line) else "LOST"

    # 6. CATEGORÍA: REMATES Y TIROS A PUERTA
    if category in ("Remates y Tiros a Puerta", "Remates", "Tiros a puerta"):
        sh_h = actual.get("shots_home")
        sh_a = actual.get("shots_away")
        sot_h = actual.get("shots_on_home")
        sot_a = actual.get("shots_on_away")

        # Tiros a puerta
        if "puerta" in selection.lower() or "arco" in selection.lower():
            if sot_h is None or sot_a is None:
                return "PENDING"
            tot_sot = sot_h + sot_a

            if "3+ tiros a puerta" in selection:
                return "WON" if sot_h >= 3 and sot_a >= 3 else "LOST"
            if "más tiros a puerta" in selection:
                if home_name in selection:
                    return "WON" if sot_h > sot_a else "LOST"
                if away_name in selection:
                    return "WON" if sot_a > sot_h else "LOST"

            if home_name in selection and line is not None:
                return "WON" if (sot_h > line if side == "over" else sot_h < line) else "LOST"
            if away_name in selection and line is not None:
                return "WON" if (sot_a > line if side == "over" else sot_a < line) else "LOST"
            if line is not None:
                return "WON" if (tot_sot > line if side == "over" else tot_sot < line) else "LOST"

        # Remates totales
        if sh_h is None or sh_a is None:
            return "PENDING"
        tot_shots = sh_h + sh_a
        if home_name in selection and line is not None:
            return "WON" if (sh_h > line if side == "over" else sh_h < line) else "LOST"
        if away_name in selection and line is not None:
            return "WON" if (sh_a > line if side == "over" else sh_a < line) else "LOST"
        if line is not None:
            return "WON" if (tot_shots > line if side == "over" else tot_shots < line) else "LOST"

    # 7. CATEGORÍA: FUERAS DE JUEGO (OFFSIDES)
    if category in ("Fueras de juego", "Fueras de Juego (Offsides)"):
        off_h = actual.get("offsides_home")
        off_a = actual.get("offsides_away")
        if off_h is None or off_a is None:
            # Sportmonks publica los fueras de juego incluso en 0: si faltan en un partido
            # con estadísticas completas, el dato no se registró y no es liquidable.
            return "VOID" if actual.get("detailed") else "PENDING"
        tot_off = off_h + off_a
        if home_name in selection and line is not None:
            return "WON" if (off_h > line if side == "over" else off_h < line) else "LOST"
        if away_name in selection and line is not None:
            return "WON" if (off_a > line if side == "over" else off_a < line) else "LOST"
        if line is not None:
            return "WON" if (tot_off > line if side == "over" else tot_off < line) else "LOST"

    # 8. CATEGORÍA: ESPECIALES (TIRO AL PALO)
    if category in ("Especiales", "Especiales del Partido"):
        if "palo" in selection.lower() or "poste" in selection.lower():
            wood = actual.get("woodwork_hit")
            if wood is None:
                return "PENDING"
            return "WON" if wood > 0 else "LOST"

    # 8b. CATEGORÍA: FALTAS
    if category in ("Faltas", "Faltas y Disciplina"):
        f_h = actual.get("fouls_home")
        f_a = actual.get("fouls_away")
        if f_h is None or f_a is None:
            return "PENDING"
        if "comete más faltas" in selection:
            if home_name in selection:
                return "WON" if f_h > f_a else "LOST"
            if away_name in selection:
                return "WON" if f_a > f_h else "LOST"
        if home_name in selection and line is not None:
            return "WON" if (f_h > line if side == "over" else f_h < line) else "LOST"
        if away_name in selection and line is not None:
            return "WON" if (f_a > line if side == "over" else f_a < line) else "LOST"
        if line is not None:
            tot_fouls = f_h + f_a
            return "WON" if (tot_fouls > line if side == "over" else tot_fouls < line) else "LOST"

    # 9. CATEGORÍA: JUGADORES
    if category == "Jugadores":
        player_stats = actual.get("player_stats")
        if not player_stats or not isinstance(player_stats, dict):
            return "PENDING"

        # Localizar al jugador por coincidencia de nombre
        matched_player: dict[str, Any] | None = None
        sel_lower = selection.lower()
        for p_key, p_val in player_stats.items():
            p_name = str(p_val.get("name") or "").lower()
            if p_name and (p_name in sel_lower or any(part in sel_lower for part in p_name.split() if len(part) > 3)):
                matched_player = p_val
                break

        if not matched_player:
            # Si el jugador no figuró en la convocatoria o no disputó minutos -> VOID
            return "VOID"

        if matched_player.get("minutes", 0) <= 0:
            return "VOID"

        p_shots = matched_player.get("shots", 0)
        p_sot = matched_player.get("shots_on", 0)
        p_goals = matched_player.get("goals", 0)

        if "4+ remates" in selection:
            return "WON" if p_shots >= 4 else "LOST"
        if "3+ remates" in selection:
            return "WON" if p_shots >= 3 else "LOST"
        if "2+ remates" in selection:
            return "WON" if p_shots >= 2 else "LOST"
        if "2+ tiros a puerta" in selection:
            return "WON" if p_sot >= 2 else "LOST"
        if "1+ tiro a puerta" in selection:
            return "WON" if p_sot >= 1 else "LOST"
        if "anota" in selection.lower():
            return "WON" if p_goals >= 1 else "LOST"

    # Mercado no reconocido por el liquidador: no se cuenta como perdido (antes sí,
    # lo que contaminaba el acierto histórico y la calibración).
    return UNSUPPORTED


class SettlementEngine:
    """Motor de liquidación y sincronización de resultados para pronósticos pendientes."""

    def __init__(self, db: DatabaseManager, api: Any) -> None:
        self.db = db
        self.api = api

    def settle_fixture(self, fixture_id: int) -> dict[str, Any]:
        """Consulta un fixture en la API, evalúa todas sus predicciones y actualiza la BD."""
        fixture_row = self.db.get_fixture(fixture_id)
        if not fixture_row:
            return {"fixture_id": fixture_id, "status": "NOT_FOUND"}

        details_dict = self.api.fixture_details([fixture_id])
        detail = details_dict.get(fixture_id)
        if not detail:
            return {"fixture_id": fixture_id, "status": "NO_API_DATA"}

        actual_stats = extract_match_actual_stats(detail)
        if not actual_stats:
            return {"fixture_id": fixture_id, "status": "STILL_PENDING_OR_IN_PLAY"}

        predictions = self.db.get_predictions_for_fixture(fixture_id)
        needs_1h_corners = any(
            p["status"] == "PENDING" and str(p.get("selection") or "").startswith("1T ") and "córner" in str(p.get("selection") or "")
            for p in predictions
        )
        if needs_1h_corners and hasattr(self.api, "first_half_corners"):
            by_team = self.api.first_half_corners(fixture_id) or {}
            home_id = int(fixture_row.get("home_team_id") or -1)
            away_id = int(fixture_row.get("away_team_id") or -1)
            if home_id in by_team and away_id in by_team:
                actual_stats["corners_first_half"] = by_team[home_id] + by_team[away_id]

        self.db.update_fixture_result(fixture_id, actual_stats, status="FINISHED")

        settled_summary = {"won": 0, "lost": 0, "void": 0, "total": len(predictions)}

        for pred in predictions:
            if pred["status"] != "PENDING":
                continue

            outcome = evaluate_prediction(
                pred,
                actual_stats,
                home_name=fixture_row["home_team_name"],
                away_name=fixture_row["away_team_name"],
            )
            if outcome == UNSUPPORTED:
                outcome = "VOID"

            odds = pred.get("odds")
            pnl = 0.0
            if outcome == "WON":
                pnl = (float(odds) - 1.0) if odds else 0.0
                settled_summary["won"] += 1
            elif outcome == "LOST":
                pnl = -1.0 if odds else 0.0
                settled_summary["lost"] += 1
            elif outcome == "VOID":
                pnl = 0.0
                settled_summary["void"] += 1

            self.db.update_prediction_status(pred["id"], outcome, pnl=round(pnl, 4))

        return {
            "fixture_id": fixture_id,
            "status": "SETTLED",
            "summary": settled_summary,
            "actual_stats": actual_stats,
        }

    def settle_all_pending(self) -> list[dict[str, Any]]:
        """Liquida todos los fixtures pendientes en la base de datos."""
        pending = self.db.get_pending_fixtures()
        results = []
        for fix in pending:
            res = self.settle_fixture(fix["fixture_id"])
            results.append(res)
        self.db.export_history()
        return results
