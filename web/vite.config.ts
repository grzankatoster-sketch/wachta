import { createReadStream, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Submarine cables and pipelines as a static file, not as a bundled import.
 *
 * data/infrastructure/baltic_cables.geojson is 221 152 B. Imported it would land inside the app's
 * JS, which the browser parses and runs before the first frame; served as its own file it is
 * 81 243 B on the wire (nginx gzip, its default comp level 1 - measured on this file) and it is
 * fetched only when the layer is actually switched on. It cannot live in web/public/ either,
 * because the detectors read the same file from data/ and a second copy would drift from the one
 * the alarms are computed against. So: streamed in dev, emitted into dist/ at build, one source.
 */
const PLIK_INFRASTRUKTURY = fileURLToPath(
  new URL("../data/infrastructure/baltic_cables.geojson", import.meta.url),
);
const SCIEZKA_INFRASTRUKTURY = "/dane/baltic_cables.geojson";

function daneInfrastruktury(): Plugin {
  return {
    name: "wachta-dane-infrastruktury",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.split("?")[0] !== SCIEZKA_INFRASTRUKTURY) return next();
        res.setHeader("Content-Type", "application/geo+json");
        createReadStream(PLIK_INFRASTRUKTURY).pipe(res);
      });
    },
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: SCIEZKA_INFRASTRUKTURY.slice(1),
        source: readFileSync(PLIK_INFRASTRUKTURY),
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), daneInfrastruktury()],
  // MapLibre ships its renderer as a web worker; Vite's dependency pre-bundling rewrites the worker
  // URL and the map stays blank ("Worker failed to load") in dev.
  optimizeDeps: { exclude: ["maplibre-gl"] },
  // Worker MapLibre jest modulem ES i importuje ./maplibre-gl-shared.mjs; domyslny format iife
  // wywalilby ten import przy budowaniu.
  worker: { format: "es" },
  server: {
    proxy: {
      "/api": "http://localhost:8080",
      "/hubs": { target: "http://localhost:8080", ws: true },
    },
  },
  // tests/ holds Playwright specs, which vitest cannot run - they go through `npm run test:ui`.
  test: { include: ["src/**/*.test.ts"] },
});
