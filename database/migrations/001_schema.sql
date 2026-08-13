CREATE TABLE IF NOT EXISTS sensor_location (
    location_id INTEGER PRIMARY KEY,
    sensor_name TEXT NOT NULL,
    sensor_description TEXT,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL,
    status TEXT,
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT sensor_location_latitude_range CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT sensor_location_longitude_range CHECK (longitude BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS pedestrian_minute_count (
    location_id INTEGER NOT NULL REFERENCES sensor_location(location_id),
    sensing_datetime TIMESTAMPTZ NOT NULL,
    direction_1 INTEGER,
    direction_2 INTEGER,
    total_count INTEGER NOT NULL CHECK (total_count >= 0),
    crowd_level TEXT NOT NULL CHECK (crowd_level IN ('low', 'medium', 'high')),
    source_fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (location_id, sensing_datetime)
);

CREATE INDEX IF NOT EXISTS pedestrian_minute_count_sensing_datetime_idx
    ON pedestrian_minute_count (sensing_datetime DESC);

CREATE TABLE IF NOT EXISTS data_refresh_log (
    refresh_id BIGSERIAL PRIMARY KEY,
    dataset_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'rate_limited')),
    records_received INTEGER NOT NULL DEFAULT 0,
    records_upserted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS data_refresh_log_dataset_started_idx
    ON data_refresh_log (dataset_name, started_at DESC);
