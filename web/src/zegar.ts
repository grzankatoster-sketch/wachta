import { useEffect, useState } from "react";

/**
 * A ticking clock for the map, so marks can be advanced between fixes.
 *
 * Ten times a second, not sixty. The fastest thing on this map is an aircraft at 450 knots, which
 * covers about 23 metres in a tenth of a second - well under a pixel at any zoom where you can see
 * the whole Baltic. Sixty would rebuild the position attribute for a thousand objects six times as
 * often for motion nobody can see, and on the software renderer the desktop window falls back to,
 * that is not free.
 *
 * requestAnimationFrame rather than setInterval, because the browser stops it when the window is
 * hidden. A minimised watch board should not be burning a core smoothly animating a map nobody is
 * looking at; when it comes back, the first tick jumps to the correct position and carries on.
 */
export function useZegar(hz = 10): number {
  const [teraz, setTeraz] = useState(() => Date.now());

  useEffect(() => {
    const okres = 1000 / hz;
    let uchwyt = 0;
    let ostatni = 0;

    const krok = (czas: number) => {
      if (czas - ostatni >= okres) {
        ostatni = czas;
        setTeraz(Date.now());
      }
      uchwyt = requestAnimationFrame(krok);
    };

    uchwyt = requestAnimationFrame(krok);
    return () => cancelAnimationFrame(uchwyt);
  }, [hz]);

  return teraz;
}
