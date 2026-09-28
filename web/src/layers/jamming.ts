import { H3HexagonLayer } from "@deck.gl/geo-layers";
import type { JammingDto } from "../api";
import { jammingColor } from "../colors";

export function jammingLayer(cells: JammingDto[]) {
  return new H3HexagonLayer<JammingDto>({
    id: "jamming",
    data: cells,
    getHexagon: (c) => c.h3,
    getFillColor: (c) => jammingColor(c.nDegraded / c.nAircraft),
    extruded: false,
    stroked: false,
    // Klikniecie w heksagon ma otworzyc panel szczegolow (co to jest / co z tego wynika / na jakiej
    // podstawie) - deck.gl nie zglasza klikniec z warstwy, ktora nie jest pickable.
    pickable: true,
  });
}
