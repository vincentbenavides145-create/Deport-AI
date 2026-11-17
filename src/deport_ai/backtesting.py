"""Backtest walk-forward de TODOS los mercados del modelo.

Cada partido se predice usando únicamente partidos jugados antes de su fecha
(sin sesgo retrospectivo). Se evalúan dos conjuntos:

* ``all``: todos los candidatos calculados por el modelo (calibración global).
* ``shown``: solo las selecciones que pasan el filtro de presentación (60–88 %,
  catálogo, deduplicación), es decir, lo que realmente ve el usuario. Aquí se
  mide el sesgo de selección: probabilidad media mostrada vs. acierto real.

Si se aportan cuotas por partido, también se calcula el ROI plano (1 unidad).
"""

from __future__ import annotations

import copy
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .domain import Team, TeamMatch
from .errors import InsufficientDataError
from .evaluation import brier_score, calibration_bins, log_loss
from .model_params import DEFAULT_PARAMETERS, ModelParameters, estimate_dispersion
from .settlement import evaluate_prediction
from .stats_engine import calculate_elo, expected_metrics, goal_probabilities
from .statistical_markets import calculate_candidate_markets, select_statistical_markets

SELECTED_BINS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.88]


@dataclass(frozen=True)
class FixtureSample:
    """Un partido terminado visto desde el local, con los nombres para liquidar."""

    fixture_id: int
    date: str
    home: TeamMatch
    away: TeamMatch
    home_name: str
    away_name: str
    league_id: int | None


@dataclass
class BacktestResult:
    evaluated_fixtures: int = 0
    skipped_fixtures: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    unsettled: dict[str, int] = field(default_factory=dict)
    scoreline_log_loss: float | None = None
    samples: dict[int, FixtureSample] = field(default_factory=dict)
    actuals: dict[int, dict[str, Any]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "evaluated_fixtures": self.evaluated_fixtures,
            "skipped_fixtures": self.skipped_fixtures,
            "scoreline_log_loss": self.scoreline_log_loss,
            "shown": summarize_records([r for r in self.records if r["shown"]], SELECTED_BINS),
            "all": summarize_records(self.records, [i / 10 for i in range(11)]),
            "unsettled_markets": dict(sorted(self.unsettled.items(), key=lambda kv: -kv[1])[:15]),
        }


def build_fixtures(
    matches_by_team: dict[int, list[TeamMatch]],
    team_names: dict[int, str],
) -> list[FixtureSample]:
    """Empareja los registros de ambos equipos de cada partido (solo equipos del conjunto)."""
    by_fixture: dict[int, dict[bool, TeamMatch]] = defaultdict(dict)
    for team_matches in matches_by_team.values():
        for match in team_matches:
            by_fixture[match.fixture_id][match.is_home] = match
    fixtures: list[FixtureSample] = []
    for fixture_id, sides in by_fixture.items():
        if True not in sides or False not in sides:
            continue
        home, away = sides[True], sides[False]
        fixtures.append(
            FixtureSample(
                fixture_id=fixture_id,
                date=home.date,
                home=home,
                away=away,
                home_name=team_names.get(home.team_id, f"Equipo {home.team_id}"),
                away_name=team_names.get(away.team_id, f"Equipo {away.team_id}"),
                league_id=home.league_id,
            )
        )
    fixtures.sort(key=lambda item: item.date)
    return fixtures


def history_before(
    matches_by_team: dict[int, list[TeamMatch]], team_id: int, date: str, window: int
) -> list[TeamMatch]:
    """Partidos del equipo estrictamente anteriores a `date`, del más reciente al más antiguo."""
    previous = [m for m in matches_by_team.get(team_id, []) if m.date < date]
    previous.sort(key=lambda m: m.date, reverse=True)
    return previous[:window]


def actual_from_fixture(sample: FixtureSample) -> dict[str, Any]:
    """Construye el diccionario de resultados que usa `settlement.evaluate_prediction`."""
    home_stats = sample.home.stats_for
    away_stats = sample.home.stats_against

    def stat(stats: dict[str, float], key: str) -> int | None:
        value = stats.get(key)
        return int(value) if value is not None else None

    def cards(stats: dict[str, float]) -> int | None:
        yellow = stat(stats, "yellow_cards")
        return None if yellow is None else yellow + (stat(stats, "red_cards") or 0)

    wood_h, wood_a = stat(home_stats, "hit_woodwork"), stat(away_stats, "hit_woodwork")
    return {
        "home_goals": sample.home.goals_for,
        "away_goals": sample.home.goals_against,
        "first_half_home_goals": None,
        "first_half_away_goals": None,
        "second_half_home_goals": None,
        "second_half_away_goals": None,
        "corners_home": stat(home_stats, "corner_kicks"),
        "corners_away": stat(away_stats, "corner_kicks"),
        "cards_home": cards(home_stats),
        "cards_away": cards(away_stats),
        "shots_home": stat(home_stats, "total_shots"),
        "shots_away": stat(away_stats, "total_shots"),
        "shots_on_home": stat(home_stats, "shots_on_goal"),
        "shots_on_away": stat(away_stats, "shots_on_goal"),
        "offsides_home": stat(home_stats, "offsides"),
        "offsides_away": stat(away_stats, "offsides"),
        "fouls_home": stat(home_stats, "fouls"),
        "fouls_away": stat(away_stats, "fouls"),
        "woodwork_hit": None if wood_h is None and wood_a is None else (wood_h or 0) + (wood_a or 0),
        "player_stats": None,
    }


def _predict(
    sample: FixtureSample,
    hist_home: list[TeamMatch],
    hist_away: list[TeamMatch],
    params: ModelParameters,
    with_counts: bool,
):
    elo_h, elo_a = calculate_elo(
        hist_home,
        hist_away,
        sample.home.team_id,
        sample.away.team_id,
        home_league=sample.league_id,
        away_league=sample.league_id,
        home_name=sample.home_name,
        away_name=sample.away_name,
        club_tier_scale=params.club_tier_scale,
    )
    probs = goal_probabilities(
        hist_home, hist_away, elo_h, elo_a, league_id=sample.league_id, params=params
    )
    if not with_counts:
        return probs, None
    expected = expected_metrics(
        hist_home,
        hist_away,
        [],
        sample.home.team_id,
        sample.away.team_id,
        elo_home=elo_h,
        elo_away=elo_a,
        league_id=sample.league_id,
        params=params,
    )
    return probs, expected


def run_walk_forward(
    fixtures: list[FixtureSample],
    matches_by_team: dict[int, list[TeamMatch]],
    params: ModelParameters = DEFAULT_PARAMETERS,
    min_history: int = 6,
    window: int = 12,
    odds_by_fixture: dict[int, dict[str, float]] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> BacktestResult:
    result = BacktestResult()
    losses: list[float] = []
    unsettled: dict[str, int] = defaultdict(int)
    for index, sample in enumerate(fixtures):
        if progress:
            progress(index + 1, len(fixtures))
        hist_home = history_before(matches_by_team, sample.home.team_id, sample.date, window)
        hist_away = history_before(matches_by_team, sample.away.team_id, sample.date, window)
        if len(hist_home) < min_history or len(hist_away) < min_history:
            result.skipped_fixtures += 1
            continue
        try:
            probs, expected = _predict(sample, hist_home, hist_away, params, with_counts=True)
        except InsufficientDataError:
            result.skipped_fixtures += 1
            continue
        result.evaluated_fixtures += 1
        hg, ag = sample.home.goals_for, sample.home.goals_against
        losses.append(-math.log(max(1e-12, _score_prob(probs.score_matrix, hg, ag))))

        home_team = Team(sample.home.team_id, sample.home_name)
        away_team = Team(sample.away.team_id, sample.away_name)
        odds = (odds_by_fixture or {}).get(sample.fixture_id) or {}
        candidates = calculate_candidate_markets(home_team, away_team, probs, expected)
        originals = copy.deepcopy(candidates)
        shown = select_statistical_markets(home_team, away_team, probs, expected, odds=odds)
        shown_keys = {(m["category"], m["market"], m["selection"]) for m in shown}
        shown_by_key = {(m["category"], m["market"], m["selection"]): m for m in shown}
        actual = actual_from_fixture(sample)
        result.samples[sample.fixture_id] = sample
        result.actuals[sample.fixture_id] = actual

        for cand in originals:
            prob = cand.get("probability")
            if prob is None:
                continue
            outcome = evaluate_prediction(cand, actual, sample.home_name, sample.away_name)
            if outcome not in ("WON", "LOST"):
                unsettled[f"{cand.get('category')}: {cand.get('market')}"] += 1
                continue
            key = (cand["category"], cand["market"], cand["selection"])
            shown_item = shown_by_key.get(key)
            result.records.append(
                {
                    "fixture_id": sample.fixture_id,
                    "league_id": sample.league_id,
                    "category": cand["category"],
                    "market": cand["market"],
                    "selection": cand["selection"],
                    "line": cand.get("line"),
                    "side": cand.get("side"),
                    "projection": cand.get("projection"),
                    "probability": float(prob),
                    "won": outcome == "WON",
                    "shown": key in shown_keys,
                    "odds": shown_item.get("odds") if shown_item else None,
                }
            )
    result.unsettled = dict(unsettled)
    result.scoreline_log_loss = round(sum(losses) / len(losses), 5) if losses else None
    return result


def scoreline_objective(
    fixtures: list[FixtureSample],
    matches_by_team: dict[int, list[TeamMatch]],
    min_history: int = 6,
    window: int = 12,
) -> Callable[[ModelParameters], tuple[float, int]]:
    """Función objetivo para el ajuste: log-loss medio del marcador exacto (walk-forward)."""
    prepared: list[tuple[FixtureSample, list[TeamMatch], list[TeamMatch]]] = []
    for sample in fixtures:
        hist_home = history_before(matches_by_team, sample.home.team_id, sample.date, window)
        hist_away = history_before(matches_by_team, sample.away.team_id, sample.date, window)
        if len(hist_home) >= min_history and len(hist_away) >= min_history:
            prepared.append((sample, hist_home, hist_away))

    def objective(params: ModelParameters) -> tuple[float, int]:
        total, count = 0.0, 0
        for sample, hist_home, hist_away in prepared:
            try:
                probs, _ = _predict(sample, hist_home, hist_away, params, with_counts=False)
            except InsufficientDataError:
                continue
            p = _score_prob(probs.score_matrix, sample.home.goals_for, sample.home.goals_against)
            total += -math.log(max(1e-12, p))
            count += 1
        return (total / count if count else float("inf")), count

    return objective


def estimate_count_dispersions(fixtures: Iterable[FixtureSample]) -> dict[str, float | None]:
    corners, cards = [], []
    for sample in fixtures:
        actual = actual_from_fixture(sample)
        if actual["corners_home"] is not None and actual["corners_away"] is not None:
            corners.append(actual["corners_home"] + actual["corners_away"])
        if actual["cards_home"] is not None and actual["cards_away"] is not None:
            cards.append(actual["cards_home"] + actual["cards_away"])
    return {
        "dispersion_corners": estimate_dispersion(corners),
        "dispersion_cards": estimate_dispersion(cards),
    }


def summarize_records(records: list[dict[str, Any]], bins: list[float]) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    probs = [r["probability"] for r in records]
    outcomes = [1 if r["won"] else 0 for r in records]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_category[r["category"]].append(r)

    def block(items: list[dict[str, Any]]) -> dict[str, Any]:
        p = [r["probability"] for r in items]
        o = [1 if r["won"] else 0 for r in items]
        priced = [r for r in items if r.get("odds")]
        roi = None
        if priced:
            pnl = sum((r["odds"] - 1.0) if r["won"] else -1.0 for r in priced)
            roi = round(pnl / len(priced), 4)
        return {
            "count": len(items),
            "mean_predicted": round(sum(p) / len(p), 4),
            "hit_rate": round(sum(o) / len(o), 4),
            "gap": round(sum(o) / len(o) - sum(p) / len(p), 4),
            "brier": round(brier_score(p, o), 4),
            "priced": len(priced),
            "roi": roi,
        }

    calibration = [
        {
            "bin": f"{b.lower * 100:.0f}-{b.upper * 100:.0f}%",
            "count": b.count,
            "predicted": round(b.mean_predicted, 4) if b.mean_predicted is not None else None,
            "observed": round(b.observed_frequency, 4) if b.observed_frequency is not None else None,
        }
        for b in calibration_bins(probs, outcomes, bins=bins)
        if b.count
    ]
    return {
        **block(records),
        "log_loss": round(log_loss(probs, outcomes), 4),
        "calibration": calibration,
        "by_category": {cat: block(items) for cat, items in sorted(by_category.items())},
    }


def _score_prob(matrix: list[list[float]], home_goals: int, away_goals: int) -> float:
    size = len(matrix)
    if home_goals < size and away_goals < size:
        return matrix[home_goals][away_goals]
    # Marcadores fuera de la matriz: masa residual repartida de forma conservadora.
    return 1e-6


# ---------------------------------------------------------------------------
# Fuentes de datos
# ---------------------------------------------------------------------------


def load_from_sportmonks(
    client: Any,
    team_queries: list[str],
    count: int = 30,
    log: Callable[[str], None] = lambda _msg: None,
) -> tuple[dict[int, list[TeamMatch]], dict[int, str]]:
    """Descarga los últimos `count` partidos terminados de cada equipo (con estadísticas)."""
    from .stats_engine import extract_team_matches

    matches_by_team: dict[int, list[TeamMatch]] = {}
    team_names: dict[int, str] = {}
    for query in team_queries:
        team = client.resolve_team(query)
        team_names[team.id] = team.name
        rows = client.recent_fixtures(team.id, count)
        ids = [int(row["fixture"]["id"]) for row in rows]
        details = client.fixture_details(ids)
        matches_by_team[team.id] = extract_team_matches(rows, team.id, details)
        log(f"  {team.name}: {len(matches_by_team[team.id])} partidos")
    return matches_by_team, team_names


def load_odds_from_sportmonks(client: Any, fixtures: list[FixtureSample]) -> dict[int, dict[str, float]]:
    from .odds import normalize_odds

    result: dict[int, dict[str, float]] = {}
    for sample in fixtures:
        try:
            odds = normalize_odds(client.odds(sample.fixture_id))
        except Exception:
            odds = {}
        if odds:
            result[sample.fixture_id] = odds
    return result


def synthetic_league(
    n_teams: int = 20, rounds: int = 2, seed: int = 7
) -> tuple[dict[int, list[TeamMatch]], dict[int, str]]:
    """Liga simulada con fuerzas conocidas y estadísticas completas.

    Sirve para verificar que el pipeline funciona de punta a punta; NO sustituye
    un backtest con datos reales.
    """
    import random

    rng = random.Random(seed)
    teams = list(range(1, n_teams + 1))
    names = {t: f"Equipo {t:02d}" for t in teams}
    attack = {t: rng.gauss(0.0, 0.25) for t in teams}
    defence = {t: rng.gauss(0.0, 0.2) for t in teams}
    style = {t: rng.gauss(0.0, 0.15) for t in teams}

    def poisson(lam: float) -> int:
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1

    def neg_bin(mean: float, alpha: float) -> int:
        shape = 1.0 / alpha
        return poisson(rng.gammavariate(shape, mean / shape))

    from datetime import datetime, timedelta

    # Round-robin por el método del círculo; las vueltas pares invierten la localía.
    single: list[list[tuple[int, int]]] = []
    order = teams[:]
    for r in range(n_teams - 1):
        pairs = []
        for i in range(n_teams // 2):
            a, b = order[i], order[n_teams - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        single.append(pairs)
        order = [order[0], order[-1], *order[1:-1]]
    rounds_list: list[list[tuple[int, int]]] = []
    for leg in range(rounds):
        for pairs in single:
            rounds_list.append(pairs if leg % 2 == 0 else [(b, a) for a, b in pairs])

    matches: dict[int, list[TeamMatch]] = {t: [] for t in teams}
    start = datetime(2025, 1, 4, 15, 0)
    index = 0
    for day, pairs in enumerate(rounds_list):
        for home, away in pairs:
            index += 1
            date = (start + timedelta(days=7 * day)).strftime("%Y-%m-%dT%H:%M:%SZ")
            lam_h = math.exp(math.log(1.45) + attack[home] - defence[away])
            lam_a = math.exp(math.log(1.10) + attack[away] - defence[home])
            shared = poisson(0.08)
            hg, ag = poisson(lam_h) + shared, poisson(lam_a) + shared
            stats_h = {
                "corner_kicks": float(neg_bin(5.4 * math.exp(attack[home] + style[home]), 0.12)),
                "yellow_cards": float(neg_bin(2.0 * math.exp(-style[home]), 0.2)),
                "red_cards": float(1 if rng.random() < 0.05 else 0),
                "total_shots": float(neg_bin(13.0 * math.exp(attack[home]), 0.08)),
                "offsides": float(neg_bin(1.9, 0.15)),
                "fouls": float(neg_bin(11.5, 0.08)),
                "hit_woodwork": float(poisson(0.25)),
            }
            stats_a = {
                "corner_kicks": float(neg_bin(4.4 * math.exp(attack[away] + style[away]), 0.12)),
                "yellow_cards": float(neg_bin(2.3 * math.exp(-style[away]), 0.2)),
                "red_cards": float(1 if rng.random() < 0.06 else 0),
                "total_shots": float(neg_bin(10.5 * math.exp(attack[away]), 0.08)),
                "offsides": float(neg_bin(1.8, 0.15)),
                "fouls": float(neg_bin(12.0, 0.08)),
                "hit_woodwork": float(poisson(0.2)),
            }
            stats_h["shots_on_goal"] = float(max(hg, round(stats_h["total_shots"] * 0.34)))
            stats_a["shots_on_goal"] = float(max(ag, round(stats_a["total_shots"] * 0.33)))
            fixture_id = 500000 + index
            for team, opp, is_home, gf, ga, sf, sa in (
                (home, away, True, hg, ag, stats_h, stats_a),
                (away, home, False, ag, hg, stats_a, stats_h),
            ):
                matches[team].append(
                    TeamMatch(
                        fixture_id=fixture_id,
                        date=date,
                        team_id=team,
                        opponent_id=opp,
                        is_home=is_home,
                        goals_for=gf,
                        goals_against=ga,
                        result="W" if gf > ga else "D" if gf == ga else "L",
                        opponent_name=names[opp],
                        stats_for=dict(sf),
                        stats_against=dict(sa),
                        competition_weight=1.0,
                        league_id=None,
                    )
                )
    for team in teams:
        matches[team].sort(key=lambda m: m.date, reverse=True)
    return matches, names
