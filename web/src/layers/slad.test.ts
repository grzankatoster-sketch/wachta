import { describe, expect, it } from "vitest";
import type { Layer } from "@deck.gl/core";
import type { ShipTrackPoint } from "../api";
import { przeanalizujSlad, type StanSladu } from "../slad";
import { sladLayers } from "./slad";

const t0 = Date.parse("2026-09-29T05:00:00Z");
const pkt = (po: number, lat: number, lon: number, sogKt = 21): ShipTrackPoint => ({
  ts: new Date(t0 + po * 1000).toISOString(), lat, lon, sogKt, cogDeg: 215,
});

const gotowy = (punkty: ShipTrackPoint[]): StanSladu => ({
  stan: "gotowy", slad: przeanalizujSlad("265623130", punkty),
});

const warstwa = (w: Layer[], id: string) => w.find((l) => l.id === id);
const ile = (w: Layer[], id: string) => (warstwa(w, id)!.props.data as unknown[]).length;

/** Prawdziwa luka z MMSI 265623130 (SEKTOR), 2026-09-29: 2211 s ciszy, 22 km miedzy koncami. */
const zLuka = [
  pkt(0, 59.7191, 19.0692),
  pkt(150, 59.6649, 19.0227),
  pkt(2361, 59.4652, 18.9167),
  pkt(2511, 59.4480, 18.8707),
];

describe("warstwy śladu", () => {
  it("luka zostaje luką: żaden odcinek linii nie łączy jej dwóch końców", () => {
    // Gdyby warstwa dostala jedna liste punktow zamiast odcinkow, deck.gl narysowalby przez
    // przerwe prosta - i 22 km wody, ktorej nikt nie sluchal, wygladaloby jak zmierzony kurs.
    const w = sladLayers(gotowy(zLuka));
    const kreski = warstwa(w, "ship-track")!.props.data as Array<{ od: [number, number]; do_: [number, number] }>;
    expect(kreski).toHaveLength(2);
    for (const k of kreski) {
      expect(Math.abs(k.do_[1] - k.od[1])).toBeLessThan(0.1);
    }
  });

  it("oba brzegi przerwy są zaznaczone, a sama przerwa podpisana", () => {
    const w = sladLayers(gotowy(zLuka));
    expect(ile(w, "ship-track-gaps")).toBe(2);
    expect(ile(w, "ship-track-gap-labels")).toBe(1);
    const tekst = (warstwa(w, "ship-track-gap-labels")!.props as unknown as {
      getText: (p: unknown) => string;
    }).getText((warstwa(w, "ship-track-gap-labels")!.props.data as unknown[])[0]);
    expect(tekst).toContain("cisza 37 min");
    expect(tekst).toContain("km");
  });

  it("przy wielu przerwach podpisana jest najdłuższa, a napis mówi ile ich jest", () => {
    // Cztery plakietki w jednym miejscu zlozyly sie na zrzucie w nieczytelny stos (MMSI
    // 265649360). Kolka zostaja przy kazdej przerwie, wiec z mapy nadal widac, ile ich jest.
    const trzyLuki = [
      pkt(0, 59.9, 19.0), pkt(150, 59.85, 19.0),
      pkt(1000, 59.7, 19.0), pkt(1150, 59.65, 19.0),
      pkt(4000, 59.4, 19.0), pkt(4150, 59.35, 19.0),
      pkt(5200, 59.2, 19.0), pkt(5350, 59.15, 19.0),
    ];
    const w = sladLayers(gotowy(trzyLuki));
    expect(ile(w, "ship-track-gaps")).toBe(6);
    expect(ile(w, "ship-track-gap-labels")).toBe(1);
    const props = warstwa(w, "ship-track-gap-labels")!.props as unknown as {
      getText: (p: unknown) => string; data: unknown[];
    };
    const tekst = props.getText(props.data[0]);
    expect(tekst).toContain("najdłuższa z 3 przerw");
    expect(tekst).toContain("48 min");           // 2850 s - najdluzsza z trzech
  });

  it("linia grubieje ku teraźniejszości, więc cienki koniec to przeszłość", () => {
    // Zanik przezroczystoscia byl pierwszym pomyslem i pomiar go odrzucil: ten fiolet zlozony
    // z podkladem morza ma 1,71:1 przy alfa 100, czyli ponizej progu 3:1 z WCAG 1.4.11.
    // Grubosc niesie wiek przy stalym, pelnym kontrascie.
    const w = sladLayers(gotowy([pkt(0, 59.7, 19.0), pkt(150, 59.6, 19.0), pkt(300, 59.5, 19.0)]));
    const props = warstwa(w, "ship-track")!.props as unknown as {
      getWidth: (k: unknown) => number;
      data: Array<{ udzial: number }>;
    };
    const szerokosci = props.data.map(props.getWidth);
    expect(szerokosci[0]).toBeLessThan(szerokosci[1]);
    expect(szerokosci[0]).toBeGreaterThanOrEqual(1.4);
    expect(szerokosci[szerokosci.length - 1]).toBeCloseTo(3.2, 5);
  });

  it("podpisy umieją polskie znaki", () => {
    // Zlapane na zrzucie 2026-09-29: domyslny atlas TextLayer to ASCII 32-127, wiec "stąd"
    // renderowalo sie jako "st d", a "·" jako pusty prostokat. Tekst po polsku jest w tym
    // projekcie wymogiem, wiec warstwa, ktora go nie uniesie, jest zepsuta.
    const w = sladLayers(gotowy(zLuka));
    for (const id of ["ship-track-start-label", "ship-track-gap-labels"]) {
      expect((warstwa(w, id)!.props as unknown as { characterSet: string }).characterSet).toBe("auto");
    }
  });

  it("ślad nie łapie kliknięć, bo leży pod statkami", () => {
    for (const l of sladLayers(gotowy(zLuka))) expect(l.props.pickable).toBe(false);
  });

  it("stan inny niż gotowy nie stawia na mapie nic", () => {
    // Ladowanie, blad i brak zaznaczenia maja swoje zdania w panelu. Znak na mapie, ktory
    // znaczy "czekam", to znak, ktory czytelnik musi odgadnac.
    expect(sladLayers({ stan: "nic" })).toHaveLength(0);
    expect(sladLayers({ stan: "ladowanie", mmsi: "1" })).toHaveLength(0);
    expect(sladLayers({ stan: "blad", powod: "HTTP 500" })).toHaveLength(0);
    expect(sladLayers(gotowy([]))).toHaveLength(0);
    expect(sladLayers(gotowy([pkt(0, 59.7, 19.0)]))).toHaveLength(0);
  });

  it("jednostka stojąca przy kei nie dostaje kreski udającej trasę", () => {
    const przyKei = Array.from({ length: 20 }, (_, i) => pkt(i * 150, 59.7191 + i * 0.00002, 19.0692, 0));
    expect(sladLayers(gotowy(przyKei))).toHaveLength(0);
  });

  it("postój dostaje kropkę, a początek śladu pierścień z podpisem", () => {
    const zPostojem = [
      ...Array.from({ length: 3 }, (_, i) => pkt(i * 150, 59.7 - i * 0.05, 19.0)),
      ...Array.from({ length: 8 }, (_, i) => pkt((3 + i) * 150, 59.55, 19.0, 0)),
      ...Array.from({ length: 3 }, (_, i) => pkt((11 + i) * 150, 59.5 - i * 0.05, 19.0)),
    ];
    const w = sladLayers(gotowy(zPostojem));
    expect(ile(w, "ship-track-stops")).toBe(1);
    expect(ile(w, "ship-track-start")).toBe(1);
    const podpis = (warstwa(w, "ship-track-start-label")!.props as unknown as {
      getText: (p: unknown) => string;
    }).getText(null);
    expect(podpis).toContain("stąd");
    expect(podpis).toContain("33 min");           // 13 x 150 s = 1950 s
  });
});
