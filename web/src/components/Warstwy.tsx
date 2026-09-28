import { opisObszaru, przelacz, WARSTWY, wszystkoWylaczone, type IdWarstwy, type Widoczne } from "../warstwy";

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
}: {
  widoczne: Widoczne;
  onZmiana: (w: Widoczne) => void;
  liczby: Record<IdWarstwy, number>;
}) {
  return (
    <section className="warstwy" aria-label="Co widać na mapie">
      <h2>Co widać na mapie</h2>
      <p className="obszar">{opisObszaru()}</p>
      <ul>
        {WARSTWY.map((w) => {
          const wlaczona = widoczne[w.id];
          return (
            <li key={w.id}>
              <button
                type="button"
                className={wlaczona ? "" : "wylaczona"}
                aria-pressed={wlaczona}
                onClick={() => onZmiana(przelacz(widoczne, w.id))}
                title={wlaczona ? "Kliknij, żeby ukryć" : "Kliknij, żeby pokazać"}
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
      {wszystkoWylaczone(widoczne) && (
        <p className="ostrzezenie">
          Wszystkie warstwy są wyłączone — mapa jest pusta, bo tak ją ustawiłeś, a nie dlatego, że nic
          się nie dzieje.
        </p>
      )}
    </section>
  );
}
