import { useEffect, useState } from "react";
import { HubConnectionBuilder, LogLevel } from "@microsoft/signalr";
import type { AlertDto, LiveAircraft, LiveShip } from "./api";

export function useLive() {
  const [aircraft, setAircraft] = useState<LiveAircraft[]>([]);
  const [ships, setShips] = useState<LiveShip[]>([]);
  // Kiedy paczka DOTARLA, wg zegara tej przegladarki. Razem z najnowszym znacznikiem czasu z paczki
  // pozwala liczyc wiek pozycji bez zakladania, ze zegar serwera i zegar tego komputera sa zgodne.
  const [odebranoSamoloty, setOdebranoSamoloty] = useState(0);
  const [odebranoStatki, setOdebranoStatki] = useState(0);
  const [alerts, setAlerts] = useState<AlertDto[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const hub = new HubConnectionBuilder().withUrl("/hubs/live").withAutomaticReconnect().configureLogging(LogLevel.Warning).build();
    hub.on("aircraft", (list: LiveAircraft[]) => { setAircraft(list); setOdebranoSamoloty(Date.now()); });
    hub.on("ships", (list: LiveShip[]) => { setShips(list); setOdebranoStatki(Date.now()); });
    hub.on("alerts", (list: AlertDto[]) => setAlerts((prev) => [...list, ...prev].slice(0, 200)));
    hub.onreconnecting(() => setConnected(false));
    hub.onreconnected(() => setConnected(true));
    // StrictMode montuje efekt dwa razy, a hub.stop() w trakcie negocjacji konczy sie wpisem
    // "Failed to start the connection" na poziomie Error - biblioteka loguje go, zanim .catch()
    // zdazy cokolwiek zrobic. Rozlaczamy sie dopiero, gdy start sie rozstrzygnie.
    let live = true;
    const started = hub.start().then(
      () => { if (live) setConnected(true); },
      () => { if (live) setConnected(false); },
    );
    return () => {
      live = false;
      void started.then(() => hub.stop());
    };
  }, []);

  return { aircraft, ships, alerts, setAlerts, connected, odebranoSamoloty, odebranoStatki };
}
