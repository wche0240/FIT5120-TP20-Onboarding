import pytest

from app.crowd import classify_crowd_level


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "low"), (50, "low"), (51, "medium"), (150, "medium"), (151, "high")],
)
def test_classify_crowd_level(count: int, expected: str) -> None:
    assert classify_crowd_level(count, low_max=50, medium_max=150) == expected


def test_classify_crowd_level_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        classify_crowd_level(-1, low_max=50, medium_max=150)
