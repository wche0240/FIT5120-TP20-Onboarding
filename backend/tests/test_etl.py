from app.etl import clean_minute_counts, clean_sensor_locations, clean_transit_access_points


def test_clean_sensor_locations_removes_duplicate_sensor_ids() -> None:
    rows = clean_sensor_locations(
        [
            {"location_id": 1, "sensor_name": "Old", "latitude": -37.81, "longitude": 144.96},
            {"location_id": 1, "sensor_name": "New", "latitude": -37.82, "longitude": 144.97},
        ]
    )
    assert rows == [(1, "New", None, -37.82, 144.97, None)]


def test_clean_minute_counts_removes_duplicate_composite_keys() -> None:
    rows = clean_minute_counts(
        [
            {
                "location_id": 1,
                "sensing_datetime": "2026-08-04 09:00:00",
                "direction_1": 25,
                "direction_2": 26,
                "total_of_directions": 51,
            },
            {
                "location_id": 1,
                "sensing_datetime": "2026-08-04 09:00:00",
                "direction_1": 10,
                "direction_2": 10,
                "total_of_directions": 20,
            },
        ],
        low_max=50,
        medium_max=150,
        city_timezone="Australia/Melbourne",
        lookback_minutes=0,
    )
    assert len(rows) == 1
    assert rows[0][4:] == (20, "low")


def test_clean_minute_counts_keeps_only_the_latest_hour() -> None:
    rows = clean_minute_counts(
        [
            {"location_id": 1, "sensing_datetime": "2026-08-04 08:59:00", "total_of_directions": 1},
            {"location_id": 1, "sensing_datetime": "2026-08-04 09:00:00", "total_of_directions": 2},
            {"location_id": 1, "sensing_datetime": "2026-08-04 10:00:00", "total_of_directions": 3},
        ],
        low_max=50,
        medium_max=150,
        city_timezone="Australia/Melbourne",
        lookback_minutes=60,
    )
    assert [row[4] for row in rows] == [2, 3]


def test_clean_transit_access_points_keeps_supported_cbd_stops() -> None:
    rows = clean_transit_access_points(
        {
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [144.9631, -37.8136]},
                    "properties": {"STOP_ID": "100", "STOP_NAME": "CBD Tram Stop", "MODE": "METRO TRAM"},
                },
                {
                    "geometry": {"type": "Point", "coordinates": [145.12, -37.7]},
                    "properties": {"STOP_ID": "101", "STOP_NAME": "Outside MVP area", "MODE": "METRO BUS"},
                },
                {
                    "geometry": {"type": "Point", "coordinates": [144.97, -37.815]},
                    "properties": {"STOP_ID": "102", "STOP_NAME": "Unsupported", "MODE": "FERRY"},
                },
            ]
        }
    )
    assert rows == [("tram:100", "CBD Tram Stop", "tram", "METRO TRAM", -37.8136, 144.9631)]
