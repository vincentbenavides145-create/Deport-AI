from __future__ import annotations

from dataclasses import replace

from deport_ai.backtesting import (
    build_fixtures,
    estimate_count_dispersions,
    run_walk_forward,
    scoreline_objective,
    synthetic_league,
)
from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team  # noqa: F401
from deport_ai.evaluation import calibration_bins
from deport_ai.model_params import (
    DEFAULT_PARAMETERS,
    ModelParameters,
    estimate_dispersion,
    fit_parameters,
    load_parameters,
    save_parameters,
)
from deport_ai.odds import odds_key_for_candidate
from deport_ai.settlement import UNSUPPORTED, evaluate_prediction
from deport_ai.stats_engine import calculate_elo, goal_probabilities
from deport_ai.statistical_markets import select_statistical_markets, select_top_recommended_pick
from tests.test_statistics import AWAY, HOME


# --- 3. Parámetros y doble conteo -------------------------------------------------


def test_parameters_roundtrip_per_league(tmp_path):
    path = tmp_path / "params.json"
    fitted = replace(DEFAULT_PARAMETERS, rho=-0.03, elo_weight=0.3, fitted=True)
    save_parameters("564", fitted, path)
    save_parameters("default", replace(DEFAULT_PARAMETERS, rho=-0.12), path)
    assert load_parameters(564, path).rho == -0.03
    assert load_parameters(999, path).rho == -0.12
    assert load_parameters(564, tmp_path / "missing.json") == DEFAULT_PARAMETERS


def test_elo_weight_zero_removes_elo_effect():
    probs_no_elo_a = goal_probabilities(HOME, AWAY, 1800, 1400, params=ModelParameters(elo_weight=0.0))
    probs_no_elo_b = goal_probabilities(HOME, AWAY, 1400, 1800, params=ModelParameters(elo_weight=0.0))
    assert probs_no_elo_a.expected_home_goals == probs_no_elo_b.expected_home_goals

    full = goal_probabilities(HOME, AWAY, 1800, 1400, params=ModelParameters(elo_weight=1.0))
    half = goal_probabilities(HOME, AWAY, 1800, 1400, params=ModelParameters(elo_weight=0.5))
    assert full.home_win > half.home_win > probs_no_elo_a.home_win


def test_elo_prior_has_no_goal_difference_bonus():
    # Sin partidos que actualicen el Elo, el rating es solo la base (no se suma la diferencia de goles).
    elo_h, elo_a = calculate_elo([], [], 1, 2, home_name="Equipo X", away_name="Equipo Y")
    assert elo_h == elo_a


def test_club_tier_scale_zero_ignores_manual_table():
    with_table = calculate_elo([], [], 1, 2, home_name="Real Madrid", away_name="Lecce")
    without = calculate_elo([], [], 1, 2, home_name="Real Madrid", away_name="Lecce", club_tier_scale=0.0)
    assert with_table[0] > with_table[1]
    assert without[0] == without[1]


def test_fit_parameters_improves_objective():
    def objective(params: ModelParameters) -> tuple[float, int]:
        return (params.rho - 0.04) ** 2 + (params.elo_weight - 0.3) ** 2, 100

    fitted = fit_parameters(objective)
    assert fitted.fitted is True
    assert fitted.rho == 0.04
    assert fitted.elo_weight == 0.3
    assert fitted.log_loss < fitted.baseline_log_loss


def test_estimate_dispersion_requires_sample_and_detects_overdispersion():
    assert estimate_dispersion([10, 11]) is None
    poisson_like = [9, 10, 11] * 10
    overdispersed = [3, 18, 6, 15, 10] * 6
    assert estimate_dispersion(poisson_like) == 0.0
    assert estimate_dispersion(overdispersed) > 0.1


# --- 2. Backtest walk-forward ----------------------------------------------------


def test_walk_forward_backtest_covers_all_categories_without_lookahead():
    matches, names = synthetic_league(n_teams=8, rounds=2, seed=3)
    fixtures = build_fixtures(matches, names)
    assert len(fixtures) == 8 * 7

    result = run_walk_forward(fixtures, matches, min_history=4, window=8)
    summary = result.summary()
    assert result.evaluated_fixtures > 0
    shown = summary["shown"]
    assert shown["count"] > 0
    assert 0.6 <= shown["mean_predicted"] <= 0.88
    for category in ("Goles", "Córners", "Tarjetas", "Faltas", "Resultado"):
        assert category in summary["all"]["by_category"]

    # Ningún registro usa partidos posteriores: el primer partido de cada equipo no se evalúa.
    first_date = fixtures[0].date
    assert all(result.samples[r["fixture_id"]].date > first_date for r in result.records)


def test_scoreline_objective_and_dispersions():
    matches, names = synthetic_league(n_teams=6, rounds=2, seed=5)
    fixtures = build_fixtures(matches, names)
    objective = scoreline_objective(fixtures, matches, min_history=4, window=8)
    loss, count = objective(DEFAULT_PARAMETERS)
    assert count > 0 and 1.5 < loss < 5.0
    disp = estimate_count_dispersions(fixtures)
    assert disp["dispersion_corners"] is not None


def test_calibration_bins_accepts_custom_edges():
    bins = calibration_bins([0.61, 0.66, 0.70, 0.87, 0.95], [1, 0, 1, 1, 1], bins=[0.6, 0.65, 0.7, 0.88])
    assert [b.count for b in bins] == [1, 1, 2]


# --- Liquidación corregida ----------------------------------------------------------


def _actual(**extra):
    base = {"home_goals": 2, "away_goals": 1}
    base.update(extra)
    return base


def test_settlement_handles_markets_that_were_always_lost():
    a = _actual(fouls_home=12, fouls_away=14)
    assert evaluate_prediction({"category": "Resultado", "selection": "Local FC"}, a, "Local FC", "Visita") == "WON"
    assert evaluate_prediction({"category": "Goles", "selection": "2 a 4 goles"}, a, "Local FC", "Visita") == "WON"
    assert (
        evaluate_prediction(
            {"category": "Faltas", "selection": "Más de 23.5 faltas", "line": 23.5, "side": "over"},
            a, "Local FC", "Visita",
        )
        == "WON"
    )
    assert (
        evaluate_prediction(
            {"category": "Resultado", "selection": "Local FC gana y Ambos Marcan"}, a, "Local FC", "Visita"
        )
        == "WON"
    )
    # Córners 1T sin dato por mitad: pendiente, no se liquida con el total del partido.
    assert (
        evaluate_prediction(
            {"category": "Córners", "selection": "1T Más de 3.5 córners", "line": 3.5, "side": "over"},
            _actual(corners_home=8, corners_away=6), "Local FC", "Visita",
        )
        == "PENDING"
    )
    assert evaluate_prediction({"category": "Desconocida", "selection": "x"}, a, "A", "B") == UNSUPPORTED


# --- 4. Selección por valor esperado ---------------------------------------------


def _probs() -> ProbabilityReport:
    return goal_probabilities(HOME, AWAY, 1650, 1500)


def test_odds_keys_mapping():
    assert odds_key_for_candidate("goals_total_over_15") == "over_15"
    assert odds_key_for_candidate("corners_total_over_95") == "over_95_corners"
    assert odds_key_for_candidate("match_1x2_home") == "home_win"
    assert odds_key_for_candidate("cards_total_over_35") is None


def test_negative_value_selection_is_dropped_and_positive_is_tagged():
    home, away = Team(1, "Local FC"), Team(2, "Visita")
    expected = ExpectedMetrics()
    probs = _probs()
    without = select_statistical_markets(home, away, probs, expected)
    assert all("edge" not in m for m in without)
    goal_pick = next(m for m in without if m["market"] == "Goles totales")
    line = goal_pick["selection"]  # p. ej. "Más de 1.5 goles"
    side = "over" if line.startswith("Más") else "under"
    code = line.split()[2].replace(".", "")
    key = f"{side}_{code}"
    p = goal_pick["probability"]

    # Cuota que deja EV negativo -> se descarta aunque la probabilidad sea alta.
    bad_price = round(0.97 / p, 2)
    dropped = select_statistical_markets(home, away, _probs(), expected, odds={key: bad_price})
    assert not any(m["selection"] == line for m in dropped)

    # Cuota con EV positivo -> se muestra con cuota y EV, y es el pick recomendado.
    good_price = round(1.15 / p, 2)
    priced = select_statistical_markets(home, away, _probs(), expected, odds={key: good_price})
    item = next(m for m in priced if m["selection"] == line)
    assert item["odds"] == good_price
    assert abs(item["edge"] - (p * good_price - 1)) < 1e-3
    top = select_top_recommended_pick(priced)
    assert top["selection"] == line and top["edge"] == item["edge"]
