import { useState } from "react";
import { parseEvidence } from "../api";
import type { AlertDto } from "../api";
import { dopisek, NAZWY, podmiot, szczegoly } from "../alert-text";
import { grupy, odfiltruj, pustaLista } from "../filtr-alarmow";

export function AlertsPanel({ alerts, onSelect, polaczone = true, wybranyId = null }:
  { alerts: AlertDto[]; onSelect: (a: AlertDto) => void; polaczone?: boolean; wybranyId?: number | null }) {
  const [detektor, setDetektor] = useState<string | null>(null);
  const widoczne = odfiltruj(alerts, detektor);

  return (
    <aside className="panel">
      <h2>Alarmy (do sprawdzenia)</h2>
      {/* Detektory nie produkuja w zblizonym tempie: D5 daje okolo stu dziennie, D4 kilka, D7 zwykle
          zero. Bez filtra lista jest wyjsciem jednego detektora, a rzadkie znalezisko tonie. */}
      <div className="filtr-alarmow" role="group" aria-label="Filtruj po detektorze">
        {grupy(alerts).map((g) => (
          <button
            key={g.detektor ?? "wszystkie"}
            type="button"
            className={detektor === g.detektor ? "wybrany" : ""}
            aria-pressed={detektor === g.detektor}
            onClick={() => setDetektor(g.detektor)}
          >
            {g.etykieta} <span className="liczba">{g.ile}</span>
          </button>
        ))}
      </div>
      {widoczne.length === 0 && <p className="muted">{pustaLista(alerts.length, detektor, polaczone)}</p>}
      <ul>
        {widoczne.map((a) => {
          const ev = parseEvidence(a.evidence);
          return (
            <li key={a.id}>
              {/* aria-current, nie sam kolor: czytnik ekranu tez ma wiedziec, ktory alarm jest otwarty. */}
              <button onClick={() => onSelect(a)} aria-current={a.id === wybranyId || undefined}>
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
