"""Rule fallback adds up named groups when no total is given."""
import pytest

from app.tools.nlu_rules import people_count


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2 elderly and a child stuck on first floor, need boat", 3),
        ("three people need a boat", 3),
        ("5 people stranded", 5),
        ("10 people including 2 children", 10),
        ("Need boat at a jetty", None),
    ],
)
def test_people_count(text, expected):
    assert people_count(text) == expected
