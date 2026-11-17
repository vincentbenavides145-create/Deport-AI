from __future__ import annotations

from typing import Any


class MarketPresentationCatalog:
    """Catálogo declarativo e independiente de presentación de mercados para DEPORT AI.

    Define estrictamente las líneas y selecciones válidas para presentación
    (referenciadas según la oferta estándar de casas de apuestas como Betano),
    excluyendo líneas triviales (+3.5 córners, +0.5 tarjetas por equipo,
    +0.5 fueras de juego por equipo, +7.5 remates) y selecciones no catalogadas.

    No contiene cuotas ni realiza consultas en tiempo real a casas de apuestas.
    """

    # Líneas numéricas permitidas por subgrupo (Over / Under)
    ALLOWED_LINES: dict[str, dict[str, set[float]]] = {
        "total_goals": {
            "over": {1.5, 2.5, 3.5, 4.5},
            "under": {1.5, 2.5, 3.5},
        },
        "home_goals": {
            "over": {1.5, 2.5},
            "under": {1.5, 2.5},
        },
        "away_goals": {
            "over": {1.5, 2.5},
            "under": {1.5, 2.5},
        },
        "corners_total": {
            "over": {7.5, 8.5, 9.5, 10.5, 11.5},
            "under": {8.5, 9.5, 10.5},
        },
        "corners_home": {
            "over": {3.5, 4.5, 5.5, 6.5},
            "under": {3.5, 4.5, 5.5},
        },
        "corners_away": {
            "over": {3.5, 4.5, 5.5, 6.5},
            "under": {3.5, 4.5, 5.5},
        },
        "cards_total": {
            "over": {3.5, 4.5, 5.5},
            "under": {3.5, 4.5},
        },
        "cards_home": {
            "over": {1.5, 2.5, 3.5},
            "under": {1.5, 2.5},
        },
        "cards_away": {
            "over": {1.5, 2.5, 3.5},
            "under": {1.5, 2.5},
        },
        "shots_total": {
            "over": {21.5, 23.5, 25.5, 27.5, 29.5},
            "under": {22.5, 24.5, 26.5},
        },
        "shots_home": {
            "over": {10.5, 11.5, 12.5, 13.5, 15.5},
            "under": {9.5, 10.5, 11.5, 12.5},
        },
        "shots_away": {
            "over": {10.5, 11.5, 12.5, 13.5, 15.5},
            "under": {9.5, 10.5, 11.5, 12.5},
        },
        "shots_on_total": {
            "over": {6.5, 7.5, 8.5, 9.5, 10.5},
            "under": {7.5, 8.5},
        },
        "shots_on_home": {
            "over": {3.5, 4.5, 5.5, 6.5},
            "under": {3.5, 4.5},
        },
        "shots_on_away": {
            "over": {3.5, 4.5, 5.5, 6.5},
            "under": {3.5, 4.5},
        },
        "offsides_total": {
            "over": {2.5, 3.5, 4.5},
            "under": {2.5, 3.5},
        },
        "offsides_home": {
            "over": {1.5, 2.5, 3.5},
            "under": {1.5, 2.5},
        },
        "offsides_away": {
            "over": {1.5, 2.5, 3.5},
            "under": {1.5, 2.5},
        },
        # +0.5 goles por mitad es una línea trivial (regla 3): solo se presenta 1.5.
        "first_half": {
            "over": {1.5},
            "under": {1.5},
        },
        "second_half": {
            "over": {1.5},
            "under": {1.5},
        },
        "corners_first_half": {
            "over": {3.5, 4.5},
            "under": {4.5, 5.5},
        },
        "fouls_total": {
            "over": {21.5, 23.5, 25.5, 27.5},
            "under": {23.5, 25.5, 27.5},
        },
        "fouls_home": {
            "over": {10.5, 11.5, 12.5, 13.5},
            "under": {10.5, 11.5, 12.5},
        },
        "fouls_away": {
            "over": {10.5, 11.5, 12.5, 13.5},
            "under": {10.5, 11.5, 12.5},
        },
    }

    # Mercados binarios / cualitativos / combinados permitidos
    ALLOWED_BINARY_GROUPS: set[str] = {
        "both_score",
        "clean_sheet",
        "corners_1x2",
        "1x2",
        "double_chance",
        "dnb",
        "win_to_nil",
        "woodwork",
        "both_teams_card",
        "both_teams_2_cards",
        "cards_1x2",
        "both_teams_corners",
        "goal_both_halves",
        "team_score_both_halves",
        "combo_result_goals",
        "both_teams_shots_on",
        "shots_on_1x2",
        "multigoals",
        "combo_1x2_btts",
        "btts_second_half",
        "fouls_1x2",
    }

    # Props de jugadores autorizados
    ALLOWED_PLAYER_SELECTIONS: set[str] = {
        "2+ remates",
        "3+ remates",
        "4+ remates",
        "1+ tiro a puerta",
        "2+ tiros a puerta",
        "Anota en cualquier momento",
    }

    @classmethod
    def is_presentable(cls, candidate: dict[str, Any]) -> bool:
        """Determina si una selección calculada por el modelo es válida para presentarse."""
        group = candidate.get("group", "")
        selection = candidate.get("selection", "")
        side = candidate.get("side", "")
        line = candidate.get("line")

        # 1. Mercados de jugadores
        if group.startswith("player_shots") or group.startswith("player_goal"):
            return any(allowed in selection for allowed in cls.ALLOWED_PLAYER_SELECTIONS)

        # 2. Mercados de líneas numéricas (Over / Under)
        if group in cls.ALLOWED_LINES:
            allowed_sides = cls.ALLOWED_LINES[group]
            if side in allowed_sides and line is not None:
                return float(line) in allowed_sides[side]
            return False

        # 3. Mercados binarios, resultados, mitades y combinados
        if group in cls.ALLOWED_BINARY_GROUPS:
            if group == "woodwork":
                return selection == "Tiro al palo en el partido"
            if group == "both_score":
                return selection in {"Sí", "No (BTTS No)"}
            if group == "clean_sheet":
                return "no recibe gol" in selection
            if group == "corners_1x2":
                return "saca más córners" in selection
            if group == "1x2":
                return True
            if group == "double_chance":
                return any(code in selection for code in ("(1X)", "(X2)", "(12)"))
            if group == "dnb":
                return selection.startswith("DNB")
            if group == "win_to_nil":
                return "gana a cero" in selection
            if group == "both_teams_card":
                return "Ambos equipos reciben al menos 1 tarjeta" in selection or "Ambos equipos reciben tarjeta" in selection
            if group == "both_teams_2_cards":
                return "Ambos equipos reciben 2+ tarjetas" in selection
            if group == "cards_1x2":
                return "recibe más tarjetas" in selection
            if group == "both_teams_corners":
                return any(allowed in selection for allowed in ("Ambos equipos sacan 3+ córners", "Ambos equipos sacan 4+ córners"))
            if group == "goal_both_halves":
                return "gol en ambas mitades" in selection.lower()
            if group == "team_score_both_halves":
                return "marca en ambas mitades" in selection or "anota en ambas mitades" in selection
            if group == "combo_result_goals":
                return any(op in selection for op in (" y Más de 1.5", " y Menos de 3.5", " y Más de 2.5"))
            if group == "both_teams_shots_on":
                return "3+ tiros a puerta" in selection
            if group == "shots_on_1x2":
                return "más tiros a puerta" in selection
            if group == "multigoals":
                return any(allowed in selection for allowed in ("1 a 3 goles", "2 a 4 goles", "2 a 5 goles"))
            if group == "combo_1x2_btts":
                return "y Ambos Marcan" in selection
            if group == "btts_second_half":
                return "Ambos anotan en el 2do tiempo" in selection or "Ambos marcan en el 2T" in selection
            if group == "fouls_1x2":
                return "comete más faltas" in selection
            return True

        return False


def get_exigence_score(candidate: dict[str, Any]) -> float:
    """Calcula el puntaje de exigencia/dificultad de una selección.

    Para Over: a mayor línea, mayor exigencia (ej: 8.5 > 7.5).
    Para Under: a menor línea, mayor exigencia (ej: -9.5 > -10.5, 9.5 es más exigente que 10.5).
    Para Jugadores: 4+ remates (4.0) > 3+ remates (3.0) > 2+ remates (2.0); 2+ SOT (2.0) > 1+ SOT (1.0).
    Para mercados binarios con escalas: 4+ córners (4.0) > 3+ córners (3.0); 2+ tarjetas (2.0) > 1+ tarjeta (1.0).
    """
    side = candidate.get("side", "")
    line = candidate.get("line")
    selection = candidate.get("selection", "")

    if side == "over" and line is not None:
        return float(line)
    if side == "under" and line is not None:
        return -float(line)

    if "4+ remates" in selection:
        return 4.0
    if "3+ remates" in selection:
        return 3.0
    if "2+ remates" in selection:
        return 2.0
    if "2+ tiros a puerta" in selection:
        return 2.0
    if "1+ tiro a puerta" in selection:
        return 1.0

    if "4+ córners" in selection:
        return 4.0
    if "3+ córners" in selection:
        return 3.0
    if "2+ tarjetas" in selection:
        return 2.0
    if "al menos 1 tarjeta" in selection or "reciben tarjeta" in selection:
        return 1.0

    return 0.0
