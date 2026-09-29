"use strict";

/**
 * WACHTA as a desktop window.
 *
 * The web build is served by nginx inside compose, so the window is a browser pointed at it. What
 * makes this worth writing rather than just bookmarking localhost is everything that has to happen
 * BEFORE there is anything to point at: the Docker engine may be down, the services may not be up,
 * and the first paint may be a minute away. A window that shows white for that minute is the same
 * complaint that started this work - "nothing works, it is just a screenshot".
 *
 * So the window opens on a status page immediately and reports each step as it happens, including
 * the step that failed and why. WACHTA.cmd already did this sequence in batch; this is the same
 * sequence with somewhere to print it.
 *
 * Quitting does NOT stop the containers. This is a watch board: ingestion and the detectors are
 * meant to keep collecting whether or not anyone is looking, and closing a window is not a
 * statement about that. The status page says so, so that it is a decision and not a surprise.
 */

const { app, BrowserWindow, shell, ipcMain } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const PORT_WEB = process.env.WACHTA_WEB_PORT || "8083";
const ADRES = `http://localhost:${PORT_WEB}/`;

const DOCKER = path.join(
  process.env["ProgramFiles"] || "C:\\Program Files",
  "Docker", "Docker", "resources", "bin", "docker.exe",
);
const DOCKER_DESKTOP = path.join(
  process.env["ProgramFiles"] || "C:\\Program Files",
  "Docker", "Docker", "Docker Desktop.exe",
);

/**
 * Where the compose file lives.
 *
 * Unpackaged, that is the repository above this folder. Packaged, the app directory sits wherever
 * the installer put it, so the path is taken from WACHTA_HOME or from a file written at build time;
 * guessing relative to the executable only works for one layout and fails silently in the others.
 */
function korzenProjektu() {
  const kandydaci = [
    process.env.WACHTA_HOME,
    path.resolve(__dirname, ".."),
    path.resolve(path.dirname(app.getPath("exe")), "..", "..", ".."),
  ].filter(Boolean);

  for (const k of kandydaci) {
    if (fs.existsSync(path.join(k, "compose.yaml"))) return k;
  }
  return null;
}

let okno = null;
let ostatniBlad = null;

function powiedz(krok, stan, szczegol) {
  // Takze na stdout. Ekran startowy widzi tylko ten, kto patrzy na okno; kiedy cos pojdzie nie tak
  // na cudzej maszynie albo w tle, jedyne, co zostaje, to log - a diagnoza bez logu to zgadywanie.
  console.log(`[wachta] ${krok}: ${stan}${szczegol ? " - " + szczegol : ""}`);
  if (okno && !okno.isDestroyed()) {
    okno.webContents.send("wachta:krok", { krok, stan, szczegol: szczegol || "" });
  }
}

/** Runs a command and resolves with its exit code and output - never rejects on a non-zero exit. */
function uruchom(plik, argumenty, opcje = {}) {
  return new Promise((resolve) => {
    let wyjscie = "";
    const p = spawn(plik, argumenty, { ...opcje, windowsHide: true });
    p.stdout.on("data", (d) => { wyjscie += d.toString(); });
    p.stderr.on("data", (d) => { wyjscie += d.toString(); });
    p.on("error", (e) => resolve({ kod: -1, wyjscie: e.message }));
    p.on("close", (kod) => resolve({ kod, wyjscie }));
  });
}

const chwila = (ms) => new Promise((r) => setTimeout(r, ms));

async function silnikDziala() {
  const { kod } = await uruchom(DOCKER, ["version", "--format", "{{.Server.Version}}"]);
  return kod === 0;
}

async function stronaOdpowiada() {
  try {
    const odp = await fetch(ADRES, { signal: AbortSignal.timeout(5000) });
    return odp.ok;
  } catch {
    return false;
  }
}

/**
 * The whole start-up, one step at a time, each one reported before it is attempted.
 *
 * Every wait has a ceiling and every ceiling has a message naming the command that would show what
 * went wrong. A start-up that gives up silently is indistinguishable from one that is still working.
 */
async function wstan() {
  ostatniBlad = null;

  const korzen = korzenProjektu();
  if (!korzen) {
    return zawiedz("projekt", "Nie znalazlem compose.yaml. Ustaw zmienna WACHTA_HOME na katalog projektu.");
  }
  powiedz("projekt", "gotowe", korzen);

  if (!fs.existsSync(path.join(korzen, ".env"))) {
    return zawiedz("konfiguracja",
      "Brak pliku .env w katalogu projektu. Skopiuj .env.example do .env i wpisz haslo do bazy.");
  }
  powiedz("konfiguracja", "gotowe", ".env na miejscu");

  powiedz("silnik", "trwa", "sprawdzam Dockera");
  if (!(await silnikDziala())) {
    if (!fs.existsSync(DOCKER_DESKTOP)) {
      return zawiedz("silnik", "Nie znalazlem Docker Desktop. Zainstaluj go albo uruchom silnik recznie.");
    }
    powiedz("silnik", "trwa", "Docker nie odpowiada - uruchamiam Docker Desktop (do 3 minut)");
    spawn(DOCKER_DESKTOP, [], { detached: true, stdio: "ignore", windowsHide: true }).unref();

    let wstal = false;
    for (let i = 0; i < 36; i++) {
      await chwila(5000);
      if (await silnikDziala()) { wstal = true; break; }
      powiedz("silnik", "trwa", `czekam na silnik... ${(i + 1) * 5} s`);
    }
    if (!wstal) {
      return zawiedz("silnik", "Silnik nie wstal w 3 minuty. Otworz Docker Desktop recznie i sprobuj ponownie.");
    }
  }
  powiedz("silnik", "gotowe", "Docker odpowiada");

  powiedz("uslugi", "trwa", "docker compose up -d");
  const { kod, wyjscie } = await uruchom(DOCKER, ["compose", "up", "-d"], { cwd: korzen });
  if (kod !== 0) {
    return zawiedz("uslugi", `Nie udalo sie podniesc uslug.\n${wyjscie.trim().slice(-600)}`);
  }
  powiedz("uslugi", "gotowe", "kontenery wstaly");

  powiedz("dane", "trwa", "czekam, az aplikacja odpowie");
  for (let i = 0; i < 40; i++) {
    if (await stronaOdpowiada()) {
      powiedz("dane", "gotowe", "aplikacja odpowiada");
      return true;
    }
    await chwila(3000);
    powiedz("dane", "trwa", `czekam... ${(i + 1) * 3} s`);
  }
  return zawiedz("dane", `Aplikacja nie odpowiedziala na ${ADRES} w 2 minuty. Sprawdz: docker compose logs web`);
}

function zawiedz(krok, tresc) {
  ostatniBlad = tresc;
  powiedz(krok, "blad", tresc);
  return false;
}

function utworzOkno() {
  okno = new BrowserWindow({
    width: 1500,
    height: 950,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#0d1117",
    title: "WACHTA",
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Okno pokazuje sie dopiero z narysowana trescia - inaczej pierwsza klatka jest biala,
  // a bialy prostokat na ciemnym interfejsie widac nawet przez ulamek sekundy.
  okno.once("ready-to-show", () => okno.show());
  okno.loadFile(path.join(__dirname, "status.html"));

  // Odnosniki do zrodel (adsb.lol, Digitraffic, OpenStreetMap) otwieraja sie w przegladarce,
  // a nie w tym oknie: to jest okno jednej aplikacji, nie przegladarka.
  okno.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  okno.webContents.on("will-navigate", (zdarzenie, url) => {
    if (!url.startsWith(ADRES)) {
      zdarzenie.preventDefault();
      shell.openExternal(url);
    }
  });

  okno.on("closed", () => { okno = null; });
}

async function startuj() {
  if (!(await wstan())) return;
  await chwila(400);            // zeby ostatni krok zdazyl sie pokazac jako zrobiony

  // Pamiec podreczna czyszczona przy kazdym starcie.
  //
  // Okno jest powloka wokol aplikacji, ktora przebudowuje sie po kilka razy dziennie. Vite hashuje
  // nazwy plikow, wiec stary index.html w cache wskazuje na pliki, ktorych juz nie ma - albo, gorzej,
  // pokazuje poprzednia wersje i wyglada to jak blad w aplikacji, a nie jak nieaktualny cache.
  // Tak wlasnie zniknely statki: przegladarka miala je, okno pokazywalo wersje sprzed ich dodania.
  // Aplikacja jest lokalna, wiec czyszczenie nic nie kosztuje.
  try {
    await okno.webContents.session.clearCache();
  } catch (e) {
    console.warn("Nie udalo sie wyczyscic pamieci podrecznej:", String(e).slice(0, 120));
  }

  // Naglowki skladane z tablicy, a nie wpisane w jeden literal: extraHeaders rozdziela je znakiem
  // nowej linii, a nowa linia wpisana wprost w napis rozbija plik. Raz juz rozbila.
  const bezCache = ["pragma: no-cache", "Cache-Control: no-cache"].join("\n") + "\n";
  await okno.loadURL(ADRES, { extraHeaders: bezCache });
  console.log(`[wachta] widok: zaladowany - ${ADRES}`);
}

// Sterownik grafiki, wybrany pomiarem, nie domyslem.
//
// Domyslna konfiguracja dawala na tej maszynie czarne okno: proces GPU ginal z naruszeniem ochrony
// pamieci (-1073741819), a mapa jest w WebGL, wiec nie zostawalo nic do pokazania. Pierwsza proba -
// wylaczenie kompozycji GPU - rysowala, ale proces GPU nadal ginal i okno czernialo po chwili.
//
// Zmierzone na uruchomionej aplikacji (probka-gpu.js, srednia jasnosc pikseli i udzial pikseli
// jasniejszych od tla, 1264x735):
//
//   brak przelacznikow                17.7   0.0 %   GPU padl   <- czarne okno
//   disable-gpu-compositing + d3d11  164.5  71.3 %   GPU padl   <- rysuje, ale nadal padal
//   use-angle=gl                     161.9  70.6 %   GPU zyje   <- to
//   use-angle=d3d11                   17.7   0.0 %   GPU padl
//   disable-gpu-sandbox               17.7   0.0 %   GPU padl
//
// ANGLE przez OpenGL zamiast przez Direct3D 11 jest jedynym wariantem, w ktorym proces GPU w ogole
// nie ginie, przy tej samej jakosci rysowania.
app.commandLine.appendSwitch("use-angle", "gl");

app.whenReady().then(() => {
  utworzOkno();
  okno.webContents.once("did-finish-load", startuj);

  ipcMain.handle("wachta:ponow", async () => {
    await okno.loadFile(path.join(__dirname, "status.html"));
    await startuj();
  });
  ipcMain.handle("wachta:blad", () => ostatniBlad);

  // Gdyby mimo wszystko padl: czarne okno to najgorsza z mozliwych odpowiedzi, bo wyglada jak
  // zawieszenie aplikacji, a nie jak awaria sterownika. Przeladowanie odtwarza kontekst WebGL.
  app.on("child-process-gone", (_zdarzenie, szczegoly) => {
    if (szczegoly.type !== "GPU" || !okno || okno.isDestroyed()) return;
    console.warn(`Proces GPU zginal (${szczegoly.reason}) - przeladowuje widok.`);
    okno.webContents.reload();
  });

  okno.webContents.on("render-process-gone", (_zdarzenie, szczegoly) => {
    console.warn(`Proces renderera zginal (${szczegoly.reason}) - przeladowuje widok.`);
    if (okno && !okno.isDestroyed()) okno.reload();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) utworzOkno();
  });
});

app.on("window-all-closed", () => {
  // Kontenery zostaja. Detektory i pobieranie danych maja chodzic niezaleznie od tego,
  // czy ktos patrzy - zamkniecie okna nie jest decyzja o zatrzymaniu obserwacji.
  app.quit();
});
