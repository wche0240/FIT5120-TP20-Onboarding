CREATE TABLE IF NOT EXISTS transit_access_point (
    access_point_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('bus', 'tram', 'train', 'coach')),
    source_mode TEXT NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL,
    source_dataset TEXT NOT NULL,
    source_fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT transit_access_point_latitude_range CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT transit_access_point_longitude_range CHECK (longitude BETWEEN -180 AND 180)
);

CREATE INDEX IF NOT EXISTS transit_access_point_mode_idx
    ON transit_access_point (mode);

CREATE INDEX IF NOT EXISTS transit_access_point_coordinates_idx
    ON transit_access_point (latitude, longitude);
