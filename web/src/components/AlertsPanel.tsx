import { parseEvidence } from "../api";
import type { AlertDto } from "../api";

const LABELS: Record<string, string> = { D1: "Zgaszony transponder" };

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
                <strong>{LABELS[a.detector] ?? a.detector}</strong> · {ev.flight ?? a.entityId} {ev.type_code ?? ""}
                <br />
                <span className="muted">
                  {new Date(a.startedAt).toLocaleString("pl-PL")} · luka {ev.gap_minutes ?? "?"} min · wynik {a.score}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
