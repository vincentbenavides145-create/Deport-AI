from __future__ import annotations

import re

from .errors import DeportAIError


PREFIX = re.compile(
    r"^\s*(?:por\s+favor\s+)?(?:analiza|analizar|análisis\s+de|pronostica|partido)\s*[:\-]?\s*",
    re.IGNORECASE,
)
SEPARATOR = re.compile(r"\s+(?:vs\.?|v\.?|contra)\s+", re.IGNORECASE)


def parse_match_query(text: str) -> tuple[str, str]:
    cleaned = PREFIX.sub("", text.strip())
    parts = SEPARATOR.split(cleaned, maxsplit=1)
    if len(parts) != 2:
        raise DeportAIError(
            "No pude reconocer el partido. Usa el formato: Real Madrid vs Barcelona"
        )
    first, second = (part.strip(" .,:;-") for part in parts)
    if len(first) < 3 or len(second) < 3:
        raise DeportAIError("Escribe los nombres completos de los dos equipos.")
    return first, second

