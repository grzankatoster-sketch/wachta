import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { BASEMAP_LAND, BASEMAP_SEA, SHIP_CARGO, SHIP_OTHER, contrastRatio } from "./colors";
import { selectionFromPicked, zbudujSzczegoly } from "./detail";
import {
  dlugoscKm,
  kolorLinii,
  parsujLinie,
  pobierzLinie,
  szczegolyLinii,
  SCIEZKA_DANYCH,
  type LiniaInfrastruktury,
  type RodzajLinii,
} from "./infrastruktura";
import { infrastructureLayers } from "./layers/infrastruktura";
import { WARSTWY, WSZYSTKO_WIDOCZNE } from "./warstwy";

/**
 * D6 was raising "statek 0,1 km od linii" over a map that drew no lines at all. These tests guard
 * the three things that makes it honest: the line is on the map, it is legible on the basemap
 * without shouting over the ships, and clicking it says what it is AND that the route is drawn,
 * not surveyed.
 */

/** The real file, read straight from data/ - the same bytes the Python detector loads. */
const PLIK = new URL("../../data/infrastructure/baltic_cables.geojson", import.meta.url);
const DANE: unknown = JSON.parse(readFileSync(PLIK, "utf-8"));

const LINIA: LiniaInfrastruktury = {
  osmId: 178372932,
  nazwa: "Nord Stream 1",
  rodzaj: "pipeline",
  operator: "Nord Stream AG",
  sciezka: [
    [21.0, 55.0],
    [21.5, 55.2],
  ],
};

describe("dane infrastruktury", () => {
  it("wczytuje wszystkie linie z pliku, ktory czytaja detektory", () => {
    // 89 obiektow zmierzone na pliku z 2026-09-26; jesli fetch z Overpass da inna liczbe, ten test
    // ma o tym powiedziec, a nie milczkiem narysowac mniej.
    const linie = parsujLinie(DANE);
    expect(linie).toHaveLength(89);
    expect(linie.filter((l) => l.rodzaj === "power")).toHaveLength(38);
    expect(linie.filter((l) => l.rodzaj === "telecom")).toHaveLength(35);
    expect(linie.filter((l) => l.rodzaj === "pipeline")).toHaveLength(16);
  });

  it("kazda linia ma nazwe i co najmniej dwa punkty", () => {
    for (const l of parsujLinie(DANE)) {
      expect(l.nazwa, String(l.osmId)).toBeTruthy();
      expect(l.sciezka.length, l.nazwa).toBeGreaterThanOrEqual(2);
    }
  });

  it("odrzuca dokladnie to, co odrzuca detektor: nie-LineString i linie krotsze niz dwa punkty", () => {
    // wachta_detectors/infrastructure.py::load_lines pomija jedno i drugie. Gdyby mapa ich nie
    // pomijala, rysowalaby infrastrukture, ktorej D6 w ogole nie mierzy.
    // MultiPoint nie jest tu przypadkiem z sufitu: ma DOKLADNIE taki sam ksztalt wspolrzednych co
    // LineString, wiec bez sprawdzenia typu dwa osobne punkty na dnie zostalyby narysowane jako
    // linia laczaca je przez pol morza - i D6 mierzylby dystans do czegos, czego nie ma.
    const linie = parsujLinie({
      features: [
        { geometry: { type: "MultiPoint", coordinates: [[21, 55], [22, 56]] }, properties: { name: "dwa punkty", kind: "power" } },
        { geometry: { type: "Point", coordinates: [21, 55] }, properties: { name: "punkt", kind: "power" } },
        { geometry: { type: "LineString", coordinates: [[21, 55]] }, properties: { name: "ogryzek", kind: "power" } },
        { geometry: { type: "LineString", coordinates: [[21, 55], [22, 56]] }, properties: { name: "dobra", kind: "power" } },
      ],
    });
    expect(linie.map((l) => l.nazwa)).toEqual(["dobra"]);
  });

  it("nieznany rodzaj z OSM nie znika z mapy, tylko trafia do wlasnego kubelka", () => {
    const [l] = parsujLinie({
      features: [{ geometry: { type: "LineString", coordinates: [[21, 55], [22, 56]] },
                   properties: { name: "cos nowego", kind: "hyperloop" } }],
    });
    expect(l.rodzaj).toBe("inny");
  });

  it("pusty albo zepsuty plik daje pusta liste, nie wyjatek", () => {
    expect(parsujLinie(null)).toEqual([]);
    expect(parsujLinie({})).toEqual([]);
  });

  it("pobiera plik statyczny spod /dane/, a nie z API", async () => {
    // Regresja na decyzje o dostarczaniu: 221 KB nie wchodzi do bundla i nie idzie przez .NET.
    const wolania: string[] = [];
    const udawany = (async (u: string) => {
      wolania.push(u);
      return { ok: true, json: async () => DANE } as Response;
    }) as unknown as typeof fetch;
    const linie = await pobierzLinie(SCIEZKA_DANYCH, udawany);
    expect(wolania).toEqual(["/dane/baltic_cables.geojson"]);
    expect(linie).toHaveLength(89);
  });
});

describe("kolory linii na podkladzie positron", () => {
  const rodzaje: RodzajLinii[] = ["power", "telecom", "pipeline", "inny"];

  it("kazdy rodzaj ma co najmniej 3:1 wobec ladu i wobec wody", () => {
    // Prog z WCAG 1.4.11 dla grafiki niosacej znaczenie. Woda jest tu warunkiem wiazacym:
    // zmierzone KABEL 6.68:1 / 4.40:1, RUROCIAG 5.85:1 / 3.85:1 (lad / woda).
    for (const r of rodzaje) {
      expect(contrastRatio(kolorLinii(r), BASEMAP_LAND), `${r} nad ladem`).toBeGreaterThanOrEqual(3);
      expect(contrastRatio(kolorLinii(r), BASEMAP_SEA), `${r} nad woda`).toBeGreaterThanOrEqual(3);
    }
  });

  it("rurociag ma inny kolor niz kabel, bo legenda obiecuje dwa", () => {
    expect(kolorLinii("pipeline")).not.toEqual(kolorLinii("power"));
    expect(kolorLinii("telecom")).toEqual(kolorLinii("power"));
  });

  it("nie sa kolorami statkow - infrastruktura nie moze udawac ruchu", () => {
    for (const r of rodzaje) {
      expect(kolorLinii(r)).not.toEqual(SHIP_CARGO);
      expect(kolorLinii(r)).not.toEqual(SHIP_OTHER);
    }
  });
});

describe("warstwa na mapie", () => {
  it("linia jest cienka i lezy pod statkami, a klikniecia lapie szerszy blizniak", () => {
    // Widoczna sciezka ma 1.2 px - grubsza konkurowalaby z kadlubami, cienszej nie da sie trafic
    // mysza. Stad dwie warstwy: widoczna (nieklikalna) i niewidoczna 9 px (klikalna) pod spodem.
    const [trafienie, widoczna] = infrastructureLayers([LINIA]);
    const p = (l: unknown) => (l as { props: Record<string, number | boolean> }).props;
    expect(p(trafienie).pickable).toBe(true);
    expect(p(widoczna).pickable).toBe(false);
    expect(p(widoczna).widthMinPixels as number).toBeLessThanOrEqual(1.5);
    expect(p(trafienie).widthMinPixels as number).toBeGreaterThan(p(widoczna).widthMinPixels as number);
    expect((trafienie as { id: string }).id).not.toBe((widoczna as { id: string }).id);
  });

  it("warstwa klikalna jest pierwsza, wiec statek nad linia dostaje klikniecie", () => {
    expect((infrastructureLayers([LINIA])[0] as { id: string }).id).toBe("infrastructure-hit");
  });
});

describe("legenda", () => {
  it("ma wiersz infrastruktury w grupie morskiej i jest on wlaczony na starcie", () => {
    const w = WARSTWY.find((x) => x.id === "infrastruktura");
    expect(w?.grupa).toBe("morze");
    expect(w?.ksztalt).toBe("linia");
    expect(WSZYSTKO_WIDOCZNE.infrastruktura).toBe(true);
  });

  it("opis mowi, ze trasy sa przyblizone", () => {
    expect(WARSTWY.find((x) => x.id === "infrastruktura")?.opis).toMatch(/przybliżon/i);
  });
});

describe("panel szczegolow linii", () => {
  it("klikniecie w linie rozpoznaje sie jako infrastrukture, nie jako statek", () => {
    expect(selectionFromPicked(LINIA)).toEqual({ kind: "infrastruktura", data: LINIA });
  });

  it("nazywa linie i jej rodzaj po polsku", () => {
    const s = zbudujSzczegoly({ kind: "infrastruktura", data: LINIA });
    expect(s.tytul).toBe("Nord Stream 1");
    expect(s.podtytul).toBe("rurociąg");
    expect(s.coToJest.join(" ")).toMatch(/Nord Stream AG/);
  });

  it("mowi wprost, ze trasa jest przyblizona i ze D6 liczy odleglosc od RYSUNKU", () => {
    // To jest sedno: detektor podaje setne czesci kilometra od geometrii, ktora ktos narysowal
    // z map morskich. Panel, ktory to przemilcza, uwiarygodnia dokladnosc, ktorej nie ma.
    const podstawa = zbudujSzczegoly({ kind: "infrastruktura", data: LINIA }).naPodstawie.join(" ");
    expect(podstawa).toMatch(/PRZYBLIŻONE/);
    expect(podstawa).toMatch(/OpenStreetMap/);
    expect(podstawa).toMatch(/D6/);
    expect(podstawa).toMatch(/nie dowodzi/i);
  });

  it("ma wszystkie trzy sekcje wypelnione", () => {
    const s = szczegolyLinii(LINIA);
    expect(s.coToJest.length).toBeGreaterThan(0);
    expect(s.coZTegoWynika.length).toBeGreaterThan(0);
    expect(s.naPodstawie.length).toBeGreaterThan(0);
  });

  it("nie zostawia w panelu surowych pol z OSM", () => {
    const s = szczegolyLinii({ ...LINIA, operator: null });
    const caly = [...s.coToJest, ...s.coZTegoWynika, ...s.naPodstawie].join(" ");
    expect(caly).not.toMatch(/osm_id|pipeline|telecom|"kind"|undefined|null/);
  });

  it("podaje dlugosc narysowanego odcinka", () => {
    // 1 stopien szerokosci to 111.32 km w tym przyblizeniu - to ten sam plaski model, ktorego
    // uzywa detektor, wiec panel nie klamie o dystansie inaczej niz alarm.
    expect(dlugoscKm([[21, 55], [21, 56]])).toBeCloseTo(111.32, 1);   // polud., czysty skladnik pn-pd
    expect(dlugoscKm([[21, 0], [22, 0]])).toBeCloseTo(111.32, 1);     // rownik, czysty skladnik wsch-zach
    expect(dlugoscKm([[21, 60], [22, 60]])).toBeCloseTo(55.66, 0);    // 60 st. - poludnik o polowe krotszy
    expect(szczegolyLinii(LINIA).coToJest.join(" ")).toMatch(/km/);
  });
});
