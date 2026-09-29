import { useCallback, useEffect, useRef, useState } from "react";
import {
  nadSzuflada, OKNO_DOMYSLNE_H, pobierzKonflikty, pobierzWersje, pobierzZdarzenia, ZOOM_ZDARZENIA,
  type KonfliktDto, type ZdarzenieDto,
} from "./konflikty";
import { zdarzeniaLayers } from "./layers/zdarzenia";
import type { WersjeDto } from "./wersje";

/**
 * State of the "pick a war" view: three nested selections, each with its own fetch.
 *
 * Every level keeps "loading", "loaded and empty" and "the request failed" apart, exactly the way
 * useSladStatku does, and for the same reason: an endpoint that is not deployed yet and a conflict
 * that genuinely had a quiet night look identical once you collapse them into an optional value.
 * The versions endpoint in particular is the last thing to ship, so a front end that reads its
 * absence as "no articles took sides" would put a false statement on screen the whole time.
 */
export type Pobranie<T> =
  | { stan: "ladowanie" }
  | { stan: "gotowe"; dane: T }
  | { stan: "blad"; powod: string };

export interface StanWojny {
  otwarty: boolean;
  przelacz: () => void;
  konflikty: Pobranie<KonfliktDto[]>;
  wybranyKonflikt: KonfliktDto | null;
  wybierzKonflikt: (k: KonfliktDto) => void;
  godziny: number;
  ustawGodziny: (h: number) => void;
  zdarzenia: Pobranie<ZdarzenieDto[]>;
  wybraneZdarzenie: ZdarzenieDto | null;
  wybierzZdarzenie: (z: ZdarzenieDto) => void;
  /** Handles a click on the map; true when the picked object was one of this view's events. */
  klikMapy: (obiekt: unknown) => boolean;
  wersje: Pobranie<WersjeDto | null>;
  /** deck.gl layers for whatever is currently selected; empty until a conflict is chosen. */
  warstwy: ReturnType<typeof zdarzeniaLayers>;
}

function powod(e: unknown): string {
  return e instanceof Error ? e.message : "nieznany błąd";
}

export function uzyjWojny(naMape: (lon: number, lat: number, zoom: number) => void): StanWojny {
  const [otwarty, setOtwarty] = useState(false);
  const [konflikty, setKonflikty] = useState<Pobranie<KonfliktDto[]>>({ stan: "ladowanie" });
  const [wybranyKonflikt, setWybranyKonflikt] = useState<KonfliktDto | null>(null);
  const [godziny, setGodziny] = useState(OKNO_DOMYSLNE_H);
  const [zdarzenia, setZdarzenia] = useState<Pobranie<ZdarzenieDto[]>>({ stan: "gotowe", dane: [] });
  const [wybraneZdarzenie, setWybraneZdarzenie] = useState<ZdarzenieDto | null>(null);
  const [wersje, setWersje] = useState<Pobranie<WersjeDto | null>>({ stan: "gotowe", dane: null });

  // The centring callback is rebuilt on every render of App; keeping it in a ref stops it from
  // re-triggering the fetches below, which would loop the whole view.
  const naMapeRef = useRef(naMape);
  naMapeRef.current = naMape;

  // Conflicts are fetched once the drawer is first opened, not on mount: the endpoint is a join
  // over the whole events table and nobody who never opens this view should pay for it.
  useEffect(() => {
    if (!otwarty || konflikty.stan !== "ladowanie") return;
    let aktualny = true;
    pobierzKonflikty().then(
      (dane) => aktualny && setKonflikty({ stan: "gotowe", dane }),
      (e: unknown) => aktualny && setKonflikty({ stan: "blad", powod: powod(e) }),
    );
    return () => {
      aktualny = false;
    };
  }, [otwarty, konflikty.stan]);

  const id = wybranyKonflikt?.id ?? null;
  useEffect(() => {
    if (id === null) {
      setZdarzenia({ stan: "gotowe", dane: [] });
      return;
    }
    let aktualny = true;
    setZdarzenia({ stan: "ladowanie" });
    pobierzZdarzenia(id, godziny).then(
      (dane) => aktualny && setZdarzenia({ stan: "gotowe", dane }),
      (e: unknown) => aktualny && setZdarzenia({ stan: "blad", powod: powod(e) }),
    );
    return () => {
      aktualny = false;
    };
  }, [id, godziny]);

  const eventId = wybraneZdarzenie?.id ?? null;
  useEffect(() => {
    if (eventId === null) {
      setWersje({ stan: "gotowe", dane: null });
      return;
    }
    let aktualny = true;
    setWersje({ stan: "ladowanie" });
    pobierzWersje(eventId).then(
      // An event whose articles all came from unassigned outlets has no sides at all. That is an
      // answer, not a failure, so it travels as `null` data rather than as an error.
      (dane) => aktualny && setWersje({ stan: "gotowe", dane: dane.sides.length > 0 ? dane : null }),
      (e: unknown) => aktualny && setWersje({ stan: "blad", powod: powod(e) }),
    );
    return () => {
      aktualny = false;
    };
  }, [eventId]);

  const wybierzKonflikt = useCallback((k: KonfliktDto) => {
    setWybranyKonflikt(k);
    // Switching wars must drop the open event: keeping it would leave a versions panel about a
    // strike in Donbas next to a list of events from another conflict entirely.
    setWybraneZdarzenie(null);
  }, []);

  const wybierzZdarzenie = useCallback((z: ZdarzenieDto) => {
    setWybraneZdarzenie(z);
    // Ile ekranu zaslania szuflada - mierzone z niej samej, zeby ta liczba nie mogla rozjechac sie
    // z arkuszem stylow. Brak elementu (np. w tescie) znaczy zero zaslony, czyli zwykle wysrodkowanie.
    const szuflada = document.querySelector(".wojna")?.getBoundingClientRect();
    const zaslona = szuflada ? Math.max(0, window.innerHeight - szuflada.top) : 0;
    naMapeRef.current(z.lon, nadSzuflada(z.lat, ZOOM_ZDARZENIA, zaslona), ZOOM_ZDARZENIA);
  }, []);

  const lista = zdarzenia.stan === "gotowe" ? zdarzenia.dane : [];

  // Klikniecie w krazek na mapie ma otwierac to samo zestawienie co klikniecie w liscie. Rozpoznajemy
  // zdarzenie po TOZSAMOSCI z wczytana lista, a nie po ksztalcie obiektu: deck.gl oddaje ten sam
  // obiekt, ktory dostal, a zgadywanie po polach ("ma kind i sources") zaczelo by lapac cudze
  // warstwy w dniu, w ktorym ktos doda pole o tej samej nazwie.
  const klikMapy = (obiekt: unknown): boolean => {
    const z = lista.find((k) => k === obiekt);
    if (!z) return false;
    setWybraneZdarzenie(z);
    return true;
  };

  return {
    otwarty,
    przelacz: () => setOtwarty((o) => !o),
    konflikty,
    wybranyKonflikt,
    wybierzKonflikt,
    godziny,
    ustawGodziny: setGodziny,
    zdarzenia,
    wybraneZdarzenie,
    wybierzZdarzenie,
    klikMapy,
    wersje,
    warstwy: otwarty ? zdarzeniaLayers(lista, wybraneZdarzenie?.id ?? null) : [],
  };
}
