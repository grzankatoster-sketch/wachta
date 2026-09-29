import { useEffect } from "react";
import type { Szczegoly } from "../detail";
import { ETYKIETY, type Ocena, type Werdykt } from "../ocena";

/**
 * Klikniecie w cokolwiek na mapie ma dawac dane, analize i podstawe twierdzenia - nie kropke bez
 * kontekstu. Trzy sekcje sa celowo rozdzielone wizualnie: surowy fakt, interpretacja zdaniami i to,
 * na czym ta interpretacja stoi (zrodlo, regula, progi) razem z tym, czego NIE dowodzi. Zero JSON-a:
 * kazde pole jest juz przetworzone na zdanie albo etykiete przez detail.ts, ten komponent tylko
 * uklada tekst na ekranie.
 *
 * @param szczegoly - already-built three-section content (see detail.ts's zbudujSzczegoly)
 * @param onClose - called on Escape or the close button; caller owns the open/closed state
 */
export function DetailPanel({ szczegoly, onClose }: { szczegoly: Szczegoly; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      role="dialog"
      aria-label={`Szczegóły: ${szczegoly.tytul}`}
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: "min(380px, 92vw)",
        overflowY: "auto",
        background: "rgba(20, 24, 30, 0.96)",
        color: "#f2f3f0",
        padding: "16px 18px 24px",
        boxShadow: "-4px 0 16px rgba(0,0,0,0.35)",
        zIndex: 20,
        fontSize: 14,
        lineHeight: 1.45,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 17 }}>{szczegoly.tytul}</h2>
          {szczegoly.podtytul && <div style={{ opacity: 0.75, fontSize: 13 }}>{szczegoly.podtytul}</div>}
        </div>
        <button
          onClick={onClose}
          aria-label="Zamknij panel szczegółów"
          style={{
            background: "transparent", color: "inherit", border: "1px solid rgba(255,255,255,0.3)",
            borderRadius: 4, width: 28, height: 28, cursor: "pointer", flexShrink: 0,
          }}
        >
          ×
        </button>
      </div>

      <Sekcja tytul="Co to jest" wiersze={szczegoly.coToJest} pusteInfo="Brak zmierzonych danych do pokazania." />
      {szczegoly.ocena && <OcenaSekcja ocena={szczegoly.ocena} />}
      <Sekcja tytul="Co z tego wynika" wiersze={szczegoly.coZTegoWynika} pusteInfo="Za mało danych na interpretację." />
      <Sekcja tytul="Na jakiej podstawie" wiersze={szczegoly.naPodstawie} />

      {szczegoly.tor && (
        <div style={{ marginTop: 14, fontSize: 12.5, opacity: 0.85 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Tor: zanik → powrót</div>
          <div>
            zanik: {szczegoly.tor.zanik.lat.toFixed(3)}, {szczegoly.tor.zanik.lon.toFixed(3)}
          </div>
          <div>
            powrót: {szczegoly.tor.powrot.lat.toFixed(3)}, {szczegoly.tor.powrot.lon.toFixed(3)}
          </div>
        </div>
      )}
    </aside>
  );
}

const BARWA_WERDYKTU: Record<Werdykt, string> = {
  rutyna: "#3fb950",
  "warte-sprawdzenia": "#e3b341",
  nietypowe: "#f85149",
};

/**
 * The assessment, kept visually apart from everything around it.
 *
 * It sits directly under the measured facts and above the interpretation, because that is the order
 * a reader needs: what was measured, what I make of it, then the reasoning and the source. It is
 * labelled as the project's own opinion and it always carries the case against - an assessment that
 * only argued one way would be the one thing this panel exists to avoid.
 */
function OcenaSekcja({ ocena }: { ocena: Ocena }) {
  return (
    <section style={{ marginTop: 14, borderTop: "1px solid rgba(255,255,255,0.15)", paddingTop: 10 }}>
      <h3 style={{ margin: "0 0 8px", fontSize: 12.5, textTransform: "uppercase", letterSpacing: 0.4, opacity: 0.7 }}>
        Moja ocena
      </h3>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7, flexWrap: "wrap" }}>
        <span
          style={{
            background: BARWA_WERDYKTU[ocena.werdykt],
            color: "#0d1117",
            fontWeight: 700,
            fontSize: 11.5,
            letterSpacing: 0.3,
            padding: "3px 9px",
            borderRadius: 999,
          }}
        >
          {ETYKIETY[ocena.werdykt]}
        </span>
        <span style={{ fontSize: 12, opacity: 0.72 }}>pewność: {ocena.pewnosc}</span>
      </div>

      <p style={{ margin: "0 0 9px" }}>{ocena.teza}</p>

      <Lista tytul="Za" wiersze={ocena.za} />
      <Lista tytul="Przeciw" wiersze={ocena.przeciw} />

      <p style={{ margin: "9px 0 0", fontSize: 12.5, opacity: 0.85 }}>
        <b>Co by to rozstrzygnęło:</b> {ocena.coBySprawdzic}
      </p>
      <p style={{ margin: "7px 0 0", fontSize: 11.5, opacity: 0.6 }}>
        Ocena wyliczona z reguł na dowodach wypisanych wyżej — bez modelu i bez sieci. Ten sam alarm
        zawsze dostaje tę samą ocenę, więc da się ją sprawdzić i się z nią nie zgodzić.
      </p>
    </section>
  );
}

function Lista({ tytul, wiersze }: { tytul: string; wiersze: string[] }) {
  if (!wiersze.length) return null;
  return (
    <div style={{ marginTop: 5 }}>
      <div style={{ fontSize: 11.5, opacity: 0.6, fontWeight: 600 }}>{tytul}</div>
      <ul style={{ margin: "2px 0 0", paddingLeft: 18, fontSize: 13 }}>
        {wiersze.map((w, i) => (
          <li key={i} style={{ marginBottom: 3 }}>
            {w}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Sekcja({ tytul, wiersze, pusteInfo }: { tytul: string; wiersze: string[]; pusteInfo?: string }) {
  if (wiersze.length === 0 && !pusteInfo) return null;
  return (
    <section style={{ marginTop: 14, borderTop: "1px solid rgba(255,255,255,0.15)", paddingTop: 10 }}>
      <h3 style={{ margin: "0 0 6px", fontSize: 12.5, textTransform: "uppercase", letterSpacing: 0.4, opacity: 0.7 }}>
        {tytul}
      </h3>
      {wiersze.length === 0 ? (
        <p style={{ margin: 0, opacity: 0.6, fontStyle: "italic" }}>{pusteInfo}</p>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {wiersze.map((w, i) => (
            <li key={i} style={{ marginBottom: 4 }}>
              {w}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
