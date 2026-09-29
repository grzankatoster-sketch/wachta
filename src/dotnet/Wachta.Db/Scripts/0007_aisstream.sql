-- Drugie zrodlo AIS: poludniowy Baltyk, ktorego finska siec nie slyszy.
--
-- Pomiar, ktory to uzasadnia (zywa baza, 2026-09-29, 20 h zbierania z Digitraffic): 165 202 pozycje,
-- 1210 kadlubow, zakres 55,48-65,80N. Ponizej 57N tylko 178 pozycji (0,11%). W Zatoce Gdanskiej,
-- przy polskim wybrzezu, na podejsciach do Kaliningradu i w ciesninach dunskich - ZERO. Mapa
-- deklaruje 48-70N / 0-40E (WatchedArea.cs), wiec obiecywala akwen, ktorego nie pokazywala.
--
-- trust_tier 3, o jeden nizej niz Digitraffic (2): AISStream agreguje odbiorniki ochotnikow, bez
-- SLA i bez rejestru statkow za soba, podczas gdy Digitraffic to siec brzegowa krajowego organu.
-- Ta roznica nie jest ozdobna - rozstrzyga deduplikacje, kiedy oba zrodla slysza ten sam kadlub
-- (wachta_detectors/aisstream.py, drop_covered).
INSERT INTO source (id, name, url, license, trust_tier, attribution) VALUES
  ('aisstream-baltic-s', 'AISStream — poludniowy Baltyk', 'wss://stream.aisstream.io/v0/stream',
   'aisstream.io terms (darmowe, niekomercyjne)', 3, 'Data: aisstream.io');
