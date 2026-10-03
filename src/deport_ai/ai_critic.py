from __future__ import annotations

import json
from collections import defaultdict
from statistics import fmean
from typing import Any

from .domain import AnalysisReport
from .llm import LLMExplainer
from .storage import DatabaseManager


class AICritic:
    """Motor de auditoría, diagnóstico y post-mortem de pronósticos con IA."""

    def __init__(self, db: DatabaseManager, explainer: LLMExplainer | None = None) -> None:
        self.db = db
        self.explainer = explainer

    def analyze_settled_performance(
        self,
        league_id: int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Calcula métricas estadísticas detalladas de aciertos, fallos y desvíos numéricos."""
        settled = self.db.get_settled_predictions(league_id=league_id, limit=limit)
        if not settled:
            return {"error": "No hay apuestas liquidadas para auditar."}

        total = len(settled)
        won = sum(1 for p in settled if p["status"] == "WON")
        lost = sum(1 for p in settled if p["status"] == "LOST")
        void = sum(1 for p in settled if p["status"] == "VOID")
        resolved = won + lost

        hit_rate = (won / resolved) if resolved > 0 else 0.0

        # Agrupación por categoría
        by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in settled:
            by_cat[p["category"]].append(p)

        categories_summary = []
        for cat, items in by_cat.items():
            c_won = sum(1 for i in items if i["status"] == "WON")
            c_lost = sum(1 for i in items if i["status"] == "LOST")
            c_void = sum(1 for i in items if i["status"] == "VOID")
            c_res = c_won + c_lost
            c_hit = (c_won / c_res) if c_res > 0 else 0.0
            avg_prob = fmean(i["predicted_prob"] for i in items)
            categories_summary.append(
                {
                    "category": cat,
                    "total": len(items),
                    "won": c_won,
                    "lost": c_lost,
                    "void": c_void,
                    "hit_rate": round(c_hit, 4),
                    "avg_predicted_prob": round(avg_prob, 4),
                    "gap": round(c_hit - avg_prob, 4),
                }
            )
        categories_summary.sort(key=lambda x: -x["total"])

        # Desvíos en proyecciones numéricas (Córners, Tarjetas, Goles)
        biases: dict[str, list[float]] = defaultdict(list)
        for p in settled:
            proj = p.get("projection")
            if proj is None:
                continue
            cat = p.get("category", "")
            if cat == "Córners":
                ch = p.get("actual_corners_home")
                ca = p.get("actual_corners_away")
                if ch is not None and ca is not None:
                    actual_tot = ch + ca
                    biases["corners"].append(actual_tot - proj)
            elif cat == "Tarjetas":
                cards_h = p.get("actual_cards_home")
                cards_a = p.get("actual_cards_away")
                if cards_h is not None and cards_a is not None:
                    actual_tot = cards_h + cards_a
                    biases["cards"].append(actual_tot - proj)
            elif cat in ("Goles", "Goles y Anotaciones"):
                gh = p.get("actual_home_goals")
                ga = p.get("actual_away_goals")
                if gh is not None and ga is not None:
                    actual_tot = gh + ga
                    biases["goals"].append(actual_tot - proj)

        bias_summary = {
            k: round(fmean(v), 2) for k, v in biases.items() if v
        }

        # Apuestas de alta confianza que fallaron (para el diagnóstico profundo)
        high_conf_misses = [
            p for p in settled
            if p["status"] == "LOST" and p["predicted_prob"] >= 0.70
        ]

        return {
            "total_evaluated": total,
            "resolved": resolved,
            "won": won,
            "lost": lost,
            "void": void,
            "hit_rate": round(hit_rate, 4),
            "categories": categories_summary,
            "biases": bias_summary,
            "high_confidence_misses": [
                {
                    "fixture": f"{m['home_team_name']} vs {m['away_team_name']}",
                    "selection": m["selection"],
                    "category": m["category"],
                    "probability": m["predicted_prob"],
                    "explanation": m["explanation"],
                    "score": f"{m.get('actual_home_goals')}-{m.get('actual_away_goals')}",
                }
                for m in high_conf_misses[:6]
            ],
        }

    def generate_diagnostic_report(
        self,
        league_id: int | None = None,
        limit: int = 100,
    ) -> str:
        """Genera el informe de auditoría y diagnóstico post-mortem con IA en formato Markdown."""
        stats = self.analyze_settled_performance(league_id=league_id, limit=limit)
        if "error" in stats:
            return f"# ⚠️ Auditoría DEPORT AI\n\n{stats['error']}"

        lines = [
            "# 🧠 Diagnóstico y Auditoría de Pronósticos (DEPORT AI)",
            f"**Muestra evaluada:** {stats['resolved']} apuestas resueltas ({stats['won']} ✅ Aciertos | {stats['lost']} ❌ Fallos | {stats['void']} ↩️ Anuladas)",
            f"**Tasa de Acierto Global (Hit Rate):** `{stats['hit_rate'] * 100:.1f}%`",
            "",
            "---",
            "",
            "## 📊 1. Rendimiento Empírico por Mercado",
            "",
            "| Categoría | Muestra | Aciertos | Fallos | Hit Rate Real | Prob. Promedio | Sesgo / Gap |",
            "|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
        ]

        for c in stats["categories"]:
            gap_pct = c["gap"] * 100
            gap_str = f"🟢 +{gap_pct:.1f}%" if gap_pct >= 0 else f"🔴 {gap_pct:.1f}%"
            lines.append(
                f"| **{c['category']}** | {c['total']} | {c['won']} | {c['lost']} | **{c['hit_rate'] * 100:.1f}%** | {c['avg_predicted_prob'] * 100:.1f}% | {gap_str} |"
            )

        if stats["biases"]:
            lines.extend([
                "",
                "---",
                "",
                "## 📐 2. Desviación Promedio en Proyecciones Numéricas",
                "*(Diferencia media entre lo ocurrido en el campo y lo proyectado por el modelo)*",
                "",
            ])
            if "corners" in stats["biases"]:
                cb = stats["biases"]["corners"]
                c_desc = f"+{cb:.2f} córners reales sobre lo estimado" if cb > 0 else f"{cb:.2f} córners reales bajo lo estimado"
                lines.append(f"• **Córners:** `{c_desc}`")
            if "cards" in stats["biases"]:
                tb = stats["biases"]["cards"]
                t_desc = f"+{tb:.2f} tarjetas reales sobre lo estimado" if tb > 0 else f"{tb:.2f} tarjetas reales bajo lo estimado"
                lines.append(f"• **Tarjetas:** `{t_desc}`")
            if "goals" in stats["biases"]:
                gb = stats["biases"]["goals"]
                g_desc = f"+{gb:.2f} goles reales sobre lo estimado" if gb > 0 else f"{gb:.2f} goles reales bajo lo estimado"
                lines.append(f"• **Goles:** `{g_desc}`")

        # Intentar llamar al LLM para la explicación cualitativa post-mortem si está configurado
        ai_narrative = None
        if self.explainer and self.explainer.api_key:
            try:
                from openai import OpenAI

                client = OpenAI(api_key=self.explainer.api_key)
                prompt_input = json.dumps(stats, ensure_ascii=False, indent=2)
                response = client.responses.create(
                    model=self.explainer.model,
                    store=False,
                    instructions=(
                        "Eres el Director Cuantitativo y Auditor Experto de DEPORT AI. "
                        "Analiza los resultados de las apuestas resueltas que te proporciono. "
                        "Genera un informe breve y punzante (máximo 160 palabras) estructurado en dos partes: "
                        "1) 'Diagnóstico Táctico-Estadístico': explica los sesgos principales detectados y por qué fallaron las apuestas de alta probabilidad. "
                        "2) 'Acciones de Calibración': directrices exactas para que el apostador y el modelo mejoren sus selecciones."
                    ),
                    input=prompt_input,
                )
                ai_narrative = response.output_text.strip()
            except Exception:
                pass

        lines.extend([
            "",
            "---",
            "",
            "## 🔍 3. Post-Mortem y Directrices de Mejora",
            "",
        ])

        if ai_narrative:
            lines.append(ai_narrative)
        else:
            # Diagnóstico determinista enriquecido
            lines.extend([
                "### Diagnóstico Estadístico Autónomo",
            ])
            if stats["high_confidence_misses"]:
                lines.append("• **Fallos de Alta Probabilidad (≥ 70%):**")
                for m in stats["high_confidence_misses"]:
                    lines.append(f"  - *{m['fixture']}* ({m['score']}): Falló **{m['selection']}** ({m['probability']*100:.1f}% estimada).")
            
            # Recomendaciones basadas en los gaps
            strong_cats = [c["category"] for c in stats["categories"] if c["hit_rate"] >= 0.70 and c["total"] >= 2]
            weak_cats = [c["category"] for c in stats["categories"] if c["hit_rate"] < 0.55 and c["total"] >= 2]

            lines.append("")
            lines.append("### Acciones de Calibración Recomendadas")
            if strong_cats:
                lines.append(f"• 🟢 **Mercados Consistentes:** Reforzar apuestas en `{', '.join(strong_cats)}` donde el acierto supera el 70%.")
            if weak_cats:
                lines.append(f"• 🔴 **Mercados con Sesgo Negativo:** Ajustar a la baja las probabilidades de `{', '.join(weak_cats)}` o elevar el filtro de exigencia.")
            if "corners" in stats["biases"] and abs(stats["biases"]["corners"]) >= 0.8:
                lines.append(f"• ⚙️ **Calibración de Córners:** Aplicar offset dinámico de `{stats['biases']['corners']:+.2f}` córners en el cálculo de Poisson/NegBinomial.")

        return "\n".join(lines)
