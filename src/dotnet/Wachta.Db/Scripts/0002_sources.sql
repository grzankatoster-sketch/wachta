CREATE TABLE source (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    url         text NOT NULL,
    license     text NOT NULL,
    trust_tier  smallint NOT NULL CHECK (trust_tier BETWEEN 1 AND 5),
    attribution text NOT NULL
);

INSERT INTO source (id, name, url, license, trust_tier, attribution) VALUES
  ('adsblol-mil',     'adsb.lol — military (global)', 'https://api.adsb.lol/v2/mil',               'ODbL 1.0', 1, 'Data: adsb.lol contributors (ODbL)'),
  ('adsblol-baltic-s','adsb.lol — Baltic south',      'https://api.adsb.lol/v2/point/55.0/20.0/250','ODbL 1.0', 1, 'Data: adsb.lol contributors (ODbL)'),
  ('adsblol-baltic-n','adsb.lol — Baltic north',      'https://api.adsb.lol/v2/point/60.0/24.0/250','ODbL 1.0', 1, 'Data: adsb.lol contributors (ODbL)');
