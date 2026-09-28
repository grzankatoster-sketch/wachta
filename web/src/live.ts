import { useEffect, useState } from "react";
import { HubConnectionBuilder, LogLevel } from "@microsoft/signalr";
import type { AlertDto, LiveAircraft } from "./api";

export function useLive() {
  const [aircraft, setAircraft] = useState<LiveAircraft[]>([]);
  const [alerts, setAlerts] = useState<AlertDto[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const hub = new HubConnectionBuilder().withUrl("/hubs/live").withAutomaticReconnect().configureLogging(LogLevel.Warning).build();
    hub.on("aircraft", (list: LiveAircraft[]) => setAircraft(list));
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

  return { aircraft, alerts, setAlerts, connected };
}
