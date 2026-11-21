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
    # Goles + asistencias por jugador del propio equipo (player_id -> aportes) y si el
    # partido trae datos de jugadores; sirve para medir el peso de las bajas.
    contributions: dict[int, float] = field(default_factory=dict)
    player_data: bool = False
    # Jugadores propios de baja (lesión o sanción) en este partido.
    sidelined: tuple[int, ...] = ()
    # Minutos de cada jugador propio y once inicial del partido (para la fuerza del once).
    minutes: dict[int, float] = field(default_factory=dict)
    starters: tuple[int, ...] = ()


@dataclass(frozen=True)
class PlayerShot:
    player_id: int
    name: str
    team_id: int
    shots_on_target: float
    minutes: float
    total_shots: float = 0.0
    goals: float = 0.0
    total_shots_known: bool = True  # False si el total se estimó desde los tiros al arco


@dataclass(frozen=True)
class ConfidenceScore:
    score: int          # 0 a 100
    level: str          # "ALTA", "MEDIA", "BAJA"
    sample_size: int
    detailed_matches: int
    lineups_confirmed: bool
    reasons: list[str] = field(default_factory=list)




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
    score_matrix: list[list[float]] = field(repr=False)
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


@dataclass
class ExpectedMetrics:
    corners_home: float | None = None
    corners_away: float | None = None
    corners_1x2_home: float | None = None
    corners_1x2_away: float | None = None
    total_shots_home: float | None = None
    total_shots_away: float | None = None
    shots_on_home: float | None = None
    shots_on_away: float | None = None
    woodwork_home: float | None = None
    woodwork_away: float | None = None
    over_05_woodwork: float | None = None
    cards_home: float | None = None
    cards_away: float | None = None
    dispersion_corners: float = 0.18
    dispersion_cards: float = 0.27
    dispersion_shots: float = 0.10
    dispersion_offsides: float = 0.16
    offsides_home: float | None = None
    offsides_away: float | None = None
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
    risks: list[str]
    sources: list[str]
    generated_at: str
    statistical_markets: list[dict[str, Any]] = field(default_factory=list)
    confidence: ConfidenceScore | None = None
    dynamic_calibration_info: Any = None
    top_pick: dict[str, Any] | None = None
    featured_markets: list[dict[str, Any]] = field(default_factory=list)
    # Árbitro asignado cuyo promedio de tarjetas entra en la proyección (nombre, promedio, partidos).
    referee: dict[str, Any] | None = None

    def json_payload(self) -> dict[str, Any]:
        """Datos cerrados del análisis para la salida JSON (`analyze.py --json`)."""
        payload = asdict(self)
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
