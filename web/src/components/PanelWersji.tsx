import { pustoWersje, tytulZdarzenia, type ZdarzenieDto } from "../konflikty";
import type { Pobranie } from "../uzyj-wojny";
import {
  nieprzypisane, ostrzezenieCalosci, rozjazd, wierszeStron, zdanieONieprzypisanych,
  ZASTRZEZENIE_WYDZWIEKU, type WersjeDto,
} from "../wersje";

/**
 * The comparison itself: one event, as told by each side.
 *
 * Reading order is the argument this panel makes, and it is deliberately upside down compared to a
 * normal report. The warning about thin data comes FIRST, above the numbers it applies to, because
 * a reader who meets the bars first has already formed the conclusion by the time the caveat
 * arrives. The caveat about what tone is comes LAST, right where the reader is about to leave with
 * a sentence in their head.
 */
export function PanelWersji({
  zdarzenie,
  wersje,
}: {
  zdarzenie: ZdarzenieDto;
  wersje: Pobranie<WersjeDto | null>;
}) {
  return (
    <section className="wersje" aria-label="Jak opisują to zdarzenie">
      <h3>Jak opisują to zdarzenie</h3>
      <p className="wersje-zdarzenie">{tytulZdarzenia(zdarzenie)}</p>

      {wersje.stan === "ladowanie" && <p className="muted">Zbieram artykuły o tym zdarzeniu…</p>}
      {wersje.stan === "blad" && (
        <p className="wojna-blad">
          Nie udało się pobrać zestawienia wersji ({wersje.powod}). To brak odpowiedzi, nie brak różnic.
        </p>
      )}
      {wersje.stan === "gotowe" && wersje.dane === null && (
        <p className="wojna-nic">{pustoWersje(true)}</p>
      )}
      {wersje.stan === "gotowe" && wersje.dane !== null && <Zestawienie w={wersje.dane} />}
    </section>
  );
}

function Zestawienie({ w }: { w: WersjeDto }) {
  const slabe = ostrzezenieCalosci(w);
  const r = rozjazd(w);
  const wiersze = wierszeStron(w);
  const brakujace = zdanieONieprzypisanych(nieprzypisane(w), w.totalArticles);

  return (
    <>
      {/* Przed liczbami, nie pod nimi: cienkie porownanie wyglada dokladnie tak samo jak solidne -
          dwie strony, dwie liczby, roznica wydzwieku - wiec ostrzezenie musi trafic do czytelnika
          zanim on sam wyciagnie wniosek z paskow. */}
      {slabe && (
        <div className="wersje-slabe" role="note">
          <strong>{slabe.naglowek}</strong>
          <ul>
            {slabe.punkty.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      <p className={`wersje-rozjazd ${r.stan}`}>
        <strong>{r.naglowek}</strong>
        <br />
        <span>{r.zdanie}</span>
      </p>

      <ul className="wersje-strony">
        {wiersze.map((s) => (
          <li key={s.kod} className={s.slaba ? "slaba" : ""}>
            <div className="strona-glowa">
              <span className="strona-nazwa" title={s.pelna}>
                {s.krotka}
              </span>
              <span className="strona-ile">
                {s.artykuly === 1 ? "1 artykuł" : `${s.artykuly} art.`}
              </span>
            </div>
            {/* Pasek liczony z WSZYSTKICH artykulow o zdarzeniu, takze nieprzypisanych - inaczej
                trzy artykuly z czterdziestu rysowalyby sie jako polowa glosow. */}
            <div className="strona-pasek" aria-hidden="true">
              <span style={{ width: `${Math.round(s.udzial * 100)}%` }} />
            </div>
            <div className="strona-ton">{s.opisWydzwieku}</div>
            <div className="strona-jezyki">{s.jezyki}</div>
            {s.ostrzezenia.length > 0 && (
              <ul className="strona-ostrzezenia">
                {s.ostrzezenia.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            )}
            {s.przyklady.length > 0 && (
              <div className="strona-przyklady">
                {s.przyklady.map((u, i) => (
                  <a key={u} href={u} target="_blank" rel="noreferrer noopener">
                    przykład {i + 1}
                  </a>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>

      {brakujace && <p className="wersje-brakujace">{brakujace}</p>}
      <p className="wersje-zastrzezenie">{ZASTRZEZENIE_WYDZWIEKU}</p>
    </>
  );
}
