import pytest

from deport_ai.errors import DeportAIError
from deport_ai.parser import parse_match_query


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Analiza Real Madrid vs Barcelona", ("Real Madrid", "Barcelona")),
        ("Alianza Lima contra Sporting Cristal", ("Alianza Lima", "Sporting Cristal")),
        ("partido: Arsenal v. Chelsea", ("Arsenal", "Chelsea")),
    ],
)
def test_parse_match_query(text, expected):
    assert parse_match_query(text) == expected


def test_rejects_unknown_format():
    with pytest.raises(DeportAIError):
        parse_match_query("Real Madrid Barcelona")

