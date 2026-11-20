"""Parámetros del modelo de goles ajustables con datos, por liga.

Los valores por defecto son conservadores. `fit_parameters` los ajusta por máxima
verosimilitud walk-forward (cada partido se predice solo con información anterior)
y el resultado se guarda en `model_params.json`, que el motor carga por liga.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from statistics import fmean, pvariance
from typing import Any, Callable, Iterable

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parents[2] / "model_params.json"


@dataclass(frozen=True)
class ModelParameters:
    # Corrección Dixon-Coles de marcadores bajos.
    rho: float = -0.08
    # Peso del diferencial Elo sobre la lambda basada en goles (0 = ignorar Elo,
    # 1 = multiplicar por el factor Elo completo, que cuenta dos veces la forma).
    elo_weight: float = 0.5
    # Mezcla de muestra en la sede (local/visitante) frente a la muestra global.
    venue_weight: float = 0.65
    # Mezcla de promedios de temporada frente a la muestra reciente.
    season_weight: float = 0.35
    # Escala de la tabla manual de niveles de club usada como prior Elo (0 = sin tabla).
    club_tier_scale: float = 1.0
    # Ajuste por nivel del rival en los goles. Desactivado: el Elo ya lo recoge.
    use_sos: bool = False
    # Peso del xG (Flashscore) frente a los goles reales al estimar ataque y defensa.
    # Solo actúa en partidos que tienen xG; 0 = modelo solo con goles.
    xg_weight: float = 0.35
    # Proporción de goles esperada en el primer tiempo.
    first_half_share: float = 0.45
    # Dispersión binomial negativa estimada desde datos (None = perfil de liga).
    dispersion_corners: float | None = None
    dispersion_cards: float | None = None
    # Metadatos del ajuste.
    fitted: bool = False
    sample_size: int = 0
    log_loss: float | None = None
    baseline_log_loss: float | None = None
    fitted_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ModelParameters":
        known = {name for name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known})


DEFAULT_PARAMETERS = ModelParameters()

# Rejillas de búsqueda para el ajuste (descenso por coordenadas).
SEARCH_GRID: dict[str, list[float]] = {
    "rho": [-0.18, -0.14, -0.10, -0.08, -0.06, -0.03, 0.0, 0.04],
    "elo_weight": [0.0, 0.15, 0.3, 0.45, 0.6, 0.8, 1.0],
    "venue_weight": [0.35, 0.5, 0.65, 0.8, 0.95],
    "season_weight": [0.0, 0.2, 0.35, 0.5],
    "club_tier_scale": [0.0, 0.25, 0.5, 0.75, 1.0],
}


def params_path() -> Path:
    env = os.getenv("DEPORT_AI_MODEL_PARAMS")
    return Path(env) if env else DEFAULT_PARAMS_PATH


def load_all_parameters(path: Path | None = None) -> dict[str, ModelParameters]:
    target = path or params_path()
    if not target.exists():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(key): ModelParameters.from_json(value) for key, value in raw.items() if isinstance(value, dict)}


def load_parameters(league_id: int | None, path: Path | None = None) -> ModelParameters:
    """Parámetros ajustados para la liga; si no existen, los globales; si no, los por defecto."""
    stored = load_all_parameters(path)
    if league_id is not None and str(league_id) in stored:
        return stored[str(league_id)]
    return stored.get("default", DEFAULT_PARAMETERS)


def save_parameters(key: str, params: ModelParameters, path: Path | None = None) -> Path:
    target = path or params_path()
    stored = load_all_parameters(target)
    stored[str(key)] = params
    target.write_text(
        json.dumps({k: v.to_json() for k, v in stored.items()}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target


def estimate_dispersion(totals: Iterable[float]) -> float | None:
    """Estima alpha de la binomial negativa por momentos: Var = mu + alpha * mu^2."""
    values = [float(v) for v in totals]
    if len(values) < 20:
        return None
    mean = fmean(values)
    if mean <= 0:
        return None
    alpha = (pvariance(values) - mean) / (mean**2)
    return round(max(0.0, min(0.6, alpha)), 4)


def fit_parameters(
    objective: Callable[[ModelParameters], tuple[float, int]],
    start: ModelParameters = DEFAULT_PARAMETERS,
    grid: dict[str, list[float]] | None = None,
    passes: int = 2,
) -> ModelParameters:
    """Descenso por coordenadas sobre la rejilla, minimizando el log-loss walk-forward.

    `objective(params)` devuelve (log_loss medio de marcadores, n partidos evaluados).
    """
    grid = grid or SEARCH_GRID
    baseline, n = objective(start)
    if not math.isfinite(baseline) or n == 0:
        return start
    best, best_loss = start, baseline
    for _ in range(passes):
        improved = False
        for name, values in grid.items():
            for value in values:
                if getattr(best, name) == value:
                    continue
                candidate = replace(best, **{name: value})
                loss, _ = objective(candidate)
                if loss < best_loss - 1e-6:
                    best, best_loss, improved = candidate, loss, True
        if not improved:
            break
    return replace(
        best,
        fitted=True,
        sample_size=n,
        log_loss=round(best_loss, 5),
        baseline_log_loss=round(baseline, 5),
    )
