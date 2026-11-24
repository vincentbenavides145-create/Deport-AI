from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean
from typing import Any

from .domain import ExpectedMetrics, ProbabilityReport
from .storage import DatabaseManager

# Mínimo de predicciones REALES liquidadas por categoría antes de alterar probabilidades.
MIN_CALIBRATION_SAMPLE = 30
# Peso de credibilidad: con n predicciones, la corrección aplicada es n / (n + CREDIBILITY_K).
CREDIBILITY_K = 50.0
# Mercado de total del partido cuya proyección sirve para medir el sesgo de cada categoría.
# Goles no se corrige aquí: sus probabilidades salen de la matriz de marcadores, que ya
# está calculada, y mover solo los goles esperados dejaría cifras que no corresponden.
TOTAL_MARKETS = {"Córners": "Córners totales", "Tarjetas": "Tarjetas totales"}
# Además de por categoría, se calibra por lado (Más/Menos): en resultados reales los
# "Menos de" de córners, tarjetas y tiros al arco acertaron 58-64 % con 71-75 % prometido,
# y los "Más de" iban bien; un solo factor por categoría mezclaba ambos y no corregía nada.
SIDES = ("over", "under")
_SIDE_RE = re.compile(r"\b(Más|Menos) de\b", re.IGNORECASE)
# Los totales del partido se miden aparte de los de equipo en estas categorías: el total
# "Menos de 3.5 goles" acertó 67 % (78.7 % prometido) y los "Menos" de equipo 82 %.
MATCH_TOTAL_CATEGORIES = frozenset({"Goles"})
# Freno por liga: una categoría cuyas últimas 20 predicciones liquidadas en una liga
# acertaron menos del 65 % no se publica en esa liga (córners de la Premier: 13 de 26).
# Mientras está frenada se sigue registrando sin publicar (`unpublished`), así que sus
# resultados nuevos pueden levantar el freno.
FREEZE_MIN_SAMPLE = 20
FREEZE_MAX_HIT_RATE = 0.65
RECENT_SUFFIX = "|recent"


# Tramos de probabilidad publicada para la calibración por tramo (global). En resultados
# reales lo prometido al 85-88 % acertó ~73 % y arrastraba al Pick, que suele ser la
# selección más probable; del 75 al 85 % el modelo iba calibrado.
PROB_BANDS = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.89)


def band_key(probability: float) -> str | None:
    """Clave del tramo de una probabilidad, p. ej. "prob|0.85"; None fuera de los tramos."""
    for low, high in zip(PROB_BANDS, PROB_BANDS[1:]):
        if low <= probability < high:
            return f"prob|{low:.2f}"
    return None


def band_factor(category_factors: dict[str, dict[str, float]], probability: float) -> dict[str, float] | None:
    key = band_key(probability)
    return category_factors.get(key) if key else None


def _prob(item: dict[str, Any], key: str) -> float:
    """Probabilidad de una etapa; las predicciones anteriores solo guardaron la publicada."""
    value = item.get(key)
    return float(value if value is not None else item["predicted_prob"])


def side_key(category: str, side: str) -> str:
    """Clave de calibración de un lado de la categoría, p. ej. "Córners|under"."""
    return f"{category}|{side}"


def selection_side(item: dict[str, Any]) -> str | None:
    """Lado (over/under) de una predicción o candidato: su campo `side` o el texto."""
    side = item.get("side")
    if side in SIDES:
        return side
    match = _SIDE_RE.search(str(item.get("selection") or ""))
    if not match:
        return None
    return "over" if match.group(1).lower() == "más" else "under"


def is_match_total(item: dict[str, Any]) -> bool:
    """Si la selección es un total del partido ("Más/Menos de ..." sin nombre de equipo)."""
    return str(item.get("selection") or "").startswith(("Más de", "Menos de"))


def total_side_key(category: str, side: str) -> str:
    """Clave del lado de los totales del partido, p. ej. "Goles total|under"."""
    return f"{category} total|{side}"


def factor_for(
    category_factors: dict[str, dict[str, float]], category: str, side: str | None, match_total: bool = False
) -> dict[str, float] | None:
    """El factor más específico con muestra propia: total del partido por lado (en
    MATCH_TOTAL_CATEGORIES), lado de la categoría o la categoría."""
    if match_total and side in SIDES and category in MATCH_TOTAL_CATEGORIES:
        specific = category_factors.get(total_side_key(category, side))
        if specific:
            return specific
    if side in SIDES and side_key(category, side) in category_factors:
        return category_factors[side_key(category, side)]
    return category_factors.get(category)


@dataclass
class DynamicCalibrationSummary:
    active: bool
    league_id: int | None
    league_name: str | None
    sample_size: int
    overall_hit_rate: float
    category_factors: dict[str, dict[str, float]]
    bias_offsets: dict[str, float]
    frozen_categories: tuple[str, ...] = ()  # tupla: la salida JSON no admite conjuntos


class DynamicCalibrator:
    """Motor de calibración adaptativa y aprendizaje continuo para DEPORT AI."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def recompute_calibrations(self, min_sample: int = MIN_CALIBRATION_SAMPLE) -> int:
        """Recalcula y actualiza los factores de calibración en la base de datos a partir de apuestas liquidadas."""
        # Las no publicadas (categorías frenadas) también miden al modelo y levantan el freno.
        settled = self.db.get_settled_predictions(include_unpublished=True)
        # Se reescribe entera: un grupo que ya no llega al mínimo (p. ej. porque las anuladas
        # dejaron de contar) no debe quedar activo con su factor antiguo.
        self.db.clear_calibration()
        if not settled:
            return 0

        # Agrupar por (league_id, category)
        grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        # También acumular un global (league_id = 0, category)
        global_grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

        band_grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in settled:
            # Las anuladas (VOID) no dicen nada del acierto: no cuentan para la muestra.
            if p.get("status") not in ("WON", "LOST"):
                continue
            band = band_key(_prob(p, "prob_before_band"))
            if band:
                band_grouped[band].append(p)
            l_id = p.get("league_id") or 0
            cat = p.get("category", "")
            keys = [cat]
            side = selection_side(p)
            if side:
                keys.append(side_key(cat, side))
                if cat in MATCH_TOTAL_CATEGORIES and is_match_total(p):
                    keys.append(total_side_key(cat, side))
            for key in keys:
                grouped[(l_id, key)].append(p)
                global_grouped[key].append(p)

        updated_count = 0

        # 0. Acierto reciente por liga y categoría (para el freno por liga).
        for (l_id, cat), items in grouped.items():
            if not l_id or "|" in cat or len(items) < FREEZE_MIN_SAMPLE:
                continue
            recent = sorted(items, key=lambda i: (i.get("match_date") or "", i.get("id") or 0))[-FREEZE_MIN_SAMPLE:]
            won = sum(1 for i in recent if i["status"] == "WON")
            self.db.save_calibration(
                league_id=l_id,
                category=cat + RECENT_SUFFIX,
                sample_size=len(recent),
                hit_rate=won / len(recent),
                brier_score=0.0,
                bias_offset=0.0,
                shrinkage_factor=1.0,
            )
            updated_count += 1

        # 1. Calibraciones por Liga
        for (l_id, cat), items in grouped.items():
            if len(items) < min_sample:
                continue
            factor_entry = self._entry(cat, items)
            self.db.save_calibration(
                league_id=l_id,
                category=cat,
                sample_size=factor_entry["sample_size"],
                hit_rate=factor_entry["hit_rate"],
                brier_score=factor_entry["brier_score"],
                bias_offset=factor_entry["bias_offset"],
                shrinkage_factor=factor_entry["shrinkage_factor"],
            )
            updated_count += 1

        # 2. Calibraciones Globales (league_id = 0)
        for cat, items in global_grouped.items():
            if len(items) >= min_sample:
                factor_entry = self._entry(cat, items)
                self.db.save_calibration(
                    league_id=0,
                    category=cat,
                    sample_size=factor_entry["sample_size"],
                    hit_rate=factor_entry["hit_rate"],
                    brier_score=factor_entry["brier_score"],
                    bias_offset=factor_entry["bias_offset"],
                    shrinkage_factor=factor_entry["shrinkage_factor"],
                )
                updated_count += 1

        # 3. Calibración por tramo de probabilidad (global): se mide sobre la probabilidad
        # previa al tramo, para que la corrección no se anule a sí misma con el tiempo.
        for key, items in band_grouped.items():
            if len(items) >= min_sample:
                entry = self._staged_entry(items, "prob_before_band")
                entry["bias_offset"] = 0.0
                self.db.save_calibration(
                    league_id=0,
                    category=key,
                    sample_size=entry["sample_size"],
                    hit_rate=entry["hit_rate"],
                    brier_score=entry["brier_score"],
                    bias_offset=0.0,
                    shrinkage_factor=entry["shrinkage_factor"],
                )
                updated_count += 1

        return updated_count

    @classmethod
    def _entry(cls, key: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        # El sesgo de proyección es del total del partido: solo vale en la fila de la
        # categoría (una fila de lado es un subconjunto elegido por su resultado esperado).
        entry = cls._staged_entry(items, "model_prob")
        if "|" in key:
            entry["bias_offset"] = 0.0
        return entry

    @classmethod
    def _staged_entry(cls, items: list[dict[str, Any]], prob_key: str) -> dict[str, Any]:
        """Acierto y muestra con todas las liquidadas; el factor y el Brier, con las que
        guardan la probabilidad de su etapa si ya son 30+.

        Las predicciones anteriores al 21/11/2026 solo guardaron la probabilidad publicada
        (ya corregida por la calibración de entonces); medir el factor sobre ella es una
        aproximación que se abandona en cuanto hay muestra limpia suficiente.
        """
        entry = cls._calculate_factor_entry(items, prob_key=prob_key)
        staged = [i for i in items if i.get(prob_key) is not None]
        if len(staged) < len(items) and len(staged) >= MIN_CALIBRATION_SAMPLE:
            clean = cls._calculate_factor_entry(staged, prob_key=prob_key)
            entry["shrinkage_factor"] = clean["shrinkage_factor"]
            entry["brier_score"] = clean["brier_score"]
        return entry

    @staticmethod
    def _calculate_factor_entry(items: list[dict[str, Any]], prob_key: str = "model_prob") -> dict[str, Any]:
        # Categoría y lado se miden sobre la probabilidad del modelo (antes de calibrar).
        won = sum(1 for i in items if i["status"] == "WON")
        lost = sum(1 for i in items if i["status"] == "LOST")
        resolved = won + lost
        hit_rate = (won / resolved) if resolved > 0 else 0.0

        probs = [_prob(i, prob_key) for i in items if i["status"] in ("WON", "LOST")]
        avg_prob = fmean(probs) if probs else 0.65

        # Brier Score
        brier = 0.0
        for i in items:
            if i["status"] in ("WON", "LOST"):
                outcome_val = 1.0 if i["status"] == "WON" else 0.0
                brier += (_prob(i, prob_key) - outcome_val) ** 2
        brier_avg = (brier / resolved) if resolved > 0 else 0.20

        # Factor de corrección con credibilidad: ratio observado/esperado, atenuado
        # según el tamaño de muestra (n / (n + K)). Puede subir o bajar probabilidades.
        if avg_prob > 0 and resolved >= MIN_CALIBRATION_SAMPLE:
            ratio = hit_rate / avg_prob
            credibility = resolved / (resolved + CREDIBILITY_K)
            shrinkage = 1.0 + (ratio - 1.0) * credibility
            shrinkage = max(0.70, min(1.15, shrinkage))
        else:
            shrinkage = 1.0

        # Sesgo de la proyección: total real del partido menos el total proyectado. Solo
        # vale para los mercados de TOTAL del partido: la proyección de un mercado de
        # equipo o del 1T no es comparable con el total del partido (eso inflaba el sesgo).
        # Una proyección se cuenta una vez por partido y hacen falta 30+ partidos.
        bias_by_fixture: dict[Any, float] = {}
        for i in items:
            proj = i.get("projection")
            cat = i.get("category", "")
            if proj is None or i.get("market") != TOTAL_MARKETS.get(cat):
                continue
            if cat == "Córners":
                home, away = i.get("actual_corners_home"), i.get("actual_corners_away")
            elif cat == "Tarjetas":
                home, away = i.get("actual_cards_home"), i.get("actual_cards_away")
            else:
                continue
            if home is not None and away is not None:
                bias_by_fixture.setdefault(i.get("fixture_id"), (home + away) - float(proj))

        if len(bias_by_fixture) >= MIN_CALIBRATION_SAMPLE:
            bias_offset = fmean(bias_by_fixture.values())
        else:
            bias_offset = 0.0

        return {
            "sample_size": resolved,
            "hit_rate": hit_rate,
            "brier_score": brier_avg,
            "bias_offset": bias_offset,
            "shrinkage_factor": shrinkage,
        }

    def get_calibration_summary(self, league_id: int | None, league_name: str | None = None) -> DynamicCalibrationSummary:
        """Construye un resumen de calibración aplicable para la liga o global."""
        # Lo de la liga manda; lo que la liga aún no tiene (p. ej. un lado con muestra
        # propia) se toma de la calibración global.
        merged: dict[str, dict[str, Any]] = {}
        league_rows = self.db.get_calibration(league_id=league_id)
        if league_id != 0:
            merged.update({r["category"]: r for r in self.db.get_calibration(league_id=0)})
        # Las filas de acierto reciente solo sirven para el freno, no para corregir.
        merged.update({r["category"]: r for r in league_rows if not r["category"].endswith(RECENT_SUFFIX)})
        rows = list(merged.values())
        frozen = tuple(sorted(
            r["category"].removesuffix(RECENT_SUFFIX) for r in league_rows
            if league_id and r["category"].endswith(RECENT_SUFFIX)
            and int(r["sample_size"]) >= FREEZE_MIN_SAMPLE and float(r["hit_rate"]) < FREEZE_MAX_HIT_RATE
        ))

        if not rows:
            return DynamicCalibrationSummary(
                active=False,
                league_id=league_id,
                league_name=league_name,
                sample_size=0,
                overall_hit_rate=0.0,
                category_factors={},
                bias_offsets={},
                frozen_categories=frozen,
            )

        cat_factors: dict[str, dict[str, float]] = {}
        bias_offsets: dict[str, float] = {}
        total_samples = 0
        total_won_weighted = 0.0

        for r in rows:
            cat = r["category"]
            sz = int(r["sample_size"])
            if sz < MIN_CALIBRATION_SAMPLE:
                # Muestra real insuficiente: no se usa para alterar el modelo.
                continue
            hr = float(r["hit_rate"])
            sh = float(r["shrinkage_factor"])
            bias = float(r["bias_offset"])

            cat_factors[cat] = {
                "hit_rate": hr,
                "shrinkage_factor": sh,
                "bias_offset": bias,
                "sample_size": sz,
            }
            if "|" in cat:
                continue  # las filas por lado no se suman al total (ya están en su categoría)
            total_samples += sz
            total_won_weighted += (hr * sz)
            if abs(bias) >= 0.3:
                bias_offsets[cat] = bias

        overall_hr = (total_won_weighted / total_samples) if total_samples > 0 else 0.0

        return DynamicCalibrationSummary(
            active=total_samples >= MIN_CALIBRATION_SAMPLE,
            league_id=league_id,
            league_name=league_name,
            sample_size=total_samples,
            overall_hit_rate=round(overall_hr, 4),
            category_factors=cat_factors,
            bias_offsets=bias_offsets,
            frozen_categories=frozen,
        )

    def apply_dynamic_calibration_to_projections(
        self,
        expected: ExpectedMetrics,
        probabilities: ProbabilityReport,
        calibration: DynamicCalibrationSummary,
    ) -> None:
        """Aplica factores de sesgo empírico directamente a las métricas del modelo."""
        if not calibration.active:
            return

        # 1. Corrección dinámica de sesgo en Córners
        if "Córners" in calibration.bias_offsets:
            c_bias = calibration.bias_offsets["Córners"]
            # Aplicar hasta el 60% del sesgo histórico para suavizado Bayesiano
            c_adj = c_bias * 0.60
            tot_corners = (
                (expected.corners_home or 0.0) + (expected.corners_away or 0.0)
            )
            if tot_corners > 0:
                h_prop = (expected.corners_home or 0.0) / tot_corners
                a_prop = (expected.corners_away or 0.0) / tot_corners
                if expected.corners_home is not None:
                    expected.corners_home = max(1.5, round(expected.corners_home + c_adj * h_prop, 2))
                if expected.corners_away is not None:
                    expected.corners_away = max(1.5, round(expected.corners_away + c_adj * a_prop, 2))

        # 2. Corrección dinámica de sesgo en Tarjetas
        if "Tarjetas" in calibration.bias_offsets:
            t_bias = calibration.bias_offsets["Tarjetas"]
            t_adj = t_bias * 0.60
            tot_cards = (
                (expected.cards_home or 0.0) + (expected.cards_away or 0.0)
            )
            if tot_cards > 0:
                h_prop = (expected.cards_home or 0.0) / tot_cards
                a_prop = (expected.cards_away or 0.0) / tot_cards
                if expected.cards_home is not None:
                    expected.cards_home = max(0.5, round(expected.cards_home + t_adj * h_prop, 2))
                if expected.cards_away is not None:
                    expected.cards_away = max(0.5, round(expected.cards_away + t_adj * a_prop, 2))
