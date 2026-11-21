"""Métricas sin estado para validar pronósticos con resultados ya conocidos.

Estas utilidades no guardan partidos ni predicciones. Quien ejecute una
evaluación proporciona las probabilidades y los desenlaces de la muestra.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Sequence


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_predicted: float | None
    observed_frequency: float | None


def brier_score(probabilities: Sequence[float], outcomes: Sequence[int | bool]) -> float:
    probabilities, outcomes = _validated_pairs(probabilities, outcomes)
    return sum((probability - outcome) ** 2 for probability, outcome in zip(probabilities, outcomes)) / len(
        probabilities
    )


def log_loss(probabilities: Sequence[float], outcomes: Sequence[int | bool]) -> float:
    probabilities, outcomes = _validated_pairs(probabilities, outcomes)
    epsilon = 1e-15
    return -sum(
        outcome * log(max(epsilon, probability))
        + (1 - outcome) * log(max(epsilon, 1.0 - probability))
        for probability, outcome in zip(probabilities, outcomes)
    ) / len(probabilities)


def calibration_bins(
    probabilities: Sequence[float],
    outcomes: Sequence[int | bool],
    bins: int | Sequence[float] = 10,
) -> list[CalibrationBin]:
    """Agrupa por tramos de probabilidad. `bins` es un número de tramos iguales o
    una lista ascendente de bordes (p. ej. [0.60, 0.65, ..., 0.88])."""
    probabilities, outcomes = _validated_pairs(probabilities, outcomes)
    if isinstance(bins, int):
        if bins < 2:
            raise ValueError("bins debe ser al menos 2.")
        edges = [index / bins for index in range(bins + 1)]
    else:
        edges = [float(edge) for edge in bins]
        if len(edges) < 2 or edges != sorted(edges):
            raise ValueError("Los bordes deben ser al menos dos y ascendentes.")

    count = len(edges) - 1
    grouped: list[list[tuple[float, int]]] = [[] for _ in range(count)]
    for probability, outcome in zip(probabilities, outcomes):
        if probability < edges[0] or probability > edges[-1]:
            continue
        index = count - 1
        for position in range(count):
            if probability < edges[position + 1]:
                index = position
                break
        grouped[index].append((probability, outcome))

    result: list[CalibrationBin] = []
    for index, values in enumerate(grouped):
        lower, upper = edges[index], edges[index + 1]
        if values:
            mean_predicted = sum(value[0] for value in values) / len(values)
            observed = sum(value[1] for value in values) / len(values)
        else:
            mean_predicted = observed = None
        result.append(CalibrationBin(lower, upper, len(values), mean_predicted, observed))
    return result


def _validated_pairs(
    probabilities: Sequence[float], outcomes: Sequence[int | bool]
) -> tuple[list[float], list[int]]:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities y outcomes deben tener la misma longitud y no estar vacíos.")
    checked_probabilities = [float(value) for value in probabilities]
    if any(value < 0.0 or value > 1.0 for value in checked_probabilities):
        raise ValueError("Cada probabilidad debe estar entre 0 y 1.")
    checked_outcomes = [int(value) for value in outcomes]
    if any(value not in {0, 1} for value in checked_outcomes):
        raise ValueError("Cada resultado debe ser 0 o 1.")
    return checked_probabilities, checked_outcomes
