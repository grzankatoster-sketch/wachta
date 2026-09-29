import type { AlertEvidence } from "./api";

/**
 * A verdict on each alert, with the reasons for it and the reasons against.
 *
 * The detectors answer "does this match the rule". They deliberately do not answer "is this worth
 * anyone's time", because a rule that tried to would need thresholds nobody measured. But a reader
 * looking at sixty alerts does need that second answer, and leaving them to work it out from raw
 * evidence is how a watch board becomes noise.
 *
 * So this is the layer that says it, out loud and attributably: a verdict, how sure it is, what
 * pushed it that way, and what argues the other way. Three rules govern it.
 *
 * First, it reasons ONLY over the evidence the panel already shows above it. Nothing here consults
 * a model, a network or a memory - the same alert always gets the same verdict, and every clause
 * can be checked against a number printed a few lines higher.
 *
 * Second, "przeciw" is never empty. An assessment that lists only supporting facts is advocacy, and
 * the cases this project cares about - a tanker going dark, two hulls alongside at night - are
 * exactly the ones where the innocent explanation is common and the guilty one is expensive to get
 * wrong.
 *
 * Third, when the evidence does not settle it, the verdict is "warte sprawdzenia" with low
 * confidence, which is an honest non-answer. It is not a compromise between two guesses.
 */

export type Werdykt = "rutyna" | "warte-sprawdzenia" | "nietypowe";
export type Pewnosc = "niska" | "srednia" | "wysoka";

export interface Ocena {
  werdykt: Werdykt;
  pewnosc: Pewnosc;
  /** One line, the headline reading. */
  teza: string;
  za: string[];
  przeciw: string[];
  /** What would settle it - the check a human should actually run. */
  coBySprawdzic: string;
}

export const ETYKIETY: Record<Werdykt, string> = {
  rutyna: "Prawdopodobnie rutyna",
  "warte-sprawdzenia": "Warte sprawdzenia",
  nietypowe: "Nietypowe",
};

const liczba = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

const nazwaSluzbowa = (s: unknown): boolean =>
  typeof s === "string" && /\b(PILOT|SVITZER|TUG|BUKSIR|PILOTBOAT|SAR|VTS)\b/i.test(s);

/** Fewer facts, less confidence. Stated as a rule so it is not decided case by case. */
function pewnoscZLiczby(ile: number): Pewnosc {
  return ile >= 3 ? "wysoka" : ile === 2 ? "srednia" : "niska";
}

function d4(ev: AlertEvidence): Ocena {
  const luka = liczba(ev.gap_minutes);
  const odbiorniki = liczba(ev.listeners);
  const rownoczesnie = liczba(ev.simultaneous);
  const wezly = liczba(ev.implied_kt);
  const za: string[] = [];
  const przeciw: string[] = [];

  // Kilka statkow milczacych w tej samej kratce i w tym samym czasie to awaria odbioru, nie decyzja
  // zalogi. To jest jedyny wzorzec w D4, ktory rozstrzyga sam z siebie - dlatego idzie pierwszy.
  if (rownoczesnie !== null && rownoczesnie >= 2) {
    return {
      werdykt: "rutyna",
      pewnosc: rownoczesnie >= 4 ? "wysoka" : "srednia",
      teza: `Cisza najpewniej po stronie odbioru, nie statku: w tym samym czasie zamilkło ${rownoczesnie} innych jednostek w tej samej kratce.`,
      za: [`${rownoczesnie} innych statków zamilkło równocześnie w tym samym miejscu.`],
      przeciw: [
        "Wspólna cisza nie wyklucza, że jeden z tych statków wyłączył transponder celowo — tylko to ukrywa.",
      ],
      coBySprawdzic: "Czy w tej kratce były w tym czasie prace na stacji bazowej albo zła propagacja.",
    };
  }

  if (odbiorniki !== null && odbiorniki >= 8) {
    za.push(`Statek słyszało ${odbiorniki} odbiorników — przy tylu świadkach zanik zasięgu jest mało prawdopodobny.`);
  } else if (odbiorniki !== null) {
    przeciw.push(`Tylko ${odbiorniki} odbiorników słyszało ten statek, więc zwykła utrata zasięgu jest w grze.`);
  }

  if (luka !== null && luka >= 60) za.push(`Cisza trwała ${Math.round(luka)} min — długo jak na chwilowy zanik.`);
  else if (luka !== null) przeciw.push(`Cisza trwała tylko ${Math.round(luka)} min.`);

  if (rownoczesnie === 0) za.push("Żaden inny statek w tej kratce nie zamilkł w tym czasie.");

  if (wezly !== null && wezly > 30) {
    przeciw.push(`Prędkość wynikająca z przeskoku pozycji to ${wezly.toFixed(1)} w. — dla statku niemożliwa, więc dane mogą być błędne.`);
  }

  przeciw.push("Cisza w AIS wygląda identycznie przy wyłączonym transponderze i przy awarii urządzenia.");

  const mocne = za.length;
  return {
    werdykt: mocne >= 2 ? "nietypowe" : "warte-sprawdzenia",
    pewnosc: pewnoscZLiczby(mocne),
    teza: mocne >= 2
      ? "Cisza wygląda na decyzję, a nie na zanik zasięgu — warto sprawdzić, dokąd ten statek szedł."
      : "Za mało przesłanek, żeby odróżnić wyłączony transponder od utraty zasięgu.",
    za: za.length ? za : ["Brak przesłanek przemawiających za celowym wyłączeniem."],
    przeciw,
    coBySprawdzic: "Czy w luce statek pojawił się w innym źródle (zdjęcia satelitarne, port docelowy, kolejny odbiornik).",
  };
}

function d5(ev: AlertEvidence): Ocena {
  const minuty = liczba(ev.duration_minutes);
  const dystans = liczba(ev.min_distance_km);
  const sluzbowa = nazwaSluzbowa(ev.name) || nazwaSluzbowa(ev.mmsi);
  const za: string[] = [];
  const przeciw: string[] = [];

  if (sluzbowa) {
    return {
      werdykt: "rutyna",
      pewnosc: "srednia",
      teza: "Jedna z jednostek ma nazwę służbową (pilot, holownik) — to wygląda na normalną pracę portu.",
      za: ["Nazwa wskazuje na jednostkę pilotową albo holownik, a te z definicji podchodzą burta w burtę."],
      przeciw: ["Nazwa w AIS jest wpisywana przez załogę i nie jest dowodem na rolę jednostki."],
      coBySprawdzic: "Czy jednostka figuruje w rejestrze usług portowych dla tego akwenu.",
    };
  }

  if (minuty !== null && minuty >= 120) za.push(`Postój burta w burtę trwał ${Math.round(minuty)} min — dłużej, niż zajmuje pilotaż czy bunkrowanie.`);
  else if (minuty !== null) przeciw.push(`Spotkanie trwało ${Math.round(minuty)} min, co mieści się w czasie zwykłych czynności portowych.`);

  if (dystans !== null && dystans <= 0.15) za.push(`Kadłuby dzieliło ${Math.round(dystans * 1000)} m — odległość, przy której przeładunek jest fizycznie możliwy.`);

  przeciw.push("Sama bliskość dwóch kadłubów nie mówi, czy cokolwiek przeładowano.");
  przeciw.push("Z doby duńskiego ruchu 12 451 spotkań zostało 11 po odsianiu kotwicowisk i jednostek służbowych — większość bliskich spotkań jest legalna.");

  const mocne = za.length;
  return {
    werdykt: mocne >= 2 ? "nietypowe" : "warte-sprawdzenia",
    pewnosc: pewnoscZLiczby(mocne),
    teza: mocne >= 2
      ? "Długi postój dwóch kadłubów przy sobie poza kotwicowiskiem — kształt zgodny z przeładunkiem."
      : "Spotkanie mieści się w tym, co robi normalny ruch — bez dodatkowych danych nie ma tu wniosku.",
    za: za.length ? za : ["Spotkanie spełniło próg reguły, ale żadna z jego cech nie wyróżnia go dodatkowo."],
    przeciw,
    coBySprawdzic: "Czy któryś z tych kadłubów jest na listach sankcyjnych i czy ich zanurzenie zmieniło się po spotkaniu.",
  };
}

function d6(ev: AlertEvidence): Ocena {
  const przesuniecie = liczba(ev.shift_km);
  const rozrzut = liczba(ev.course_spread_deg);
  const wezly = liczba(ev.mean_sog_kn);
  const za: string[] = [];
  const przeciw: string[] = [];

  if (przesuniecie !== null && przesuniecie >= 1) za.push(`Statek przesunął się o ${przesuniecie.toFixed(1)} km, mimo że nie robił drogi.`);
  if (rozrzut !== null && rozrzut >= 40) za.push(`Kurs wahał się o ${Math.round(rozrzut)}° — tak zachowuje się jednostka ciągnięta, nie sterowana.`);
  if (wezly !== null && wezly <= 2) za.push(`Średnia prędkość ${wezly.toFixed(1)} w. — za wolno na tranzyt, za szybko na leżącą kotwicę.`);

  przeciw.push("Wolny, kluczący kurs blisko kabla ma dziesiątki niewinnych przyczyn: pogoda, prąd, pilot na pokładzie, awaria silnika.");
  przeciw.push("Trasy kabli w OpenStreetMap są przybliżone — „blisko linii” znaczy blisko tego, co ktoś narysował.");

  const mocne = za.length;
  return {
    werdykt: mocne >= 3 ? "nietypowe" : mocne >= 1 ? "warte-sprawdzenia" : "rutyna",
    pewnosc: pewnoscZLiczby(mocne),
    teza: mocne >= 3
      ? "Wszystkie trzy cechy wleczonej kotwicy naraz, w pobliżu infrastruktury podwodnej."
      : "Pojedyncza cecha wleczenia — to za mało, żeby odróżnić awarię od zamiaru, a pogodę od obu.",
    za: za.length ? za : ["Reguła zadziałała, ale żadna z mierzonych cech nie osiągnęła wyraźnego poziomu."],
    przeciw,
    coBySprawdzic: "Jaka była pogoda i stan morza w tym czasie, i czy operator kabla zgłosił uszkodzenie.",
  };
}

function d1(ev: AlertEvidence): Ocena {
  const lotnisko = liczba(ev.nearest_airport_km);
  const zgloszenia = liczba(ev.cell_reports);
  const za: string[] = [];
  const przeciw: string[] = [];

  if (lotnisko !== null && lotnisko <= 15) {
    return {
      werdykt: "rutyna",
      pewnosc: "wysoka",
      teza: `Maszyna zamilkła ${Math.round(lotnisko)} km od lotniska — to wygląda po prostu na lądowanie.`,
      za: [`Najbliższe lotnisko jest ${Math.round(lotnisko)} km stąd.`],
      przeciw: ["Bliskość lotniska nie wyklucza wyłączenia transpondera akurat tam."],
      coBySprawdzic: "Czy ta maszyna pojawiła się ponownie na tym lotnisku w ciągu kilku godzin.",
    };
  }

  if (lotnisko !== null) za.push(`Najbliższe lotnisko jest ${Math.round(lotnisko)} km stąd — na lądowanie to za daleko.`);
  if (zgloszenia !== null && zgloszenia >= 50) za.push(`Z tej kratki normalnie pada ${zgloszenia} zgłoszeń, więc pokrycie odbiorników jest tu dobre.`);

  przeciw.push("Cisza ADS-B to także awaria transpondera, zejście poniżej horyzontu radiowego i zwykła dziura w pokryciu.");

  const mocne = za.length;
  return {
    werdykt: mocne >= 2 ? "nietypowe" : "warte-sprawdzenia",
    pewnosc: pewnoscZLiczby(mocne),
    teza: mocne >= 2
      ? "Maszyna zamilkła daleko od lotniska, w miejscu o dobrym pokryciu — to nie wygląda na zasięg."
      : "Cisza odnotowana, ale nic jej dodatkowo nie wyróżnia.",
    za: za.length ? za : ["Brak cech wyróżniających tę ciszę."],
    przeciw,
    coBySprawdzic: "Czy ten znak wywoławczy pojawił się ponownie, gdzie i po jakim czasie.",
  };
}

function d7(ev: AlertEvidence): Ocena {
  const wezly = liczba(ev.implied_kt);
  return {
    werdykt: wezly !== null && wezly > 60 ? "nietypowe" : "warte-sprawdzenia",
    pewnosc: wezly !== null ? "srednia" : "niska",
    teza: wezly !== null && wezly > 60
      ? `Ten sam numer MMSI w dwóch miejscach naraz — przeskok wymagałby ${Math.round(wezly)} w., co dla statku jest niemożliwe.`
      : "Ten sam numer MMSI zgłoszony z dwóch miejsc.",
    za: wezly !== null ? [`Prędkość wynikająca z przeskoku: ${Math.round(wezly)} w.`] : [],
    przeciw: [
      "Zduplikowany MMSI to najczęściej błąd konfiguracji transpondera albo tani sprzęt, a nie podszywanie się.",
      "Pojedyncza błędna pozycja z zakłóconego odbioru daje ten sam obraz.",
    ],
    coBySprawdzic: "Czy oba ślady mają spójne nazwy i wymiary jednostki, i czy jeden z nich nie urywa się nagle.",
  };
}

/** The assessment for one alert, or null for a detector this layer does not judge yet. */
export function ocen(detektor: string, ev: AlertEvidence): Ocena | null {
  if (detektor === "D1") return d1(ev);
  if (detektor === "D4") return d4(ev);
  if (detektor === "D5") return d5(ev);
  if (detektor === "D6") return d6(ev);
  if (detektor === "D7") return d7(ev);
  return null;
}
