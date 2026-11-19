from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Team:
    id: int
    name: str
    country: str | None = None


@dataclass(frozen=True)
class MatchRef:
    fixture_id: int
    home: Team
    away: Team
    date: str
    league_id: int | None
    league_name: str | None
    season: int | None
    status: str
    home_goals: int | None = None
    away_goals: int | None = None


@dataclass(frozen=True)
class TeamMatch:
    fixture_id: int
    date: str
    team_id: int
    opponent_id: int
    is_home: bool
    goals_for: int
    goals_against: int
    result: str
    opponent_name: str = ""
    stats_for: dict[str, float] = field(default_factory=dict)
    stats_against: dict[str, float] = field(default_factory=dict)
    competition_weight: float = 1.0
    league_id: int | None = None
    # Goles al descanso (None si la API no publica el marcador del 1T)
    goals_for_1h: int | None = None
    goals_against_1h: int | None = None


@dataclass(frozen=True)
class PlayerShot:
    player_id: int
    name: str
    team_id: int
    shots_on_target: float
    minutes: float
    total_shots: float = 0.0
    goals: float = 0.0
    total_shots_known: bool = True  # False si el total se estimó desde los tiros a puerta


@dataclass(frozen=True)
class ConfidenceScore:
    score: int          # 0 a 100
    level: str          # "ALTA", "MEDIA", "BAJA"
    sample_size: int
    detailed_matches: int
    lineups_confirmed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FactorAttribution:
    base_league_goals: float
    elo_impact: float
    venue_impact: float
    recent_form_impact: float
    rest_impact: float
    final_expected_goals: float


@dataclass
class ProbabilityReport:
    home_win: float
    draw: float
    away_win: float
    over_15: float
    over_25: float
    under_25: float
    btts: float
    expected_home_goals: float
    expected_away_goals: float
    shared_goal_component: float
    score_matrix: list[list[float]] = field(repr=False)
    ah_home_minus_15: float | None = None
    ah_away_plus_15: float | None = None
    ah_home_plus_15: float | None = None
    ah_away_minus_15: float | None = None
    ah_home_minus_25: float | None = None
    ah_away_plus_25: float | None = None
    ah_home_plus_25: float | None = None
    ah_away_minus_25: float | None = None
    dnb_home: float | None = None
    dnb_away: float | None = None
    first_half_over_05: float | None = None
    first_half_over_15: float | None = None
    first_half_under_15: float | None = None
    second_half_over_05: float | None = None
    second_half_over_15: float | None = None
    second_half_under_15: float | None = None
    over_35: float | None = None
    under_35: float | None = None
    home_over_15: float | None = None
    home_over_25: float | None = None
    away_over_15: float | None = None
    home_under_15: float | None = None
    away_under_15: float | None = None
    clean_sheet_home: float | None = None
    clean_sheet_away: float | None = None
    multigoal_1_3: float | None = None
    multigoal_2_4: float | None = None
    multigoal_2_5: float | None = None
    home_win_and_btts: float | None = None
    away_win_and_btts: float | None = None
    dc_1x_and_btts: float | None = None
    dc_x2_and_btts: float | None = None
    btts_second_half: float | None = None
    attribution_home: FactorAttribution | None = None
    attribution_away: FactorAttribution | None = None


@dataclass
class ExpectedMetrics:
    corners_home: float | None = None
    corners_away: float | None = None
    corners_1x2_home: float | None = None
    corners_1x2_tie: float | None = None
    corners_1x2_away: float | None = None
    over_75_corners: float | None = None
    over_85_corners: float | None = None
    over_95_corners: float | None = None
    over_105_corners: float | None = None
    over_115_corners: float | None = None
    under_105_corners: float | None = None
    over_45_corners_home: float | None = None
    over_45_corners_away: float | None = None
    under_35_corners_home: float | None = None
    under_35_corners_away: float | None = None
    under_45_corners_home: float | None = None
    under_45_corners_away: float | None = None
    over_55_corners_home: float | None = None
    over_55_corners_away: float | None = None
    over_65_corners_home: float | None = None
    over_65_corners_away: float | None = None
    over_25_cards_home: float | None = None
    over_25_cards_away: float | None = None
    total_shots_home: float | None = None
    total_shots_away: float | None = None
    over_215_total_shots: float | None = None
    over_235_total_shots: float | None = None
    over_255_total_shots: float | None = None
    over_275_total_shots: float | None = None
    over_295_total_shots: float | None = None
    under_245_total_shots: float | None = None
    under_265_total_shots: float | None = None
    over_115_shots_home: float | None = None
    over_135_shots_home: float | None = None
    over_155_shots_home: float | None = None
    over_175_shots_home: float | None = None
    over_115_shots_away: float | None = None
    over_135_shots_away: float | None = None
    under_85_shots_home: float | None = None
    under_95_shots_home: float | None = None
    under_85_shots_away: float | None = None
    under_95_shots_away: float | None = None
    shots_on_home: float | None = None
    shots_on_away: float | None = None
    over_75_shots_on: float | None = None
    over_85_shots_on: float | None = None
    over_95_shots_on: float | None = None
    over_105_shots_on: float | None = None
    under_85_shots_on: float | None = None
    under_95_shots_on: float | None = None
    over_45_shots_on_home: float | None = None
    over_55_shots_on_home: float | None = None
    over_65_shots_on_home: float | None = None
    over_75_shots_on_home: float | None = None
    under_25_shots_on_home: float | None = None
    under_35_shots_on_home: float | None = None
    over_35_shots_on_away: float | None = None
    over_45_shots_on_away: float | None = None
    under_25_shots_on_away: float | None = None
    under_35_shots_on_away: float | None = None
    woodwork_home: float | None = None
    woodwork_away: float | None = None
    over_05_woodwork: float | None = None
    cards_home: float | None = None
    cards_away: float | None = None
    over_15_cards: float | None = None
    over_25_cards: float | None = None
    over_35_cards: float | None = None
    over_45_cards: float | None = None
    over_15_cards_home: float | None = None
    over_15_cards_away: float | None = None
    over_25_cards_home: float | None = None
    over_25_cards_away: float | None = None
    dispersion_corners: float = 0.18
    dispersion_cards: float = 0.27
    dispersion_shots: float = 0.10
    dispersion_offsides: float = 0.16
    offsides_home: float | None = None
    offsides_away: float | None = None
    over_25_offsides: float | None = None
    over_35_offsides: float | None = None
    under_25_offsides: float | None = None
    under_35_offsides: float | None = None
    under_45_offsides: float | None = None
    over_15_offsides_home: float | None = None
    over_15_offsides_away: float | None = None
    under_15_offsides_home: float | None = None
    under_15_offsides_away: float | None = None
    fouls_home: float | None = None
    fouls_away: float | None = None
    dispersion_fouls: float = 0.12
    corners_first_half: float | None = None
    player_shots: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    anytime_goalscorers: dict[int, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass
class AnalysisReport:
    home: Team
    away: Team
    fixture: MatchRef | None
    recent_home: list[TeamMatch]
    recent_away: list[TeamMatch]
    h2h: list[MatchRef]
    probabilities: ProbabilityReport
    expected: ExpectedMetrics
    elo_home: float
    elo_away: float
    injuries: list[dict[str, Any]]
    lineups: list[dict[str, Any]]
    odds: dict[str, float]
    opportunities: list[dict[str, Any]]
    risks: list[str]
    sources: list[str]
    generated_at: str
    statistical_markets: list[dict[str, Any]] = field(default_factory=list)
    common_opponents: list[dict[str, Any]] = field(default_factory=list)
    confidence: ConfidenceScore | None = None
    attribution_home: FactorAttribution | None = None
    attribution_away: FactorAttribution | None = None
    narrative: str | None = None
    dynamic_calibration_info: Any = None
    top_pick: dict[str, Any] | None = None

    def llm_payload(self) -> dict[str, Any]:
        """Datos cerrados: el LLM puede explicarlos, no recalcularlos."""
        payload = asdict(self)
        payload.pop("narrative", None)
        if self.probabilities.score_matrix:
            scores = [
                (f"{h}-{a}", self.probabilities.score_matrix[h][a])
                for h in range(len(self.probabilities.score_matrix))
                for a in range(len(self.probabilities.score_matrix[h]))
            ]
            if scores:
                best_score, best_prob = max(scores, key=lambda x: x[1])
                payload["probabilities"]["most_likely_score"] = best_score
                payload["probabilities"]["score_prob"] = round(best_prob, 4)
        payload["probabilities"].pop("score_matrix", None)
        payload["recent_home"] = payload["recent_home"][:5]
        payload["recent_away"] = payload["recent_away"][:5]
        payload["h2h"] = payload["h2h"][:5]

        adaptive_md = ""
        try:
            from .formatter import format_adaptive_report
            adaptive_md = format_adaptive_report(self)
        except Exception:
            pass

        ordered_payload: dict[str, Any] = {
            "adaptive_report": adaptive_md,
            "statistical_markets": payload.get("statistical_markets", []),
        }
        for k, v in payload.items():
            if k not in ordered_payload:
                ordered_payload[k] = v
        return ordered_payload
