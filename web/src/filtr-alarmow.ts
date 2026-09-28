import type { AlertDto } from "./api";
import { NAZWY } from "./alert-text";

/**
 * Filtering the alert list by detector.
 *
 * Needed because the detectors do not produce alerts at anything like the same rate. D5 alone
 * yields around a hundred a day on Finnish waters - most of them tugs, pilot boats and ferries
 * going about their work - while D4 gives a handful and D7 usually none. Without a filter the list
 * becomes one detector's output, and the rare finding that someone actually wants is buried under
 * the common one. Sorting by score would not fix it either: the scores are not comparable between
 * detectors, they each mean something different.
 */

export interface Grupa {
  detektor: string | null; // null = wszystkie
  etykieta: string;
  ile: number;
}

/**
 * One chip per detector that actually produced something, plus "all" in front.
 *
 * Detectors with nothing to show are left out rather than greyed: an empty chip invites the reader
 * to click it and find out that nothing is there, which is a worse way to learn the same fact than
 * simply not seeing the chip.
 */
export function grupy(alerts: AlertDto[]): Grupa[] {
  const licznik = new Map<string, number>();
  for (const a of alerts) licznik.set(a.detector, (licznik.get(a.detector) ?? 0) + 1);

  const posortowane = [...licznik.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return [
    { detektor: null, etykieta: "wszystkie", ile: alerts.length },
    ...posortowane.map(([d, ile]) => ({ detektor: d, etykieta: NAZWY[d] ?? d, ile })),
  ];
}

export function odfiltruj(alerts: AlertDto[], detektor: string | null): AlertDto[] {
  return detektor === null ? alerts : alerts.filter((a) => a.detector === detektor);
}

/**
 * What to say when the list is empty, which is not one situation but three.
 *
 * "No alerts at all" is the system saying the last day was quiet. "None of this kind" is the
 * reader's own filter. Showing the same sentence for both makes a filter look like an outage.
 */
export function pustaLista(wszystkich: number, detektor: string | null): string {
  if (wszystkich === 0) return "Brak alarmów z ostatnich 24 h. Detektory liczą - po prostu nic nie znalazły.";
  return `Żaden alarm z ostatnich 24 h nie jest tego typu (${NAZWY[detektor ?? ""] ?? detektor}). Wybierz „wszystkie”, żeby zobaczyć pozostałe.`;
}
