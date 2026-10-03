from __future__ import annotations

import pytest
from deport_ai.settlement import evaluate_prediction, extract_match_actual_stats


def test_evaluate_goals_and_results():
    home = "Real Madrid"
    away = "Barcelona"
    actual = {
        "home_goals": 3,
        "away_goals": 1,
        "first_half_home_goals": 1,
        "first_half_away_goals": 0,
        "second_half_home_goals": 2,
        "second_half_away_goals": 1,
    }

    # 1X2
    assert evaluate_prediction({"category": "Resultado", "selection": "Victoria Real Madrid"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Resultado", "selection": "Victoria Barcelona"}, actual, home, away) == "LOST"
    assert evaluate_prediction({"category": "Resultado", "selection": "Empate"}, actual, home, away) == "LOST"

    # Doble Oportunidad
    assert evaluate_prediction({"category": "Resultado", "selection": "Doble oportunidad (Real Madrid o Empate) (1X)"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Resultado", "selection": "Doble oportunidad (Barcelona o Empate) (X2)"}, actual, home, away) == "LOST"

    # DNB
    assert evaluate_prediction({"category": "Resultado", "selection": "DNB Real Madrid"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Resultado", "selection": "DNB Barcelona"}, actual, home, away) == "LOST"

    # Goles Totales Over/Under
    assert evaluate_prediction({"category": "Goles", "selection": "Más de 2.5 goles", "line": 2.5, "side": "over"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Goles", "selection": "Menos de 2.5 goles", "line": 2.5, "side": "under"}, actual, home, away) == "LOST"
    assert evaluate_prediction({"category": "Goles", "selection": "Menos de 4.5 goles", "line": 4.5, "side": "under"}, actual, home, away) == "WON"

    # Ambos Marcan (BTTS)
    assert evaluate_prediction({"category": "Goles", "selection": "Sí"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Goles", "selection": "No (BTTS No)"}, actual, home, away) == "LOST"

    # Mitades
    assert evaluate_prediction({"category": "Mitades", "selection": "Más de 0.5 goles 1T", "line": 0.5, "side": "over"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Mitades", "selection": "Más de 1.5 goles 1T", "line": 1.5, "side": "over"}, actual, home, away) == "LOST"
    assert evaluate_prediction({"category": "Mitades", "selection": "Más de 1.5 goles 2T", "line": 1.5, "side": "over"}, actual, home, away) == "WON"


def test_evaluate_corners_and_cards():
    home = "Arsenal"
    away = "Chelsea"
    actual = {
        "corners_home": 7,
        "corners_away": 4,
        "cards_home": 2,
        "cards_away": 3,
    }

    # Córners
    assert evaluate_prediction({"category": "Córners", "selection": "Más de 8.5 córners", "line": 8.5, "side": "over"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Córners", "selection": "Más de 11.5 córners", "line": 11.5, "side": "over"}, actual, home, away) == "LOST"
    assert evaluate_prediction({"category": "Córners", "selection": "Arsenal saca más córners (Experimental)"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Córners", "selection": "Arsenal Más de 5.5 córners", "line": 5.5, "side": "over"}, actual, home, away) == "WON"

    # Tarjetas
    assert evaluate_prediction({"category": "Tarjetas", "selection": "Más de 4.5 tarjetas", "line": 4.5, "side": "over"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Tarjetas", "selection": "Más de 5.5 tarjetas", "line": 5.5, "side": "over"}, actual, home, away) == "LOST"
    assert evaluate_prediction({"category": "Tarjetas", "selection": "Chelsea Más de 2.5 tarjetas", "line": 2.5, "side": "over"}, actual, home, away) == "WON"


def test_evaluate_player_props_and_void():
    home = "Liverpool"
    away = "Everton"
    actual = {
        "player_stats": {
            "mohamed salah": {"name": "Mohamed Salah", "minutes": 88, "shots": 4, "shots_on": 2, "goals": 1},
            "darwin nunez": {"name": "Darwin Núñez", "minutes": 0, "shots": 0, "shots_on": 0, "goals": 0},
        }
    }

    # Jugador activo
    assert evaluate_prediction({"category": "Jugadores", "selection": "Mohamed Salah 3+ remates"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Jugadores", "selection": "Mohamed Salah 2+ tiros a puerta"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Jugadores", "selection": "Mohamed Salah Anota en cualquier momento"}, actual, home, away) == "WON"

    # Jugador que no jugó (minutos = 0 o ausente) -> VOID
    assert evaluate_prediction({"category": "Jugadores", "selection": "Darwin Núñez 2+ remates"}, actual, home, away) == "VOID"
    assert evaluate_prediction({"category": "Jugadores", "selection": "Luis Diaz 2+ remates"}, actual, home, away) == "VOID"


def test_evaluate_creative_and_combo_markets():
    home = "Manchester City"
    away = "Sunderland"
    actual = {
        "home_goals": 2,
        "away_goals": 1,
        "first_half_home_goals": 1,
        "first_half_away_goals": 0,
        "second_half_home_goals": 1,
        "second_half_away_goals": 1,
        "corners_home": 6,
        "corners_away": 3,
        "cards_home": 1,
        "cards_away": 2,
        "shots_on_home": 7,
        "shots_on_away": 3,
    }

    # Tarjetas mutuas y 1X2
    assert evaluate_prediction({"category": "Tarjetas", "selection": "Ambos equipos reciben al menos 1 tarjeta"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Tarjetas", "selection": "Ambos equipos reciben 2+ tarjetas"}, actual, home, away) == "LOST"
    assert evaluate_prediction({"category": "Tarjetas", "selection": "Sunderland recibe más tarjetas"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Tarjetas", "selection": "Manchester City recibe más tarjetas"}, actual, home, away) == "LOST"

    # Córners mutuos
    assert evaluate_prediction({"category": "Córners", "selection": "Ambos equipos sacan 3+ córners"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Córners", "selection": "Ambos equipos sacan 4+ córners"}, actual, home, away) == "LOST"

    # Mitades: gol en ambas mitades y equipo anota en ambas mitades
    assert evaluate_prediction({"category": "Mitades", "selection": "Habrá gol en ambas mitades"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Mitades", "selection": "Manchester City anota en ambas mitades"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Mitades", "selection": "Sunderland anota en ambas mitades"}, actual, home, away) == "LOST"

    # Combos de partido
    assert evaluate_prediction({"category": "Resultado", "selection": "Manchester City o Empate (1X) y Más de 1.5 goles"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Resultado", "selection": "Manchester City o Empate (1X) y Menos de 3.5 goles"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Resultado", "selection": "Manchester City gana y Más de 1.5 goles"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Resultado", "selection": "Sunderland gana y Más de 1.5 goles"}, actual, home, away) == "LOST"
    assert evaluate_prediction({"category": "Goles", "selection": "Ambos marcan y Más de 2.5 goles"}, actual, home, away) == "WON"

    # Tiros a puerta combinados y 1X2
    assert evaluate_prediction({"category": "Remates y Tiros a Puerta", "selection": "Ambos equipos tienen 3+ tiros a puerta"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Remates y Tiros a Puerta", "selection": "Manchester City tiene más tiros a puerta"}, actual, home, away) == "WON"
    assert evaluate_prediction({"category": "Remates y Tiros a Puerta", "selection": "Sunderland tiene más tiros a puerta"}, actual, home, away) == "LOST"
