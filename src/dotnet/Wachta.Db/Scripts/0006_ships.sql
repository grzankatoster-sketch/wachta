-- Warstwa morska: pozycje statkow AIS, wzorowane 1:1 na aircraft_position (0003).
-- Bez tabeli tu D4 (cisza AIS) i D6 (wleczenie kotwicy) nie maja z czego czytac - zyly wylacznie
-- w testach i eval/feasibility. Jedno zrodlo na start (Digitraffic, wody finskie), stad source_id
-- w kazdym wierszu zamiast zakladania z gory jednego dostawcy.
CREATE TABLE ship_position (
    ts          timestamptz NOT NULL,
    mmsi        text NOT NULL,
    name        text,
    imo         text,
    ship_type   text,      -- Digitraffic daje kod AIS liczbowy, ale zapisujemy tekstem: przyszle
                            -- zrodla (AISStream, dane dunskie) opisuja typ slownie, nie liczba.
    nav_status  text,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    sog_kt      real,
    cog_deg     real,
    source_id   text NOT NULL REFERENCES source(id),
    fetched_at  timestamptz NOT NULL
);
SELECT create_hypertable('ship_position', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ship_position_mmsi_ts ON ship_position (mmsi, ts DESC);
ALTER TABLE ship_position SET (timescaledb.compress, timescaledb.compress_segmentby = 'mmsi');
SELECT add_compression_policy('ship_position', INTERVAL '1 day');
SELECT add_retention_policy('ship_position', INTERVAL '7 days');

-- Digitraffic (Fintraffic): bez klucza, ale wymaga naglowkow User-Agent i Digitraffic-User, inaczej
-- odmawia - ten sam blad projekt juz przerabial z adsb.lol (403 bez opisowego User-Agent).
INSERT INTO source (id, name, url, license, trust_tier, attribution) VALUES
  ('digitraffic-ais', 'Digitraffic (Fintraffic) AIS', 'https://meri.digitraffic.fi/api/ais/v1/locations',
   'CC BY 4.0', 2, 'Data: Fintraffic / Digitraffic (CC BY 4.0)');
