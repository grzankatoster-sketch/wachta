import {
  cienkiKonflikt, OKNA_H, osCzasu, podpisZdarzenia, pustoKonflikty, pustoZdarzenia, szczyt,
  tytulZdarzenia,
} from "../konflikty";
import type { StanWojny } from "../uzyj-wojny";
import { PanelWersji } from "./PanelWersji";
import "../wojna.css";

/**
 * Pick a war, see what happened in it, then see how each side tells one of those happenings.
 *
 * Three columns, left to right, in the order the question is asked - which war, what happened,
 * how is it told. The third column is the point of the whole view; the first two exist to get a
 * reader to it. It is a drawer rather than a permanent panel because the rest of this application
 * answers "what is moving right now" and that question deserves the map when nobody is asking this
 * one.
 */
export function PanelWojny({ stan }: { stan: StanWojny }) {
  if (!stan.otwarty) {
    return (
      <div className="wojna-zwiniety">
        <button type="button" onClick={stan.przelacz}>
          Wybierz wojnę
        </button>
      </div>
    );
  }

  return (
    <section className="wojna" aria-label="Wybór wojny i relacje stron">
      <div className="wojna-glowa">
        <h2>Wybierz wojnę</h2>
        <p className="muted">
          Zdarzenia lądowe z GDELT: to, co <b>doniesiono</b>, nie to, co potwierdzono.
        </p>
        <div className="wojna-okna" role="group" aria-label="Okno czasu">
          {OKNA_H.map((h) => (
            <button
              key={h}
              type="button"
              className={stan.godziny === h ? "wybrany" : ""}
              aria-pressed={stan.godziny === h}
              onClick={() => stan.ustawGodziny(h)}
            >
              {h} h
            </button>
          ))}
        </div>
        <button type="button" className="wojna-zamknij" onClick={stan.przelacz} aria-label="Zamknij wybór wojny">
          ×
        </button>
      </div>

      <div className="wojna-kolumny">
        <div className="wojna-kolumna wojna-lista">
          <h3>Konflikty</h3>
          {stan.konflikty.stan === "ladowanie" && <p className="muted">Ładuję listę konfliktów…</p>}
          {stan.konflikty.stan === "blad" && (
            <p className="wojna-blad">{pustoKonflikty(false)}</p>
          )}
          {stan.konflikty.stan === "gotowe" && stan.konflikty.dane.length === 0 && (
            <p className="wojna-nic">{pustoKonflikty(true)}</p>
          )}
          {stan.konflikty.stan === "gotowe" && (
            <ul>
              {stan.konflikty.dane.map((k) => (
                <li key={k.id}>
                  <button
                    type="button"
                    aria-current={k.id === stan.wybranyKonflikt?.id || undefined}
                    onClick={() => stan.wybierzKonflikt(k)}
                  >
                    <strong>{k.nazwa}</strong>
                    <br />
                    <span className="muted">
                      {k.actor1} ⇄ {k.actor2} · {k.events} zdarz.
                    </span>
                    {/* Jeden zgrupowany artykul to nie jest wojna, tylko artefakt grupowania -
                        i wyglada na liscie identycznie jak konflikt z tysiacem zdarzen. */}
                    {cienkiKonflikt(k) && (
                      <span className="wojna-cienki">jedno zdarzenie — to jeszcze nie obraz konfliktu</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="wojna-kolumna wojna-zdarzenia">
          <h3>{stan.wybranyKonflikt ? `Co się działo · ${stan.wybranyKonflikt.nazwa}` : "Co się działo"}</h3>
          {!stan.wybranyKonflikt && <p className="muted">Wybierz konflikt z lewej.</p>}
          {stan.wybranyKonflikt && stan.zdarzenia.stan === "ladowanie" && (
            <p className="muted">Ładuję zdarzenia…</p>
          )}
          {stan.wybranyKonflikt && stan.zdarzenia.stan === "blad" && (
            <p className="wojna-blad">
              {pustoZdarzenia(stan.wybranyKonflikt.nazwa, stan.godziny, false)}
            </p>
          )}
          {stan.wybranyKonflikt && stan.zdarzenia.stan === "gotowe" && stan.zdarzenia.dane.length === 0 && (
            <p className="wojna-nic">{pustoZdarzenia(stan.wybranyKonflikt.nazwa, stan.godziny, true)}</p>
          )}
          {stan.zdarzenia.stan === "gotowe" && stan.zdarzenia.dane.length > 0 && (
            <>
              <OsCzasu stan={stan} />
              <ul>
                {stan.zdarzenia.dane.map((z) => (
                  <li key={z.id}>
                    <button
                      type="button"
                      aria-current={z.id === stan.wybraneZdarzenie?.id || undefined}
                      onClick={() => stan.wybierzZdarzenie(z)}
                    >
                      <strong>{tytulZdarzenia(z)}</strong>
                      <br />
                      <span className="muted">{podpisZdarzenia(z)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <div className="wojna-kolumna wojna-wersje">
          {stan.wybraneZdarzenie ? (
            <PanelWersji zdarzenie={stan.wybraneZdarzenie} wersje={stan.wersje} />
          ) : (
            <>
              <h3>Jak opisują to zdarzenie</h3>
              <p className="muted">
                Wybierz zdarzenie ze środkowej kolumny albo kliknij krążek na mapie. Zobaczysz, ile
                artykułów napisała każda ze stron, w jakich językach i jak różni się ich ton.
              </p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

/**
 * When the reporting happened, as bars.
 *
 * The axis spans the events themselves rather than the requested window, so every event is inside
 * exactly one bar and the bars always add up to the list below them (see osCzasu).
 */
function OsCzasu({ stan }: { stan: StanWojny }) {
  const dane = stan.zdarzenia.stan === "gotowe" ? stan.zdarzenia.dane : [];
  const kubelki = osCzasu(dane);
  const max = szczyt(kubelki);
  if (kubelki.length === 0 || max === 0) return null;
  return (
    <div className="wojna-os" aria-label={`Rozkład ${dane.length} zdarzeń w czasie`}>
      <div className="wojna-slupki">
        {kubelki.map((k) => (
          <span
            key={k.od}
            className="wojna-slupek"
            style={{ height: `${Math.max(2, Math.round((k.ile / max) * 100))}%` }}
            title={`${k.etykieta} UTC · ${k.ile}`}
          />
        ))}
      </div>
      <div className="wojna-os-opis">
        <span>{kubelki[0].etykieta} UTC</span>
        <span>{kubelki[kubelki.length - 1].etykieta} UTC</span>
      </div>
    </div>
  );
}
