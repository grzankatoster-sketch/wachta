import { useEffect, useState } from "react";
import { getShipTrack } from "./api";
import type { Selection } from "./detail";
import { OKNO_H, przeanalizujSlad, type StanSladu } from "./slad";

/**
 * Fetches the selected ship's track and keeps the four states apart.
 *
 * "Loading", "loaded but empty", "loaded and moored" and "the request failed" are four different
 * facts and the panel says a different sentence for each. Collapsing them into one optional value
 * is how a map ends up showing a hull with no history exactly the way it shows a broken endpoint.
 *
 * The request is aborted when the selection changes, and a reply for a ship that is no longer
 * selected is dropped: clicking along a convoy fires one fetch per hull and they do not come back in
 * order, so without this the panel settles on whichever answer happened to be slowest.
 */
export function useSladStatku(wybrany: Selection | null): StanSladu {
  const mmsi = wybrany?.kind === "ship" ? wybrany.data.mmsi : null;
  const [stan, setStan] = useState<StanSladu>({ stan: "nic" });

  useEffect(() => {
    if (mmsi === null) {
      setStan({ stan: "nic" });
      return;
    }
    let aktualny = true;
    setStan({ stan: "ladowanie", mmsi });
    getShipTrack(mmsi, OKNO_H).then(
      (punkty) => {
        if (aktualny) setStan({ stan: "gotowy", slad: przeanalizujSlad(mmsi, punkty) });
      },
      (e: unknown) => {
        if (aktualny) setStan({ stan: "blad", powod: e instanceof Error ? e.message : "nieznany błąd" });
      },
    );
    return () => {
      aktualny = false;
    };
  }, [mmsi]);

  return stan;
}
