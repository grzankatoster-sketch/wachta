import { defineConfig } from "@playwright/test";

/**
 * Two suites, two servers.
 *
 * `dev` runs against `vite dev`. It is fast and catches layout and logic regressions, but it can
 * never catch a packaging bug: the dev server transforms modules on the fly, serves every source
 * path unhashed and proxies /api, so a build that is broken only once bundled still looks healthy.
 * That is exactly how the blank basemap reached production - MapLibre's worker chunk is hashed by
 * the bundler, the sibling path MapLibre asks for does not exist in dist/, and nginx answers the
 * miss with index.html.
 *
 * `prod` runs against the artifact that actually ships: a fresh `vite build` served as static
 * files with an SPA fallback, i.e. the same shape as the nginx container.
 *
 * Two routes, on purpose:
 *  - domyslna (bez zmiennych): budowa + `vite preview`. Nie wymaga dockera i ZAWSZE mierzy artefakt
 *    zbudowany przed chwila, wiec nie da sie przepuscic zepsutego kodu na starym dist/. To jest
 *    droga dla CI. Koszt: pelny `npm run build` przy kazdym przebiegu.
 *  - WACHTA_E2E_PROD_URL=http://localhost:8083: testy ida na dzialajacy kontener nginx ze stosu
 *    compose. Szybsza (bez budowy) i jedyna, ktora sprawdza prawdziwy nginx i API za proxy - ale
 *    mierzy to, co kontener ma w srodku, a to moze byc stary obraz. To jest droga do pracy lokalnej.
 *
 * `vite preview` odwzorowuje tu nginksowe `try_files $uri /index.html`: na brakujacy /assets/*.mjs
 * oddaje HTTP 200 z index.html i text/html, czyli dokladnie ten sam maskujacy fallback.
 */

const PREVIEW_PORT = 4180;
// Adres i --host musza byc tym SAMYM literalem. Domyslnie `vite preview` slucha na "localhost",
// co na tym Windowsie rozwiazuje sie do ::1, a Playwright odpytywal 127.0.0.1 - port nigdy nie
// odpowiadal i bramka konczyla sie timeoutem webServera po 300 s, nie wynikiem testu.
const PREVIEW_HOST = "127.0.0.1";
const PREVIEW_URL = `http://${PREVIEW_HOST}:${PREVIEW_PORT}`;
const prodUrl = process.env.WACHTA_E2E_PROD_URL;

// Playwright startuje KAZDY wpis webServer niezaleznie od wybranych projektow, wiec wybor czytamy
// sami z linii polecen. Bez tego `--project=prod` podnosilby tez serwer deweloperski (i odwrotnie).
const selected = new Set(
  process.argv.flatMap((arg, i) =>
    arg === "--project" ? [process.argv[i + 1]] : arg.startsWith("--project=") ? [arg.slice("--project=".length)] : [],
  ),
);
const wanted = (project: string) => selected.size === 0 || selected.has(project);

const devServer = {
  command: "npm run dev",
  url: "http://localhost:5173",
  reuseExistingServer: true,
  timeout: 120_000,
};

const previewServer = {
  // Budujemy w komendzie serwera, a nie obok - inaczej bramka moze zmierzyc stary dist/ i przepuscic
  // zepsuty kod. To wlasnie ten scenariusz mamy zamknac.
  command: `npm run build && npm run preview -- --host ${PREVIEW_HOST} --port ${PREVIEW_PORT} --strictPort`,
  url: PREVIEW_URL,
  // Swiadomie bez reuseExistingServer: stary podglad z poprzedniego przebiegu serwowalby stary build.
  reuseExistingServer: false,
  timeout: 300_000,
};

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  use: { viewport: { width: 1600, height: 1000 } },
  projects: [
    {
      name: "dev",
      testMatch: /ui\.spec\.ts/,
      use: { baseURL: "http://localhost:5173" },
    },
    {
      name: "prod",
      testMatch: /prod\.spec\.ts/,
      use: { baseURL: prodUrl ?? PREVIEW_URL },
    },
  ],
  webServer: [
    ...(wanted("dev") ? [devServer] : []),
    ...(wanted("prod") && !prodUrl ? [previewServer] : []),
  ],
});
