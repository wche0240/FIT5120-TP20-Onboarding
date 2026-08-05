from app.route_scoring import SensorReading, assess_route_segments, point_to_segment_distance_metres, score_route


def test_point_to_segment_distance_is_small_for_a_nearby_sensor() -> None:
    distance = point_to_segment_distance_metres(
        latitude=-37.8100,
        longitude=144.9652,
        start_latitude=-37.8100,
        start_longitude=144.9650,
        end_latitude=-37.8100,
        end_longitude=144.9660,
    )
    assert distance < 25


def test_score_route_uses_the_busiest_nearby_sensor() -> None:
    result = score_route(
        coordinates=[(144.9650, -37.8100), (144.9660, -37.8100)],
        readings=[
            SensorReading(location_id=1, latitude=-37.8100, longitude=144.9652, total_count=20),
            SensorReading(location_id=2, latitude=-37.8100, longitude=144.9658, total_count=180),
            SensorReading(location_id=3, latitude=-37.8200, longitude=144.9800, total_count=999),
        ],
        sensor_radius_metres=80,
        low_max=50,
        medium_max=150,
    )
    assert result.crowd_score == 180
    assert result.crowd_level == "high"
    assert result.matched_sensor_count == 2


def test_score_route_reports_no_coverage_when_no_sensor_is_nearby() -> None:
    result = score_route(
        coordinates=[(144.9650, -37.8100), (144.9660, -37.8100)],
        readings=[SensorReading(location_id=1, latitude=-37.8200, longitude=144.9800, total_count=20)],
        sensor_radius_metres=80,
        low_max=50,
        medium_max=150,
    )
    assert result.crowd_score is None
    assert result.crowd_level is None
    assert result.matched_sensor_count == 0


def test_assess_route_segments_keeps_unmonitored_sections_unknown() -> None:
    segments = assess_route_segments(
        coordinates=[
            (144.9650, -37.8100),
            (144.9654, -37.8100),
            (144.9658, -37.8100),
            (144.9664, -37.8100),
        ],
        readings=[
            SensorReading(location_id=1, latitude=-37.8100, longitude=144.9652, total_count=20),
            SensorReading(location_id=2, latitude=-37.8100, longitude=144.9656, total_count=180),
        ],
        sensor_radius_metres=15,
        low_max=50,
        medium_max=150,
    )

    assert [segment.crowd_level for segment in segments] == ["low", "high", None]
    assert segments[0].matched_sensor_count == 1
    assert segments[1].crowd_score == 180
    assert segments[2].matched_sensor_count == 0
