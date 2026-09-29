"use strict";

/**
 * A test rig for one question: which GPU switches let this window actually draw the map?
 *
 * Disabling GPU compositing stopped the GPU process from crashing and produced a black window
 * instead, which is not an improvement - the map is WebGL, and a renderer with nowhere to composite
 * to paints nothing. Guessing a second time would be the same mistake, so this measures.
 *
 * It launches with whatever switches WACHTA_PRZELACZNIKI names, loads the running app, waits for it
 * to settle, captures what the compositor actually produced, and prints the mean brightness of the
 * pixels plus how many of them are not background. A black window scores near zero on both; a drawn
 * map scores high on both. Run per configuration, compare, keep the winner.
 *
 * Kept rather than deleted: the answer is driver-specific, so the next machine - or the next driver
 * update on this one - may need the table rebuilt. Run:
 *
 *   WACHTA_PRZELACZNIKI="use-angle=gl" electron probka-gpu.js
 *
 * with the app already serving, once per configuration, and compare.
 */

const { app, BrowserWindow } = require("electron");

const PRZELACZNIKI = (process.env.WACHTA_PRZELACZNIKI || "").split(",").map((s) => s.trim()).filter(Boolean);
const ADRES = process.env.WACHTA_ADRES || "http://localhost:8083/";
const CZEKAJ_MS = Number(process.env.WACHTA_CZEKAJ || 16000);

for (const p of PRZELACZNIKI) {
  const [nazwa, wartosc] = p.split("=");
  if (wartosc === undefined) app.commandLine.appendSwitch(nazwa);
  else app.commandLine.appendSwitch(nazwa, wartosc);
}

let bladGpu = false;
app.on("child-process-gone", (_e, szczegoly) => {
  if (szczegoly.type === "GPU") bladGpu = true;
});

app.whenReady().then(async () => {
  const okno = new BrowserWindow({
    width: 1280, height: 800, show: false, backgroundColor: "#0d1117",
    webPreferences: { offscreen: false },
  });

  try {
    await okno.loadURL(ADRES);
  } catch (e) {
    console.log(JSON.stringify({ przelaczniki: PRZELACZNIKI.join(" ") || "(brak)", blad: String(e).slice(0, 120) }));
    app.exit(0);
    return;
  }

  await new Promise((r) => setTimeout(r, CZEKAJ_MS));

  const obraz = await okno.webContents.capturePage();
  const { width, height } = obraz.getSize();
  const bitmapa = obraz.toBitmap();               // BGRA

  let suma = 0;
  let jasnych = 0;
  const pikseli = width * height;
  for (let i = 0; i < bitmapa.length; i += 4) {
    const j = (bitmapa[i] + bitmapa[i + 1] + bitmapa[i + 2]) / 3;
    suma += j;
    if (j > 60) jasnych++;                        // tlo interfejsu to #0d1117, czyli ok. 18
  }

  console.log(JSON.stringify({
    przelaczniki: PRZELACZNIKI.join(" ") || "(brak)",
    rozmiar: `${width}x${height}`,
    srednia_jasnosc: Math.round((suma / pikseli) * 10) / 10,
    udzial_jasnych: Math.round((jasnych / pikseli) * 1000) / 10,
    gpu_padl: bladGpu,
  }));

  app.exit(0);
});
