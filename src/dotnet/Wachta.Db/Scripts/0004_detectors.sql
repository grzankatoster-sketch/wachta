CREATE TABLE alert (
    id          bigserial PRIMARY KEY,
    detector    text NOT NULL,
    entity_id   text NOT NULL,
    started_at  timestamptz NOT NULL,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    score       real NOT NULL,
    evidence    jsonb NOT NULL,
    state       text NOT NULL DEFAULT 'new' CHECK (state IN ('new','triaged','confirmed','dismissed')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (detector, entity_id, started_at)
);
CREATE INDEX alert_created ON alert (created_at DESC);

CREATE TABLE jamming_cell (
    hour        timestamptz NOT NULL,
    h3          text NOT NULL,
    n_aircraft  integer NOT NULL,
    n_degraded  integer NOT NULL,
    PRIMARY KEY (hour, h3)
);

CREATE TABLE coverage_hourly (
    hour      timestamptz NOT NULL,
    h3        text NOT NULL,
    n_reports integer NOT NULL,
    PRIMARY KEY (hour, h3)
);

-- Frozen D1 inputs for EVERY aircraft that went silent, including those the rules rejected.
-- Without the rejected ones recall cannot be measured: the detector would be graded on its own output.
CREATE TABLE d1_sample (
    hex          text NOT NULL,
    evaluated_at timestamptz NOT NULL,
    alerted      boolean NOT NULL,
    inputs       jsonb NOT NULL,
    PRIMARY KEY (hex, evaluated_at)
);
