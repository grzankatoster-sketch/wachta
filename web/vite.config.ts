import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
