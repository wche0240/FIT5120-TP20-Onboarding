from unittest.mock import MagicMock

from app.geocoding import is_in_melbourne_cbd, search_cbd_locations


def test_search_cbd_locations_filters_results_outside_the_mvp_boundary(monkeypatch) -> None:
    response = MagicMock()
    response.json.return_value = [
        {
            "name": "State Library Victoria",
            "display_name": "State Library Victoria, Swanston Street, Melbourne, Victoria, Australia",
            "lat": "-37.8099",
            "lon": "144.9652",
        },
        {
            "name": "Outside the CBD",
            "display_name": "Outside the CBD, Victoria, Australia",
            "lat": "-37.85",
            "lon": "144.99",
        },
    ]
    monkeypatch.setattr("app.geocoding.requests.get", lambda *args, **kwargs: response)
    search_cbd_locations.cache_clear()

    locations = search_cbd_locations("State Library Victoria")

    assert locations == (
        {
            "name": "State Library Victoria",
            "display_name": "State Library Victoria, Swanston Street, Melbourne, Victoria, Australia",
            "latitude": -37.8099,
            "longitude": 144.9652,
        },
    )


def test_is_in_melbourne_cbd_accepts_only_the_documented_mvp_boundary() -> None:
    assert is_in_melbourne_cbd(144.9652, -37.8099) is True
    assert is_in_melbourne_cbd(145.0, -37.8099) is False
