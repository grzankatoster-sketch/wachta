import { useEffect, useState } from "react";
import type { MapViewState } from "@deck.gl/core";
import { getJSON, type AlertDto, type JammingDto, type ReplayPath } from "./api";
import { AlertsPanel } from "./components/AlertsPanel";
import { BALTIC_VIEW, MapView } from "./components/MapView";
import { ReplayBar } from "./components/ReplayBar";
import { SearchPanel } from "./components/SearchPanel";
import { DetailPanel } from "./components/DetailPanel";
import { Warstwy } from "./components/Warstwy";
import { SourcesFooter } from "./components/SourcesFooter";
import { aircraftLayers } from "./layers/aircraft";
import { shipLayers } from "./layers/ships";
import { alertsLayer } from "./layers/alerts";
import { jammingLayer } from "./layers/jamming";
import { tripsLayer } from "./layers/trips";
import { infrastructureLayers } from "./layers/infrastruktura";
import { useInfrastruktura } from "./infrastruktura";
import { sladLayers } from "./layers/slad";
import { wyborLayers } from "./layers/wybor";
import { useSladStatku } from "./uzyj-sladu";
import { isCargo } from "./colors";
import { kategoriaSamolotu, kategoriaStatku, obecne } from "./typy";
import { useLive } from "./live";
import { useZegar } from "./zegar";
import { najnowszy, zegarDanych } from "./ruch";
import { replayBounds, toTrips, type Trip } from "./replay";
import { selectionFromPicked, zbudujSzczegoly, type Selection } from "./detail";
import { stanDanych, WSZYSTKO_WIDOCZNE, type Widoczne } from "./warstwy";

export default function App() {
  const { aircraft, ships, alerts, setAlerts, connected, odebranoSamoloty, odebranoStatki } = useLive();
  const [jamming, setJamming] = useState<JammingDto[]>([]);
  const [view, setView] = useState<MapViewState>(BALTIC_VIEW);
  const [replay, setReplay] = useState<{ trips: Trip[]; start: number; max: number } | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [widoczne, setWidoczne] = useState<Widoczne>(WSZYSTKO_WIDOCZNE);
  const [wybrany, setWybrany] = useState<Selection | null>(null);
  // Przebyta trasa wybranego statku: skad przyplynal (patrz slad.ts). Null dla wszystkiego innego.
  const slad = useSladStatku(wybrany);

  useEffect(() => {
    getJSON<AlertDto[]>("/api/alerts").then(setAlerts).catch(() => undefined);
    const load = () => getJSON<JammingDto[]>("/api/jamming").then(setJamming).catch(() => undefined);
    load();
    const id = setInterval(load, 10 * 60 * 1000);
    return () => clearInterval(id);
  }, [setAlerts]);

  useEffect(() => {
    if (!playing || !replay) return;
    const id = setInterval(() => setCurrentTime((t) => (t + 60 > replay.max ? 0 : t + 60)), 100);
    return () => clearInterval(id);
  }, [playing, replay]);

  const toggleReplay = async () => {
    if (replay) {
      setReplay(null);
      setPlaying(false);
      return;
    }
    const to = new Date();
    const from = new Date(to.getTime() - 6 * 3600 * 1000);
    const paths = await getJSON<ReplayPath[]>(
      `/api/replay?from=${from.toISOString()}&to=${to.toISOString()}&militaryOnly=true`,
    );
    const bounds = replayBounds(paths);
    if (!bounds) return;
    setReplay({ trips: toTrips(paths, bounds.start), start: bounds.start, max: bounds.end - bounds.start });
    setCurrentTime(0);
    setPlaying(true);
  };

  // Filtrujemy DANE, nie warstwy: warstwa bez danych nadal sie rysuje (i nadal lapie klikniecia),
  // a pusta lista znika z mapy calkowicie. Dzieki temu wylaczenie w panelu znaczy to, co widac.
  const widoczneSamoloty = aircraft.filter((a) =>
    a.isMilitary ? widoczne.wojskowe : widoczne.cywilne);
  const widoczneStatki = ships.filter((s) =>
    isCargo(s.shipType) ? widoczne.ladunek : widoczne.statki);
  const infrastruktura = useInfrastruktura(widoczne.infrastruktura);
  const widoczneLinie = widoczne.infrastruktura ? infrastruktura : [];
  const widoczneAlarmy = widoczne.alarmy ? alerts : [];
  const widoczneZaklocenia = widoczne.zaklocenia ? jamming : [];

  // Zegar mapy. Tyka 10 razy na sekunde i przesuwa znaczniki miedzy odczytami - bez tego samolot
  // stoi minute, a potem przeskakuje 14 km naraz. Czas liczymy na ZEGARZE DANYCH: najnowszy
  // znacznik z paczki plus to, ile realnie uplynelo od jej odebrania. Dzieki temu rozjechany zegar
  // w przegladarce nie oznacza calego ruchu jako przestarzaly.
  const tik = useZegar(10);
  const najnowszySamolot = najnowszy(aircraft.map((a) => a.ts));
  const najnowszyStatek = najnowszy(ships.map((s) => s.ts));
  const terazSamoloty = najnowszySamolot === null ? tik : zegarDanych(najnowszySamolot, odebranoSamoloty, tik);
  const terazStatki = najnowszyStatek === null ? tik : zegarDanych(najnowszyStatek, odebranoStatki, tik);

  // Wiek najswiezszej pozycji. Wczesniej szlo tu null, wiec zdanie o swiezosci nigdy sie nie
  // pokazywalo - mapa wygladala tak samo, czy dane mialy 5 sekund, czy przyszly ostatni raz kwadrans
  // temu. Brak danych zostaje nullem: "nie wiem, ile to ma lat" to nie to samo co "jest swieze".
  // Liczony z OBU zrodel. Samoloty przychodza co kilka sekund, statki co kilkadziesiat; branie
  // wieku z samych samolotow mowiloby "sprzed chwili" takze wtedy, gdy AIS milczy od kwadransa.
  const znaczniki = [...aircraft.map((a) => a.ts), ...ships.map((s) => s.ts)];
  const sekundOdOdczytu = znaczniki.length
    ? Math.max(0, Math.round((Date.now() - Math.max(...znaczniki.map(Date.parse))) / 1000))
    : null;

  const liczby = {
    wojskowe: aircraft.filter((a) => a.isMilitary && !a.onGround).length,
    cywilne: aircraft.filter((a) => !a.isMilitary && !a.onGround).length,
    ladunek: ships.filter((s) => isCargo(s.shipType)).length,
    statki: ships.filter((s) => !isCargo(s.shipType)).length,
    infrastruktura: infrastruktura.length,
    alarmy: alerts.length,
    zaklocenia: jamming.length,
  };

  // Klucz wypisuje tylko to, co naprawde jest na ekranie - i liczy z DANYCH WIDOCZNYCH, nie ze
  // wszystkich, zeby wylaczenie warstwy znikalo takze z klucza.
  const kategorie = {
    powietrze: obecne(widoczneSamoloty.filter((a) => !a.onGround).map(kategoriaSamolotu)),
    morze: obecne(widoczneStatki.map(kategoriaStatku)),
  };

  const layers = replay
    ? [jammingLayer(widoczneZaklocenia), ...infrastructureLayers(widoczneLinie),
       tripsLayer(replay.trips, currentTime), alertsLayer(widoczneAlarmy)]
    : [
        jammingLayer(widoczneZaklocenia),
        // Kolejnosc od dna: infrastruktura lezy na dnie od lat, slad wybranego statku jest nad nia,
        // a znaczniki ruchu na wierzchu. Odwrotna kolejnosc chowalaby to, co sie rusza, pod tym,
        // co stoi w miejscu.
        ...infrastructureLayers(widoczneLinie),
        // Slad pod znacznikami: to tlo dla wybranego statku, nie kolejny obiekt do klikania.
        ...sladLayers(slad),
        // Statki pod samolotami: jest ich osiem razy wiecej i sa mniejsze, wiec lezac na wierzchu
        // zabieraly by klikniecia maszynom, ktorych i tak jest na mapie garstka.
        ...shipLayers(widoczneStatki, terazStatki),
        ...aircraftLayers(widoczneSamoloty, terazSamoloty),
        alertsLayer(widoczneAlarmy),
        // Na samym wierzchu: co jest wybrane i czego ten wybor dotyczy. Bez tego klikniecie alarmu
        // centrowalo mape na lawicy jednakowych pierscieni i czytelnik nie wiedzial, ktory jest ten.
        ...wyborLayers(wybrany, ships),
      ];

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <MapView
        layers={layers}
        viewState={view}
        onViewStateChange={setView}
        onObjectClick={(o) => setWybrany(selectionFromPicked(o))}
      />
      {wybrany && <DetailPanel szczegoly={zbudujSzczegoly(wybrany, slad)} onClose={() => setWybrany(null)} />}
      <SearchPanel />
      <div className="lewa-kolumna">
        <header className="naglowek">
        <h1>WACHTA</h1>
        <p>
          Co widać z danych publicznych: ruch lotniczy i morski, zakłócenia GPS, oraz miejsca, które
          własne detektory uznały za warte sprawdzenia. Każdy alarm jest <b>kandydatem do
          sprawdzenia</b>, nigdy wyrokiem.
        </p>
        {/* Kropka pulsuje tylko przy polaczeniu. To jedyny element interfejsu, ktory sie rusza
            sam z siebie - i wlasnie dlatego niesie informacje: jak stoi, to znaczy, ze stoi. */}
        <p className={`stan ${connected ? "zywe" : "martwe"}`}>
          <span className="puls" aria-hidden="true" />
          <span>
            {stanDanych(connected, liczby.wojskowe + liczby.cywilne,
                        liczby.ladunek + liczby.statki, sekundOdOdczytu)}
          </span>
        </p>
        </header>
        <Warstwy widoczne={widoczne} onZmiana={setWidoczne} liczby={liczby} kategorie={kategorie} />
        <AlertsPanel
          alerts={alerts}
          polaczone={connected}
          wybranyId={wybrany?.kind === "alert" ? wybrany.data.id : null}
          onSelect={(a) => {
            // Lista otwiera ten sam panel co klikniecie w mape. Wczesniej robila tylko setView, wiec
            // analiza - "co to jest, co z tego wynika, na jakiej podstawie" - byla dostepna wylacznie
            // przez trafienie mysza w kilkupikselowy znacznik na canvasie deck.gl. Bez myszy nie bylo
            // jej wcale, a przy kilku alarmach w jednym miejscu trafialo sie w sasiada.
            setView({ ...view, longitude: a.lon, latitude: a.lat, zoom: 8 });
            setWybrany({ kind: "alert", data: a });
          }}
        />
      </div>
      <ReplayBar
        active={!!replay}
        onToggle={toggleReplay}
        currentTime={currentTime}
        max={replay?.max ?? 0}
        setCurrentTime={setCurrentTime}
        playing={playing}
        setPlaying={setPlaying}
        startEpoch={replay?.start ?? null}
      />
      <SourcesFooter />
    </div>
  );
}
