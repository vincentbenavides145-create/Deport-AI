"""Resolución de nombres de equipos con resultados reales de la búsqueda de Sportmonks."""

import pytest

from deport_ai.domain import Team
from deport_ai.errors import AmbiguousTeamError
from deport_ai.sportmonks import SportmonksClient, _name_score, _rank_team_rows


def _rows(*items):
    return [{"id": i, "name": n, "type": t, "country_id": 1} for i, n, t in items]


# Respuestas reales de teams/search (17-11-2026), en el orden en que llegan.
RUSSIA_ROWS = _rows(
    (68, "Borussia Dortmund", "domestic"),
    (683, "Borussia Mönchengladbach", "domestic"),
    (3198, "Borussia Hildesheim", "domestic"),
    (3655, "Borussia Dortmund II", "domestic"),
    (3694, "Borussia Mönchengladbach II", "domestic"),
    (4163, "Borussia Dortmund U19", "domestic"),
    (4226, "Tennis Borussia", "domestic"),
    (4535, "Borussia Fulda", "domestic"),
    (4845, "Borussia Freialdenhoven", "domestic"),
    (5047, "Borussia Neunkirchen", "domestic"),
    (18702, "Russia", "national"),
    (24947, "Russia U19", "national"),
    (61490, "Russia U21", "national"),
)
IRAN_ROWS = _rows(
    (4137, "Mirandela", "domestic"),
    (5197, "Partizani Tirana", "domestic"),
    (5202, "Tirana", "domestic"),
    (6013, "Ypiranga Erechim", "domestic"),
    (6968, "Mirandés", "domestic"),
    (11671, "Almirante Brown de Lules", "domestic"),
    (12710, "Almirante Brown", "domestic"),
    (14441, "América de Pirán", "domestic"),
    (14992, "Ypiranga AP", "domestic"),
    (15239, "Deportivo Miranda FC", "domestic"),
    (18652, "Iran", "national"),
)
VENEZUELA_ROWS = _rows(
    (8338, "Atlético Venezuela", "domestic"),
    (18711, "Venezuela", "national"),
    (75737, "Venezuela U20", "national"),
)


class FakeSearchClient(SportmonksClient):
    """Cliente sin red: responde búsquedas y partidos programados desde memoria."""

    def __init__(self, searches, fixtures=None):
        super().__init__("dummy")
        self.searches = searches
        self.fixtures = fixtures or set()
        self.search_page_sizes = []

    def _get(self, path, **params):
        if path.startswith("teams/search/"):
            self.search_page_sizes.append(params.get("per_page"))
            query = path.rsplit("/", 1)[1].replace("%20", " ").lower()
            return self.searches.get(query, [])
        if path.startswith("teams/"):
            return None
        return []

    def upcoming_between(self, first_id, second_id):
        return {"id": 1} if frozenset((first_id, second_id)) in self.fixtures else None


def test_word_containment_ignores_substrings_inside_words():
    assert _name_score("Russia", "Borussia Dortmund") < 0.6
    # Ya no reciben el 0.93 de contención; solo queda la similitud de letras.
    assert _name_score("Iran", "Mirandela") < 0.7
    assert _name_score("Iran", "Partizani Tirana") < 0.7
    assert _name_score("Russia", "Russia U21") == 0.93


def test_existing_club_preferences_still_hold():
    assert _name_score("Barcelona", "FC Barcelona") > _name_score("Barcelona", "Barcelona Guayaquil")
    ranked = _rank_team_rows("Borussia Dortmund", "Borussia Dortmund", RUSSIA_ROWS)
    assert ranked[0][1].id == 68


@pytest.mark.parametrize(
    "query, rows, expected_id",
    [("Russia", RUSSIA_ROWS, 18702), ("Iran", IRAN_ROWS, 18652), ("Venezuela", VENEZUELA_ROWS, 18711)],
)
def test_national_teams_resolve_beyond_first_ten_results(query, rows, expected_id):
    client = FakeSearchClient({query.lower(): rows})
    assert client.resolve_team(query).id == expected_id
    assert all(size >= 50 for size in client.search_page_sizes)


def test_youth_and_reserve_teams_only_when_requested():
    assert FakeSearchClient({"russia u21": RUSSIA_ROWS}).resolve_team("Russia U21").id == 61490
    ranked = _rank_team_rows("Russia", "Russia", RUSSIA_ROWS)
    assert ranked[0][1].id == 18702
    assert ranked[1][1].id in {24947, 61490}
    assert ranked[0][0] - ranked[1][0] > 0.035


def test_same_name_prefers_senior_national_team():
    rows = _rows((900, "Panama", "domestic"), (18600, "Panama", "national"))
    assert FakeSearchClient({"panama": rows}).resolve_team("Panama").id == 18600


def test_homonyms_are_resolved_with_scheduled_fixture():
    rows = _rows((10, "Deportivo Ejemplo", "domestic"), (11, "Deportivo Ejemplo", "domestic"))
    searches = {"deportivo ejemplo": rows, "venezuela": VENEZUELA_ROWS}

    # Sin contexto de partido se conserva el comportamiento previo: el primer resultado.
    assert FakeSearchClient(searches).resolve_team("Deportivo Ejemplo").id == 10
    assert FakeSearchClient(searches).resolve_match("Deportivo Ejemplo", "Venezuela")[0].id == 10

    # Con un partido programado contra el rival, gana el homónimo que lo juega.
    client = FakeSearchClient(searches, fixtures={frozenset((11, 18711))})
    first, second = client.resolve_match("Deportivo Ejemplo", "Venezuela")
    assert (first.id, second.id) == (11, 18711)


def test_close_scores_are_ambiguous_and_resolved_with_scheduled_fixture():
    near = _rows((30, "Sport Club Alfa", "domestic"), (31, "Club Alfa Junior", "domestic"))
    searches = {"club alfa": near, "venezuela": VENEZUELA_ROWS}

    with pytest.raises(AmbiguousTeamError) as info:
        FakeSearchClient(searches).resolve_team("Club Alfa")
    assert {team.id for team in info.value.candidates} == {30, 31}

    client = FakeSearchClient(searches, fixtures={frozenset((31, 18711))})
    assert client.resolve_match("Club Alfa", "Venezuela")[0].id == 31

    # Sin partido que desempate, el error se mantiene.
    with pytest.raises(AmbiguousTeamError):
        FakeSearchClient(searches).resolve_match("Club Alfa", "Venezuela")


def test_resolve_match_without_ambiguity_matches_resolve_team():
    client = FakeSearchClient({"russia": RUSSIA_ROWS, "venezuela": VENEZUELA_ROWS})
    first, second = client.resolve_match("Russia", "Venezuela")
    assert (first, second) == (Team(18702, "Russia", "1"), Team(18711, "Venezuela", "1"))


INTERNACIONAL_ROWS = _rows(
    (2696, "Internacional", "domestic"),
    (9952, "Internacional de Bogotá", "domestic"),
    (28155, "Internacional", "domestic"),
)


class FakeOverrideClient(FakeSearchClient):
    """Como FakeSearchClient, pero la ficha del equipo de la lista de alias sí existe."""

    def _get(self, path, **params):
        if path == "teams/2930":
            return {"id": 2930, "name": "Inter", "country_id": 251}
        return super()._get(path, **params)


def test_fuzzy_alias_does_not_beat_exact_search_name():
    # "internacional" se parece a "internazionale" (Inter de Milán), pero Sportmonks tiene
    # equipos llamados exactamente "Internacional": gana la búsqueda.
    searches = {"internacional": INTERNACIONAL_ROWS, "vasco da gama": _rows((696, "Vasco da Gama", "domestic"))}
    client = FakeOverrideClient(searches, fixtures={frozenset((696, 2696))})
    assert client.resolve_team("Internacional").id in {2696, 28155}
    home, away = client.resolve_match("Vasco da Gama", "Internacional")
    assert (home.id, away.id) == (696, 2696)
    # Un nombre sin coincidencia exacta en la búsqueda sigue usando la lista de alias.
    assert FakeOverrideClient({}).resolve_team("Inter").id == 2930
