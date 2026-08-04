from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app, crowd_thresholds
from app.routing import WalkingRoute


def mock_connection(row=None, rows=None) -> MagicMock:
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    cursor.fetchall.return_value = rows or []
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def client_for(connection: MagicMock) -> TestClient:
    def override_database():
        yield connection

    app.dependency_overrides[get_db] = override_database
    return TestClient(app)


def test_health_confirms_database_connection() -> None:
    response = client_for(mock_connection(row={"ok": 1})).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_profiled_crowd_thresholds_are_the_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CROWD_LOW_MAX", raising=False)
    monkeypatch.delenv("CROWD_MEDIUM_MAX", raising=False)
    assert crowd_thresholds() == (10, 30)


def test_data_status_reports_available_data() -> None:
    latest = datetime.now(timezone.utc) - timedelta(minutes=5)
    response = client_for(mock_connection(row={"latest_data_at": latest})).get("/api/v1/data-status")
    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert response.json()["age_minutes"] == 5


def test_data_status_reports_unavailable_without_rows() -> None:
    response = client_for(mock_connection(row={"latest_data_at": None})).get("/api/v1/data-status")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"


def test_sensors_returns_map_ready_rows() -> None:
    rows = [
        {
            "location_id": 1,
            "sensor_name": "Test sensor",
            "latitude": -37.81,
            "longitude": 144.96,
            "status": "A",
            "last_seen_at": datetime.now(timezone.utc),
            "total_count": 42,
            "crowd_level": "low",
        }
    ]
    response = client_for(mock_connection(rows=rows)).get("/api/v1/sensors")
    assert response.status_code == 200
    assert response.json()[0]["sensor_name"] == "Test sensor"
    assert response.json()[0]["crowd_level"] == "low"


def test_location_search_returns_cbd_location_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.main.search_cbd_locations",
        lambda query: (
            {
                "name": "State Library Victoria",
                "display_name": "State Library Victoria, Swanston Street, Melbourne, Victoria, Australia",
                "latitude": -37.8099,
                "longitude": 144.9652,
            },
        ),
    )

    response = client_for(mock_connection()).get("/api/v1/location-search?query=State%20Library%20Victoria")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "State Library Victoria"
    assert response.json()[0]["longitude"] == 144.9652


def test_location_search_rejects_an_empty_meaningful_query() -> None:
    response = client_for(mock_connection()).get("/api/v1/location-search?query=%20%20%20")
    assert response.status_code == 422
    assert "non-space characters" in response.json()["detail"]


def test_transit_access_points_can_be_ranked_by_distance() -> None:
    rows = [
        {
            "access_point_id": "tram:10",
            "name": "Nearby tram stop",
            "mode": "tram",
            "source_mode": "METRO TRAM",
            "latitude": -37.8136,
            "longitude": 144.9631,
        },
        {
            "access_point_id": "train:20",
            "name": "Further train station",
            "mode": "train",
            "source_mode": "METRO TRAIN",
            "latitude": -37.8183,
            "longitude": 144.9667,
        },
    ]
    response = client_for(mock_connection(rows=rows)).get(
        "/api/v1/transit-access-points?longitude=144.9631&latitude=-37.8136&radius_metres=1000"
    )
    assert response.status_code == 200
    assert response.json()[0]["access_point_id"] == "tram:10"
    assert response.json()[0]["distance_metres"] == 0.0


def test_transit_access_points_require_both_coordinates_for_a_nearby_search() -> None:
    response = client_for(mock_connection()).get("/api/v1/transit-access-points?longitude=144.9631")
    assert response.status_code == 422
    assert response.json()["detail"] == "Longitude and latitude must be supplied together."


def test_route_score_returns_a_crowd_level_for_fresh_sensor_data() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        {
            "location_id": 1,
            "latitude": -37.81,
            "longitude": 144.9652,
            "last_seen_at": now,
            "total_count": 180,
        }
    ]
    response = client_for(mock_connection(rows=rows)).post(
        "/api/v1/route-score",
        json={
            "coordinates": [
                {"longitude": 144.965, "latitude": -37.81},
                {"longitude": 144.966, "latitude": -37.81},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert response.json()["crowd_level"] == "high"
    assert response.json()["matched_sensor_count"] == 1


def test_routes_recommends_the_quieter_route_within_the_selected_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORS_API_KEY", "test-key")
    rows = [
        {
            "location_id": 1,
            "latitude": -37.8100,
            "longitude": 144.9652,
            "last_seen_at": datetime.now(timezone.utc),
            "total_count": 20,
        },
        {
            "location_id": 2,
            "latitude": -37.8110,
            "longitude": 144.9652,
            "last_seen_at": datetime.now(timezone.utc),
            "total_count": 180,
        },
    ]
    provider_routes = [
        WalkingRoute(coordinates=[(144.9650, -37.8100), (144.9660, -37.8100)], distance_metres=120, duration_seconds=90),
        WalkingRoute(coordinates=[(144.9650, -37.8110), (144.9660, -37.8110)], distance_metres=110, duration_seconds=80),
    ]
    monkeypatch.setattr("app.main.request_walking_routes", lambda **_: provider_routes)

    response = client_for(mock_connection(rows=rows)).post(
        "/api/v1/routes",
        json={
            "start": {"longitude": 144.9650, "latitude": -37.8100},
            "destination": {"longitude": 144.9660, "latitude": -37.8100},
            "max_crowd_level": "medium",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["recommended_route_id"] == 1
    assert body["routes"][0]["recommended"] is True
    assert body["routes"][1]["meets_crowd_threshold"] is False


def test_routes_warns_when_no_monitored_route_meets_the_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORS_API_KEY", "test-key")
    rows = [
        {
            "location_id": 1,
            "latitude": -37.8100,
            "longitude": 144.9652,
            "last_seen_at": datetime.now(timezone.utc),
            "total_count": 180,
        }
    ]
    provider_routes = [WalkingRoute(coordinates=[(144.9650, -37.8100), (144.9660, -37.8100)], distance_metres=120, duration_seconds=90)]
    monkeypatch.setattr("app.main.request_walking_routes", lambda **_: provider_routes)

    response = client_for(mock_connection(rows=rows)).post(
        "/api/v1/routes",
        json={
            "start": {"longitude": 144.9650, "latitude": -37.8100},
            "destination": {"longitude": 144.9660, "latitude": -37.8100},
            "max_crowd_level": "medium",
        },
    )

    assert response.status_code == 200
    assert response.json()["recommended_route_id"] is None
    assert "No currently monitored route" in response.json()["warning"]


def test_routes_reports_a_configuration_error_without_an_ors_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORS_API_KEY", raising=False)

    response = client_for(mock_connection()).post(
        "/api/v1/routes",
        json={
            "start": {"longitude": 144.9650, "latitude": -37.8100},
            "destination": {"longitude": 144.9660, "latitude": -37.8100},
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Routing is not configured on this server."


def test_routes_rejects_destinations_outside_the_melbourne_cbd() -> None:
    response = client_for(mock_connection()).post(
        "/api/v1/routes",
        json={
            "start": {"longitude": 144.9650, "latitude": -37.8100},
            "destination": {"longitude": 145.1, "latitude": -37.9},
        },
    )
    assert response.status_code == 422
    assert "Melbourne CBD" in response.json()["detail"]
