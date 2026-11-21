"""Formato corto: Pick Recomendado + las selecciones más seguras, y su seguimiento."""

from types import SimpleNamespace

from deport_ai.domain import ExpectedMetrics, ProbabilityReport, Team
from deport_ai.formatter import format_adaptive_report
from deport_ai.statistical_markets import mark_highlights, select_featured_markets
from deport_ai.storage import DatabaseManager


def _m(category, selection, prob):
    return {"category": category, "selection": selection, "market": category, "probability": prob, "explanation": "Porque sí."}


MARKETS = [
    _m("Goles", "Más de 1.5 goles", 0.87),  # Pick
    _m("Córners", "Más de 7.5 córners", 0.85),
    _m("Córners", "Local Más de 3.5 córners", 0.84),
    _m("Córners", "Ambos equipos sacan 3+ córners", 0.83),  # tercera de córners: fuera
    _m("Córners", "1T Menos de 5.5 córners", 0.86),  # mercado por mitad: fuera
    _m("Tarjetas", "Menos de 4.5 tarjetas", 0.82),  # categoría no destacada
    _m("Faltas", "Más de 21.5 faltas", 0.80),
    _m("Remates", "Local Más de 10.5 remates", 0.79),
    _m("Goles", "Visitante Menos de 1.5 goles", 0.78),
    _m("Tiros al arco", "Más de 6.5 tiros al arco", 0.74),  # bajo 75%: fuera
]
PICK = {"selection": "Más de 1.5 goles", "probability": 0.87, "category": "Goles", "explanation": "Porque sí."}


def test_featured_selection_rules():
    featured = select_featured_markets(MARKETS, PICK)
    assert [m["selection"] for m in featured] == [
        "Más de 7.5 córners",
        "Local Más de 3.5 córners",
        "Más de 21.5 faltas",
        "Local Más de 10.5 remates",
        "Visitante Menos de 1.5 goles",
    ]


def test_mark_highlights():
    markets = [dict(m) for m in MARKETS]
    featured = select_featured_markets(markets, PICK)
    mark_highlights(markets, PICK, featured)
    tags = {m["selection"]: m.get("highlight") for m in markets}
    assert tags["Más de 1.5 goles"] == "pick"
    assert tags["Más de 7.5 córners"] == "top5"
    assert tags["Menos de 4.5 tarjetas"] is None


def _report():
    probs = ProbabilityReport(
        home_win=0.5, draw=0.25, away_win=0.25, over_15=0.87, over_25=0.6, under_25=0.4, btts=0.5,
        expected_home_goals=1.6, expected_away_goals=1.1, score_matrix=[[1.0]],
    )
    return SimpleNamespace(
        home=Team(1, "Local"), away=Team(2, "Visitante"), confidence=None, top_pick=PICK,
        statistical_markets=[dict(m) for m in MARKETS], featured_markets=select_featured_markets(MARKETS, PICK),
        probabilities=probs, expected=ExpectedMetrics(),
    )


def test_compact_report_is_default_and_full_is_optional():
    compact = format_adaptive_report(_report())
    assert "#### 🔒 Las más seguras" in compact
    for market in select_featured_markets(MARKETS, PICK):
        assert f"• **{market['selection']} — " in compact
    assert "Menos de 4.5 tarjetas" not in compact and "1T Menos de 5.5 córners" not in compact
    assert "#### 🟨 Tarjetas" not in compact
    assert "#### 📊 Proyecciones numéricas" in compact
    full = format_adaptive_report(_report(), full=True)
    assert "#### 🟨 Tarjetas" in full and "#### 🔒 Las más seguras" not in full


def test_highlights_are_tracked_and_summarized():
    db = DatabaseManager(":memory:")
    markets = [dict(m, line=None, side=None) for m in MARKETS]
    mark_highlights(markets, PICK, select_featured_markets(markets, PICK))
    db.save_fixture_and_predictions(1, 1, "Local", 2, "Visitante", 8, "Premier League", "2026-11-21T10:00:00-05:00", markets)
    preds = {p["selection"]: p for p in db.get_predictions_for_fixture(1)}
    db.update_prediction_status(preds["Más de 1.5 goles"]["id"], "WON")
    db.update_prediction_status(preds["Más de 7.5 córners"]["id"], "LOST")
    db.update_prediction_status(preds["Más de 21.5 faltas"]["id"], "WON")
    stats = db.get_summary_stats()["highlights"]
    assert stats["pick"]["won"] == 1 and stats["pick"]["hit_rate"] == 1.0
    assert stats["top5"]["won"] == 1 and stats["top5"]["lost"] == 1 and stats["top5"]["pending"] == 3
