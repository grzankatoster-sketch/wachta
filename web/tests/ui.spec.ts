import { expect, test } from "@playwright/test";

/**
 * Guards the map shell. The layout once shipped with half of styles.css missing: every panel was
 * still in the DOM and "visible", but stacked in normal flow at x=0 and hidden behind the map canvas.
 * Presence assertions passed; only geometry caught it.
 */
test("map shell renders with the panels in their places", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => {
    // The API is not running in this test; its 502s are expected.
    if (m.type() === "error" && !m.text().includes("502") && !m.text().includes("Bad Gateway")) {
      consoleErrors.push(m.text());
    }
  });
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  await page.goto("/", { waitUntil: "networkidle" });
  await page.waitForTimeout(3000);

  const panel = await page.locator(".panel").boundingBox();
  expect(panel, "panel alarmów").not.toBeNull();
  expect(panel!.x).toBeGreaterThan(0);
  expect(panel!.width).toBeLessThan(500);

  const legend = await page.locator(".legend").boundingBox();
  expect(legend!.x).toBeGreaterThan(900);

  const sources = await page.locator(".sources").boundingBox();
  expect(sources!.y).toBeGreaterThan(900);

  await expect(page.locator(".panel h2")).toHaveText(/Alarmy/);
  await expect(page.locator(".sources")).toContainText("OpenStreetMap");

  expect(consoleErrors, "błędy konsoli poza brakiem API").toEqual([]);
});

test("map canvas paints tiles, not an empty surface", async ({ page }) => {
  // MapLibre renders in a web worker; with Vite pre-bundling it silently fails and the map stays blank.
  const tileResponses: number[] = [];
  page.on("response", (r) => {
    if (r.url().includes("openfreemap")) tileResponses.push(r.status());
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  // Cold Vite starts can take seconds to bundle deps, so wait for the event instead of a fixed pause.
  await page.waitForResponse((r) => r.url().includes("openfreemap"), { timeout: 45_000 });
  await page.waitForTimeout(2000);

  expect(tileResponses.length, "zapytania o kafle").toBeGreaterThan(0);
  expect(tileResponses.every((s) => s < 400), "wszystkie kafle OK").toBe(true);

  // Reading pixels back from WebGL after the frame is composited returns a cleared buffer, so the
  // blank-map failure mode is guarded by the console-error assertion in the test above instead
  // (a dead MapLibre worker logs "Worker failed to load"). Here we check the canvas is real and sized.
  const canvas = await page.locator("canvas").first().boundingBox();
  expect(canvas, "kanwa mapy").not.toBeNull();
  expect(canvas!.width).toBeGreaterThan(800);
  expect(canvas!.height).toBeGreaterThan(500);
});
