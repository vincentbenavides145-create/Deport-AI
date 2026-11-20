"""xG de Flashscore: lectura de páginas, emparejamiento, caché y uso en el modelo."""

import json
from datetime import date
from pathlib import Path

from deport_ai.backtesting import (
    BacktestResult,
    format_xg_comparison,
    goal_market_summary,
    xg_coverage,
    build_fixtures,
)
from deport_ai.domain import TeamMatch
from deport_ai.flashscore import (
    FlashscoreRow,
    FlashscoreXG,
    SportmonksFixture,
    attach_xg,
    fixtures_from_matches,
    match_fixture,
    name_similarity,
    parse_match_stats,
    parse_results_html,
    season_label,
    stats_url,
    strip_xg,
)
from deport_ai.model_params import ModelParameters
from deport_ai.stats_engine import goal_probabilities

DATA = Path(__file__).parent / "data"


# ---------------------------------------------------------------- parsers

def test_parse_results_row_from_real_page():
    rows = parse_results_html((DATA / "flashscore_results_row.html").read_text(encoding="utf-8"))
    assert len(rows) == 1
    row = rows[0]
    assert row.mid == "8UYgdAyq"
    assert (row.home, row.away) == ("Al Nassr", "Al Kholood")
    assert (row.home_score, row.away_score) == (5, 3)
    assert (row.day, row.month, row.year) == (29, 10, None)
    assert row.url.endswith("/al-kholood-Mqs1WbFK/al-nassr-h4I89ZuE/?mid=8UYgdAyq")


def test_parse_match_stats_from_real_page():
    stats = parse_match_stats((DATA / "flashscore_stats.md").read_text(encoding="utf-8"))
    assert stats["xg_home"] == 3.76 and stats["xg_away"] == 1.96
    assert stats["xgot_home"] == 4.73 and stats["xgot_away"] == 3.19
    assert stats["xa_home"] == 2.92 and stats["xa_away"] == 1.01
    assert stats["box_touches_home"] == 43 and stats["big_chances_home"] == 8


def test_parse_match_stats_without_xg_returns_none():
    assert parse_match_stats("Ball possession\n\n53%\n\nTotal shots\n\n7") is None


def test_stats_url_keeps_match_id():
    url = "https://www.flashscore.com/match/football/a-1/b-2/?mid=8UYgdAyq"
    assert stats_url(url) == "https://www.flashscore.com/match/football/a-1/b-2/summary/stats/?mid=8UYgdAyq"


# ---------------------------------------------------------------- emparejamiento

def _row(mid, day, month, home, away, hs, as_):
    return FlashscoreRow(mid, f"https://www.flashscore.com/match/football/x/y/?mid={mid}", day, month, None,
                         home, away, hs, as_)


def test_name_similarity_handles_suffixes_and_accents():
    assert name_similarity("Al Ahli", "Al Ahli SC") >= 0.9
    assert name_similarity("São Paulo", "Sao Paulo") == 1.0
    assert name_similarity("Al Ahli", "Al Hilal") < 0.75


def test_season_label():
    assert season_label(date(2026, 10, 29), "split") == "2026-2027"
    assert season_label(date(2026, 3, 1), "split") == "2025-2026"
    assert season_label(date(2026, 3, 1), "calendar") == "2026"


def test_match_fixture_requires_date_score_and_names():
    fixture = SportmonksFixture(1, date(2026, 10, 29), "Al Nassr", "Al Kholood", 5, 3, 944)
    good = _row("AAAAAAAA", 29, 10, "Al Nassr", "Al Kholood", 5, 3)
    other_score = _row("BBBBBBBB", 29, 10, "Al Nassr", "Al Kholood", 1, 0)
    far_date = _row("CCCCCCCC", 2, 10, "Al Nassr", "Al Kholood", 5, 3)
    other_teams = _row("DDDDDDDD", 30, 10, "Al Hilal", "Al Fateh", 5, 3)
    assert match_fixture(fixture, [other_score, far_date, other_teams, good], "2026-2027") is good
    assert match_fixture(fixture, [other_score, far_date, other_teams], "2026-2027") is None


def test_match_fixture_tolerates_one_day_timezone_shift():
    fixture = SportmonksFixture(1, date(2026, 10, 30), "Al Nassr", "Al Kholood", 5, 3, 944)
    assert match_fixture(fixture, [_row("AAAAAAAA", 29, 10, "Al Nassr", "Al Kholood", 5, 3)], "2026-2027")


# ---------------------------------------------------------------- proveedor con caché

class FakeFetcher:
    def __init__(self):
        self.listing_calls = 0
        self.batch_calls: list[list[str]] = []

    def scrape(self, url, formats, actions=None, wait_for=3000):
        self.listing_calls += 1
        return {"rawHtml": (DATA / "flashscore_results_row.html").read_text(encoding="utf-8")}

    def batch_markdown(self, urls, **_kwargs):
        self.batch_calls.append(list(urls))
        return {url: (DATA / "flashscore_stats.md").read_text(encoding="utf-8") for url in urls}


def test_provider_fetches_once_and_caches(tmp_path):
    cache = tmp_path / "xg.json"
    fixture = SportmonksFixture(19778769, date(2026, 10, 29), "Al Nassr", "Al Kholood", 5, 3, 944)
    unsupported = SportmonksFixture(2, date(2026, 10, 29), "A", "B", 0, 0, 99999)
    fetcher = FakeFetcher()
    provider = FlashscoreXG(fetcher=fetcher, cache_path=cache, today=date(2026, 11, 20))
    counts = provider.fetch([fixture, unsupported])
    assert counts["new"] == 1 and counts["unsupported"] == 1
    assert provider.get(19778769)["xg_home"] == 3.76
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["matches"]["19778769"]["mid"] == "8UYgdAyq"

    again = FlashscoreXG(fetcher=fetcher, cache_path=cache, today=date(2026, 11, 20))
    assert again.fetch([fixture])["cached"] == 1
    assert len(fetcher.batch_calls) == 1  # no se vuelve a gastar créditos


def _team_match(fid, team_id, opp_id, is_home, gf, ga, day, name=""):
    return TeamMatch(
        fixture_id=fid, date=f"2026-10-{day:02d}T18:00:00", team_id=team_id, opponent_id=opp_id,
        is_home=is_home, goals_for=gf, goals_against=ga,
        result="W" if gf > ga else "D" if gf == ga else "L", opponent_name=name, league_id=944,
    )


def test_attach_xg_orients_home_and_away(tmp_path):
    cache = tmp_path / "xg.json"
    cache.write_text(json.dumps({"version": 1, "matches": {"7": {"mid": "x", "xg_home": 2.5, "xg_away": 0.4}}}))
    provider = FlashscoreXG(fetcher=FakeFetcher(), cache_path=cache)
    home = _team_match(7, 1, 2, True, 2, 0, 10)
    away = _team_match(7, 2, 1, False, 0, 2, 10)
    missing = _team_match(8, 1, 3, True, 1, 1, 12)
    out = attach_xg([home, away, missing], provider)
    assert out[0].stats_for["expected_goals"] == 2.5 and out[0].stats_against["expected_goals"] == 0.4
    assert out[1].stats_for["expected_goals"] == 0.4 and out[1].stats_against["expected_goals"] == 2.5
    assert "expected_goals" not in out[2].stats_for
    assert "expected_goals" not in strip_xg(out)[0].stats_for


def test_fixtures_from_matches_builds_home_view():
    matches = [_team_match(7, 2, 1, False, 0, 2, 10, name="Local")]
    [fixture] = fixtures_from_matches(matches, {2: "Visitante"})
    assert (fixture.home, fixture.away, fixture.home_goals, fixture.away_goals) == ("Local", "Visitante", 2, 0)
    assert fixture.date == date(2026, 10, 10)


# ---------------------------------------------------------------- modelo

def _history(team_id, xg_for=None, xg_against=None):
    out = []
    for i in range(8):
        stats_for = {} if xg_for is None else {"expected_goals": xg_for}
        stats_against = {} if xg_against is None else {"expected_goals": xg_against}
        out.append(TeamMatch(
            fixture_id=100 * team_id + i, date=f"2026-10-{20 - i:02d}", team_id=team_id, opponent_id=50 + i,
            is_home=i % 2 == 0, goals_for=1, goals_against=1, result="D",
            stats_for=stats_for, stats_against=stats_against, league_id=944,
        ))
    return out


def test_xg_moves_expected_goals_and_weight_zero_is_current_model():
    plain_home, plain_away = _history(1), _history(2)
    xg_home, xg_away = _history(1, xg_for=2.4, xg_against=0.6), _history(2, xg_for=0.6, xg_against=2.4)
    base = goal_probabilities(plain_home, plain_away, 1500, 1500, league_id=944)
    zero = goal_probabilities(xg_home, xg_away, 1500, 1500, league_id=944, params=ModelParameters(xg_weight=0.0))
    with_xg = goal_probabilities(xg_home, xg_away, 1500, 1500, league_id=944, params=ModelParameters(xg_weight=0.5))
    assert zero.expected_home_goals == base.expected_home_goals
    assert zero.expected_away_goals == base.expected_away_goals
    assert with_xg.expected_home_goals > base.expected_home_goals
    assert with_xg.expected_away_goals < base.expected_away_goals


# ---------------------------------------------------------------- informe del backtest

def test_goal_market_summary_and_report():
    def rec(cat, p, won, shown):
        return {"category": cat, "probability": p, "won": won, "shown": shown}

    base = BacktestResult(evaluated_fixtures=2, scoreline_log_loss=2.9,
                          records=[rec("Goles", 0.7, True, True), rec("Goles", 0.6, False, False),
                                   rec("Córners", 0.8, True, True)])
    better = BacktestResult(evaluated_fixtures=2, scoreline_log_loss=2.8,
                            records=[rec("Goles", 0.8, True, True), rec("Goles", 0.4, False, False)])
    summaries = {"Base: sin xG (modelo actual)": goal_market_summary(base),
                 "Con xG, peso 0.35": goal_market_summary(better)}
    assert "Córners" not in summaries["Con xG, peso 0.35"]
    assert summaries["Con xG, peso 0.35"]["Goles"]["brier"] < summaries["Base: sin xG (modelo actual)"]["Goles"]["brier"]
    report = format_xg_comparison(summaries, (2, 1), "Backtest xG")
    assert "2.8000 (-0.1000)" in report
    assert "con xG suficiente en ambos equipos: 1/2 (50%)" in report


def test_xg_coverage_counts_fixtures_with_enough_xg():
    home = _history(1, xg_for=1.5, xg_against=1.0)
    away = _history(2)
    target_home = TeamMatch(fixture_id=999, date="2026-10-30", team_id=1, opponent_id=2, is_home=True,
                            goals_for=1, goals_against=0, result="W", league_id=944)
    target_away = TeamMatch(fixture_id=999, date="2026-10-30", team_id=2, opponent_id=1, is_home=False,
                            goals_for=0, goals_against=1, result="L", league_id=944)
    by_team = {1: home + [target_home], 2: away + [target_away]}
    fixtures = [f for f in build_fixtures(by_team, {1: "A", 2: "B"}) if f.fixture_id == 999]
    assert xg_coverage(fixtures, by_team) == (1, 0)
    by_team[2] = _history(2, xg_for=1.0, xg_against=1.0) + [target_away]
    assert xg_coverage(fixtures, by_team) == (1, 1)


class PagedFetcher:
    """Simula una lista con botón "mostrar más" que desaparece tras 3 clics."""

    def __init__(self):
        self.clicks_seen: list[int] = []

    def scrape(self, url, formats, actions=None, wait_for=3000):
        from deport_ai.flashscore import FirecrawlError

        clicks = sum(1 for a in actions or [] if a["type"] == "click")
        self.clicks_seen.append(clicks)
        if clicks > 3:
            raise FirecrawlError("HTTP 500: Element not found")
        row = (DATA / "flashscore_results_row.html").read_text(encoding="utf-8")
        rows = "".join(row.replace("8UYgdAyq", f"{i:08d}") for i in range(clicks + 1))
        footer = '<div data-testid="wcl-section-footer"><button>Show more</button></div>' if clicks < 3 else ""
        return {"rawHtml": rows + footer}


def test_listing_keeps_clicking_while_show_more_exists(tmp_path):
    fetcher = PagedFetcher()
    provider = FlashscoreXG(fetcher=fetcher, cache_path=tmp_path / "xg.json", today=date(2026, 11, 20))
    rows = provider.listing(944, "2025-2026")
    assert len(rows) == 4  # la lectura con 3 clics, la más completa
    assert fetcher.clicks_seen == [0, 3]  # sin botón tras 3 clics: no se gastan más créditos
