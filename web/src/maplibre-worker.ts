import { config } from "maplibre-gl";
// Vite bundluje workera razem z jego wlasnym importem ./maplibre-gl-shared.mjs i zwraca adres
// wyemitowanego pliku. Samo "?url" skopiowaloby plik bez tej zaleznosci i worker padlby na imporcie.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

/**
 * URL of the MapLibre tile worker as emitted by the bundler.
 *
 * MapLibre derives the worker location from `import.meta.url` of its own bundle and appends
 * `maplibre-gl-worker.mjs`. Vite renames and hashes that bundle, so the sibling never exists in a
 * production build; nginx's SPA fallback then answers the worker request with index.html and the
 * worker dies with "Worker failed to load". Without the worker MapLibre parses no vector tiles at
 * all: the style JSON and sprites load, the canvas paints, and the basemap stays an empty surface.
 */
export const MAPLIBRE_WORKER_URL = workerUrl;

/** Points MapLibre at the bundled worker. Idempotent; called once when MapView is imported. */
export function configureMaplibreWorker(): void {
  config.WORKER_URL = MAPLIBRE_WORKER_URL;
}
