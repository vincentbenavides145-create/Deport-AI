from __future__ import annotations

import sys

from .config import Settings
from .errors import DeportAIError
from .formatter import format_report
from .llm import LLMExplainer
from .service import AnalysisService
from .sportmonks import SportmonksClient


BANNER = """
+------------------------------------------------+
|                   DEPORT AI                    |
|  Datos reales -> Estadistica -> Explicacion    |
+------------------------------------------------+
Escribe: Real Madrid vs Barcelona
Comandos: ayuda | salir
No se guarda historial.
""".strip()


def main() -> None:
    _configure_utf8_console()
    try:
        settings = Settings.from_env()
        settings.validate()
    except ValueError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

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
    print(BANNER)
    while True:
        try:
            question = input("\nTú > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            return
        if not question:
            continue
        if question.casefold() in {"salir", "exit", "quit"}:
            print("Hasta luego.")
            return
        if question.casefold() in {"ayuda", "help"}:
            print("Escribe dos equipos separados por 'vs' o 'contra'. Ejemplo: Alianza Lima vs Sporting Cristal")
            continue
        try:
            print("\nDEPORT AI > Consultando datos y calculando modelos...")
            report = service.analyze(question)
            print(format_report(report))
            quota = (
                f" | cuota restante informada: {api.requests_remaining}"
                if api.requests_remaining is not None
                else ""
            )
            print(
                f"\nProveedor: {api.provider_label} | Consultas API de esta sesión: "
                f"{api.requests_used}{quota}"
            )
        except DeportAIError as exc:
            print(f"\nDEPORT AI > No puedo completar el análisis: {exc}")
        except Exception as exc:
            print(f"\nDEPORT AI > Error inesperado: {exc}")


def _configure_utf8_console() -> None:
    """Evita caracteres rotos en PowerShell/cmd al redirigir la salida."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    main()
