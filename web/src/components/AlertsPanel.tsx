import { parseEvidence } from "../api";
import type { AlertDto } from "../api";
import { dopisek, NAZWY, podmiot, szczegoly } from "../alert-text";

export function AlertsPanel({ alerts, onSelect }: { alerts: AlertDto[]; onSelect: (a: AlertDto) => void }) {
  return (
    <aside className="panel">
      <h2>Alarmy (do sprawdzenia)</h2>
      {alerts.length === 0 && <p className="muted">Brak alarmów z ostatnich 24 h.</p>}
      <ul>
        {alerts.map((a) => {
          const ev = parseEvidence(a.evidence);
          return (
            <li key={a.id}>
              <button onClick={() => onSelect(a)}>
                <strong>{NAZWY[a.detector] ?? a.detector}</strong> · {podmiot(ev, a.entityId)}{" "}
                {dopisek(ev)}
                <br />
                <span className="muted">
                  {[new Date(a.startedAt).toLocaleString("pl-PL"), ...szczegoly(ev),
                    `wynik ${a.score}`].join(" · ")}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
