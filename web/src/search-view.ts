import type { SearchResult } from "./api";

/**
 * The decisions the search panel makes about what it is looking at, kept out of the component so
 * they can be tested without rendering anything.
 *
 * The one that matters is `stanZOdpowiedzi`: an empty result and a failed request must never
 * collapse into the same state. "Nothing in the corpus passed the floor" is an answer about the
 * world; "the model did not respond" is the absence of an answer. They look identical on screen if
 * nobody keeps them apart, and a search tool that shows an outage as "no results" is a tool that
 * quietly reports a quiet world.
 */

export type Sila = { etykieta: string; klasa: "mocne" | "srednie" | "slabe" };

/**
 * Turns a similarity score into a word.
 *
 * Thresholds come from the measurement behind the cutoff: on 600 GDELT events sensible questions
 * scored 0.570-0.782 and unrelated ones 0.354-0.445. Anything just over the 0.50 floor is therefore
 * barely distinguishable from noise and is called weak, not "a hit".
 */
export function sila(score: number): Sila {
  if (score >= 0.65) return { etykieta: "mocne", klasa: "mocne" };
  if (score >= 0.55) return { etykieta: "średnie", klasa: "srednie" };
  return { etykieta: "słabe", klasa: "slabe" };
}

export type Stan =
  | { rodzaj: "pusto" }
  | { rodzaj: "szukam" }
  | { rodzaj: "wynik"; dane: SearchResult }
  | { rodzaj: "blad"; komunikat: string };

/** A successful response, whether or not it found anything. Empty is a result, not a failure. */
export function stanZOdpowiedzi(dane: SearchResult): Stan {
  return { rodzaj: "wynik", dane };
}

/** A failed request. Never a result - see the note at the top of this file. */
export function stanZBledu(e: unknown): Stan {
  return { rodzaj: "blad", komunikat: e instanceof Error ? e.message : String(e) };
}

/** Query string for the endpoint. `kind` is left out entirely when the reader wants everything. */
export function zapytanie(query: string, kind?: string, limit = 8): string {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (kind) params.set("kind", kind);
  return params.toString();
}
