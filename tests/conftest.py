from __future__ import annotations

import pytest

import deport_ai.service as service
import deport_ai.storage as storage


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Ninguna prueba escribe en la base real ni en el histórico del repositorio."""
    monkeypatch.setattr(storage, "DEFAULT_DB_PATH", tmp_path / "deport_ai.db")
    monkeypatch.setattr(storage, "DEFAULT_HISTORY_PATH", tmp_path / "history" / "predictions.jsonl")
    # Las pruebas no llaman a Firecrawl/Flashscore salvo que lo pidan explícitamente.
    monkeypatch.setattr(service, "XG_ENABLED", False)
