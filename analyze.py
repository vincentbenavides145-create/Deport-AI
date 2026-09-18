"""Script directo para analizar un partido por línea de comandos o para el asistente de IA."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Añadir src al sys.path
_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from deport_ai.config import Settings
from deport_ai.errors import DeportAIError
from deport_ai.formatter import format_report
from deport_ai.llm import LLMExplainer
from deport_ai.service import AnalysisService
from deport_ai.sportmonks import SportmonksClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Analiza un partido de fútbol con DEPORT AI")
    parser.add_argument("query", nargs="*", help="Enfrentamiento, ej: 'Real Madrid vs Barcelona'")
    parser.add_argument("--json", action="store_true", help="Devuelve la salida en formato JSON estructurado")
    args = parser.parse_args()

    query_str = " ".join(args.query).strip() if args.query else ""
    if not query_str:
        print("Uso: python analyze.py \"Equipo 1 vs Equipo 2\" [--json]", file=sys.stderr)
        sys.exit(1)

    try:
        settings = Settings.from_env()
        settings.validate()
    except ValueError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        sys.exit(2)

    api = SportmonksClient(
        settings.sportmonks_api_token or "",
        timeout=settings.timeout_seconds,
        timezone=settings.timezone,
        base_url=settings.sportmonks_base_url,
    )
    service = AnalysisService(
        api,
        LLMExplainer(settings.openai_api_key, settings.openai_model),
        recent_count=settings.recent_matches,
        h2h_count=settings.h2h_matches,
    )

    try:
        report = service.analyze(query_str)
        if args.json:
            print(json.dumps(report.llm_payload(), ensure_ascii=False, indent=2))
        else:
            print(format_report(report))
    except DeportAIError as exc:
        print(f"Error en el análisis: {exc}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
