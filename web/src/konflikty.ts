import { getJSON } from "./api";
import type { WersjeDto } from "./wersje";

/**
 * Picking a war and reading what happened in it.
 *
 * The map elsewhere in this application answers "what is moving right now". This module answers a
 * different question - "what happened in this conflict, and how does each side tell it" - and the
 * two must not be confused, because the land events come from GDELT, which is a record of what was
 * REPORTED. A row here is an article's claim about the world, clustered with other articles making
 * the same claim. It is not a confirmed strike.
 */

export interface KonfliktDto {
  id: string;
  nazwa: string;
  actor1: string;
  actor2: string;
  /** How many events the backend has for this conflict. */
  events: number;
  lastEventAt: string;
}

export interface ZdarzenieDto {
  id: string;
  ts: string;
  /** CAMEO root code already translated to Polish by the backend ("napasc", "walka"...). */
  kind: string;
  actor1: string | null;
  actor2: string | null;
  place: string | null;
  lat: number;
  lon: number;
  /** CAMEO scale, -10 (worst) .. +10 (best). Null when GDELT did not give one. */
  goldstein: number | null;
  /** Distinct outlets that carried it. */
  sources: number;
  url: string;
  /** GDELT's mention count: a measure of how widely it was told, not of how true it is. */
  mentions: number;
}

/** Time windows the view offers. 24 h is the default because that is what the alert list uses. */
export const OKNA_H = [6, 24, 72] as const;
export const OKNO_DOMYSLNE_H = 24;

export async function pobierzKonflikty(): Promise<KonfliktDto[]> {
  return getJSON<KonfliktDto[]>("/api/conflicts");
}

export async function pobierzZdarzenia(id: string, godziny: number, limit = 500): Promise<ZdarzenieDto[]> {
  return getJSON<ZdarzenieDto[]>(`/api/conflicts/${encodeURIComponent(id)}/events?hours=${godziny}&limit=${limit}`);
}

export async function pobierzWersje(eventId: string): Promise<WersjeDto> {
  return getJSON<WersjeDto>(`/api/events/${encodeURIComponent(eventId)}/versions`);
}

/**
 * One event's headline: who, to whom, what kind of action.
 *
 * `kind` is a CAMEO root code and says what the ARTICLE reported, never what happened - the same
 * caveat events.py carries. The arrow between the actors is GDELT's direction, which is often the
 * grammatical subject of a sentence, so it is drawn as a plain arrow and not as "attacked".
 */
export function tytulZdarzenia(z: ZdarzenieDto): string {
  const kto = z.actor1 ?? "nieznany aktor";
  const kogo = z.actor2 ? ` → ${z.actor2}` : "";
  return `${kto}${kogo}: ${z.kind}`;
}

/**
 * The grey line under an event: when, where, how widely reported.
 *
 * Time is printed in UTC, spelled out. GDELT timestamps are UTC and the front covers three time
 * zones; a local-time label would silently mean something different for every reader.
 */
export function podpisZdarzenia(z: ZdarzenieDto): string {
  const czesci = [`${godzinaUTC(Date.parse(z.ts))} UTC`];
  if (z.place) czesci.push(z.place);
  czesci.push(z.sources === 1 ? "1 redakcja" : `${z.sources} redakcji`);
  return czesci.join(" · ");
}

function godzinaUTC(ms: number): string {
  return new Date(ms).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
}

export interface Kubelek {
  /** Inclusive start, epoch ms. */
  od: number;
  /** Exclusive end, except in the last bucket where it is inclusive. */
  do: number;
  ile: number;
  etykieta: string;
}

/**
 * The timeline under the event list: how the reporting was spread over the window.
 *
 * The axis is built from the DATA's own extent, not from the requested window. A window-based axis
 * has to decide what to do with an event that arrived just outside it, and every answer to that
 * question either drops events from the chart or draws them in the wrong bucket. An axis that
 * starts at the first event and ends at the last one cannot lose any: `ile` over all buckets always
 * sums to the number of events, which is the invariant the test pins down.
 */
export function osCzasu(zdarzenia: ZdarzenieDto[], kubelkow = 24): Kubelek[] {
  if (zdarzenia.length === 0 || kubelkow < 1) return [];
  const czasy = zdarzenia.map((z) => Date.parse(z.ts)).filter((t) => Number.isFinite(t));
  if (czasy.length === 0) return [];
  const min = Math.min(...czasy);
  const max = Math.max(...czasy);
  // Everything in one instant: one bucket, not twenty-four empty ones next to a full one.
  const n = max === min ? 1 : kubelkow;
  const szerokosc = max === min ? 1 : (max - min) / n;

  const kubelki: Kubelek[] = [...Array(n)].map((_, i) => ({
    od: min + i * szerokosc,
    do: min + (i + 1) * szerokosc,
    ile: 0,
    etykieta: godzinaUTC(min + i * szerokosc),
  }));
  for (const t of czasy) {
    const i = Math.min(n - 1, Math.floor((t - min) / szerokosc));
    kubelki[i].ile += 1;
  }
  return kubelki;
}

/** Tallest bar in the timeline, so the bars can be drawn relative to it. */
export function szczyt(kubelki: Kubelek[]): number {
  return kubelki.reduce((m, k) => Math.max(m, k.ile), 0);
}

/**
 * Three empty views, three different facts - kept in one place so the difference is visible.
 *
 * "No conflicts" means the backend has not grouped anything yet. "No events in this conflict"
 * means the chosen window is quiet, or too narrow. "No versions for this event" means the article
 * that produced it belongs to no assigned outlet - the event exists, the comparison does not.
 * Written as one sentence apiece, they would be indistinguishable on screen, and a reader would
 * read the deepest one ("nothing to compare") as the shallowest ("nothing happened").
 *
 * Each of them also has a fourth sibling: nothing answered at all. That one is never folded into
 * the others, because "we looked and found nothing" and "we cannot see" are opposite claims and
 * only one of them is ours to make.
 */
export function pustoKonflikty(polaczono: boolean): string {
  if (!polaczono) {
    return "Nie udało się pobrać listy konfliktów. To nie znaczy, że nic się nie dzieje — znaczy, że nic nie widzimy.";
  }
  return "Backend nie zgrupował jeszcze żadnego konfliktu. Nie ma z czego wybierać — to stan zbioru, nie stan świata.";
}

export function pustoZdarzenia(nazwa: string, godziny: number, polaczono: boolean): string {
  if (!polaczono) {
    return `Nie udało się pobrać zdarzeń dla „${nazwa}”. Okno ${godziny} h mogło być spokojne — ale tego nie wiemy.`;
  }
  return (
    `W oknie ${godziny} h nie ma zdarzeń przypisanych do „${nazwa}”. To znaczy, że w tym czasie nic o nim ` +
    "nie doniesiono w źródłach, które zbieramy — spróbuj szerszego okna."
  );
}

export function pustoWersje(polaczono: boolean): string {
  if (!polaczono) {
    return "Nie udało się pobrać zestawienia wersji dla tego zdarzenia.";
  }
  return (
    "Żaden artykuł o tym zdarzeniu nie pochodzi z redakcji przypisanej do którejkolwiek strony. " +
    "Zdarzenie istnieje, porównania nie ma — i nie zgadujemy przypisań, żeby jakieś było."
  );
}

/** Close enough to see a whole front, far enough to keep the neighbouring events on screen. */
export const ZOOM_ZDARZENIA = 6;

/**
 * The map's CENTRE latitude for a picked event, moved south of the event itself.
 *
 * Centring the map on the event puts it in the middle of the canvas - and the middle of the canvas
 * is under the panel that describes it. The map then re-centres on a mark the reader cannot see,
 * which on screen is indistinguishable from the map doing nothing (seen in a screenshot before this
 * was written: the picked event sat behind the drawer while the visible strip showed a region 300
 * km away).
 *
 * The visible strip is the TOP of the canvas, so the centre has to go SOUTH of the event by half of
 * what the drawer covers; the event then lands in the middle of what is left. `wysokoscZaslony` is
 * MEASURED off the drawer element rather than copied from its stylesheet - two constants that do
 * not know about each other is how this application once ended up with a legend on top of a header.
 */
export function nadSzuflada(lat: number, zoom: number, wysokoscZaslony: number): number {
  // Web Mercator: a pixel is worth fewer degrees of latitude the further from the equator you are.
  const stopniNaPiksel = (360 * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** zoom);
  return Math.max(-85, Math.min(85, lat - (wysokoscZaslony / 2) * stopniNaPiksel));
}

/**
 * Whether a conflict list is worth calling a conflict list.
 *
 * A "conflict" the backend built out of a single event is a clustering artefact, not a war, and
 * putting it in the picker next to a real one invites the reader to open it and compare versions
 * of a headline. It stays in the list - hiding data is its own kind of lie - but it is labelled.
 */
export function cienkiKonflikt(k: KonfliktDto): boolean {
  return k.events < 2;
}
