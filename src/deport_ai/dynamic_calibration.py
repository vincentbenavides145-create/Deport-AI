from __future__ import annotations

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


@dataclass
class DynamicCalibrationSummary:
    active: bool
    league_id: int | None
    league_name: str | None
    sample_size: int
    overall_hit_rate: float
    category_factors: dict[str, dict[str, float]]
    bias_offsets: dict[str, float]

    def badge_text(self) -> str:
        if not self.active or self.sample_size < MIN_CALIBRATION_SAMPLE:
            return "🟡 Calibración preliminar (acumulando muestra)"
        return (
            f"🟢 Calibración Dinámica Activa ({self.sample_size} apuestas auditadas | "
            f"{self.overall_hit_rate * 100:.1f}% acierto histórico)"
        )


class DynamicCalibrator:
    """Motor de calibración adaptativa y aprendizaje continuo para DEPORT AI."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        try:
            self.purge_synthetic_seed()
        except Exception:
            pass

    def purge_synthetic_seed(self) -> int:
        """Elimina los registros ficticios creados por versiones anteriores (auto-seed).

        Esas versiones generaban predicciones con probabilidades fijas y estadísticas
        rivales inventadas. Se borran y la calibración se recalcula solo con datos reales.
        """
        removed = self.db.purge_synthetic_seed()
        if removed:
            self.db.clear_calibration()
            self.recompute_calibrations()
        return removed

    def recompute_calibrations(self, min_sample: int = MIN_CALIBRATION_SAMPLE) -> int:
        """Recalcula y actualiza los factores de calibración en la base de datos a partir de apuestas liquidadas."""
        settled = self.db.get_settled_predictions()
        if not settled:
            return 0

        # Agrupar por (league_id, category)
        grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        # También acumular un global (league_id = 0, category)
        global_grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for p in settled:
            l_id = p.get("league_id") or 0
            cat = p.get("category", "")
            grouped[(l_id, cat)].append(p)
            global_grouped[cat].append(p)

        updated_count = 0

        # 1. Calibraciones por Liga
        for (l_id, cat), items in grouped.items():
            if len(items) < min_sample:
                continue
            factor_entry = self._calculate_factor_entry(items)
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
                factor_entry = self._calculate_factor_entry(items)
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

        return updated_count

    @staticmethod
    def _calculate_factor_entry(items: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(items)
        won = sum(1 for i in items if i["status"] == "WON")
        lost = sum(1 for i in items if i["status"] == "LOST")
        resolved = won + lost
        hit_rate = (won / resolved) if resolved > 0 else 0.0

        probs = [float(i["predicted_prob"]) for i in items if i["status"] in ("WON", "LOST")]
        avg_prob = fmean(probs) if probs else 0.65

        # Brier Score
        brier = 0.0
        for i in items:
            if i["status"] in ("WON", "LOST"):
                outcome_val = 1.0 if i["status"] == "WON" else 0.0
                brier += (float(i["predicted_prob"]) - outcome_val) ** 2
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
            "sample_size": n,
            "hit_rate": hit_rate,
            "brier_score": brier_avg,
            "bias_offset": bias_offset,
            "shrinkage_factor": shrinkage,
        }

    def get_calibration_summary(self, league_id: int | None, league_name: str | None = None) -> DynamicCalibrationSummary:
        """Construye un resumen de calibración aplicable para la liga o global."""
        rows = self.db.get_calibration(league_id=league_id)
        if not rows and league_id != 0:
            # Fallback a calibración global
            rows = self.db.get_calibration(league_id=0)

        if not rows:
            return DynamicCalibrationSummary(
                active=False,
                league_id=league_id,
                league_name=league_name,
                sample_size=0,
                overall_hit_rate=0.0,
                category_factors={},
                bias_offsets={},
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

            total_samples += sz
            total_won_weighted += (hr * sz)
            cat_factors[cat] = {
                "hit_rate": hr,
                "shrinkage_factor": sh,
                "bias_offset": bias,
                "sample_size": sz,
            }
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
