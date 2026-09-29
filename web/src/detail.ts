import type { AlertDto, JammingDto, LiveAircraft, LiveShip } from "./api";
import { parseEvidence } from "./api";
import { NAZWY, dopisek, podmiot, szczegoly } from "./alert-text";
import { ocen, type Ocena } from "./ocena";
import { szczegolyLinii, type LiniaInfrastruktury } from "./infrastruktura";

/**
 * Turns one clicked map object into the three sections the detail panel shows: what it is, what it
 * implies in plain sentences, and what it is based on (source, rule, thresholds) plus what it does
 * NOT prove. This is the one place that reasoning lives, so it can be unit-tested without React.
 *
 * Every detector writes its own evidence shape (see api.ts's AlertEvidence and alert-text.ts's
 * docstring). A detector this file does not yet know about must still render something honest - the
 * raw numbers `szczegoly()` already knows how to read - never a blank panel or a JSON dump.
 */

export type Selection =
  | { kind: "aircraft"; data: LiveAircraft }
  | { kind: "alert"; data: AlertDto }
  | { kind: "ship"; data: LiveShip }
  | { kind: "jamming"; data: JammingDto }
  | { kind: "infrastruktura"; data: LiniaInfrastruktury };

export interface Punkt {
  lon: number;
  lat: number;
}

export interface Szczegoly {
  tytul: string;
  podtytul: string | null;
  /** "Co to jest" - surowe fakty o obiekcie, w czytelnej formie (nie JSON). */
  coToJest: string[];
  /** "Co z tego wynika" - interpretacja po polsku, zdaniami. */
  coZTegoWynika: string[];
  /** "Na jakiej podstawie" - zrodlo, regula, progi i CZEGO TO NIE DOWODZI. */
  naPodstawie: string[];
  /** Punkty zaniku/powrotu, jesli dostepne w evidence (D4/D6) - do narysowania toru. */
  tor: { zanik: Punkt; powrot: Punkt } | null;
  /** Wlasna ocena alarmu: werdykt, za, przeciw. Null dla obiektow, ktore nie sa alarmem. */
  ocena?: Ocena | null;
}

function liczba(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function tekst(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function godzina(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("pl-PL");
}

// --- Samolot (punkt na mapie, nie alarm) ------------------------------------------------------

function aircraftDetail(a: LiveAircraft): Szczegoly {
  const nazwa = a.flight?.trim() || a.hex;
  const coToJest: string[] = [`Znak wywoławczy / hex: ${nazwa}${a.flight ? ` (${a.hex})` : ""}`];
  if (a.typeCode) coToJest.push(`Typ statku powietrznego: ${a.typeCode}`);
  coToJest.push(a.isMilitary ? "Oznaczony jako wojskowy" : "Oznaczony jako cywilny");
  if (a.altBaroFt !== null) coToJest.push(`Wysokość barometryczna: ${a.altBaroFt} ft`);
  if (a.gsKt !== null) coToJest.push(`Prędkość względem ziemi: ${a.gsKt} w.`);
  if (a.trackDeg !== null) coToJest.push(`Kurs: ${a.trackDeg}°`);
  coToJest.push(a.onGround ? "Na ziemi" : "W powietrzu");
  coToJest.push(`Ostatnia pozycja: ${godzina(a.ts)}`);

  const coZTegoWynika = [
    a.onGround
      ? "Samolot stoi lub kołuje po ziemi - to jego ostatnia zarejestrowana pozycja."
      : `Samolot leci obecnie${a.altBaroFt !== null ? ` na wysokości ${a.altBaroFt} ft` : ""}${
          a.gsKt !== null ? ` z prędkością ${a.gsKt} węzłów` : ""
        }.`,
  ];
  if (a.isMilitary) {
    coZTegoWynika.push(
      "Klasyfikacja wojskowy/cywilny pochodzi z bazy typów kadłubów i numeru hex, nie z deklaracji lotu.",
    );
  }

  return {
    tytul: nazwa,
    podtytul: a.typeCode,
    coToJest,
    coZTegoWynika,
    naPodstawie: [
      "Źródło: odbiór ADS-B (patrz stopka źródeł na mapie za dokładną licencję i atrybucję).",
      "Pozycja to ostatni odebrany komunikat, nie potwierdzenie trasy ani celu lotu.",
      "Czego to nie dowodzi: brak kolejnej transmisji w danej chwili nie oznacza awarii ani celowego ukrycia - oba wyglądają w danych identycznie.",
    ],
    tor: null,
  };
}

// --- Zaklocenia GPS (heksagon H3) -------------------------------------------------------------

const Z_95 = 1.96;
const MEDIUM_THRESHOLD = 0.02;
const HIGH_THRESHOLD = 0.1;

/** Same formula as the Python detector (wachta_detectors/jamming.py): a lower confidence bound, not the raw share. */
export function wilsonLowerBound(successes: number, total: number, z: number = Z_95): number {
  if (total <= 0) return 0;
  const p = successes / total;
  const denominator = 1 + (z * z) / total;
  const centre = p + (z * z) / (2 * total);
  const margin = z * Math.sqrt((p * (1 - p) + (z * z) / (4 * total)) / total);
  return Math.max(0, (centre - margin) / denominator);
}

export function poziomZaklocen(confidenceFloor: number): "high" | "medium" | "low" {
  if (confidenceFloor >= HIGH_THRESHOLD) return "high";
  if (confidenceFloor >= MEDIUM_THRESHOLD) return "medium";
  return "low";
}

const NAZWA_POZIOMU: Record<"high" | "medium" | "low", string> = {
  high: "wysoki",
  medium: "średni",
  low: "niski",
};

function jammingDetail(c: JammingDto): Szczegoly {
  const pct = c.nAircraft > 0 ? c.nDegraded / c.nAircraft : 0;
  const floor = wilsonLowerBound(c.nDegraded, c.nAircraft);
  const poziom = poziomZaklocen(floor);

  return {
    tytul: "Komórka zakłóceń GPS",
    podtytul: c.h3,
    coToJest: [
      `Samolotów w tej komórce w tej godzinie: ${c.nAircraft}`,
      `Z nich ze zdegradowaną jakością pozycji (NACp): ${c.nDegraded}`,
      `Surowy udział: ${(pct * 100).toFixed(1)}%`,
      `Poziom po metodzie z dolną granicą ufności: ${NAZWA_POZIOMU[poziom]}`,
    ],
    coZTegoWynika: [
      `${c.nDegraded} z ${c.nAircraft} samolotów w tej komórce zgłaszało obniżoną jakość pozycji (NACp) w tej godzinie.`,
      `Dolna granica 95% przedziału ufności dla tego udziału wynosi ${(floor * 100).toFixed(1)}%, co kwalifikuje komórkę jako poziom "${NAZWA_POZIOMU[poziom]}".`,
    ],
    naPodstawie: [
      "Źródło: wartości NACp z odbieranych komunikatów ADS-B, agregowane godzinowo w komórce H3.",
      "Reguła: próg NACp < 8 liczy się jako zdegradowany; komórka wymaga min. 10 samolotów, żeby w ogóle być ocenianą.",
      "Klasyfikacja liczona z dolnej granicy przedziału Wilsona (95%), nie z surowego procentu - metoda w duchu gpsjam.org, bo surowy procent przy małej próbie zawyża pojedyncze zgłoszenia do „wysokiego” poziomu.",
      "Czego to nie dowodzi: zdegradowany NACp może mieć przyczyny inne niż celowe zakłócanie (słaba geometria satelitów, usterka odbiornika); to wskaźnik zbiorowy dla obszaru, nie dowód na konkretne źródło ani konkretny statek powietrzny.",
    ],
    tor: null,
  };
}

// --- Alarmy (D1/D4/D6 maja wlasna interpretacje, reszta dostaje wersje ogolna) -----------------

function torZEvidence(ev: Record<string, unknown>): Szczegoly["tor"] {
  const zanikLat = liczba(ev.vanish_lat);
  const zanikLon = liczba(ev.vanish_lon);
  const powrotLat = liczba(ev.resume_lat);
  const powrotLon = liczba(ev.resume_lon);
  if (zanikLat === null || zanikLon === null || powrotLat === null || powrotLon === null) return null;
  return { zanik: { lat: zanikLat, lon: zanikLon }, powrot: { lat: powrotLat, lon: powrotLon } };
}

function d1Detail(a: AlertDto, ev: ReturnType<typeof parseEvidence>): Szczegoly {
  const podmiotNazwa = podmiot(ev, a.entityId);
  const gap = liczba(ev.gap_minutes);
  const cellReports = liczba(ev.cell_reports);
  const airportKm = liczba(ev.nearest_airport_km);

  const coZTegoWynika: string[] = [];
  if (gap !== null) {
    coZTegoWynika.push(
      `Samolot ${podmiotNazwa} przestał nadawać na ${Math.round(gap)} minut w komórce, w której odbiór działał` +
        (cellReports !== null ? ` (zwykle ${cellReports} zgłoszeń)` : "") +
        ".",
    );
  }
  if (airportKm !== null) {
    coZTegoWynika.push(
      airportKm > 40
        ? `Najbliższe lotnisko jest ${airportKm.toFixed(1)} km dalej, więc to nie zwykłe podejście do lądowania.`
        : `Najbliższe lotnisko jest ${airportKm.toFixed(1)} km dalej.`,
    );
  }
  if (coZTegoWynika.length === 0) coZTegoWynika.push(`Samolot ${podmiotNazwa} przestał nadawać na czas mieszczący się w progach detektora.`);

  return {
    tytul: podmiotNazwa,
    podtytul: dopisek(ev) || NAZWY.D1,
    coToJest: szczegoly(ev).length ? [`Zmierzone: ${szczegoly(ev).join(", ")}`] : [],
    coZTegoWynika,
    naPodstawie: [
      "Źródło: odbiór ADS-B, filtrowany tylko do lotu powyżej 3000 ft i 100 w., w komórce z dobrym pokryciem (≥200 zgłoszeń) i żywym odbiornikiem w pobliżu.",
      "Reguła D1: cisza 5-30 minut, dalej niż 40 km od lotniska - poza tym oknem uznaje się to za start/lądowanie albo koniec lotu, nie zanik.",
      "Czego to nie dowodzi: awaria transpondera wygląda w danych identycznie jak jego wyłączenie. To kandydat do sprawdzenia, nie wyrok.",
    ],
    tor: torZEvidence(ev),
  };
}

function d4Detail(a: AlertDto, ev: ReturnType<typeof parseEvidence>): Szczegoly {
  const podmiotNazwa = podmiot(ev, a.entityId);
  const minuty = liczba(ev.duration_minutes);
  const km = liczba(ev.shift_km);
  const swiadkowie = liczba(ev.listeners);
  const rownoczesnie = liczba(ev.simultaneous);
  const verdict = tekst(ev.verdict);
  const motion = tekst(ev.motion);

  const coZTegoWynika: string[] = [];
  if (minuty !== null && km !== null) {
    coZTegoWynika.push(
      `Statek ${podmiotNazwa} przestał nadawać na ${Math.round(minuty)} minut i pojawił się ${km.toFixed(1)} km dalej` +
        (swiadkowie !== null ? `, a w tym czasie ${swiadkowie} innych statków w tej samej kratce było słyszanych.` : "."),
    );
  }
  if (rownoczesnie !== null && rownoczesnie > 0) {
    coZTegoWynika.push(`Równocześnie zamilkło tam jeszcze ${rownoczesnie} innych statków.`);
  }
  if (verdict) coZTegoWynika.push(`Ocena odbioru: ${verdict}.`);
  if (motion) coZTegoWynika.push(`Ocena ruchu: ${motion}.`);

  return {
    tytul: podmiotNazwa,
    podtytul: dopisek(ev) || NAZWY.D4,
    coToJest: szczegoly(ev).length ? [`Zmierzone: ${szczegoly(ev).join(", ")}`] : [],
    coZTegoWynika,
    naPodstawie: [
      "Źródło: pozycje AIS z Digitraffic (wody fińskie i przyległe; brak pokrycia dalej na południe Bałtyku).",
      "Reguła D4: luka 45 minut - 12 godzin, statek miał płynąć min. 3 w. przed zanikiem, przesunięcie min. 1 km; „cisza przy działającym odbiorze” wymaga min. 3 świadków w tej samej kratce (~28 km) w czasie ciszy, a więcej niż 2 równoczesne zaniki liczą się jako awaria stacji, nie statku.",
      "Czego to nie dowodzi: cisza w AIS wygląda identycznie przy wyłączonym transponderze i przy zwykłej utracie zasięgu. Kształt luki sam nie mówi nic o zamiarze załogi.",
    ],
    tor: torZEvidence(ev),
  };
}

function d6Detail(a: AlertDto, ev: ReturnType<typeof parseEvidence>): Szczegoly {
  const podmiotNazwa = podmiot(ev, a.entityId);
  const minuty = liczba(ev.duration_minutes);
  const dystans = liczba(ev.min_distance_km);
  const predkosc = liczba(ev.mean_sog_kn);
  const rozrzut = liczba(ev.course_spread_deg);
  const linia = tekst(ev.line_name);
  const rodzajLinii = tekst(ev.line_kind);

  const coZTegoWynika: string[] = [];
  if (linia) {
    coZTegoWynika.push(
      `Statek ${podmiotNazwa} płynął${predkosc !== null ? ` ${predkosc.toFixed(1)} w.` : ""} w pobliżu linii ${linia}` +
        (rodzajLinii ? ` (${rodzajLinii})` : "") +
        (dystans !== null ? `, najbliżej ${dystans.toFixed(2)} km` : "") +
        (minuty !== null ? `, przez ${Math.round(minuty)} minut` : "") +
        ".",
    );
  }
  if (rozrzut !== null) {
    coZTegoWynika.push(`Kurs w tym czasie wahał się o ${rozrzut.toFixed(0)}°, czyli statek nie trzymał prostej linii.`);
  }

  return {
    tytul: podmiotNazwa,
    podtytul: dopisek(ev) || NAZWY.D6,
    coToJest: szczegoly(ev).length ? [`Zmierzone: ${szczegoly(ev).join(", ")}`] : [],
    coZTegoWynika,
    naPodstawie: [
      "Źródło: pozycje AIS (Digitraffic) i trasy kabli/gazociągów (OpenStreetMap).",
      "Reguła D6: statek w paśmie prędkości 1-7 w. (za wolno na normalny tranzyt, za szybko żeby kotwica leżała bezczynnie), bliżej niż 2 km od linii, min. 5 pozycji, min. 15 minut, kurs wahający się o co najmniej 20°.",
      "Wzorzec z incydentów bałtyckich (Eagle S / Estlink 2, Yi Peng 3 / C-Lion 1): wleczona kotwica steruje statkiem tak samo jak ster.",
      "Czego to nie dowodzi: wolniejszy, kluczący kurs blisko kabla ma dziesiątki niewinnych przyczyn (pogoda, ruch, pilot na pokładzie, awaria silnika). Kształt toru sam nie mówi nic o misji ani zamiarze załogi.",
    ],
    tor: torZEvidence(ev),
  };
}

/**
 * D5 - two hulls side by side. The interpretation has to carry the base rate, because the shape of
 * the event does not distinguish a transfer from the ordinary business of a harbour: pilot boats,
 * tugs and bunker barges come alongside for a living. Measured on a day of Danish AIS, 12 451
 * meetings became 11 once anchorages, moored craft and service vessels were removed.
 */
function d5Detail(ev: ReturnType<typeof parseEvidence>): Szczegoly {
  const nazwaA = tekst(ev.name_a) ?? tekst(ev.mmsi_a) ?? "statek A";
  const nazwaB = tekst(ev.name_b) ?? tekst(ev.mmsi_b) ?? "statek B";
  const minuty = liczba(ev.minutes);
  const metry = liczba(ev.min_separation_m);
  const dryf = liczba(ev.drift_km);
  const sog = liczba(ev.mean_sog);

  const coZTegoWynika: string[] = [];
  if (minuty !== null && metry !== null) {
    coZTegoWynika.push(
      `${nazwaA} i ${nazwaB} stały burta w burtę przez ${Math.round(minuty)} minut, najbliżej ${Math.round(metry)} metrów od siebie.`,
    );
  }
  if (dryf !== null) {
    coZTegoWynika.push(
      dryf < 0.1
        ? "Para nie przesunęła się w tym czasie praktycznie wcale - to postój, nie wspólny dryf."
        : `Para przesunęła się o ${dryf.toFixed(1)} km, czyli dryfowała razem.`,
    );
  }
  if (sog !== null) coZTegoWynika.push(`Średnia prędkość w trakcie: ${sog.toFixed(1)} w.`);
  coZTegoWynika.push(
    "Samo spotkanie nie mówi, czy cokolwiek przeładowano - mówi tylko, że dwa kadłuby były przy sobie dość długo, żeby to było możliwe.",
  );

  return {
    tytul: `${nazwaA} + ${nazwaB}`,
    podtytul: NAZWY.D5,
    coToJest: szczegoly(ev).length ? [`Zmierzone: ${szczegoly(ev).join(", ")}`] : [],
    coZTegoWynika,
    naPodstawie: [
      "Źródło: pozycje AIS z Digitraffic (wody fińskie i przyległe).",
      "Reguła D5: dwa statki bliżej niż 800 m, wolniej niż 3 w., przez co najmniej 30 minut, poza kotwicowiskiem wyprowadzonym z ruchu całej doby; oba muszą gdzieś płynąć w ciągu 6 h wokół spotkania, bo przeładunek jest zdarzeniem, a keja stanem.",
      "Czego to nie dowodzi: większość takich spotkań to legalna praca portu - pilotaż, holowanie, bunkrowanie paliwa. Na dobie duńskiego ruchu z 12 451 spotkań zostało 11 po odsianiu kotwicowisk, postojów i jednostek służbowych. Nazwa zaczynająca się od PILOT albo SVITZER jest tu ostrzeżeniem, nie znaleziskiem.",
    ],
    tor: torZEvidence(ev),
  };
}

function genericAlertDetail(a: AlertDto, ev: ReturnType<typeof parseEvidence>): Szczegoly {
  const podmiotNazwa = podmiot(ev, a.entityId);
  const fakty = szczegoly(ev);
  return {
    tytul: podmiotNazwa,
    podtytul: dopisek(ev) || NAZWY[a.detector] || a.detector,
    coToJest: fakty.length ? [`Zmierzone: ${fakty.join(", ")}`] : [],
    coZTegoWynika: [
      `Ten typ alarmu (${NAZWY[a.detector] ?? a.detector}) nie ma jeszcze w tym panelu osobnej interpretacji - pokazane są tylko zmierzone wartości.`,
    ],
    naPodstawie: [
      `Wynik detektora: ${a.score}.`,
      // Pole "note" detektory zapisuja po angielsku dla czytelnika bazy; na ekran idzie polski
      // odpowiednik, zeby panel nie mieszal dwoch jezykow w jednym akapicie.
      "Kandydat do sprawdzenia, nie wyrok.",
      "Czego to nie dowodzi: dopasowanie automatycznej reguły nie jest ustaleniem faktu - wymaga sprawdzenia przez człowieka.",
    ],
    tor: torZEvidence(ev),
  };
}

function alertDetail(a: AlertDto): Szczegoly {
  const ev = parseEvidence(a.evidence);
  const base =
    a.detector === "D1" ? d1Detail(a, ev)
    : a.detector === "D4" ? d4Detail(a, ev)
    : a.detector === "D5" ? d5Detail(ev)
    : a.detector === "D6" ? d6Detail(a, ev)
    : genericAlertDetail(a, ev);
  return {
    ...base,
    coToJest: [
      `Detektor: ${NAZWY[a.detector] ?? a.detector} (${a.detector})`,
      `Zgłoszono: ${godzina(a.startedAt)}`,
      `Wynik: ${a.score}`,
      ...base.coToJest,
    ],
    ocena: ocen(a.detector, ev),
  };
}

/** Top-level dispatch used by the detail panel: one map object in, three-section text out. */
/**
 * AIS ship types, as words.
 *
 * The wire carries a number because that is what AIS carries; turning it into a phrase is a display
 * decision and belongs here, not in the API. Ranges rather than every code: 71 and 74 are both
 * "cargo" to anyone reading this map, and pretending the distinction is meaningful would be dressing
 * up a number we do not actually use.
 */
export function rodzajStatku(kod: string | null | undefined): string | null {
  const n = Number(kod);
  if (!Number.isFinite(n) || n <= 0) return null;
  if (n >= 80 && n <= 89) return "tankowiec";
  if (n >= 70 && n <= 79) return "masowiec / drobnicowiec";
  if (n >= 60 && n <= 69) return "pasażerski";
  if (n === 30) return "kuter rybacki";
  if (n === 35) return "jednostka wojskowa";
  if (n === 50) return "pilotówka";
  if (n === 51) return "ratowniczy";
  if (n === 52) return "holownik";
  if (n >= 53 && n <= 59) return "jednostka portowa";
  if (n >= 40 && n <= 49) return "jednostka szybka";
  return "inna jednostka";
}

/**
 * AIS navigational status, in words.
 *
 * The wire carries whatever the source sends - Digitraffic sends the number, other feeds send the
 * phrase - and "Status nawigacyjny: 5" on a panel is the same raw-code failure this project fixed
 * everywhere else. A code we cannot name is printed as the code, labelled as unknown, rather than
 * silently dropped: an unrecognised status is information too.
 */
const STATUSY: Record<number, string> = {
  0: "w drodze, na silniku",
  1: "na kotwicy",
  2: "bez możliwości manewru",
  3: "ograniczona zdolność manewrowa",
  4: "ograniczony zanurzeniem",
  5: "zacumowany",
  6: "na mieliźnie",
  7: "połów",
  8: "w drodze, pod żaglami",
  14: "sygnał ratunkowy (AIS-SART)",
  15: "nieokreślony",
};

export function statusSlownie(surowy: string | null | undefined): string | null {
  if (surowy === null || surowy === undefined) return null;
  const tekst = String(surowy).trim();
  if (!tekst) return null;
  const n = Number(tekst);
  if (!Number.isFinite(n)) return tekst;           // zrodlo przyslalo juz opis slowny
  return STATUSY[n] ?? `kod ${n} (nieznany)`;
}

const ROZA = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

/** A course in degrees said the way a person says it: "142 stopnie (SE)". */
export function kursSlownie(deg: number | null | undefined): string | null {
  if (deg === null || deg === undefined || !Number.isFinite(deg)) return null;
  const kierunek = ROZA[Math.round(((deg % 360) + 360) % 360 / 45) % 8];
  return `${Math.round(deg)}° (${kierunek})`;
}

function shipDetail(s: LiveShip): Szczegoly {
  const rodzaj = rodzajStatku(s.shipType);
  const wezly = s.sogKt ?? null;
  const kurs = kursSlownie(s.cogDeg);
  const plynie = (wezly ?? 0) >= 0.5;

  const coToJest = [
    `MMSI: ${s.mmsi}`,
    rodzaj ? `Rodzaj (AIS ${s.shipType}): ${rodzaj}` : null,
    wezly !== null ? `Prędkość: ${wezly.toFixed(1)} w.` : null,
    kurs ? `Kurs: ${kurs}` : null,
    statusSlownie(s.navStatus) ? `Status nawigacyjny: ${statusSlownie(s.navStatus)}` : null,
    `Ostatnia pozycja: ${new Date(s.ts).toLocaleString("pl-PL")}`,
  ].filter((x): x is string => x !== null);

  const coZTegoWynika = plynie
    ? [`Statek jest w drodze: ${wezly!.toFixed(1)} w. kursem ${kurs ?? "nieznanym"}. Linia przed dziobem na mapie pokazuje, dokąd dopłynie w dwie minuty, jeśli nic nie zmieni.`]
    : ["Statek nie robi drogi — stoi na kotwicy, przy nabrzeżu albo dryfuje. Sam postój niczego nie znaczy: większość jednostek na tej mapie stoi."];

  return {
    tytul: s.name?.trim() || s.mmsi,
    podtytul: rodzaj ?? "jednostka o nieznanym typie",
    coToJest,
    coZTegoWynika,
    naPodstawie: [
      "Źródło: AIS przez Digitraffic (Fintraffic, licencja CC BY 4.0) — transpondery statków, odbierane przez fińską sieć brzegową.",
      "AIS nadaje sam statek. Nazwa, rodzaj i status nawigacyjny to pola wpisywane przez załogę i bywają nieaktualne albo puste; pozycja, prędkość i kurs idą z odbiornika i są wiarygodniejsze.",
      "Zasięg tej sieci to Zatoka Fińska i Botnicka. Brak statku na mapie nie znaczy, że go nie ma — znaczy, że nikt go stąd nie słyszy.",
    ],
    tor: null,
  };
}

export function zbudujSzczegoly(sel: Selection): Szczegoly {
  if (sel.kind === "aircraft") return aircraftDetail(sel.data);
  if (sel.kind === "ship") return shipDetail(sel.data);
  if (sel.kind === "jamming") return jammingDetail(sel.data);
  if (sel.kind === "infrastruktura") return szczegolyLinii(sel.data);
  return alertDetail(sel.data);
}

/**
 * Classifies a deck.gl picked object into a Selection, the same way MapView's tooltip() tells
 * aircraft from alerts (by the `hex`/`detector` keys), plus jamming cells (`h3`). Exported so the
 * click handler wiring in MapView only needs to call this and zbudujSzczegoly().
 */
export function selectionFromPicked(object: unknown): Selection | null {
  if (!object || typeof object !== "object") return null;
  if ("hex" in object && "lat" in object) return { kind: "aircraft", data: object as LiveAircraft };
  if ("mmsi" in object && "lat" in object) return { kind: "ship", data: object as LiveShip };
  if ("detector" in object) return { kind: "alert", data: object as AlertDto };
  if ("h3" in object) return { kind: "jamming", data: object as JammingDto };
  // Linia infrastruktury: "sciezka" nie wystepuje w zadnym z powyzszych, wiec rozroznia sama.
  if ("sciezka" in object && "rodzaj" in object) return { kind: "infrastruktura", data: object as LiniaInfrastruktury };
  return null;
}
