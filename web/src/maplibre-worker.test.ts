import { describe, expect, it } from "vitest";
import { config } from "maplibre-gl";
import { MAPLIBRE_WORKER_URL, configureMaplibreWorker } from "./maplibre-worker";

describe("worker MapLibre", () => {
  it("wskazuje na plik wyemitowany przez bundler, nie na siostrzany plik obok index.js", () => {
    // Pusty WORKER_URL oznacza, ze MapLibre zgaduje adres z import.meta.url swojego chunka - a tam
    // po zbudowaniu nic nie ma i nginx oddaje index.html zamiast skryptu.
    expect(MAPLIBRE_WORKER_URL).toBeTruthy();
    // W dev Vite dokleja ?worker_file&type=module, w buildzie zostaje samo /assets/<hash>.js.
    expect(MAPLIBRE_WORKER_URL).toMatch(/\.m?js(\?.*)?$/);
  });

  it("ustawia config.WORKER_URL, bo tylko to przebija zgadywanie po import.meta.url", () => {
    config.WORKER_URL = "";
    configureMaplibreWorker();
    expect(config.WORKER_URL).toBe(MAPLIBRE_WORKER_URL);
    expect(config.WORKER_URL).not.toBe("");
  });
});
