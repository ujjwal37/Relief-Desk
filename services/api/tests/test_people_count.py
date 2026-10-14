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
        ("2-3 people on the roof", 3),
        ("4-5 people stranded", 5),
        ("2 to 3 people need a boat", 3),
    ],
)
def test_people_count(text, expected):
    assert people_count(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Family of 4 including a pregnant woman stuck on roof", 4),
        ("family of five stranded near the church", 5),
        ("a 6-member family on the terrace", 6),
    ],
)
def test_family_of_n(text, expected):
    assert people_count(text) == expected
