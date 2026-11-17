from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    sportmonks_api_token: str | None
    sportmonks_base_url: str
    openai_api_key: str | None
    openai_model: str
    recent_matches: int
    h2h_matches: int
    timeout_seconds: float
    timezone: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            # KEY: nombre de la variable configurada en el entorno cloud de Claude Code.
            sportmonks_api_token=(
                os.getenv("SPORTMONKS_API_TOKEN", "").strip() or os.getenv("KEY", "").strip() or None
            ),
            sportmonks_base_url=os.getenv(
                "SPORTMONKS_BASE_URL", "https://api.sportmonks.com/v3/football"
            ).strip().rstrip("/"),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.2").strip(),
            recent_matches=_bounded_int("DEPORT_AI_RECENT_MATCHES", 15, 5, 25),
            h2h_matches=_bounded_int("DEPORT_AI_H2H_MATCHES", 15, 3, 30),
            timeout_seconds=float(os.getenv("DEPORT_AI_TIMEOUT_SECONDS", "30")),
            timezone=os.getenv("DEPORT_AI_TIMEZONE", "America/Lima").strip(),
        )

    def validate(self) -> None:
        if not self.sportmonks_api_token:
            raise ValueError("Falta SPORTMONKS_API_TOKEN en el archivo .env.")
        if not self.sportmonks_base_url.startswith("https://"):
            raise ValueError("SPORTMONKS_BASE_URL debe comenzar con https://")


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))
