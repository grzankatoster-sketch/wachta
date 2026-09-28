import { expect, test } from "@playwright/test";

/**
 * Gate for the production bundle - the failure mode `dev` structurally cannot see.
 *
 * History: the basemap shipped blank. MapLibre locates its tile worker relative to `import.meta.url`
 * of its own bundle, the bundler hashes that bundle, so `assets/maplibre-gl-worker.mjs` does not
 * exist in dist/ and the SPA fallback answers the request with index.html (HTTP 200!). The worker
 * dies, no vector tile is ever parsed, yet the page loads, the canvas is sized and painted and every
 * presence assertion passes. Only counting the tile traffic separates a live worker from a dead one.
 */

// Kafle wektorowe pobiera WYLACZNIE worker MapLibre. Styl, sprite'y i czcionki ciagnie watek glowny,
// wiec licza sie tak samo przy zywym i martwym workerze - stad wzorzec tylko na /planet/z/x/y.pbf.
const TILE_RE = /tiles\.openfreemap\.org\/planet\/[^/]+\/\d+\/\d+\/\d+\.pbf/;

// Widok BALTIC_VIEW przy 1600x1000 pobiera okolo 12 kafli; martwy worker daje dokladnie 0. Prog
// nizej zostawia zapas na inny rozmiar okna i cache, ale zadne "0" ani "2" go nie przejdzie.
const MIN_TILES = 6;

// Zadanie o plik statyczny odbite jako text/html to podpis fallbacku SPA maskujacego brak pliku.
// Przegladarka nie zglasza tego jako bledu - dostaje HTTP 200 - wiec musimy to wylapac sami.
const ASSET_RE = /\.(m?js|css|json|png|jpe?g|svg|wasm|woff2?)(\?|$)/;

test("production bundle loads the basemap, with no console or network failures", async ({ page, baseURL }) => {
  const tiles: string[] = [];
  const consoleErrors: string[] = [];
  const badResponses: string[] = [];
  const htmlInsteadOfAsset: string[] = [];
  const origin = new URL(baseURL!).origin;

  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e}`));
  page.on("requestfailed", (r) => badResponses.push(`${r.url()} :: ${r.failure()?.errorText}`));
  page.on("response", (r) => {
    const url = r.url();
    if (TILE_RE.test(url)) tiles.push(url);
    if (r.status() >= 400) badResponses.push(`HTTP ${r.status()} ${url}`);
    const isHtml = (r.headers()["content-type"] ?? "").includes("text/html");
    if (isHtml && url.startsWith(origin) && ASSET_RE.test(url)) htmlInsteadOfAsset.push(`${url} -> text/html`);
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  // Nie przerywamy testu na timeoucie: chcemy zebrac komplet diagnostyki, a nie sam blad czekania.
  await page.waitForResponse((r) => TILE_RE.test(r.url()), { timeout: 45_000 }).catch(() => undefined);
  await page.waitForTimeout(3_000);

  // expect.soft zglasza wszystkie naruszenia naraz - przy awarii workera widac od razu i zero kafli,
  // i plik oddany jako HTML, zamiast zgadywac po pierwszym czerwonym assercie.
  expect.soft(tiles.length, "zapytania o kafle wektorowe (martwy worker MapLibre = 0)").toBeGreaterThanOrEqual(MIN_TILES);
  expect.soft(htmlInsteadOfAsset, "pliki statyczne oddane jako index.html (fallback SPA maskuje brak pliku)").toEqual([]);
  expect.soft(consoleErrors, "bledy w konsoli przegladarki").toEqual([]);
  expect.soft(badResponses, "nieudane zapytania sieciowe").toEqual([]);

  // Sanity: strona faktycznie sie zlozyla. Sam ten warunek przechodzil przy pustej mapie, dlatego
  // stoi na koncu jako uzupelnienie, nie jako bramka.
  const canvas = await page.locator("canvas").first().boundingBox();
  expect(canvas, "kanwa mapy").not.toBeNull();
  expect(canvas!.width).toBeGreaterThan(800);
  await expect(page.locator(".panel h2")).toHaveText(/Alarmy/);
});
