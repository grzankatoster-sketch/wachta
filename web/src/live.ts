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
    hub.start().then(() => setConnected(true)).catch(() => setConnected(false));
    return () => { void hub.stop(); };
  }, []);

  return { aircraft, alerts, setAlerts, connected };
}
