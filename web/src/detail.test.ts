import { describe, expect, it } from "vitest";
import type { AlertDto, JammingDto, LiveAircraft } from "./api";
import { poziomZaklocen, selectionFromPicked, wilsonLowerBound, zbudujSzczegoly } from "./detail";

/**
 * Nikt nie klika w mape, zeby zobaczyc JSON - te testy pilnuja trzech rzeczy: ze kazdy typ obiektu
 * dostaje interpretacje zdaniami (nie tylko surowe pola), ze tor zaniku/powrotu wychodzi z evidence
 * tam gdzie detektor go zapisal, i ze nigdzie nie wycieka surowy JSON ani znak zapytania.
 */

const AIRCRAFT: LiveAircraft = {
  hex: "4ca7b3", flight: "FORTE10", typeCode: "F16", isMilitary: true,
  lat: 55.1, lon: 21.2, altBaroFt: 32000, onGround: false,
  gsKt: 420, trackDeg: 90, ts: "2026-09-28T10:00:00Z",
};

function alertOf(detector: string, evidence: object, extra: Partial<AlertDto> = {}): AlertDto {
  return {
    id: 1, detector, entityId: "265762770", startedAt: "2026-09-28T09:00:00Z",
    lat: 55.0, lon: 21.0, score: 0.82, evidence: JSON.stringify(evidence), state: "open",
    ...extra,
  };
}

const D4_EVIDENCE = {
  mmsi: "265762770", name: "DUX", duration_minutes: 78.8, shift_km: 5.0,
  listeners: 20, simultaneous: 0, implied_kt: 2.1, verdict: "cisza przy dzialajacym odbiorze",
  motion: "plynal w czasie ciszy",
  vanish_lat: 55.0, vanish_lon: 21.0, resume_lat: 55.05, resume_lon: 21.08,
};

const D1_EVIDENCE = {
  flight: "FORTE10", type_code: "F16", gap_minutes: 12, cell_reports: 340, nearest_airport_km: 120.4,
};

const D6_EVIDENCE = {
  mmsi: "230007910", name: "SVEA", min_distance_km: 0.42, line_name: "Nord Stream 1",
  line_kind: "gazociag", duration_minutes: 40, mean_sog_kn: 3.2, course_spread_deg: 55,
};

const JAMMING: JammingDto = { h3: "841f24bffffffff", nAircraft: 274, nDegraded: 11 };

function calyTekst(sz: ReturnType<typeof zbudujSzczegoly>): string {
  return [...sz.coToJest, ...sz.coZTegoWynika, ...sz.naPodstawie].join(" ");
}

describe("panel szczegolow - brak surowego JSON-a", () => {
  it("samolot, alarmy D1/D4/D6 i heksagon zakłóceń nie pokazują JSON-a ani znaku zapytania", () => {
    const przypadki = [
      { kind: "aircraft" as const, data: AIRCRAFT },
      { kind: "alert" as const, data: alertOf("D1", D1_EVIDENCE) },
      { kind: "alert" as const, data: alertOf("D4", D4_EVIDENCE) },
      { kind: "alert" as const, data: alertOf("D6", D6_EVIDENCE) },
      { kind: "jamming" as const, data: JAMMING },
    ];
    for (const sel of przypadki) {
      const tekst = calyTekst(zbudujSzczegoly(sel));
      expect(tekst, sel.kind).not.toContain("{");
      expect(tekst, sel.kind).not.toContain("}");
      expect(tekst, sel.kind).not.toMatch(/\s\?\s|\s\?$/);
    }
  });
});

describe("samolot", () => {
  it("pokazuje dane lotu, nie tylko surowy hex", () => {
    const sz = zbudujSzczegoly({ kind: "aircraft", data: AIRCRAFT });
    expect(sz.tytul).toBe("FORTE10");
    expect(sz.coToJest.join(" ")).toContain("32000 ft");
    expect(sz.coZTegoWynika.join(" ")).toMatch(/leci/);
    expect(sz.naPodstawie.join(" ")).toMatch(/nie dowodzi/);
  });
});

describe("alarm D4 - statek zamilkl w ruchu", () => {
  it("zdanie interpretacji zawiera minuty, kilometry i liczbe swiadkow - jak w wymaganiu", () => {
    const sz = zbudujSzczegoly({ kind: "alert", data: alertOf("D4", D4_EVIDENCE) });
    const zdanie = sz.coZTegoWynika.join(" ");
    expect(zdanie).toContain("79 minut");
    expect(zdanie).toContain("5.0 km dalej");
    expect(zdanie).toContain("20 innych statków");
  });

  it("tor wychodzi z punktow zaniku i powrotu w evidence", () => {
    const sz = zbudujSzczegoly({ kind: "alert", data: alertOf("D4", D4_EVIDENCE) });
    expect(sz.tor).toEqual({ zanik: { lat: 55.0, lon: 21.0 }, powrot: { lat: 55.05, lon: 21.08 } });
  });

  it("bez punktow zaniku/powrotu w evidence tor jest null, a nie polowicznym obiektem", () => {
    const sz = zbudujSzczegoly({ kind: "alert", data: alertOf("D4", { mmsi: "1", shift_km: 2 }) });
    expect(sz.tor).toBeNull();
  });

  it("ostrzega, ze cisza wyglada tak samo przy awarii jak przy wylaczeniu", () => {
    const sz = zbudujSzczegoly({ kind: "alert", data: alertOf("D4", D4_EVIDENCE) });
    expect(sz.naPodstawie.join(" ")).toMatch(/wygląda.*identycznie/);
  });
});

describe("alarm D1 - zgaszony transponder", () => {
  it("mowi o lotnisku i progach, nie tylko o luce czasowej", () => {
    const sz = zbudujSzczegoly({ kind: "alert", data: alertOf("D1", D1_EVIDENCE) });
    expect(sz.coZTegoWynika.join(" ")).toContain("12 minut");
    expect(sz.naPodstawie.join(" ")).toMatch(/3000 ft/);
  });
});

describe("alarm D6 - wleczenie kotwicy", () => {
  it("nazywa linie i mowi o rozrzucie kursu", () => {
    const sz = zbudujSzczegoly({ kind: "alert", data: alertOf("D6", D6_EVIDENCE) });
    expect(sz.coZTegoWynika.join(" ")).toContain("Nord Stream 1");
    expect(sz.coZTegoWynika.join(" ")).toContain("55°");
    expect(sz.naPodstawie.join(" ")).toMatch(/nie mówi nic o misji/);
  });
});

describe("nieznany detektor", () => {
  it("nie wywala sie i nie pokazuje pustki - pokazuje to, co szczegoly() umie przeczytac", () => {
    const sz = zbudujSzczegoly({ kind: "alert", data: alertOf("D8", { listeners: 4 }) });
    expect(sz.tytul).toBeTruthy();
    expect(sz.coZTegoWynika.length).toBeGreaterThan(0);
    expect(sz.naPodstawie.join(" ")).toMatch(/nie jest ustaleniem faktu|Kandydat do sprawdzenia/);
  });
});

describe("heksagon zakłóceń GPS", () => {
  it("wilsonLowerBound odtwarza formule detektora (wachta_detectors/jamming.py)", () => {
    // Wartosc z docstringu detektora: hotspot bałtycki mial 11 komorek 'high' na duzej probie.
    expect(wilsonLowerBound(0, 0)).toBe(0);
    expect(wilsonLowerBound(10, 10)).toBeGreaterThan(0.6);
    expect(wilsonLowerBound(1, 5)).toBeLessThan(0.2); // mala proba nie ma prawa wygladac na "wysoki"
  });

  it("klasyfikacja trzyma progi z detektora: 10% wysoki, 2% sredni", () => {
    expect(poziomZaklocen(0.15)).toBe("high");
    expect(poziomZaklocen(0.05)).toBe("medium");
    expect(poziomZaklocen(0.001)).toBe("low");
  });

  it("panel pokazuje liczby uzyte do klasyfikacji, nie tylko surowy procent", () => {
    const sz = zbudujSzczegoly({ kind: "jamming", data: JAMMING });
    expect(sz.coToJest.join(" ")).toContain("274");
    expect(sz.coToJest.join(" ")).toContain("11");
    expect(sz.naPodstawie.join(" ")).toMatch(/Wilsona/);
  });
});

describe("selectionFromPicked - rozroznianie typu klikniętego obiektu", () => {
  it("samolot po polach hex+lat, alarm po detector, heksagon po h3", () => {
    expect(selectionFromPicked(AIRCRAFT)).toEqual({ kind: "aircraft", data: AIRCRAFT });
    const alert = alertOf("D4", D4_EVIDENCE);
    expect(selectionFromPicked(alert)).toEqual({ kind: "alert", data: alert });
    expect(selectionFromPicked(JAMMING)).toEqual({ kind: "jamming", data: JAMMING });
  });

  it("null i obiekty bez rozpoznawalnych pol dają null, a nie zgadywanie", () => {
    expect(selectionFromPicked(null)).toBeNull();
    expect(selectionFromPicked({})).toBeNull();
    expect(selectionFromPicked("napis")).toBeNull();
  });
});

describe("D5 - przeladunek burta w burte", () => {
  const D5 = {
    id: 9, detector: "D5", entityId: "265585630+265623130",
    startedAt: "2026-09-28T15:10:00Z", lat: 59.719, lon: 19.07, score: 0.744, state: "new",
    evidence: JSON.stringify({
      name_a: "PILOT 792 SE", name_b: "SEKTOR", mmsi_a: "265585630", mmsi_b: "265623130",
      minutes: 33, min_separation_m: 30, drift_km: 0.0, mean_sog: 0.0,
      note: "Candidate to check, not a verdict.",
    }),
  };

  it("nazywa oba statki, nie numer pary", () => {
    const s = zbudujSzczegoly({ kind: "alert", data: D5 });
    expect(s.tytul).toContain("PILOT 792 SE");
    expect(s.tytul).toContain("SEKTOR");
  });

  it("mowi, co sie stalo, w minutach i metrach", () => {
    const s = zbudujSzczegoly({ kind: "alert", data: D5 });
    const tekst = s.coZTegoWynika.join(" ");
    expect(tekst).toContain("33 minut");
    expect(tekst).toContain("30 metrów");
  });

  it("odroznia postoj od wspolnego dryfu", () => {
    const s = zbudujSzczegoly({ kind: "alert", data: D5 });
    expect(s.coZTegoWynika.join(" ")).toMatch(/postój, nie wspólny dryf/);
  });

  it("podaje czestosc podstawowa, bo sam ksztalt zdarzenia niczego nie rozstrzyga", () => {
    // Bez tego pilotowka wyglada jak przeladunek poza rejestrem. Na dobie duńskiego ruchu
    // z 12 451 spotkan zostalo 11 po odsianiu kotwicowisk i jednostek sluzbowych.
    const s = zbudujSzczegoly({ kind: "alert", data: D5 });
    const podstawa = s.naPodstawie.join(" ");
    expect(podstawa).toMatch(/pilotaż|bunkrowanie|holowanie/);
    expect(podstawa).toMatch(/12 451|Czego to nie dowodzi/);
  });

  it("nie przepuszcza angielskiego z pola note na ekran", () => {
    const s = zbudujSzczegoly({ kind: "alert", data: D5 });
    const caly = [...s.coToJest, ...s.coZTegoWynika, ...s.naPodstawie].join(" ");
    expect(caly).not.toContain("Candidate to check");
  });
});
