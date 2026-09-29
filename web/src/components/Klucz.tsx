import { KATEGORIE, type Kategoria } from "../typy";
import { urlIkony } from "../layers/ikony";

/**
 * What the shapes and colours on the map mean.
 *
 * Separate from the layer switches above it, and deliberately not clickable: the switches decide
 * what is drawn, this decides nothing and only explains. Mixing the two would give the reader six
 * controls and fourteen look-alike rows that do nothing when pressed.
 *
 * Only categories that are on screen right now appear. An empty category is a row inviting the
 * reader to look for something that is not there, and on this map most of the fourteen are empty
 * most of the time - a surveillance aircraft over the Baltic is an event, not a fixture.
 *
 * Each chip carries the real silhouette, masked in the real colour, on the basemap's own light
 * fill. That last part is why the palette could be chosen for the map alone: the key inherits the
 * map's contrast instead of forcing every colour to clear a dark panel as well.
 */
export function Klucz({ kategorie }: { kategorie: Array<{ id: Kategoria; ile: number }> }) {
  if (!kategorie.length) return null;

  return (
    <ul className="klucz" aria-label="Znaczenie kształtów i kolorów">
      {kategorie.map(({ id, ile }) => {
        const k = KATEGORIE[id];
        const kolor = `rgb(${k.kolor[0]},${k.kolor[1]},${k.kolor[2]})`;
        return (
          <li key={id}>
            <span
              className="klucz-znak"
              aria-hidden="true"
              style={{
                backgroundColor: kolor,
                WebkitMaskImage: `url("${urlIkony(k.ksztalt)}")`,
                maskImage: `url("${urlIkony(k.ksztalt)}")`,
              }}
            />
            <span className="klucz-nazwa">{k.nazwa}</span>
            <span className="klucz-ile">{ile}</span>
          </li>
        );
      })}
    </ul>
  );
}
