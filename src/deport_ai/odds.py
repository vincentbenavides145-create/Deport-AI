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
            key = _selection_key_v3(market_desc, label, total)
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


def _selection_key_v3(market: str, label: str, total: str = "") -> str | None:
    if "result" in market or "winner" in market or "1x2" in market:
        if label in {"home", "1"}:
            return "home_win"
        if label in {"draw", "x", "tie"}:
            return "draw"
        if label in {"away", "2"}:
            return "away_win"
    if "over" in market or "under" in market or "goals" in market or "total" in market:
        if "over" in label or label == "over":
            if "1 5" in total or total == "1.5" or "over 1 5" in label:
                return "over_15"
            if "2 5" in total or total == "2.5" or "over 2 5" in label:
                return "over_25"
        if "under" in label or label == "under":
            if "2 5" in total or total == "2.5" or "under 2 5" in label:
                return "under_25"
    if "both teams" in market or "btts" in market:
        if label in {"yes", "si", "y"}:
            return "btts_yes"
        if label in {"no", "n"}:
            return "btts_no"
    return None


def select_opportunities(
    probabilities: ProbabilityReport, odds: dict[str, float], maximum: int = 2
) -> list[dict[str, Any]]:
    model = {
        "Victoria local": probabilities.home_win,
        "Empate": probabilities.draw,
        "Victoria visitante": probabilities.away_win,
        "Más de 1.5 goles": probabilities.over_15,
        "Más de 2.5 goles": probabilities.over_25,
        "Menos de 2.5 goles": probabilities.under_25,
        "Ambos marcan": probabilities.btts,
    }
    odds_keys = {
        "Victoria local": "home_win",
        "Empate": "draw",
        "Victoria visitante": "away_win",
        "Más de 1.5 goles": "over_15",
        "Más de 2.5 goles": "over_25",
        "Menos de 2.5 goles": "under_25",
        "Ambos marcan": "btts_yes",
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

