import { useCallback, useRef, useState } from "react";
import { search, type SearchHit } from "../api";
import { sila, stanZBledu, stanZOdpowiedzi, type Stan } from "../search-view";

/**
 * Search the corpus by meaning, in whatever language the reader thinks in.
 *
 * The events are indexed in English, the outlets write in Russian and Ukrainian, and the question
 * gets typed in Polish. That is the whole reason this panel exists rather than a text filter.
 *
 * Three states are shown differently on purpose, because conflating them is how a search tool
 * starts lying:
 *
 *   - hits found: each with its similarity score, so the reader can disbelieve a weak one;
 *   - nothing above the floor: an ANSWER, phrased as one. A nearest neighbour always exists, so a
 *     search that never says "nothing here" is a search that always invents something;
 *   - the model is down: an ERROR, and clearly not the same thing as an empty corpus.
 */

const FILTRY: Array<{ id?: string; etykieta: string; opis: string }> = [
  { etykieta: "wszystko", opis: "alarmy detektorów i zdarzenia ze świata" },
  { id: "alert", etykieta: "alarmy", opis: "tylko to, co zdecydowały detektory" },
  { id: "event", etykieta: "zdarzenia", opis: "tylko doniesienia z GDELT" },
];

const PRZYKLADY = ["statek przy kablu podmorskim", "protesty i zamieszki", "zakłócenia GPS"];

function Trafienie({ hit }: { hit: SearchHit }) {
  const { etykieta, klasa } = sila(hit.score);
  const rodzaj = typeof hit.metadata.kind === "string" ? hit.metadata.kind : null;
  const miejsce = typeof hit.metadata.place === "string" ? hit.metadata.place : null;
  const zrodlo = typeof hit.metadata.url === "string" ? hit.metadata.url : null;

  return (
    <li className="trafienie">
      <div className="trafienie-glowa">
        <span className={`wynik ${klasa}`} title={`podobieństwo ${hit.score.toFixed(3)} — ${etykieta}`}>
          {hit.score.toFixed(2)}
        </span>
        {rodzaj && <span className="znacznik">{rodzaj === "alert" ? "alarm" : "zdarzenie"}</span>}
        {miejsce && <span className="miejsce">{miejsce}</span>}
      </div>
      <div className="trafienie-tresc">{hit.text}</div>
      {zrodlo && (
        <a className="zrodlo" href={zrodlo} target="_blank" rel="noreferrer">
          {new URL(zrodlo).host}
        </a>
      )}
    </li>
  );
}

export function SearchPanel() {
  const [pytanie, setPytanie] = useState("");
  const [filtr, setFiltr] = useState<string | undefined>(undefined);
  const [stan, setStan] = useState<Stan>({ rodzaj: "pusto" });
  // Kazde zapytanie dostaje numer. Odpowiedz ze starszego numeru jest porzucana - bez tego wolniejsza
  // odpowiedz na wczesniejsze pytanie potrafi nadpisac wynik pytania zadanego pozniej.
  const numer = useRef(0);

  const szukaj = useCallback(
    async (tekst: string, rodzajFiltru: string | undefined) => {
      const zapytanie = tekst.trim();
      if (!zapytanie) {
        setStan({ rodzaj: "pusto" });
        return;
      }
      const moj = ++numer.current;
      setStan({ rodzaj: "szukam" });
      try {
        const dane = await search(zapytanie, rodzajFiltru);
        if (moj === numer.current) setStan(stanZOdpowiedzi(dane));
      } catch (e) {
        if (moj === numer.current) setStan(stanZBledu(e));
      }
    },
    [],
  );

  const zmienFiltr = (id: string | undefined) => {
    setFiltr(id);
    if (stan.rodzaj === "wynik" || stan.rodzaj === "blad") void szukaj(pytanie, id);
  };

  return (
    <section className="szukaj" aria-label="Wyszukiwanie po znaczeniu">
      <h2>Szukaj po znaczeniu</h2>
      <p className="szukaj-wstep">
        Pytaj po polsku. Zdarzenia są po angielsku, doniesienia bywają po rosyjsku i ukraińsku —
        dopasowanie idzie po znaczeniu, nie po słowach.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void szukaj(pytanie, filtr);
        }}
      >
        <input
          type="search"
          value={pytanie}
          onChange={(e) => setPytanie(e.target.value)}
          placeholder="np. statek przy kablu podmorskim"
          aria-label="Pytanie"
        />
        <button type="submit" disabled={!pytanie.trim() || stan.rodzaj === "szukam"}>
          {stan.rodzaj === "szukam" ? "szukam…" : "szukaj"}
        </button>
      </form>

      <div className="filtry" role="group" aria-label="Zakres wyszukiwania">
        {FILTRY.map((f) => (
          <button
            key={f.etykieta}
            type="button"
            className={filtr === f.id ? "wybrany" : ""}
            title={f.opis}
            onClick={() => zmienFiltr(f.id)}
          >
            {f.etykieta}
          </button>
        ))}
      </div>

      {stan.rodzaj === "pusto" && (
        <div className="podpowiedzi">
          {PRZYKLADY.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => {
                setPytanie(p);
                void szukaj(p, filtr);
              }}
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {stan.rodzaj === "blad" && (
        <div className="szukaj-blad" role="alert">
          <b>Wyszukiwanie niedostępne.</b> {stan.komunikat}
          <div className="drobne">
            To nie znaczy, że w korpusie nic nie ma — znaczy, że nie dało się zadać pytania.
          </div>
        </div>
      )}

      {stan.rodzaj === "wynik" && stan.dane.found === 0 && (
        <div className="szukaj-nic">
          <b>Brak danych.</b>
          <div className="drobne">{stan.dane.caveat}</div>
        </div>
      )}

      {stan.rodzaj === "wynik" && stan.dane.found > 0 && (
        <>
          <div className="szukaj-licznik">
            {stan.dane.found} trafień · próg {stan.dane.minScore.toFixed(2)} · {stan.dane.model}
          </div>
          <ul className="trafienia">
            {stan.dane.hits.map((h) => (
              <Trafienie key={h.id} hit={h} />
            ))}
          </ul>
          <p className="drobne">{stan.dane.caveat}</p>
        </>
      )}
    </section>
  );
}
