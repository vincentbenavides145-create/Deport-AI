from __future__ import annotations

import re
from collections import defaultdict
from statistics import median
from typing import Any

from .domain import ProbabilityReport


def normalize_odds(rows: list[dict[str, Any]]) -> dict[str, float]:
    values: defaultdict[str, list[float]] = defaultdict(list)
    for item in rows:
        # Sportmonks v3 flat odds object
        if isinstance(item, dict) and ("market_description" in item or "value" in item and "label" in item):
            market_desc = _norm(item.get("market_description") or item.get("market", {}).get("name") or "")
            label = _norm(item.get("label") or "")
            total = str(item.get("total") or "").strip()
            handicap = str(item.get("handicap") or "").strip()
            key = _selection_key_v3(market_desc, label, total, handicap)
            price = _float(item.get("value") or item.get("odd"))
            if key and price and price > 1.0:
                values[key].append(price)
            continue

        # Nested bookmaker structure
        for bookmaker in item.get("bookmakers", []) or []:
            for bet in bookmaker.get("bets", []) or []:
                bet_name = _norm(bet.get("name", ""))
                for selection in bet.get("values", []) or []:
                    key = _selection_key(bet_name, _norm(selection.get("value", "")))
                    price = _float(selection.get("odd"))
                    if key and price and price > 1.0:
                        values[key].append(price)
    return {key: round(median(prices), 3) for key, prices in values.items()}


def _selection_key_v3(market: str, label: str, total: str = "", handicap: str = "") -> str | None:
    # 1X2 / Ganador
    if "result" in market or "winner" in market or "1x2" in market:
        if "1st half" not in market and "2nd half" not in market:
            if label in {"home", "1"}:
                return "home_win"
            if label in {"draw", "x", "tie"}:
                return "draw"
            if label in {"away", "2"}:
                return "away_win"

    # Doble Oportunidad (Double Chance)
    if "double chance" in market:
        if "1st half" not in market and "2nd half" not in market:
            if "home draw" in label or "1x" in label or label == "home/draw":
                return "double_chance_1x"
            if "draw away" in label or "x2" in label or label == "draw/away":
                return "double_chance_x2"
            if "home away" in label or "12" in label or label == "home/away":
                return "double_chance_12"

    # Empate Apuesta No Válida (Draw No Bet / DNB)
    if "draw no bet" in market or market == "dnb":
        if label in {"1", "home"}:
            return "dnb_home"
        if label in {"2", "away"}:
            return "dnb_away"

    # Hándicap Asiático (Asian Handicap)
    if "asian handicap" in market and "corner" not in market and "half" not in market:
        norm_h = handicap.replace(" ", "").replace("+", "")
        if label in {"home", "1"}:
            if norm_h == "-1.5":
                return "ah_home_minus_15"
            if norm_h == "1.5":
                return "ah_home_plus_15"
            if norm_h == "-2.5":
                return "ah_home_minus_25"
            if norm_h == "2.5":
                return "ah_home_plus_25"
        if label in {"away", "2"}:
            if norm_h == "1.5":
                return "ah_away_plus_15"
            if norm_h == "-1.5":
                return "ah_away_minus_15"
            if norm_h == "2.5":
                return "ah_away_plus_25"
            if norm_h == "-2.5":
                return "ah_away_minus_25"

    # Goles por Mitad (1T y 2T)
    if ("1st half" in market or "first half" in market) and ("goals" in market or "goal" in market):
        if "over" in label:
            if "0.5" in total or "0 5" in total:
                return "first_half_over_05"
            if "1.5" in total or "1 5" in total:
                return "first_half_over_15"
        if "under" in label:
            if "0.5" in total or "0 5" in total:
                return "first_half_under_05"
            if "1.5" in total or "1 5" in total:
                return "first_half_under_15"

    if ("2nd half" in market or "second half" in market) and ("goals" in market or "goal" in market):
        if "over" in label:
            if "0.5" in total or "0 5" in total:
                return "second_half_over_05"
            if "1.5" in total or "1 5" in total:
                return "second_half_over_15"
        if "under" in label:
            if "0.5" in total or "0 5" in total:
                return "second_half_under_05"
            if "1.5" in total or "1 5" in total:
                return "second_half_under_15"

    # Goles Totales (Goals Over/Under)
    if ("over" in market or "under" in market or "goals" in market or "total" in market) and "home" not in market and "away" not in market and "corner" not in market and "1st half" not in market and "2nd half" not in market:
        if "over" in label or label == "over":
            if "0 5" in total or total == "0.5":
                return "over_05"
            if "1 5" in total or total == "1.5":
                return "over_15"
            if "2 5" in total or total == "2.5":
                return "over_25"
            if "3 5" in total or total == "3.5":
                return "over_35"
        if "under" in label or label == "under":
            if "2 5" in total or total == "2.5":
                return "under_25"
            if "3 5" in total or total == "3.5":
                return "under_35"

    # Ambos Equipos Marcan (BTTS)
    if "both teams" in market or "btts" in market:
        if "1st half" not in market and "2nd half" not in market:
            if label in {"yes", "si", "y"}:
                return "btts_yes"
            if label in {"no", "n"}:
                return "btts_no"

    # Goles por Equipo (Total - Home / Total - Away / Team Total Goals)
    if "total home" in market or ("team total" in market and (label in {"home", "1"} or "home" in market)):
        if "over" in label or "over" in market:
            if "1 5" in total or total == "1.5":
                return "home_over_15"
        if "under" in label or "under" in market:
            if "1 5" in total or total == "1.5":
                return "home_under_15"

    if "total away" in market or ("team total" in market and (label in {"away", "2"} or "away" in market)):
        if "over" in label or "over" in market:
            if "1 5" in total or total == "1.5":
                return "away_over_15"
        if "under" in label or "under" in market:
            if "1 5" in total or total == "1.5":
                return "away_under_15"

    # Portería a Cero (Clean Sheet)
    if "clean sheet" in market:
        norm_h = handicap.lower().strip()
        if label in {"1", "home"}:
            if "yes" in norm_h or label == "yes":
                return "clean_sheet_home"
        if label in {"2", "away"}:
            if "yes" in norm_h or label == "yes":
                return "clean_sheet_away"

    # Córners Totales
    if "corners over under" in market or ("corner" in market and "over" in market):
        if "over" in label:
            if "7.5" in total or "7 5" in total:
                return "over_75_corners"
            if "8.5" in total or "8 5" in total:
                return "over_85_corners"
            if "9.5" in total or "9 5" in total:
                return "over_95_corners"
            if "10.5" in total or "10 5" in total:
                return "over_105_corners"
            if "11.5" in total or "11 5" in total:
                return "over_115_corners"
        if "under" in label:
            if "8.5" in total or "8 5" in total:
                return "under_85_corners"
            if "9.5" in total or "9 5" in total:
                return "under_95_corners"
            if "10.5" in total or "10 5" in total:
                return "under_105_corners"

    return None


def select_opportunities(
    probabilities: ProbabilityReport, odds: dict[str, float], maximum: int = 4
) -> list[dict[str, Any]]:
    model: dict[str, float] = {
        "Victoria local": probabilities.home_win,
        "Empate": probabilities.draw,
        "Victoria visitante": probabilities.away_win,
        "Doble oportunidad 1X": min(1.0, probabilities.home_win + probabilities.draw),
        "Doble oportunidad X2": min(1.0, probabilities.away_win + probabilities.draw),
        "Doble oportunidad 12": min(1.0, probabilities.home_win + probabilities.away_win),
        "DNB Local": probabilities.dnb_home,
        "DNB Visitante": probabilities.dnb_away,
        "Más de 1.5 goles": probabilities.over_15,
        "Más de 2.5 goles": probabilities.over_25,
        "Menos de 2.5 goles": probabilities.under_25,
        "Más de 3.5 goles": probabilities.over_35,
        "Menos de 3.5 goles": probabilities.under_35,
        "Ambos marcan": probabilities.btts,
        "Más de 0.5 goles en 1T": probabilities.first_half_over_05,
        "Más de 0.5 goles en 2T": probabilities.second_half_over_05,
        "Local más de 1.5 goles": probabilities.home_over_15,
        "Local menos de 1.5 goles": probabilities.home_under_15,
        "Visitante menos de 1.5 goles": probabilities.away_under_15,
        "Local (-1.5) Hándicap Asiático": probabilities.ah_home_minus_15,
        "Visitante (+1.5) Hándicap Asiático": probabilities.ah_away_plus_15,
        "Local (+1.5) Hándicap Asiático": probabilities.ah_home_plus_15,
        "Visitante (-1.5) Hándicap Asiático": probabilities.ah_away_minus_15,
        "Visitante (+2.5) Hándicap Asiático": probabilities.ah_away_plus_25,
        "Portería a cero Local": probabilities.clean_sheet_home,
    }
    odds_keys: dict[str, str] = {
        "Victoria local": "home_win",
        "Empate": "draw",
        "Victoria visitante": "away_win",
        "Doble oportunidad 1X": "double_chance_1x",
        "Doble oportunidad X2": "double_chance_x2",
        "Doble oportunidad 12": "double_chance_12",
        "DNB Local": "dnb_home",
        "DNB Visitante": "dnb_away",
        "Más de 1.5 goles": "over_15",
        "Más de 2.5 goles": "over_25",
        "Menos de 2.5 goles": "under_25",
        "Más de 3.5 goles": "over_35",
        "Menos de 3.5 goles": "under_35",
        "Ambos marcan": "btts_yes",
        "Más de 0.5 goles en 1T": "first_half_over_05",
        "Más de 0.5 goles en 2T": "second_half_over_05",
        "Local más de 1.5 goles": "home_over_15",
        "Local menos de 1.5 goles": "home_under_15",
        "Visitante menos de 1.5 goles": "away_under_15",
        "Local (-1.5) Hándicap Asiático": "ah_home_minus_15",
        "Visitante (+1.5) Hándicap Asiático": "ah_away_plus_15",
        "Local (+1.5) Hándicap Asiático": "ah_home_plus_15",
        "Visitante (-1.5) Hándicap Asiático": "ah_away_minus_15",
        "Visitante (+2.5) Hándicap Asiático": "ah_away_plus_25",
        "Portería a cero Local": "clean_sheet_home",
    }
    candidates: list[dict[str, Any]] = []
    for market, probability in model.items():
        price = odds.get(odds_keys[market])
        edge = probability - 1.0 / price if price else None
        if price and edge is not None and edge >= 0.02 and probability >= 0.60:
            candidates.append(
                {
                    "market": market,
                    "probability": probability,
                    "odds": price,
                    "edge": edge,
                    "risk": _risk(probability),
                    "basis": "Posible valor frente a la cuota mediana observada.",
                }
            )
    candidates.sort(key=lambda item: item["edge"], reverse=True)
    if candidates:
        return candidates[:maximum]

    # Sin cuotas comparables no afirmamos valor; solo mostramos las señales más probables (mínimo 60%).
    fallback = [
        (market, probability)
        for market, probability in model.items()
        if market not in {"Empate"} and probability >= 0.60
    ]
    # Si aparecen dos mercados de goles opuestos (ej. +1.5 y -2.5), nos quedamos con el más fuerte
    filtered_fallback: list[tuple[str, float]] = []
    has_goal_market = False
    for market, probability in sorted(fallback, key=lambda item: item[1], reverse=True):
        is_goal = "goles" in market.lower() or "marcan" in market.lower()
        if is_goal:
            if not has_goal_market:
                filtered_fallback.append((market, probability))
                has_goal_market = True
        else:
            filtered_fallback.append((market, probability))

    return [
        {
            "market": market,
            "probability": probability,
            "odds": None,
            "edge": None,
            "risk": _risk(probability),
            "basis": "Señal estadística de alta confianza (≥ 60%).",
        }
        for market, probability in filtered_fallback[:maximum]
    ]


def _selection_key(bet: str, value: str) -> str | None:
    if "match winner" in bet or "winner" == bet:
        return {"home": "home_win", "draw": "draw", "away": "away_win"}.get(value)
    if "goals over under" in bet or "over under" in bet:
        if "over 1 5" in value:
            return "over_15"
        if "over 2 5" in value:
            return "over_25"
        if "under 2 5" in value:
            return "under_25"
    if "both teams" in bet and ("score" in bet or "scor" in bet) and value in {"yes", "si"}:
        return "btts_yes"
    return None


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _risk(probability: float) -> str:
    if probability >= 0.72:
        return "Medio-bajo"
    if probability >= 0.60:
        return "Medio"
    return "Alto"

