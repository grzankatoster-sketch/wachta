import { useEffect, useState } from "react";
import type { MapViewState } from "@deck.gl/core";
import { getJSON, type AlertDto, type JammingDto, type ReplayPath } from "./api";
import { AlertsPanel } from "./components/AlertsPanel";
import { BALTIC_VIEW, MapView } from "./components/MapView";
import { ReplayBar } from "./components/ReplayBar";
import { SearchPanel } from "./components/SearchPanel";
import { SourcesFooter } from "./components/SourcesFooter";
import { aircraftLayers } from "./layers/aircraft";
import { alertsLayer } from "./layers/alerts";
import { jammingLayer } from "./layers/jamming";
import { tripsLayer } from "./layers/trips";
import { useLive } from "./live";
import { replayBounds, toTrips, type Trip } from "./replay";

export default function App() {
  const { aircraft, alerts, setAlerts, connected } = useLive();
  const [jamming, setJamming] = useState<JammingDto[]>([]);
  const [view, setView] = useState<MapViewState>(BALTIC_VIEW);
  const [replay, setReplay] = useState<{ trips: Trip[]; start: number; max: number } | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);

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

  const layers = replay
    ? [jammingLayer(jamming), tripsLayer(replay.trips, currentTime), alertsLayer(alerts)]
    : [jammingLayer(jamming), ...aircraftLayers(aircraft), alertsLayer(alerts)];

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <MapView layers={layers} viewState={view} onViewStateChange={setView} />
      <AlertsPanel alerts={alerts} onSelect={(a) => setView({ ...view, longitude: a.lon, latitude: a.lat, zoom: 8 })} />
      <SearchPanel />
      <div className="status status-pod-szukaniem">{connected ? `na żywo · ${aircraft.length} samolotów` : "łączenie…"}</div>
      <div className="legend">
        GPS: <i className="amber" /> 2–10% zakłóconych <i className="red" /> ≥ 10%
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
