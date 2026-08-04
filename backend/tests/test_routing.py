from unittest.mock import MagicMock

from app.routing import parse_walking_routes, request_walking_routes


def test_parse_walking_routes_reads_geojson_features() -> None:
    routes = parse_walking_routes(
        {
            "features": [
                {
                    "geometry": {"coordinates": [[144.965, -37.81], [144.966, -37.81]]},
                    "properties": {"summary": {"distance": 123.4, "duration": 96.7}},
                }
            ]
        }
    )

    assert len(routes) == 1
    assert routes[0].coordinates[0] == (144.965, -37.81)
    assert routes[0].distance_metres == 123.4


def test_request_walking_routes_sends_the_key_and_alternative_route_request(monkeypatch) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "features": [
            {
                "geometry": {"coordinates": [[144.965, -37.81], [144.966, -37.81]]},
                "properties": {"summary": {"distance": 123.4, "duration": 96.7}},
            }
        ]
    }
    post = MagicMock(return_value=response)
    monkeypatch.setattr("app.routing.requests.post", post)

    routes = request_walking_routes(
        start=(144.965, -37.81),
        destination=(144.966, -37.81),
        api_key="not-a-real-key",
        timeout_seconds=10,
    )

    assert len(routes) == 1
    assert post.call_args.kwargs["headers"]["Authorization"] == "not-a-real-key"
    assert post.call_args.kwargs["json"]["alternative_routes"]["target_count"] == 3
