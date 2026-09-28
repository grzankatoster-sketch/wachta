import { useEffect } from "react";
import type { Szczegoly } from "../detail";

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
