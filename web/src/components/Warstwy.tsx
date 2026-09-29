import { Klucz } from "./Klucz";
import type { Kategoria } from "../typy";
import { NAZWY_GRUP, opisObszaru, przelacz, wGrupie, wszystkoWylaczone,
  type Grupa, type IdWarstwy, type Widoczne } from "../warstwy";

/**
 * The key to the map, which is also the switch for it.
 *
 * Each row names one kind of mark, says in a sentence what it means, shows how many of them are on
 * screen, and turns them off. Turning a layer off is the fastest way to learn what its marks were -
 * faster than reading a legend, which is why the legend is the control rather than a caption beside
 * it.
 */
export function Warstwy({
  widoczne,
  onZmiana,
  liczby,
  kategorie,
}: {
  widoczne: Widoczne;
  onZmiana: (w: Widoczne) => void;
  liczby: Record<IdWarstwy, number>;
  /** Categories actually on screen, per domain - the key below each group's switches. */
  kategorie?: Partial<Record<Grupa, Array<{ id: Kategoria; ile: number }>>>;
}) {
  return (
    <section className="warstwy" aria-label="Co widać na mapie">
      <h2>Co widać na mapie</h2>
      <p className="obszar">{opisObszaru()}</p>
      {(["powietrze", "morze", "detektory"] as Grupa[]).map((grupa) => (
        <div className="grupa" key={grupa}>
          <h3>{NAZWY_GRUP[grupa]}</h3>
          <ul>
            {wGrupie(grupa).map((w) => {
              const wlaczona = widoczne[w.id];
              return (
                <li key={w.id}>
                  <button
                    type="button"
                    className={wlaczona ? "" : "wylaczona"}
                    aria-pressed={wlaczona}
                    onClick={() => onZmiana(przelacz(widoczne, w.id))}
                    title={`${w.opis}

${wlaczona ? "Kliknij, żeby ukryć" : "Kliknij, żeby pokazać"}`}
                  >
                    <span className={`znak ${w.ksztalt}`} style={{ background: w.kolor, borderColor: w.kolor }} />
                    <span className="nazwa">{w.nazwa}</span>
                    <span className="liczba">{liczby[w.id]}</span>
                  </button>
                  <p className="opis">{w.opis}</p>
                </li>
              );
            })}
          </ul>
          <Klucz kategorie={kategorie?.[grupa] ?? []} />
        </div>
      ))}
      {wszystkoWylaczone(widoczne) && (
        <p className="ostrzezenie">
          Wszystkie warstwy są wyłączone — mapa jest pusta, bo tak ją ustawiłeś, a nie dlatego, że nic
          się nie dzieje.
        </p>
      )}
    </section>
  );
}
