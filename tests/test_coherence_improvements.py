"""Tests de las correcciones de coherencia: Elo en amistosos, filtro de evidencia,
justificaciones, reglas de presentación y titularidad."""

from types import SimpleNamespace

from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team, TeamMatch
from deport_ai.formatter import format_adaptive_report
from deport_ai.markets_catalog import MarketDefinition
from deport_ai.presentation_catalog import MarketPresentationCatalog
from deport_ai.service import lineups_are_confirmed
from deport_ai.sportmonks import _period_score
from deport_ai.statistical_markets import (
    _explain_market,
    _get_concept_group,
    evidence_contradicts,
    select_statistical_markets,
)
from deport_ai.stats_engine import (
    _expected_count,
    extract_team_matches,
    calculate_confidence_score,
    get_competition_profile,
    goal_probabilities,
    stat_value,
)

HOME = Team(1, "Local")
AWAY = Team(2, "Visitante")


def _match(i, gf, ga, is_home=True, stats_for=None, stats_against=None, ht=None, weight=1.0):
    return TeamMatch(
        fixture_id=i,
        date=f"2026-10-{30 - i:02d}",
        team_id=1,
        opponent_id=100 + i,
        is_home=is_home,
        goals_for=gf,
        goals_against=ga,
        result="W" if gf > ga else "D" if gf == ga else "L",
        stats_for=stats_for or {},
        stats_against=stats_against or {},
        competition_weight=weight,
        goals_for_1h=None if ht is None else ht[0],
        goals_against_1h=None if ht is None else ht[1],
    )


def _defn(group, selection, line=None, side="binary"):
    return MarketDefinition(
        id=f"test_{group}",
        category="Test",
        group=group,
        selection_template=selection,
        market_template=selection,
        line=line,
        side=side,
        probability_source="none",
        projection_source=None,
        explanation_template="Porque el modelo lo proyecta.",
    )


def _probabilities(**overrides) -> ProbabilityReport:
    base = dict(
        home_win=0.72,
        draw=0.18,
        away_win=0.10,
        over_15=0.86,
        over_25=0.67,
        under_25=0.33,
        btts=0.52,
        expected_home_goals=2.1,
        expected_away_goals=0.8,
        shared_goal_component=0.0,
        score_matrix=[[1.0]],
    )
    base.update(overrides)
    return ProbabilityReport(**base)


# ---------------------------------------------------------------- 1. Elo / amistosos

def _strong_vs_weak():
    strong = [_match(i, 3, 0, is_home=i % 2 == 0, weight=0.35) for i in range(10)]
    weak = [_match(i, 0, 3, is_home=i % 2 == 0, weight=0.35) for i in range(10)]
    return strong, weak


def test_friendly_profile_is_selected_by_id_and_name():
    assert get_competition_profile(1082).name == "Amistoso Internacional"
    assert get_competition_profile(None, "Club Friendlies").elo_weight_cap == 0.15


def test_friendly_caps_elo_weight_and_expected_goals():
    strong, weak = _strong_vs_weak()
    generic = goal_probabilities(strong, weak, 1900.0, 1400.0)
    friendly = goal_probabilities(strong, weak, 1900.0, 1400.0, league_id=1082)
    assert friendly.attribution_home.elo_impact < generic.attribution_home.elo_impact
    assert friendly.expected_home_goals <= 3.5
    assert friendly.expected_away_goals <= 3.0
    assert friendly.expected_home_goals < generic.expected_home_goals


# ---------------------------------------------------------------- tiros al palo

def test_sparse_woodwork_missing_counts_as_zero_in_detailed_matches():
    detailed = {"total_shots": 12.0}
    assert stat_value(detailed, "hit_woodwork") == 0.0
    assert stat_value({}, "hit_woodwork") is None
    assert stat_value(detailed, "corner_kicks") is None  # solo eventos raros se rellenan

    # 1 partido con palo y 7 detallados sin palo: antes promediaba solo el partido con palo.
    att = [_match(0, 1, 0, stats_for={"total_shots": 10, "hit_woodwork": 2})] + [
        _match(i, 1, 0, stats_for={"total_shots": 10}) for i in range(1, 8)
    ]
    dfn = [_match(0, 1, 0, stats_against={"total_shots": 10, "hit_woodwork": 2})] + [
        _match(i, 1, 0, stats_against={"total_shots": 10}) for i in range(1, 8)
    ]
    value = _expected_count(att, dfn, True, False, "hit_woodwork")
    assert value is not None and value < 1.0


# ---------------------------------------------------------------- 2. filtro de coherencia

def test_evidence_contradicts_rules():
    # Tasa histórica < 50%
    assert evidence_contradicts(0.75, {"hits": 3, "n": 10, "avg": None, "line": None, "side": None}, False)
    # Desvío modelo-historial > 20 pp
    assert evidence_contradicts(0.81, {"hits": 6, "n": 11, "avg": None, "line": None, "side": None}, False)
    # Promedio del lado contrario de la línea
    assert evidence_contradicts(0.82, {"hits": 5, "n": 7, "avg": 4.9, "line": 4.5, "side": "under"}, True)
    # Muestra insuficiente solo descarta mercados de estadísticas
    assert evidence_contradicts(0.70, {"hits": 4, "n": 4, "avg": 15.8, "line": 10.5, "side": "over"}, True)
    assert not evidence_contradicts(0.70, {"hits": 4, "n": 4, "avg": None, "line": None, "side": None}, False)
    # Evidencia consistente
    assert not evidence_contradicts(0.80, {"hits": 7, "n": 8, "avg": 6.4, "line": 3.5, "side": "over"}, True)
    assert not evidence_contradicts(0.80, None, True)


def _corner_matches(value):
    return [_match(i, 1, 1, stats_for={"corner_kicks": value}, stats_against={"corner_kicks": 4}) for i in range(8)]


def test_contradicted_team_corners_line_is_discarded():
    expected = ExpectedMetrics(corners_home=7.0, corners_away=3.0, dispersion_corners=0.10)
    low = select_statistical_markets(
        HOME, AWAY, _probabilities(), expected, recent_home=_corner_matches(3), recent_away=_corner_matches(3)
    )
    assert not any(m["selection"].startswith("Local Más de") and "córners" in m["selection"] for m in low)

    high = select_statistical_markets(
        HOME, AWAY, _probabilities(), expected, recent_home=_corner_matches(7), recent_away=_corner_matches(3)
    )
    assert any(m["selection"].startswith("Local Más de") and "córners" in m["selection"] for m in high)
    assert all("evidence" not in m for m in high)


# ---------------------------------------------------------------- 3. justificaciones

def test_team_score_both_halves_uses_halftime_scores():
    # 2+ goles pero todos en el 1T: antes se citaba como "anotó 2 o más goles".
    rec = [_match(i, 2, 0, ht=(2, 0)) for i in range(6)] + [_match(6, 2, 0, ht=(1, 0))]
    text, ev = _explain_market(_defn("team_score_both_halves", "Local anota en ambas mitades"), HOME, AWAY, 2.0, 0.7, rec, rec)
    assert "marcó en ambos tiempos en 1 de sus últimos 7" in text
    assert ev == {"hits": 1, "n": 7, "avg": None, "line": None, "side": None}


def test_halves_without_halftime_data_use_projection_without_counts():
    rec = [_match(i, 2, 0) for i in range(8)]
    text, ev = _explain_market(_defn("goal_both_halves", "Habrá gol en ambas mitades"), HOME, AWAY, 2.6, 0.7, rec, rec)
    assert ev is None and "2.60 goles" in text


def test_fouls_total_wording_follows_average_not_side():
    rec = [_match(i, 1, 1, stats_for={"fouls": 15}, stats_against={"fouls": 13}) for i in range(8)]
    text, ev = _explain_market(_defn("fouls_total", "Menos de 27.5 faltas", 27.5, "under"), HOME, AWAY, 27.6, 0.66, rec, rec)
    assert "fluido" not in text and "promedian 28.0 faltas" in text
    assert evidence_contradicts(0.66, ev, True)  # promedio 28.0 por encima de la línea Menos de 27.5


def test_result_wording_has_no_venue_claims_and_dnb_ignores_draws():
    rec = [_match(i, 1, 0, is_home=False) for i in range(5)] + [_match(5 + i, 1, 1) for i in range(5)]
    text, _ = _explain_market(_defn("double_chance", "Local o Empate (1X)"), HOME, AWAY, None, 0.8, rec, rec)
    assert "local" not in text.split("Local", 1)[1].lower()
    text, ev = _explain_market(_defn("dnb", "DNB Local"), HOME, AWAY, None, 0.8, rec, rec)
    assert ev["n"] == 5 and ev["hits"] == 5


def test_no_club_wording_and_shots_on_target_uses_real_key():
    rec = [_match(i, 1, 1, stats_for={"shots_on_goal": 5, "total_shots": 12}, stats_against={"shots_on_goal": 2, "total_shots": 8}) for i in range(8)]
    text, ev = _explain_market(_defn("shots_on_1x2", "Local tiene más tiros a puerta"), HOME, AWAY, None, 0.7, rec, rec)
    assert ev["hits"] == 8
    text, _ = _explain_market(_defn("shots_total", "Menos de 26.5 remates", 26.5, "under"), HOME, AWAY, 20.0, 0.7, rec, rec)
    assert "clubes" not in text


def test_woodwork_explanation_cites_real_frequency():
    rec = [_match(i, 1, 1, stats_for={"total_shots": 10, **({"hit_woodwork": 1} if i < 2 else {})}, stats_against={"total_shots": 9}) for i in range(8)]
    text, ev = _explain_market(_defn("woodwork", "Tiro al palo en el partido", 0.5), HOME, AWAY, 0.5, 0.78, rec, rec)
    assert ev["hits"] == 4 and ev["n"] == 16
    assert evidence_contradicts(0.78, ev, True)


# ---------------------------------------------------------------- 5. reglas de presentación

def test_half_over_05_is_trivial_and_not_presentable():
    for group, sel in (("first_half", "1T Más de 0.5 goles"), ("second_half", "2T Más de 0.5 goles")):
        assert not MarketPresentationCatalog.is_presentable({"group": group, "selection": sel, "side": "over", "line": 0.5})
    assert MarketPresentationCatalog.is_presentable({"group": "first_half", "selection": "1T Más de 1.5 goles", "side": "over", "line": 1.5})


def test_correlated_markets_share_one_family():
    result = {_get_concept_group({"group": g}) for g in ("1x2", "double_chance", "dnb", "combo_result_goals", "combo_1x2_btts")}
    clean = {_get_concept_group({"group": g}) for g in ("both_score", "clean_sheet", "win_to_nil")}
    goals = {_get_concept_group({"group": g, "side": "over"}) for g in ("total_goals", "multigoals")}
    assert len(result) == len(clean) == len(goals) == 1


def test_top_pick_is_not_repeated_in_its_category():
    pick = {"selection": "Más de 1.5 goles", "probability": 0.85, "category": "Goles", "explanation": "Porque sí."}
    other = {"selection": "Local Más de 1.5 goles", "probability": 0.70, "category": "Goles", "market": "x", "explanation": "Porque sí."}
    report = SimpleNamespace(
        home=HOME,
        away=AWAY,
        confidence=None,
        top_pick=pick,
        statistical_markets=[{**pick, "market": "Goles totales"}, other],
        probabilities=_probabilities(),
        expected=ExpectedMetrics(),
    )
    text = format_adaptive_report(report)
    assert text.count("Más de 1.5 goles — 85.0%") == 1
    assert "Local Más de 1.5 goles — 70.0%" in text
    assert "Experimental" not in text


# ---------------------------------------------------------------- 4. titularidad y muestra

def test_lineups_need_both_teams():
    assert not lineups_are_confirmed([{"startXI": [{"player": {"id": 1}}]}, {"startXI": []}])
    assert lineups_are_confirmed([{"startXI": [{"player": {"id": 1}}]}, {"startXI": [{"player": {"id": 2}}]}])
    assert not lineups_are_confirmed(None)


def test_player_props_follow_confirmed_starter_status():
    def shots(is_starter):
        return [{"name": "Nueve", "expected_per_match": 3.0, "probability_two_plus": 0.75, "is_starter": is_starter}]

    starter = select_statistical_markets(HOME, AWAY, _probabilities(), ExpectedMetrics(player_shots={1: shots(True)}))
    prop = next(m for m in starter if m["category"] == "Jugadores")
    assert "requires_starter_confirmation" not in prop

    unknown = select_statistical_markets(HOME, AWAY, _probabilities(), ExpectedMetrics(player_shots={1: shots(None)}))
    assert next(m for m in unknown if m["category"] == "Jugadores")["requires_starter_confirmation"] is True

    bench = select_statistical_markets(HOME, AWAY, _probabilities(), ExpectedMetrics(player_shots={1: shots(False)}))
    assert not any(m["category"] == "Jugadores" for m in bench)


def test_confidence_cannot_be_high_with_few_detailed_matches_for_one_team():
    detailed = {"shots_on_goal": 4, "corner_kicks": 5}
    home = [_match(i, 1, 1, stats_for=detailed) for i in range(12)]
    away = [_match(i, 1, 1, stats_for=detailed if i < 3 else {}) for i in range(12)]
    full = calculate_confidence_score(home, home, lineups_confirmed=True)
    thin = calculate_confidence_score(home, away, lineups_confirmed=True)
    assert full.level == "ALTA"
    assert thin.level != "ALTA"


# ---------------------------------------------------------------- marcador al descanso

def test_halftime_score_is_parsed_from_sportmonks_and_team_matches():
    scores = [
        {"participant_id": 1, "description": "1ST_HALF", "score": {"goals": 1}},
        {"participant_id": 2, "description": "1ST_HALF", "score": {"goals": 0}},
        {"participant_id": 1, "description": "CURRENT", "score": {"goals": 2}},
    ]
    assert _period_score(scores, 1, "1ST_HALF") == 1
    assert _period_score(scores, 3, "1ST_HALF") is None

    row = {
        "fixture": {"id": 10, "date": "2026-10-01"},
        "teams": {"home": {"id": 1, "name": "Local"}, "away": {"id": 2, "name": "Visitante"}},
        "goals": {"home": 2, "away": 1},
        "halftime": {"home": 1, "away": 0},
        "league": {"id": 1082, "name": "Friendly International"},
    }
    match = extract_team_matches([row], 2, {})[0]
    assert (match.goals_for, match.goals_for_1h, match.goals_against_1h) == (1, 0, 1)
