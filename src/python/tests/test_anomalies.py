from datetime import date, datetime, timedelta, timezone

import pytest

from wachta_detectors.anomalies import detect_spikes, poisson_tail
from wachta_detectors.events import Event

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
KYIV = (50.45, 30.52)
TALLINN = (59.44, 24.75)


def event(day: date, lat: float, lon: float, root: str = "19", mentions: int = 1, place: str = "Gdzies",
          at: datetime | None = None) -> Event:
    stamp = at or datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).replace(hour=11)
    return Event(id=f"{day}-{lat}-{lon}-{mentions}-{stamp:%H%M}", day=day, added=stamp, actor1="A", actor1_country="AA",
                 actor2="B", actor2_country="BB", root_code=root, event_code=root + "0",
                 quad_class=4, goldstein=-8.0, mentions=mentions, place=place, country="UP",
                 lat=lat, lon=lon, url=f"https://example.org/{day}/{mentions}")


class TestPoissonTail:
    def test_zero_or_negative_count_is_certain(self):
        assert poisson_tail(0, 2.0) == 1.0

    def test_expected_number_of_events_is_not_surprising(self):
        assert poisson_tail(3, 3.0) > 0.3

    def test_many_events_where_few_are_expected_is_improbable(self):
        assert poisson_tail(8, 0.5) < 1e-5

    def test_probability_falls_as_the_count_rises(self):
        assert poisson_tail(6, 2.0) < poisson_tail(4, 2.0) < poisson_tail(2, 2.0)

    def test_no_baseline_at_all(self):
        assert poisson_tail(3, 0.0) == 0.0


class TestSpikes:
    def quiet_history(self, lat, lon, per_day=1):
        """One event a day for the previous two days - an ordinary place."""
        return [event(NOW.date() - timedelta(days=d), lat, lon, mentions=i)
                for d in (1, 2) for i in range(per_day)]

    def test_place_breaking_its_own_rhythm_is_flagged(self):
        events = self.quiet_history(*KYIV) + [event(NOW.date(), *KYIV, mentions=i, at=NOW - timedelta(hours=1)) for i in range(8)]
        [spike] = detect_spikes(events, NOW)
        assert spike.recent == 8
        assert spike.p_value < 0.01
        assert spike.times_over > 1

    def test_busy_place_keeping_its_rhythm_is_not_flagged(self):
        events = self.quiet_history(*KYIV, per_day=40) + [event(NOW.date(), *KYIV, mentions=i, at=NOW - timedelta(hours=1)) for i in range(6)]
        assert detect_spikes(events, NOW) == []

    def test_two_reports_are_never_a_spike(self):
        events = self.quiet_history(*TALLINN) + [event(NOW.date(), *TALLINN, mentions=i, at=NOW - timedelta(hours=1)) for i in range(2)]
        assert detect_spikes(events, NOW) == []

    def test_cells_are_independent(self):
        events = (self.quiet_history(*KYIV) + self.quiet_history(*TALLINN)
                  + [event(NOW.date(), *KYIV, mentions=i, at=NOW - timedelta(hours=1)) for i in range(8)]
                  + [event(NOW.date(), *TALLINN, mentions=99, at=NOW - timedelta(hours=1))])
        [spike] = detect_spikes(events, NOW)
        assert abs(spike.lat - KYIV[0]) < 0.5

    def test_only_conflict_events_count_by_default(self):
        aid = [event(NOW.date(), *KYIV, root="07", mentions=i, at=NOW - timedelta(hours=1)) for i in range(8)]
        assert detect_spikes(self.quiet_history(*KYIV) + aid, NOW) == []
        assert detect_spikes(self.quiet_history(*KYIV) + aid, NOW, conflict_only=False)

    def test_spike_carries_kinds_and_examples_for_checking(self):
        # Piec zdarzen, bo trzy przy tej historii nie przekraczaja progu istotnosci - i dobrze.
        events = (self.quiet_history(*KYIV)
                  + [event(NOW.date(), *KYIV, root="19", mentions=5, at=NOW - timedelta(hours=1))]
                  + [event(NOW.date(), *KYIV, root="19", mentions=4, at=NOW - timedelta(hours=2))]
                  + [event(NOW.date(), *KYIV, root="18", mentions=3, at=NOW - timedelta(hours=1))]
                  + [event(NOW.date(), *KYIV, root="18", mentions=2, at=NOW - timedelta(hours=3))]
                  + [event(NOW.date(), *KYIV, root="20", mentions=1, at=NOW - timedelta(hours=1))])
        [spike] = detect_spikes(events, NOW)
        assert set(spike.kinds) == {"walka", "napasc", "przemoc masowa"}
        assert spike.examples[0].endswith("/5")   # najpierw najszerzej opisane

    def test_place_with_no_history_needs_more_than_the_minimum(self):
        # Pusta historia daje oczekiwane 0,5 - trzy zdarzenia to za malo, by przejsc prog istotnosci.
        three = [event(NOW.date(), *TALLINN, mentions=i, at=NOW - timedelta(hours=1)) for i in range(3)]
        assert detect_spikes(three, NOW) == []
        seven = [event(NOW.date(), *TALLINN, mentions=i, at=NOW - timedelta(hours=1)) for i in range(7)]
        assert detect_spikes(seven, NOW)

    def test_results_are_ordered_by_how_improbable_they_are(self):
        events = (self.quiet_history(*KYIV) + self.quiet_history(*TALLINN)
                  + [event(NOW.date(), *KYIV, mentions=i, at=NOW - timedelta(hours=1)) for i in range(12)]
                  + [event(NOW.date(), *TALLINN, mentions=i, at=NOW - timedelta(hours=1)) for i in range(5)])
        spikes = detect_spikes(events, NOW)
        assert len(spikes) == 2
        assert spikes[0].p_value <= spikes[1].p_value
        assert spikes[0].recent == 12

    def test_empty_input(self):
        assert detect_spikes([], NOW) == []


def test_times_over_is_readable_but_not_the_decision():
    events = [event(NOW.date(), *KYIV, mentions=i, at=NOW - timedelta(hours=1)) for i in range(10)]
    [spike] = detect_spikes(events, NOW)
    assert spike.times_over == pytest.approx(20.0)  # 10 przy oczekiwanych 0,5
    assert spike.expected == 0.5


def test_events_stamped_in_the_future_do_not_raise_an_alarm():
    """Znalezione w audycie: okno biezace nie mialo gornej granicy.

    Znacznik z przyszlosci - zegar zrodla, blad parsowania albo zastepcze poludnie dla dzisiejszej
    daty - wpadal do biezacego okna. Osiem takich zdarzen wystarczylo, zeby samo wywolalo alarm.
    """
    from datetime import datetime, timedelta, timezone

    from wachta_detectors.anomalies import detect_spikes
    from wachta_detectors.events import Event

    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

    def event(i: int, hours: float) -> Event:
        t = now + timedelta(hours=hours)
        return Event(str(i), t.date(), t, "A", None, "B", None, "19", "190", 4,
                     -9.0, 1, "X", "PL", 50.0, 20.0, "u")

    tlo = [event(100 + i, -20 - i) for i in range(4)]
    z_przyszlosci = [event(i, +5) for i in range(8)]
    assert detect_spikes(z_przyszlosci + tlo, now,
                         window=timedelta(hours=6), baseline=timedelta(hours=42)) == []

    # Kontrola: prawdziwe skupisko sprzed godziny nadal ma byc widziane.
    sprzed_godziny = [event(i, -1) for i in range(8)]
    assert detect_spikes(sprzed_godziny + tlo, now,
                         window=timedelta(hours=6), baseline=timedelta(hours=42))
