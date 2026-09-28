import { useEffect, useState } from "react";
import type { MapViewState } from "@deck.gl/core";
import { getJSON, type AlertDto, type JammingDto, type ReplayPath } from "./api";
import { AlertsPanel } from "./components/AlertsPanel";
import { BALTIC_VIEW, MapView } from "./components/MapView";
import { ReplayBar } from "./components/ReplayBar";
import { SearchPanel } from "./components/SearchPanel";
import { DetailPanel } from "./components/DetailPanel";
import { Warstwy } from "./components/Warstwy";
import { SourcesFooter } from "./components/SourcesFooter";
import { aircraftLayers } from "./layers/aircraft";
import { alertsLayer } from "./layers/alerts";
import { jammingLayer } from "./layers/jamming";
import { tripsLayer } from "./layers/trips";
import { useLive } from "./live";
import { replayBounds, toTrips, type Trip } from "./replay";
import { selectionFromPicked, zbudujSzczegoly, type Selection } from "./detail";
import { stanDanych, WSZYSTKO_WIDOCZNE, type Widoczne } from "./warstwy";

export default function App() {
  const { aircraft, alerts, setAlerts, connected } = useLive();
  const [jamming, setJamming] = useState<JammingDto[]>([]);
  const [view, setView] = useState<MapViewState>(BALTIC_VIEW);
  const [replay, setReplay] = useState<{ trips: Trip[]; start: number; max: number } | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [widoczne, setWidoczne] = useState<Widoczne>(WSZYSTKO_WIDOCZNE);
  const [wybrany, setWybrany] = useState<Selection | null>(null);

  useEffect(() => {
    getJSON<AlertDto[]>("/api/alerts").then(setAlerts).catch(() => undefined);
    const load = () => getJSON<JammingDto[]>("/api/jamming").then(setJamming).catch(() => undefined);
    load();
    const id = setInterval(load, 10 * 60 * 1000);
    return () => clearInterval(id);
  }, [setAlerts]);

  useEffect(() => {
    if (!playing || !replay) return;
    const id = setInterval(() => setCurrentTime((t) => (t + 60 > replay.max ? 0 : t + 60)), 100);
    return () => clearInterval(id);
  }, [playing, replay]);

  const toggleReplay = async () => {
    if (replay) {
      setReplay(null);
      setPlaying(false);
      return;
    }
    const to = new Date();
    const from = new Date(to.getTime() - 6 * 3600 * 1000);
    const paths = await getJSON<ReplayPath[]>(
      `/api/replay?from=${from.toISOString()}&to=${to.toISOString()}&militaryOnly=true`,
    );
    const bounds = replayBounds(paths);
    if (!bounds) return;
    setReplay({ trips: toTrips(paths, bounds.start), start: bounds.start, max: bounds.end - bounds.start });
    setCurrentTime(0);
    setPlaying(true);
  };

  // Filtrujemy DANE, nie warstwy: warstwa bez danych nadal sie rysuje (i nadal lapie klikniecia),
  // a pusta lista znika z mapy calkowicie. Dzieki temu wylaczenie w panelu znaczy to, co widac.
  const widoczneSamoloty = aircraft.filter((a) =>
    a.isMilitary ? widoczne.wojskowe : widoczne.cywilne);
  const widoczneAlarmy = widoczne.alarmy ? alerts : [];
  const widoczneZaklocenia = widoczne.zaklocenia ? jamming : [];

  // Wiek najswiezszej pozycji. Wczesniej szlo tu null, wiec zdanie o swiezosci nigdy sie nie
  // pokazywalo - mapa wygladala tak samo, czy dane mialy 5 sekund, czy przyszly ostatni raz kwadrans
  // temu. Brak danych zostaje nullem: "nie wiem, ile to ma lat" to nie to samo co "jest swieze".
  const sekundOdOdczytu = aircraft.length
    ? Math.max(0, Math.round((Date.now() - Math.max(...aircraft.map((a) => Date.parse(a.ts)))) / 1000))
    : null;

  const liczby = {
    wojskowe: aircraft.filter((a) => a.isMilitary && !a.onGround).length,
    cywilne: aircraft.filter((a) => !a.isMilitary && !a.onGround).length,
    alarmy: alerts.length,
    zaklocenia: jamming.length,
  };

  const layers = replay
    ? [jammingLayer(widoczneZaklocenia), tripsLayer(replay.trips, currentTime), alertsLayer(widoczneAlarmy)]
    : [jammingLayer(widoczneZaklocenia), ...aircraftLayers(widoczneSamoloty), alertsLayer(widoczneAlarmy)];

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <MapView
        layers={layers}
        viewState={view}
        onViewStateChange={setView}
        onObjectClick={(o) => setWybrany(selectionFromPicked(o))}
      />
      {wybrany && <DetailPanel szczegoly={zbudujSzczegoly(wybrany)} onClose={() => setWybrany(null)} />}
      <AlertsPanel
        alerts={alerts}
        polaczone={connected}
        onSelect={(a) => {
          // Lista otwiera ten sam panel co klikniecie w mape. Wczesniej robila tylko setView, wiec
          // analiza - "co to jest, co z tego wynika, na jakiej podstawie" - byla dostepna wylacznie
          // przez trafienie mysza w kilkupikselowy znacznik na canvasie deck.gl. Bez myszy nie bylo
          // jej wcale, a przy kilku alarmach w jednym miejscu trafialo sie w sasiada.
          setView({ ...view, longitude: a.lon, latitude: a.lat, zoom: 8 });
          setWybrany({ kind: "alert", data: a });
        }}
      />
      <SearchPanel />
      <div className="lewa-kolumna">
        <header className="naglowek">
        <h1>WACHTA</h1>
        <p>
          Co widać z danych publicznych: ruch lotniczy i morski, zakłócenia GPS, oraz miejsca, które
          własne detektory uznały za warte sprawdzenia. Każdy alarm jest <b>kandydatem do
          sprawdzenia</b>, nigdy wyrokiem.
        </p>
        <p className="stan">{stanDanych(connected, liczby.wojskowe + liczby.cywilne, sekundOdOdczytu)}</p>
        </header>
        <Warstwy widoczne={widoczne} onZmiana={setWidoczne} liczby={liczby} />
      </div>
      <ReplayBar
        active={!!replay}
        onToggle={toggleReplay}
        currentTime={currentTime}
        max={replay?.max ?? 0}
        setCurrentTime={setCurrentTime}
        playing={playing}
        setPlaying={setPlaying}
        startEpoch={replay?.start ?? null}
      />
      <SourcesFooter />
    </div>
  );
}
