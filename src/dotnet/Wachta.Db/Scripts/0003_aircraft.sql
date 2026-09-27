CREATE TABLE fetch_log (
    id           bigserial PRIMARY KEY,
    source_id    text NOT NULL REFERENCES source(id),
    url          text NOT NULL,
    fetched_at   timestamptz NOT NULL,
    content_hash text NOT NULL,
    n_received   integer NOT NULL,
    n_written    integer NOT NULL
);
CREATE INDEX fetch_log_source_time ON fetch_log (source_id, fetched_at DESC);

CREATE TABLE aircraft_position (
    ts          timestamptz NOT NULL,
    hex         text NOT NULL,
    flight      text,
    type_code   text,
    is_military boolean NOT NULL,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    alt_baro_ft integer,
    on_ground   boolean NOT NULL,
    gs_kt       real,
    track_deg   real,
    nic         smallint,
    nac_p       smallint,
    source_id   text NOT NULL REFERENCES source(id),
    fetched_at  timestamptz NOT NULL
);
SELECT create_hypertable('aircraft_position', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX aircraft_position_hex_ts ON aircraft_position (hex, ts DESC);
ALTER TABLE aircraft_position SET (timescaledb.compress, timescaledb.compress_segmentby = 'hex');
SELECT add_compression_policy('aircraft_position', INTERVAL '1 day');
SELECT add_retention_policy('aircraft_position', INTERVAL '7 days');

-- One row per aircraft: when did we last hear it at all, and when did it last report a position.
-- Small table (thousands of rows), upserted on every fetch. D1 needs "silent", not "no position".
CREATE TABLE aircraft_contact (
    hex              text PRIMARY KEY,
    last_message_at  timestamptz NOT NULL,
    last_position_at timestamptz,
    source_id        text NOT NULL REFERENCES source(id),
    updated_at       timestamptz NOT NULL
);
CREATE INDEX aircraft_contact_last_message ON aircraft_contact (last_message_at DESC);
