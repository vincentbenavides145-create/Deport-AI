from __future__ import annotations

import json

from .domain import AnalysisReport


class LLMExplainer:
    def __init__(self, api_key: str | None, model: str):
        self.api_key = api_key
        self.model = model

    def explain(self, report: AnalysisReport) -> str | None:
        if not self.api_key:
            return None
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.responses.create(
                model=self.model,
                store=False,
                instructions=(
                    "Eres DEPORT AI. Explica en español un informe estadístico de fútbol. "
                    "Los datos y probabilidades son inmutables: no recalcules, no agregues cifras, "
                    "no inventes lesiones, alineaciones ni cuotas. No prometas ganancias ni uses tono "
                    "de certeza. Devuelve un único párrafo breve (máximo 90 palabras) que conecte forma, "
                    "probabilidades y principales riesgos. Si falta un dato, reconoce la limitación."
                ),
                input=json.dumps(report.llm_payload(), ensure_ascii=False, default=str),
                text={"verbosity": "low"},
            )
            return response.output_text.strip() or None
        except Exception:
            # La explicación es una capa opcional; nunca bloquea el cálculo verificable.
            return None

