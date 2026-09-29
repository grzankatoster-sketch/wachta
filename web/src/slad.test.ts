import { describe, expect, it } from "vitest";
import type { ShipTrackPoint } from "./api";
import {
  czasSlownie,
  kmSlownie,
  PROG_POSTOJU_S,
  PROG_PRZERWY_S,
  przeanalizujSlad,
  podstawaSladu,
  skadPlynie,
  stronaSwiata,
  type StanSladu,
} from "./slad";

/**
 * Fixtures are shaped like the real feed, not like round numbers: the ingest poll lands every 150 s
 * (median of 49 813 measured intervals), so that is the cadence used here, and the gap case is the
 * real one observed on MMSI 265623130 (SEKTOR) on 2026-09-29 - 2211 s of silence between
 * 59.6649/19.0227 and 59.4652/18.9167, 22.3 km apart at 21 knots.
 */
const KROK_S = 150;

function tor(punkty: Array<Partial<ShipTrackPoint> & { po: number }>): ShipTrackPoint[] {
  const t0 = Date.parse("2026-09-29T05:00:00Z");
  return punkty.map((p) => ({
    ts: new Date(t0 + p.po * 1000).toISOString(),
    lat: p.lat ?? 59.0,
    lon: p.lon ?? 19.0,
    sogKt: p.sogKt ?? 12,
    cogDeg: p.cogDeg ?? 90,
  }));
}

/** Płynie na wschód: kolejne pozycje mają rosnący lon. */
const naWschod = (n: number, krok = KROK_S): ShipTrackPoint[] =>
  tor(Array.from({ length: n }, (_, i) => ({ po: i * krok, lat: 59.0, lon: 19.0 + i * 0.05 })));

const gotowy = (punkty: ShipTrackPoint[]): StanSladu => ({
  stan: "gotowy",
  slad: przeanalizujSlad("265623130", punkty),
});

describe("ślad statku — ciągłość", () => {
  it("normalna kadencja nie jest przerwą, nawet tuż pod progiem", () => {
    // 599 s to jeszcze zwykly odstep (99. percentyl zmierzony na zywych danych = 598,6 s),
    // 601 s to juz cisza. Prog musi lezec dokladnie miedzy tymi dwoma, bo inaczej albo kazdy
    // statek ma "przerwy", albo nie ma ich nikt.
    expect(przeanalizujSlad("1", naWschod(4, PROG_PRZERWY_S - 1)).przerwy).toHaveLength(0);
    expect(przeanalizujSlad("1", naWschod(4, PROG_PRZERWY_S + 1)).przerwy).toHaveLength(3);
  });

  it("przerwa dzieli ślad na dwa odcinki i NIE jest zasypywana linią", () => {
    // To jest cala rzecz: polilinia laczy swoje wierzcholki bez wzgledu na to, co bylo miedzy nimi,
    // wiec 37 minut ciszy zamienialoby sie w pewna prosta przez 22 km wody, ktorej nikt nie
    // sluchal. Dokladnie to wykrywa detektor D4.
    const punkty = tor([
      { po: 0, lat: 59.7191, lon: 19.0692, sogKt: 21 },
      { po: 150, lat: 59.6649, lon: 19.0227, sogKt: 21 },
      // 2211 s ciszy - prawdziwa luka z MMSI 265623130
      { po: 150 + 2211, lat: 59.4652, lon: 18.9167, sogKt: 21.1 },
      { po: 150 + 2211 + 150, lat: 59.4480, lon: 18.8707, sogKt: 21.6 },
    ]);
    const s = przeanalizujSlad("265623130", punkty);

    expect(s.odcinki).toHaveLength(2);
    expect(s.odcinki[0].punkty).toHaveLength(2);
    expect(s.odcinki[1].punkty).toHaveLength(2);
    expect(s.przerwy).toHaveLength(1);
    expect(s.przerwy[0].sekundy).toBe(2211);
    expect(s.przerwy[0].km).toBeGreaterThan(20);
    expect(s.przerwy[0].km).toBeLessThan(25);

    // Zaden odcinek nie moze zawierac obu brzegow luki.
    for (const o of s.odcinki) {
      const lats = o.punkty.map((p) => p.lat);
      expect(Math.max(...lats) - Math.min(...lats)).toBeLessThan(0.1);
    }

    // Droga przebyta liczy tylko to, co widziano: 22 km luki nie wchodzi do sumy.
    expect(s.przebytaKm).toBeLessThan(12);
    expect(s.wLiniiKm).toBeGreaterThan(30);
  });

  it("opis przerwy mówi ile ciszy i ile kilometrów, i że mapa nie rysuje tam linii", () => {
    const punkty = tor([
      { po: 0, lat: 59.7191, lon: 19.0692, sogKt: 21 },
      { po: 2400, lat: 59.4652, lon: 18.9167, sogKt: 21 },
      { po: 2550, lat: 59.4480, lon: 18.8707, sogKt: 21 },
    ]);
    const zdania = skadPlynie(gotowy(punkty)).join(" ");
    expect(zdania).toContain("przerwa");
    expect(zdania).toContain("40 min");
    expect(zdania).toContain("dziurę");
    expect(zdania).not.toMatch(/\bnull\b|NaN|undefined/);
  });

  it("ciągły ślad mówi wprost, że przerw nie ma", () => {
    expect(skadPlynie(gotowy(naWschod(10))).join(" ")).toContain("Ślad jest ciągły");
  });
});

describe("ślad statku — skąd przypłynął", () => {
  it("nazywa kierunek, z którego statek nadszedł, a nie ten, w którym płynie", () => {
    // Plynie na wschod, wiec PRZYPLYNAL z zachodu. Odwrocenie namiaru to najlatwiejszy blad
    // w calym tym pliku i wyglada w panelu zupelnie wiarygodnie.
    expect(skadPlynie(gotowy(naWschod(8))).join(" ")).toContain("z kierunku zachodu");
    const naPolnoc = tor(Array.from({ length: 8 }, (_, i) => ({ po: i * KROK_S, lat: 59.0 + i * 0.05, lon: 19.0 })));
    expect(skadPlynie(gotowy(naPolnoc)).join(" ")).toContain("z kierunku południa");
  });

  it("podaje czas, drogę w linii prostej i drogę po śladzie", () => {
    const zdania = skadPlynie(gotowy(naWschod(8))).join(" ");
    expect(zdania).toContain("18 min");           // 7 x 150 s = 1050 s
    expect(zdania).toMatch(/\d+ km w linii prostej/);
    expect(zdania).toContain("po zaobserwowanym śladzie");
  });

  it("róża wiatrów nazywa strony po polsku, bez kodów", () => {
    expect(stronaSwiata(0)).toBe("północy");
    expect(stronaSwiata(225)).toBe("południowego zachodu");
    expect(stronaSwiata(359)).toBe("północy");
  });
});

describe("ślad statku — brak danych nie wygląda jak błąd", () => {
  it("zero pozycji to zdanie o zasięgu, nie komunikat o awarii", () => {
    const zdania = skadPlynie(gotowy([]));
    expect(zdania.join(" ")).toContain("To nie błąd");
    expect(zdania.join(" ")).not.toMatch(/błąd\b(?!:)|awari|nie udało/i);
    expect(przeanalizujSlad("1", []).odcinki).toHaveLength(0);
  });

  it("jedna pozycja to za mało na trasę i tak jest to powiedziane", () => {
    const zdania = skadPlynie(gotowy(naWschod(1))).join(" ");
    expect(zdania).toContain("tylko jedna pozycja");
    expect(zdania).toContain("za mało");
  });

  it("nieudane pobranie jest odróżnione od pustej historii", () => {
    const zdania = skadPlynie({ stan: "blad", powod: "HTTP 500" }).join(" ");
    expect(zdania).toContain("Nie udało się pobrać trasy");
    expect(zdania).toContain("HTTP 500");
  });

  it("stojąca jednostka nie dostaje trasy ani zdania o kierunku", () => {
    // 56% zywych tras (496 z 881) nie oddala sie od pierwszej pozycji nawet o 50 m. Dla nich
    // "przyplynal z polnocy" bylby wymyslonym faktem o szumie GPS przy kei.
    const przyKei = tor(Array.from({ length: 20 }, (_, i) => ({
      po: i * KROK_S, lat: 59.7191 + i * 0.00002, lon: 19.0692, sogKt: 0,
    })));
    const s = przeanalizujSlad("1", przyKei);
    expect(s.nieruchomy).toBe(true);
    expect(s.zNamiaru).toBeNull();
    const zdania = skadPlynie(gotowy(przyKei)).join(" ");
    expect(zdania).toContain("nie ruszyła się z miejsca");
    expect(zdania).not.toContain("z kierunku");
  });

  it("stojącej jednostce panel nie obiecuje znaków, których mapa nie rysuje", () => {
    // Zlapane na zywym panelu (MMSI 255804570, 2026-09-29): tankowiec na kotwicy, 77 pozycji w
    // promieniu 37 m i cztery przerwy w nadawaniu dostal tekst "Mapa zostawia tam dziurę i
    // zaznacza oba końce kółkami" - a dla stojacej jednostki sladLayers nie rysuje niczego.
    // Do tego 27 minut ciszy przy kei nie jest znaleziskiem: D4 liczy cisze statku, ktory PLYNAL.
    const przyKei = tor([
      ...Array.from({ length: 5 }, (_, i) => ({ po: i * KROK_S, lat: 59.7191, lon: 19.0692, sogKt: 0 })),
      { po: 5 * KROK_S + 1700, lat: 59.7192, lon: 19.0692, sogKt: 0 },
      { po: 6 * KROK_S + 1700, lat: 59.7192, lon: 19.0692, sogKt: 0 },
    ]);
    const s = przeanalizujSlad("255804570", przyKei);
    expect(s.nieruchomy).toBe(true);
    expect(s.przerwy.length).toBe(1);

    const zdania = skadPlynie(gotowy(przyKei)).join(" ");
    expect(zdania).toContain("cisza stojącej jednostki nie mówi nic");
    expect(zdania).not.toContain("kółkami");
    expect(zdania).not.toContain("dziurę");
    expect(zdania).not.toContain("Po drodze");
    expect(zdania).not.toContain("Ślad jest ciągły");
  });
});

describe("ślad statku — postoje", () => {
  it("krótkie zwolnienie to nie postój, długie tak", () => {
    // Histogram 724 zwolnien wewnatrz ruchomych tras: 248 konczy sie przed 2,5 min, a od 10 min
    // rozklad jest plaski az za 90 min. Prog ma odciac ten pierwszy garb.
    const zrobTor = (ileWolnych: number) =>
      tor([
        ...Array.from({ length: 3 }, (_, i) => ({ po: i * KROK_S, lon: 19.0 + i * 0.05, sogKt: 12 })),
        ...Array.from({ length: ileWolnych }, (_, i) => ({ po: (3 + i) * KROK_S, lon: 19.15, sogKt: 0.1 })),
        ...Array.from({ length: 3 }, (_, i) => ({ po: (3 + ileWolnych + i) * KROK_S, lon: 19.2 + i * 0.05, sogKt: 12 })),
      ]);
    // 3 pozycje po 150 s = 300 s ciszy w ruchu, ponizej progu 600 s
    expect(przeanalizujSlad("1", zrobTor(3)).postoje).toHaveLength(0);
    // 6 pozycji = 750 s, powyzej progu
    const dlugi = przeanalizujSlad("1", zrobTor(6));
    expect(dlugi.postoje).toHaveLength(1);
    expect(dlugi.postoje[0].sekundy).toBeGreaterThanOrEqual(PROG_POSTOJU_S);
  });

  it("postój jest opisany w panelu po polsku", () => {
    const z = tor([
      ...Array.from({ length: 3 }, (_, i) => ({ po: i * KROK_S, lon: 19.0 + i * 0.05, sogKt: 12 })),
      ...Array.from({ length: 8 }, (_, i) => ({ po: (3 + i) * KROK_S, lon: 19.15, sogKt: 0 })),
      ...Array.from({ length: 3 }, (_, i) => ({ po: (11 + i) * KROK_S, lon: 19.2 + i * 0.05, sogKt: 12 })),
    ]);
    expect(skadPlynie(gotowy(z)).join(" ")).toContain("najdłuższy postój trwał");
  });
});

describe("ślad statku — dane, którym nie można ufać", () => {
  it("wiersz bez sensownej pozycji jest wyrzucany, a nie rysowany", () => {
    // Jedna szerokosc NaN wystarczy, zeby polilinia poszla w Zatoke Gwinejska - i zeby to
    // wygladalo jak znalezisko.
    const brudny: ShipTrackPoint[] = [
      { ts: "2026-09-29T05:00:00Z", lat: 59.0, lon: 19.0, sogKt: 12, cogDeg: 90 },
      { ts: "2026-09-29T05:02:30Z", lat: Number.NaN, lon: 19.05, sogKt: 12, cogDeg: 90 },
      { ts: "nie-data", lat: 59.0, lon: 19.1, sogKt: 12, cogDeg: 90 },
      { ts: "2026-09-29T05:05:00Z", lat: 999, lon: 19.15, sogKt: 12, cogDeg: 90 },
      { ts: "2026-09-29T05:07:30Z", lat: 59.0, lon: 19.2, sogKt: 12, cogDeg: 90 },
    ];
    const s = przeanalizujSlad("1", brudny);
    expect(s.punkty).toHaveLength(2);
    expect(s.punkty.every((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon))).toBe(true);
  });

  it("pozycje przychodzą posortowane po czasie nawet gdy wpadły nie po kolei", () => {
    const s = przeanalizujSlad("1", [
      { ts: "2026-09-29T05:05:00Z", lat: 59.0, lon: 19.1, sogKt: 12, cogDeg: 90 },
      { ts: "2026-09-29T05:00:00Z", lat: 59.0, lon: 19.0, sogKt: 12, cogDeg: 90 },
    ]);
    expect(s.punkty[0].ts).toBeLessThan(s.punkty[1].ts);
  });
});

describe("ślad statku — teksty dla człowieka", () => {
  it("czas i dystans są po polsku, bez surowych sekund i metrów po przecinku", () => {
    expect(czasSlownie(45)).toBe("45 s");
    expect(czasSlownie(2211)).toBe("37 min");
    expect(czasSlownie(8640)).toBe("2 h 24 min");
    expect(czasSlownie(7200)).toBe("2 h");
    expect(kmSlownie(0.2)).toBe("200 m");
    expect(kmSlownie(3.14)).toBe("3,1 km");
    expect(kmSlownie(45.6)).toBe("46 km");
  });

  it("podstawa wypisuje zmierzone progi i to, czego przerwa nie dowodzi", () => {
    const punkty = tor([
      { po: 0, lat: 59.7191, lon: 19.0692, sogKt: 21 },
      { po: 2400, lat: 59.4652, lon: 18.9167, sogKt: 21 },
    ]);
    const wiersze = podstawaSladu(gotowy(punkty)).join(" ");
    expect(wiersze).toContain("10 min");
    expect(wiersze).toContain("mediana 150 s");
    expect(wiersze).toContain("wyłączony transponder i zwykła utrata zasięgu wyglądają w danych identycznie");
    // Bez sladu nie ma sekcji o progach - panel nie tlumaczy regul, ktorych nie zastosowal.
    expect(podstawaSladu({ stan: "nic" })).toHaveLength(0);
    expect(podstawaSladu(gotowy([]))).toHaveLength(0);
  });
});
