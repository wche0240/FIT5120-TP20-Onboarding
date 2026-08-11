ALTER TABLE data_refresh_log
    DROP CONSTRAINT IF EXISTS data_refresh_log_status_check;

ALTER TABLE data_refresh_log
    ADD CONSTRAINT data_refresh_log_status_check
    CHECK (status IN ('running', 'succeeded', 'failed', 'rate_limited'));
