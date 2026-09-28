# Stan projektu — 2026-09-26, praca nocna

Repozytorium stoi, front działa i jest przetestowany w przeglądarce. Wszystko, czego dało się
dotknąć bez uprawnień administratora i bez Twoich kluczy API, jest zrobione i zweryfikowane.

## Zielone (sprawdzone uruchomieniem)

| Co | Wynik |
|---|---|
| Detektory w Pythonie (D1, D3, pokrycie, geo, lotniska) | **36 testów** przechodzi, także przez `uv run` (jak w kontenerze i CI) |
| Bramka jakości ewaluacji | 4 testy: detektor zwracający pustkę dostaje recall 0, detektor flagujący wszystko — precyzję 0,5 |
| Front: testy jednostkowe | 4 testy (kolory, przeliczanie odtwarzania) |
| Front: kontrola typów i budowa | `tsc -b && vite build` bez błędów, cały kod mapy z planu kompiluje się |
| Front: testy w przeglądarce (Playwright) | 2 testy dymne, obie mutacje wykryte (patrz niżej) |
| Mapa w działaniu | zrzut: `docs/screenshots/mapa-dev.png` — Bałtyk, panel alarmów, legenda GPS, pasek odtwarzania, stopka źródeł |
| Zależności Pythona | `uv.lock` wygenerowany |
| Geometria infrastruktury (wejście dla D6, faza morska) | moduł `infrastructure.py` + 7 testów: odległość statku od kabla, wybór najbliższej linii, wczytywanie GeoJSON |

Jedna komenda na wszystkie kontrole: `scripts\check.ps1` (pomija to, czego nie da się uruchomić, i mówi dlaczego).
Stan środowiska: `scripts\bootstrap.ps1`.

## Co znalazłem i naprawiłem w nocy

1. **Połowa arkusza stylów nie istniała.** Wyciągając kod z planu wziąłem tylko wersję bazową
   `styles.css` — bez reguł panelu, legendy, paska i stopki. Efekt: wszystkie elementy były w DOM
   i „widoczne”, ale leżały w zwykłym przepływie na `x=0`, schowane pod kanwą mapy. Testy obecności
   by tego nie wykryły; złapała to dopiero asercja geometrii. Plan poprawiony — ma teraz jeden
   kompletny plik CSS zamiast trzech fragmentów „dopisz”.
2. **Mapa była pusta mimo poprawnych zapytań o kafle (HTTP 200).** MapLibre renderuje w web workerze,
   a prebundlowanie zależności przez Vite psuje jego adres: „Worker failed to load”. Naprawa:
   `optimizeDeps: { exclude: ["maplibre-gl"] }` w `vite.config.ts`. Bez tego cały front wyglądałby
   na zepsuty przy pierwszym uruchomieniu.
3. **Testy UI sprawdzone mutacjami** — usunięcie reguły `.panel` i przywrócenie błędu workera
   wywalają zestaw. Test, który niczego nie łapie, jest gorszy niż brak testu.
4. **`bootstrap.ps1` kłamał** przy pierwszym podejściu (pokazywał .NET SDK i WSL2 jako obecne).
   Poprawione: sprawdza `dotnet --list-sdks` i kod wyjścia `wsl --status`.

## Linia frontu, dwie wersje i anomalie — mapa obejmuje teraz świat

**Linia frontu (DeepStateMap).** 109 obszarów: 25 okupowanych, 53 wyzwolone, 31 o nieznanym statusie.
Ich znaczniki statusu są niekonsekwentne (wyzwolone to w danych `status.dismissed`), więc klasyfikacja
mapuje je jawnie. Źródło nie podaje licencji — używam lokalnie z atrybucją, a **przed publicznym demem
trzeba zapytać autorów o zgodę**; to zastrzeżenie jest też w SOURCES.md.

**Dwie wersje.** Moduł `versions.py` (20 testów) czyta plik wzmianek GDELT: dla każdego artykułu
domenę, język oryginału i wydźwięk. Po sklejeniu powtórzeń w jedno wydarzenie porównuje, **jak opisały
je strony**. Dwa pomiary, które ukształtowały ten moduł:

- W podstawowym strumieniu GDELT tylko 9% wzmianek pochodzi z redakcji, którą da się przypisać do
  strony, a rosyjskich i ukraińskich mediów praktycznie nie ma. W **strumieniu tłumaczeniowym** jest
  35%, z prawdziwym RU, UA i PL — tam mieszka druga wersja historii.
- Przy wymaganiu dwóch artykułów na stronę w całym świecie zostawały **3** porównywalne wydarzenia na
  4 godziny; przy jednym artykule — **22**. Więc próg to jeden artykuł, ale każde takie porównanie jest
  oznaczone jako „cienka podstawa”.

Z 12 godzin: 55 wydarzeń opisanych przez co najmniej dwie strony. Przykład: groźba Putina —
rosyjskie media ton −5,8, zachodnie +0,9, różnica 6,7. Ton to cecha tekstu, nie dowód, kto ma rację.

**Anomalie (D8).** Moduł `anomalies.py` (16 testów) szuka miejsc, które **łamią własny rytm**:
liczba doniesień w oknie kontra własne tło miejsca, oceniana **prawdopodobieństwem Poissona**, nie
krotnością. Kijów zawsze ma więcej doniesień niż Tallin i to nie jest anomalia. Na 18 godzinach danych
z całego świata: 70 860 zdarzeń, **58 nietypowych skupisk**, na czele Colombo (28 zdarzeń przy 1,5
spodziewanych), Tovuz na granicy ormiańsko-azerbejdżańskiej i Ternowa pod Charkowem.

## Warstwa lądowa i wsparcie — mapa nie jest już tylko bałtycka

Dwie nowe warstwy, obie bez klucza API:

**Zdarzenia (GDELT).** Paczka zdarzeń co 15 minut, około 40 KB — cała doba świata to kilka megabajtów.
Moduł `events.py` (12 testów) czyta z niej: kto, komu, co zrobił, gdzie, kiedy i który artykuł tak podaje.
Kody CAMEO tłumaczę na polskie nazwy, ale **nie na twierdzenia** — kod mówi, co doniesiono, nie co się stało.
Powtórzenia (to samo zdarzenie w wielu artykułach) grupuję po dniu, akcji i pozycji; liczba źródeł jest
miarą zasięgu opisu, nie pewności. Z 6 godzin: 2878 zdarzeń w regionie, po zgrupowaniu 2204, w tym 367 konfliktowych.

**Wsparcie dla Ukrainy (Kiel Institute).** 42 darczyńców, **426 mld $ przekazane, w tym 205 mld wojskowe**.
Świadomie biorę wartości *przekazane*, nie *obiecane* — to rozróżnienie zwykle ginie w nagłówkach,
a różnica bywa wielomiliardowa. Największi: USA 131, Komisja i Rada UE 109, Niemcy 35, Wielka Brytania 26,
Kanada 16, Japonia 14, Dania 13, Szwecja 13. Polska 6,7.

Zasięg mapy demo rozszerzony z Bałtyku na Europę i Bliski Wschód.

## Detektor D6 (wleczenie kotwicy nad kablem) — reguła gotowa

`src/python/wachta_detectors/anchor.py` + 18 testów. Reguła: statek w buforze kabla (2 km),
prędkość w oknie 1–7 węzłów (poniżej stoi, powyżej kotwica nie sięgnęłaby dna), epizod co najmniej
15 minut i 5 pozycji, do tego **rozrzut kursu** liczony okrężnie — statek trzymający kurs ma kilka
stopni, wleczony przez kotwicę kilkadziesiąt. Testy pilnują między innymi tego, że przejście przez
północ (359° i 1°) to dwa stopnie różnicy, a nie 358, i że przyspieszenie przerywa epizod na dwa.

**Zmierzone na pełnej dobie duńskiego AIS** (25.12.2024, 510 MB pobrane i przefiltrowane do okolic kabli,
904 statki z trasą): 35 alarmów na dobę dla wszystkich statków (1,46/h — nie do użytku),
ale **tylko 1 alarm na dobę po ograniczeniu do statków handlowych** (0,04/h).
Powód: 26 z 35 alarmów to jednostki robocze przy Ostwind, Kriegers Flak, Fehmarn Belt i Kontek —
pracują nad tymi kablami. To nie jest kwestia progu, tylko tego, kogo detektor w ogóle ogląda.

Czego ten pomiar nie mówi: dane duńskie nie sięgają Zatoki Fińskiej, więc incydentu Eagle S w nich nie ma.
Zmierzony jest poziom szumu, nie czułość.

## Statki z list sankcyjnych przy infrastrukturze (kontekst, nie zarzut)

`eval/feasibility/shadow_near_cables.py` zestawia pozycje statków z listami sankcyjnymi i geometrią kabli.
Odczyt z 26.09, godz. 17:25 UTC, 649 statków w Zatoce Fińskiej: **22 statki z list w promieniu 5 km
od kabla lub rurociągu, w tym 2 z etykietą floty cieni**. Najciekawszy wpis: sankcjonowany tankowiec
SHPINEL w odległości 1,66 km od **HVDC Estlink 2** — tego samego kabla, który uszkodził Eagle S —
przy prędkości 0,5 węzła.

Ta lista jest kontekstem, nie zarzutem, i pokazuje, dlaczego D6 ma takie reguły: większość tych statków
stoi (0,2–0,8 węzła) na kotwicowisku w Zatoce Fińskiej, a nie wlecze niczego. Dlatego detektor wymaga
ruchu 1–7 węzłów **i** błądzącego kursu — samo „blisko kabla i wolno” to opis normalnego kotwicowiska.

## Strona demonstracyjna (bez bazy i bez Dockera)

`docs/demo/index.html` — jeden plik, działa po dwukliku, dane osadzone w środku:
samoloty z jednego odczytu, zakłócenia GPS z zebranej godziny, kable podmorskie z OSM
oraz **649 statków z Zatoki Fińskiej zestawionych z listami sankcyjnymi**.
Wynik zestawienia: 62 statki na listach sankcji lub ryzyka, w tym **6 oznaczonych jako flota cieni**
(BRAVIS, KALLISTIS, SHPINEL i inne) — wszystkie na podejściu do rosyjskich portów.
Buduje ją `python eval/feasibility/build_demo.py`, zrzut: `docs/screenshots/demo.png`.

Po drodze dwa błędy warte zapamiętania:

1. **Warstwa statków renderowała zero obiektów, mimo że źródło miało 649 i nie było żadnego błędu.**
   Przyczyna: warstwa podpisów nie miała podanej czcionki, więc MapLibre poprosił o domyślną
   „Open Sans Regular”, której podkład OpenFreeMap nie ma. Nieudane pobranie glifów wyłączyło
   renderowanie **całego źródła**, także kółek. Samoloty przeżyły tylko dlatego, że ich podpisy były
   odfiltrowane do zera. Naprawa: `"text-font": ["Noto Sans Regular"]` w każdej warstwie tekstowej.
2. **Sama strona nie powie, że jest pusta**, więc buduje ją teraz skrypt z bramką: po zrzucie liczy
   wyrenderowane obiekty w każdej warstwie i przerywa, jeśli któraś jest pusta. To ta bramka złapała
   błąd numer 1, a nie moje oko.

## Detektor D3 przeszedł pierwszy prawdziwy test — i przy okazji się poprawił

1. **Zebrałem godzinę prawdziwych danych** (13 781 pozycji, 14:41–15:37 UTC, zero błędów po
   rozsunięciu zapytań) do `eval/fixtures/d3_hour.json`. To jest fixture, którego wymaga bramka CI.
2. **Pierwszy przebieg wyglądał źle**: 154 z 274 komórek jako „wysokie”, także nad Niemcami i
   środkową Polską. Przyczyna: przy pięciu samolotach w komórce jeden zakłócony daje 20%, więc próg
   10% przekracza szum. Rozkład danych to potwierdził — zakłócone są 13,6% pozycji i skupiają się
   na 56,2°N 21,3°E (wschodni Bałtyk), a nie tam, gdzie świeciła mapa.
3. **Poprawka:** poziom komórki liczy się teraz z **dolnej granicy przedziału ufności Wilsona**
   i wymaga min. 10 samolotów. Efekt zmierzony na tych samych danych: 11 komórek wysokich,
   82% w promieniu 400 km od ogniska (wcześniej 62%), mediana odległości 189 km zamiast 359 km.
4. **Niezależna walidacja:** gpsjam.org publikuje dzienne pliki H3 z liczbą samolotów dobrych
   i zakłóconych — inna implementacja, inny pipeline. Etykiety do ewaluacji pochodzą teraz stamtąd,
   a nie z mojej reguły „150 km od Kaliningradu” (która na tych danych dała **zero** etykiet, bo
   ognisko było 200 km dalej na północ).
   **Wynik: precyzja 0,60, recall 0,75** przy 8 komórkach zakłóconych i 22 czystych.
5. **Bramka sprawdzona na prawdziwych metrykach:** detektor zwracający pustkę oblewa
   (`d3.recall: 0.75 -> 0.0`), obecny kod przechodzi.

Mapa z tej godziny: `docs/screenshots/zaklocenia-gps.png` (wysokie komórki układają się wzdłuż Litwy,
Łotwy i wejścia do Zatoki Fińskiej).

## Dane kabli bałtyckich (wejście dla detektora D6, faza morska)

Zamrożone w `data/infrastructure/baltic_cables.geojson`: 82 odcinków, 56 nazw, w tym
Estlink 1 i 2, C-Lion 1, BCS North, Baltic Connector i Nord Stream — czyli wszystkie linie z incydentów,
na których będzie testowany detektor D6. Źródło: OpenStreetMap (ODbL), skrypt `eval/feasibility/fetch_cables.py`.

Po drodze test złapał **fałszywy alarm mojego własnego testu**: sprawdzał nazwę „Balticconnector”, a OSM
nazywa odcinek podwodny „Baltic Connector” ze spacją. Dopasowanie ignoruje teraz spacje i myślniki.

## Zmierzone limity zewnętrzne (zapisane w planie i w SOURCES.md)

- **adsb.lol odrzuca równoczesne serie zapytań** (HTTP 429). Konfiguracja pobierania w planie miała
  trzy źródła co 15 s — strzelałyby razem. Poprawione: `StartDelaySeconds` (0/10/20) i 30 s dla
  obszarów; doszło pole w `SourceOptions`, opóźnienie startowe w dekoratorze i test na nie.
- **Overpass nie odda całego Bałtyku z geometrią naraz** (504). Pobieranie kabli dzieli obszar na
  cztery części i wysyła jeden warunek na zapytanie.

## Czeka na Ciebie (wymaga uprawnień administratora albo Twoich kont)

```powershell
# 1. WSL2 — PowerShell jako administrator, potem restart komputera
wsl --install --no-distribution

# 2. Docker Desktop i .NET 10 SDK
winget install -e --id Docker.DockerDesktop
winget install -e --id Microsoft.DotNet.SDK.10

# 3. Solution .NET (nie da się wygenerować bez SDK)
cd src\dotnet
dotnet new sln -n Wachta --format sln
dotnet sln add Wachta.Domain Wachta.Db Wachta.Ingestion Wachta.Api Wachta.Tests
dotnet build
dotnet test

# 4. Cały system
cd ..\..
docker compose up -d --build
```

Konta i klucze API (zadanie T0.2 w planie działania): AISStream, OpenSky, NASA FIRMS, Global Fishing
Watch, plus maile do UCDP i airplanes.live. Lista i po co — `docs/SOURCES.md`.
`.env` już istnieje z wylosowanym hasłem do bazy; klucze dopisz obok.

## D2 - tory dyzurne w powietrzu (2026-09-27)

Twoj pierwszy pomysl ("jak leca tankowce w linii to wiadomo, ze cos tankuja") jest w kodzie:
`src/python/wachta_detectors/racetrack.py`, 17 testow.

Detektor odroznia trzy rzeczy: przelot z A do B, **tor wyscigowy** (dyzur) i **krazenie** (okrag).
Pierwsze podejscie mylilo okrag z torem, bo prog oparlem na udziale kierunkow - a dla rownomiernego
okregu ten udzial wynosi 0,444 przy progu 0,45, czyli prog nie mierzyl niczego. Kryterium jest teraz
**najdluzsza prosta noga**: tor ma nogi ponad 25 km, okrag nie ma zadnej. Suma obrotu do tego nie
sluzy - prawoskretny tor kumuluje 360 stopni na okrazenie tak samo jak okrag (jest na to osobny test).

Zmierzone na 47 prawdziwych torach z `/v2/mil`:

| rodzaj samolotu | z wzorcem | sprawdzonych |
|---|---|---|
| tankowiec | 2 | 5 |
| rozpoznanie | 0 | 4 |
| inny | 0 | 36 |
| bez typu | 1 | 2 |

Zero alarmow na 36 zwyklych samolotach - detektor nie zalewa mapy. Czulosci nie znam: nie wiem, ile
z tych 5 tankowcow w ogole pelnilo dyzur, a nie lecialo do bazy. Do tego trzeba listy potwierdzonych
lotow tankowania, ktorej publicznie nie ma.

Najciekawsze trafienie: **AE67DE** - samolot USAF bez typu, bez rejestracji i bez znaku wywolawczego,
**6 godzin 35 minut** na jednej linii na 31 000 ft nad Zatoka Omanska, nogi po 138 km, 9 zawrotow.
Nie podaje o sobie nic poza pozycja, a zachowanie mowi wszystko. To jest odpowiedz na pytanie, po co
ten projekt istnieje.

Zastrzezenie w dymku na mapie i w kodzie: **to ksztalt toru, nie misja.** Tak lata tankowiec na
dyzurze, ale tak samo lata rozpoznanie i samolot czekajacy na lotnisko.

## D4 - podejrzana luka AIS (2026-09-27)

`src/python/wachta_detectors/gaps.py`, 18 testow. Sedno jest to samo co przy D1 dla samolotow:
**luka nie jest dowodem.** Statek znika z AIS glownie dlatego, ze odbiornik go nie slyszy, a nie
dlatego, ze ktos przekrecil wylacznik. Wylaczony transponder wyglada w danych identycznie jak
wyplyniecie poza zasieg.

Dlatego kazda cisza dostaje dwie **osobne** oceny, liczone z tych samych danych:

1. **Odbior** - ilu innych statkow slychac bylo w tej kratce w czasie ciszy (swiadkowie), i czy nie
   zamilkl tam wtedy nikt wiecej naraz (to byloby awaria stacji, nie decyzja zalogi).
2. **Ruch** - predkosc wyliczona z przebytej drogi. Ponizej 2 w. statek stal (port, kotwicowisko).
   Powyzej 30 w. zaden kadlub tego nie zrobil, wiec to blad danych - warto przeczytac, ale to nie
   jest ciemny rejs.

Pierwsze podejscie mialo tylko ocene odbioru i wyplulo 10 przypadkow, z czego wiekszosc to byly
statki **stojace** w Goteborgu i Aalborgu. Rozdzielenie tych dwoch pytan usunelo caly ten smiec.

Pomiar na dobie duńskiego AIS (15,0 mln wierszy, 1740 statkow):

| krok | ile zostaje |
|---|---|
| luki >= 45 min w ruchu | 91 |
| przy czynnym odbiorze | 78 |
| statek naprawde plynal | 72 |
| nie tlumaczy tego wyjscie poza prostokat | **4** |

Cztery alarmy na dobe na 1740 statkow - z tym da sie pracowac.

Osobna pulapka, ktora bylaby cicha porazka pomiaru: fixture zbudowany wczesniej dla D6 zawieral
tylko ruch w poblizu kabli. Statek wyplywajacy poza ten obszar udawalby w nim luke. Dlatego D4
czyta te sama dobe jeszcze raz, prostokatem o granicy, ktora da sie policzyc.

**Znalezisko: STANISLAV GOVORUKHIN** - MMSI 273258520, IMO 9621596, bandera rosyjska, lista
`ua_war_sanctions`. 46 minut ciszy, plynal 11,4 w. tuz przed zaniknieciem, pojawil sie 16,3 km dalej,
a w tym samym czasie w tej samej kratce slychac bylo 12 innych statkow. Pozycja 54,97 N / 13,56 E -
na poludnie od Bornholmu, przy rurociagach. Nazwa z AIS i numer MMSI zgadzaja sie z wpisem na liscie,
wiec to nie jest przypadkowe trafienie po numerze.

Czego to nie dowodzi: awaria transpondera wyglada dokladnie tak samo. Detektor mowi "sprawdz to",
nigdy "ten to zrobil".

## Analizator - co bramka cytowan lapie, a czego nie

`eval/feasibility/analityk.py` daje modelowi lokalnemu 32 ponumerowane fakty z danych i przepuszcza
tylko te zdania, ktore wskazuja na istniejacy numer. Dwa uruchomienia (2026-09-27):

- **Pierwsze**: 11 zdan, 1 odrzucone - "Brak jest danych dotyczacych przyczyn tych zdarzen ani
  intencji stron", zdanie bez odnosnika. Dokladnie po to ta bramka jest.
- **Drugie**, po dodaniu D2 i D4: 10 z 10 przyjetych.

Ale bramka sprawdza **istnienie** odnosnika, nie **zgodnosc** zdania z faktem, na ktory wskazuje. W
drugim przebiegu przeszly dwa zdania wadliwe mimo poprawnych cytowan:

- "Danych o wsparciu finansowym dla Ukrainy nie ma w faktach, jednak podano laczna kwote" - zdanie
  samo sobie przeczy, a fakt [12] podaje te kwote wprost;
- "W Zatoce Finskiej i Dunach zanotowano przypadki milczenia statkow" - D4 liczono na wodach
  dunskich, nie w Zatoce Finskiej.

Czyli bramka odsiewa **zmyslenia**, ale nie **przekrecenia**. Nastepny krok to sprawdzanie zgodnosci
liczb: wyciagnac z kazdego zdania liczby i nazwy wlasne i wymagac, zeby wystepowaly w cytowanym
fakcie. Zgodne z wczesniejszymi pomiarami modelu lokalnego: nadaje sie do szkicu przy gotowej
specyfikacji, nie do prozy, ktora ma byc scisla.

## D5 - przeladunek burta w burte (2026-09-27)

`src/python/wachta_detectors/sts.py`, 17 testow. Trzy warunki, i kazdy z nich dodalem dopiero
dlatego, ze poprzedni wynik byl bezuzyteczny:

| co odsiewam | czym | ile zostaje |
|---|---|---|
| spotkania >= 30 min, blisko i wolno | - | 12 451 |
| kotwicowiska wyprowadzone z ruchu doby | kratka z >= 12 stojacymi statkami | 2 648 |
| statki, ktore nigdy nigdzie nie plynely | predkosc 6 h wokol spotkania | 129 |
| lodzie sluzbowe | typ: para ladunkowiec/tankowiec | **11** |

Drugi krok byl najwazniejszy. Bez niego detektor zwracal 3119 "przeladunkow", a na czele listy staly
kutry rybackie przywiazane do kei przez cale 24 godziny, po 8 metrow od siebie. Przeladunek jest
**zdarzeniem**: statki przyplywaja, staja przy sobie i odplywaja. Keja to **stan**.

Prawie wszystkie 11 par lezy przy Skagen (57,6-57,7 N) - to najwieksze miejsce bunkrowania paliwa w
Europie. Czyli detektor dziala, i jednoczesnie widac jego granice: sam ksztalt zdarzenia nie
odroznia legalnego tankowania paliwa od przeladunku ropy poza rejestrem. Do tego trzeba ladunku,
tras i list.

Blad, ktory znalazlem czytajac wlasny kod przed napisaniem testu: polowiczne sasiedztwo w siatce
gubilo pary lezace po dwoch stronach granicy kratki, gdy porzadek numerow MMSI byl przeciwny do
porzadku kratek. Test na to czerwienieje po przywroceniu tamtej wersji - sprawdzilem mutacja.

## Wykaz to nie to samo co sankcje (poprawka 2026-09-27)

Przy D5 wyszlo cos, co dotyczylo calego projektu. Ponad polowa pliku OpenSanctions maritime to
**inspekcje i zatrzymania portowe** (Tokyo, Paris, Abuja, Black Sea MoU), a nie sankcje. Statek
zatrzymany za przeciekajaca pompe zeznaje o swoim stanie technicznym, a nie o tym, czyj wozi
ladunek.

Mapa pisala "na listach sankcji/ryzyka: 90". Prawda jest taka:

| rodzaj wykazu | statkow |
|---|---|
| listy sankcyjne | 51 |
| protokoly inspekcji portowych | 38 |
| raport badawczy (RUSI) | 1 |

Czyli etykieta byla nieprawdziwa dla 43% tych statkow. `SanctionMatch.category` rozdziela to teraz
na cztery rodzaje, mapa pokazuje rozbicie, a dymek statku mowi wprost, czym jest wykaz, w ktorym go
znaleziono.

## Ciemny STS - zlozenie D4 i D5 (2026-09-27)

`src/python/wachta_detectors/dark_sts.py`, 12 testow. To nie jest nowy pomiar, tylko polaczenie
dwoch, ktore osobno nic nie znacza: **statek stojacy w otwartej wodzie bez widocznego sasiada** i
**cudza niewyjasniona cisza AIS** obok niego, nakladajaca sie w czasie.

Pierwsze podejscie laczylo je po odleglosci (10 km) i bylo bezwartosciowe. Wskazalo holownik
FAIRPLAY-30 stojacy na budowie tunelu Fehmarn - obok niego w ciagu doby zamilkly cztery rozne
statki, bo po prostu przeplywaly ciesnina. Stojacy statek w ruchliwym miejscu ma obok siebie czyjas
cisze co chwile.

Zastapione **testem wykonalnosci drogi**: zgaszony statek musial zdazyc podejsc do stojacego, postac
co najmniej pol godziny i wrocic na trase, wszystko w czasie swojej ciszy. Ta sama arytmetyka co
test brzegu w D4 - liczy sie droga i zegar, nie przeczucie.

| krok | zostaje |
|---|---|
| postoje w miejscu | 1 291 |
| bez widocznego sasiada (D5 ich nie sparowal) | 300 |
| poza kotwicowiskiem i po przyplynieciu | 98 |
| niewyjasnione ciszy AIS w tej dobie (D4) | 63 |
| pary po tescie wykonalnosci drogi | 1 |
| po odrzuceniu jednostek sluzbowych | **0** |

Ta jedna odrzucona to KBV 316, szwedzka straz przybrzezna - jednostka, ktora stoi w miejscu z zawodu.

**Zero jest sprawdzone, nie przyjete na wiare.** Rozluzniajac progi dostaje 1 -> 2 -> 5 -> 8 -> 16,
czyli odpowiedz monotoniczna: lancuch dziala, a zero bierze sie z progow, nie z zepsutego potoku.
To jest wynik, ktory chce miec: w calej dobie ruchu duńskiego nie bylo wiarygodnego ciemnego
przeladunku. Gdyby detektor cokolwiek wskazywal codziennie, nie nadawalby sie do niczego.

Warstwy na mapie nie ma, bo nie ma czego narysowac. Pusta warstwa przeszlaby przez bramke jako
"jest" i to byloby klamstwo.

## D7 - tozsamosc statku (2026-09-27)

`src/python/wachta_detectors/identity.py`, 18 testow. Numer MMSI to nie statek, tylko liczba wpisana
do radia. Jeden kadlub nie moze byc w dwoch miejscach naraz - i to jest cale pytanie.

Detektor rozdziela dwa przypadki, bo wolaja o zupelnie rozna reakcje:

- **bledny punkt** - jedna pozycja poza torem miedzy dwiema spojnymi. Blad dekodowania. Czeste,
  nudne, i nie wolno tego oglaszac jako oszustwa.
- **dwa kadluby** - tor na przemian wraca miedzy oddalonymi skupiskami, a po obu stronach sa
  prawdziwe odcinki spojnego ruchu (min. 3 pozycje kazdy).

**Falszywka, ktora zlapalem dopiero na prawdziwych danych.** Pierwszy przebieg wskazal 5 numerow,
z czego cztery zaczynaly sie od `111`. To jest w standardzie ITU prefiks **statkow powietrznych
SAR** - duńskie smiglowce ratownicze robiace 160 wezlow zgodnie z przeznaczeniem. Moj limit 40 w.
dla kadluba ich po prostu nie dotyczy. Po dodaniu tabeli prefiksow: 5 -> 1.

Wynik na dobie 2024-12-25 (1740 numerow):

| co | ile |
|---|---|
| numery z niemozliwym skokiem pozycji | 27 |
| z tego pojedyncze bledne punkty | 26 |
| z tego "dwa kadluby" | **1** |

Ten jeden to **RAGNA**, MMSI 219006091, prom pasazerski. Przez wiekszosc doby stoi przy nabrzezu
(56.4096, 10.9259) z predkoscia 0,0. Ale o 13:39-13:42 pod tym samym numerem biegnie **spojny
czteropunktowy tor** 40 km dalej, przy 9-14 wezlach, z plynnie narastajaca pozycja. To nie jest
jeden przeklamany punkt - to drugi tor.

Czego to nie dowodzi: odbiornik, ktory pomyli bity w czyjejs wiadomosci, przypisze ja do sasiedniego
numeru i wyglada to identycznie. Krotkie wyskoki w tym samym torze o 03:38-03:40 sa wlasnie tym.

Nazwy okazaly sie slabym sygnalem: tylko jeden numer w calej dobie nadawal wiecej niz jedna nazwe, i
byla to `LANGELAND` kontra `LANGELANDC]6`, czyli przeklamany ciag znakow.

## Blad w bramce zrzutow, ktory ukrywal sie od poczatku

Przy 16 warstwach mapa przestala sie miescic w 30 sekundach i zrzut zaczal padac. Okazalo sie, ze
limit czasu nigdy nie dzialal: `page.waitForFunction(fn, options)` ma sygnature `(fn, arg, options)`,
wiec moje `{ timeout: 90000 }` szlo do funkcji jako jej **parametr**, a limit zostawal domyslny.
Przez caly czas bylo 30 sekund, tylko mapa sie w nich miescila. Poprawione na `(fn, null, {...})`
z odpytywaniem co pol sekundy - domyslna klatka animacji przy tylu warstwach potrafi nie nadejsc.

## Bramka ewaluacji dla nowych detektorow (2026-09-27)

D2, D4, D5 i D7 nie mialy zadnej ochrony przed regresja - kazda zmiana progu mogla po cichu zgasic
detektor, a testy jednostkowe tego nie widza, bo sprawdzaja regule na danych syntetycznych, nie
zachowanie na prawdziwych.

Wycialem trzy male zamrozone fragmenty doby (`eval/feasibility/cut_fixtures.py`), kazdy wokol
przypadku, ktory przeczytalem recznie, **razem z otoczeniem potrzebnym detektorowi**: sam podejrzany
nie dowodzilby niczego, bo D4 potrzebuje swiadkow, D5 potrzebuje kei, ktore ma pominac, a D7
potrzebuje smiglowcow, ktorych nie ma oskarzyc.

| wycinek | co zawiera | rozmiar |
|---|---|---|
| `d4_slice.json` | Bornholm 13-19 UTC, 79 statkow | 1,4 MB |
| `d5_slice.json` | Skagen 6-14 UTC, 234 statki | 7,6 MB |
| `d7_slice.json` | RAGNA + cztery smiglowce SAR + prom | 294 KB |

**To jest bramka regresji, nie jakosci** - i tak jest nazwana w kodzie. Przypadki w niej przeczytalem
i rozumiem, ale nie ma niezaleznego zrodla mowiacego, ktory statek naprawde zgasil transponder.
Te liczby mowia "zachowanie sie nie zmienilo", nigdy "detektor ma racje". Jedynym detektorem z
etykietami spoza projektu pozostaje D3 (gpsjam).

Porownanie jest **doslowne, bez tolerancji**: nie ma tu metryki, ktora moglaby "troche spasc".

Bramka jest udowodniona czterema mutacjami - kazda przywrocona po sprawdzeniu:

| zmiana w kodzie | co zglosila bramka |
|---|---|
| D4: prog swiadkow 3 -> 99 | `found: 2 -> 0` |
| D5: znika warunek "oba statki gdzies plynely" | `cargo_pairs: 2 -> 11`, `offshore: 5 -> 73` |
| D7: znika tabela prefiksow ITU | `two_hulls: 1 -> 5`, z nazwanymi numerami 111xxxxxx |
| D2: prog dlugosci nogi 25 -> 500 km | `tor wyscigowy -> krazenie` |

Przy okazji: pierwsza wersja porownania **w ogole nie weszla do pliku** - podmiana tekstu cicho nie
znalazla wzorca i bramka przepuszczala wszystkie cztery mutacje, zglaszajac zielono. Znalazlem to
tylko dlatego, ze mutacje mialy obowiazek zaswiecic na czerwono. Bramka, ktorej sie nie zmutowalo,
jest wartа tyle co jej brak.

## Warstwa C# wreszcie skompilowana (2026-09-27)

SDK zainstalowany do profilu uzytkownika - bez admina, bez WSL, bez zmian w systemie. Pierwsza w
historii tego kodu kompilacja dala **6 bledow**, wszystkie prawdziwe:

| blad | co bylo nie tak |
|---|---|
| 2x CS8629 w `AdsbV2Parser` | kompilator nie wiaze osobnego `bool hasPosition` z tym, ze `lat` i `lon` nie sa null. Poprawka rozpakowuje je wzorcem `is not { } latitude`, wiec nie-nullowosc **wynika z warunku**, a nie z wykrzyknika, ktory jest obietnica bez pokrycia |
| 4x CS0246 w `Wachta.Api` | `AlertDto`, `JammingDto` i `ReplayPath` byly uzywane w trzech miejscach, ale **nigdy nie powstaly**. Plan podaje ich dokladny ksztalt (linie 3137-3139) - po prostu nie trafily do `Dtos.cs` |

Po nich jeden blad wiecej, z `TreatWarningsAsErrors`: przestarzaly konstruktor `PostgreSqlBuilder()`
w Testcontainers. Obraz idzie teraz do konstruktora i jest stala obok komentarza, dlaczego musi byc
ten sam co w `compose.yaml`.

**Testy: 22 przechodzi, 0 bledow, 13 pominietych.** Poczatkowo 18 z nich **oblewalo** ze stosem
wywolan z Docker.DotNet, bo Testcontainers odpowiada na pytanie "czy jest Docker" rzucajac wyjatkiem.
Osiemnascie czerwonych "nie da sie tu uruchomic" skutecznie chowa te, ktore by cos znaczyly. Dodalem
`DockerFact` i `DockerTheory` - sprawdzaja obecnosc gniazda (`\\.\pipe\docker_engine`) cicho i tanio,
i pomijaja test z czytelnym powodem. `PostgresFixture` buduje kontener dopiero w `InitializeAsync`,
bo samo zbudowanie go szukalo Dockera, zanim ktorykolwiek test zdazyl sie pominac.

## CI, ktore nigdy by nie ruszylo

Przy okazji obejrzalem `azure-pipelines.yml` z dzialajacym lancuchem narzedzi w reku i okazalo sie,
ze to **fragment**: `dependsOn: Test` przy nieistniejacym etapie `Test`, bez `stages:`, bez `pool`,
bez `trigger`. Ten plik nie uruchomilby sie nigdy. Napisany od nowa: etap `Test` (Python, C#, front
rownolegle) i etap `Eval` z bramka detektorow oraz publikacja wynikow jako artefakt.

`scripts/check.ps1` szukal SDK przez systemowy `dotnet.exe`, ktory tutaj jest **samym runtime** -
wiec pomijalby testy C# mimo zainstalowanego SDK. Teraz sprawdza tez `~/.dotnet` i wymaga, zeby
kandydat naprawde widzial jakis SDK, a nie tylko istnial.

Pelny przebieg `scripts/check.ps1`: **WSZYSTKO ZIELONE**.

## Audyt Codeksa i siedem napraw (2026-09-27)

Router skierowal audyt architektury do modelu lokalnego w trybie `debug` z pewnoscia **0,35** (qwen
wpadl w timeout, zeszlo na zapasowy TF-IDF). To zadanie jest na liscie wprost wykluczonych dla
modelu lokalnego - **piaty udokumentowany blad skierowania**. Poszlo zgodnie z polityka: ciezki
odczyt do Codeksa, synteza i decyzje u Claude.

Codex zwrocil **24 znaleziska: 7 HIGH, 13 MED, 4 LOW**, najgesciej w `sts.py` (6) i `gaps.py` (4) -
czyli w kodzie pisanym najszybciej. Kazde HIGH odtworzylem sam przed przyjeciem; **kazda poprawka
ma test dowiedziony mutacja**.

| co bylo nie tak | dlaczego to bolalo |
|---|---|
| `sanctions.py` - kategoryzacja na liscie **wykluczen** | kazdy nieznany wykaz (nowy zbior, literowka) awansowal statek do "sankcjonowanego". Ta sama klasa bledu, ktora ta kategoryzacja miala naprawic |
| `identity.py` - zerowy czas dawal 0 wezlow | dwie pozycje w tej samej sekundzie 300 km od siebie byly "spojne". Wyrzucalem najmocniejszy mozliwy dowod, zeby nie dzielic przez zero |
| `sts.py` - brak pola SOG znaczyl "wolno" | statek pedzacy **21,6 w.** liczyl sie jako stojacy przez 79 minut i mogl utworzyc falszywa pare |
| `sts.py` - staly zasieg siatki | na 75 stopniu para odlegla o 0,63 km znikala przy limicie 0,8 km. **Ten sam blad naprawialem juz w `spatial_index.py`** i powtorzylem go w nowym module |
| `dark_sts.py` - okno z calej ciszy | zglaszalo spotkania, na ktore zgaszony statek zdazylby dopiero po koncu postoju. Okno liczy sie teraz od chwili mozliwego przybycia do chwili, w ktorej trzeba juz ruszac |
| `dark_sts.py` - wykluczanie calego MMSI | jedno bunkrowanie rano skreslalo statek na cala dobe i moglo ukryc niezalezny ciemny przeladunek wieczorem |
| `gaps.py` - licznik awarii z samych kandydatow | statki stojace pod stacja nie przechodzily filtru ruchu, wiec padajaca stacja cichla "tylko jednemu" statkowi, a jego cisza dostawala etykiete dzialajacego odbioru |

Po naprawach: **235 testow**, bramka regresji bez zmian, a wynik D4 na prawdziwej dobie **przezyl** -
te same cztery przypadki, w tym STANISLAV GOVORUKHIN. Zmienila sie jedna klasyfikacja: przypadek,
ktory wczesniej byl bledny, jest teraz rozpoznany jako awaria odbioru.

Dwie rzeczy warte zapamietania. Po pierwsze, **dwa razy powtorzylem wlasny wczesniejszy blad** -
zasieg siatki wedlug szerokosci geograficznej i domyslne przyjmowanie mocniejszego twierdzenia przy
braku danych. Po drugie, pierwsza wersja testu na okno czasowe **przechodzila rowniez na starym
kodzie** - odrzucal go inny warunek. Gdybym nie zmutowal, dopisalbym test, ktory niczego nie pilnuje.

## Warstwa AI - wyszukiwanie po znaczeniu i analityk RAG (2026-09-27)

To byl punkt 1 audytu: z jedenastu wymagan oferty szesc nie istnialo w kodzie. Ta czesc domyka
cztery z nich - **LLM, RAG, GenAI i baze wektorowa** - i robi to na prawdziwym korpusie, nie na
przykladzie.

**Embeddingi** (`embeddings.py`): model `bge-m3` na lokalnej Ollamie, 1024 wymiary, nic nie wychodzi
z maszyny. Zmierzone: polskie zdanie i jego angielski odpowiednik daja **0,724**, zdanie bez zwiazku
**0,274**. To jest cala racja bytu tej warstwy - korpus jest po angielsku, rosyjsku i ukrainsku, a
pytania zadaje sie po polsku.

**Sklep wektorowy** (`vector_store.py`): jeden protokol, dwie implementacje - w pamieci (testy, CI,
brak bazy) i pgvector (produkcja). Migracja `0005_embeddings.sql` z indeksem HNSW po odleglosci
kosinusowej. Filtr metadanych dziala PRZED wyborem sasiadow, bo filtrowanie po wyborze k najblizszych
cicho zwraca mniej wynikow, czasem zero.

**Prog odciecia jest zmierzony, nie zgadniety.** Na 600 zdarzeniach GDELT pytania sensowne trafialy
z wynikiem 0,570-0,782, pytania bez zwiazku z korpusem 0,354-0,445. Prog 0,50 lezy w tej luce.
Dzieki temu na pytanie o statki i kable podmorskie analityk odpowiada "brak danych" zamiast podac
najblizszego sasiada - a najblizszy sasiad istnieje **zawsze**, takze gdy nic nie pasuje.

**Analityk RAG** (`analyst.py`) ma dwie bramki, obie mechaniczne:
- **cytowan** - zdanie bez odnosnika albo z odnosnikiem do nieistniejacego faktu wypada;
- **liczb** - kazda liczba w zdaniu musi wystepowac w cytowanym fakcie.

Druga powstala dlatego, ze pierwsza sama **przepuszczala przekrecenia**: na wlasnym wyjsciu tego
projektu przeszlo zdanie mowiace, ze danych o wsparciu brak, tuz obok podanej kwoty, oraz przypisanie
wynikow z wod dunskich Zatoce Finskiej. Na zywym przebiegu bramka liczb zlapala zdanie "Dane te
pochodza z lacznie 23 doniesien" - suma, ktorej zaden pojedynczy fakt nie potwierdza.

### Pomiar, ktory najwiecej nauczyl

Pierwsza wersja skryptu doklejala do kazdego dokumentu "(opisane w N doniesieniach)". Wygladalo
niewinnie. Zmierzone:

| pytanie | bez dopisku | z dopiskiem |
|---|---|---|
| co sie dzieje w Iranie? | 0,619 | **0,498** |
| co z Ukraina? | 0,582 | **0,500** |
| protesty w Teheranie | 0,782 | 0,628 |

Ten sam tekst w kazdym dokumencie dodaje wszystkim **wspolny kierunek** i rozciencza to, czym
dokumenty sie roznia - spadek 0,12-0,15 i dwa z trzech pytan pod progiem. Analityk odpowiadal
"brak danych" na pytanie o Iran, majac w korpusie 173 zdarzenia z Teheranu. **W RAG tresc dokumentu
wazy wiecej niz model i prog razem wziete.** Liczba doniesien jest teraz w metadanych, ktore nie ida
do modelu.

### Czego ta warstwa nie umie

- **Bramka liczb widzi tylko cyfry.** "siedmiu zabitych" przechodzi bez sprawdzenia, bo to slowo.
- Ocena jakosci wyszukiwania opiera sie na moim odczycie kilkunastu pytan, nie na zbiorze etykiet.
- `DeterministicEmbedder` w testach sprawdza hydraulike (kolejnosc, filtry, progi) i **nic** nie mowi
  o znaczeniu. Kazdy wynik nim uzyskany jest bez wartosci dla oceny trafnosci.
- Indeks zyje w pamieci procesu; `PgVectorStore` jest napisany i nieuruchomiony, bo nie ma bazy.

## Serwer MCP - detektory jako narzedzia modelu (2026-09-27)

Piate z szesciu brakujacych wymagan: **Agentic AI**. Model nie dostaje streszczenia tego, co
detektory znalazly - dostaje **narzedzia**, ktorymi pyta sam i sam decyduje, o co. Pelny opis:
[MCP.md](MCP.md).

Dziala jako proces mowiacy po stdio (JSON-RPC 2.0). Sprawdzone rozmowa z prawdziwym procesem:
handshake, `tools/list` z siedmioma narzedziami, `tools/call` zwracajacy dane z detektora D4,
nieznane narzedzie odrzucone z lista dostepnych, powiadomienie bez odpowiedzi.

**Protokol napisany wprost, bez SDK.** Cztery istotne metody mieszcza sie w jednym pliku, sa w
calosci przetestowane (22 testy) i nie wnosza zaleznosci do CI. Gdyby doszly zasoby albo probkowanie,
SDK zacznie sie oplacac - przy siedmiu narzedziach nie.

Dwie decyzje warte nazwania:

- **Narzedzie, ktore sie wywroci, zwraca blad NARZEDZIA, nie protokolu.** Blad JSON-RPC znaczy
  "wywolanie bylo niepoprawne"; padajacy detektor znaczy "wywolanie zadzialalo, a odpowiedzia jest
  niepowodzenie" - i model musi umiec to przeczytac, zeby sprobowac czegos innego.
- **Powiadomienie nie dostaje odpowiedzi w ogole.** Odpowiedz na nie lamie protokol; czesc klientow
  to toleruje, czesc sie zawiesza.

### Zasada, na ktorej to stoi

Kazda odpowiedz niesie **wlasne zastrzezenie**. Nie z grzecznosci: model dostajacy liste
"podejrzanych statkow" opisze je jako podejrzane statki. Ten sam model, dostajac razem z lista
zdanie "awaria transpondera wyglada w danych identycznie", zwykle je powtorzy. Test
`test_every_real_tool_answer_carries_its_own_caveat` pilnuje, zeby zadne narzedzie nie oddalo danych
bez tego zdania.

### Czego nie robi

- Nie liczy detektorow na zywo - czyta migawki, i kazda odpowiedz podaje, z kiedy sa dane.
- Wersja na zywo wymaga bazy, ktorej nie ma.
- Nie sprawdzilem go z prawdziwym klientem MCP, tylko wlasnym klientem testowym mowiacym tym samym
  protokolem. To nie to samo co zgodnosc z Claude Code w praktyce.

## Model ML dla D3 - ostatnie brakujace wymaganie (2026-09-27)

Zaczalem od sprawdzenia, czy jest na czym trenowac, bo model uczony na etykietach z wlasnej reguly
uczylby sie tylko tej reguly. Pierwsza odpowiedz byla **nie**: 8 przykladow pozytywnych i 22
negatywne. Na trzydziestu przykladach nie trenuje sie niczego.

Ale ograniczeniem nie byly etykiety, tylko **moje pokrycie**. gpsjam etykietuje caly swiat: na dobie
2026-09-26 daje 356 komorek zakloconych i 21835 spokojnych. Brakowalo wlasnych obserwacji z tych
miejsc.

Pierwsza proba - jeden szeroki odczyt nad 28 okregami - dala **zero** komorek pozytywnych: 1571
samolotow rozlozone na 845 komorek to okolo dwoch na komorke, a z dwoch samolotow nie liczy sie
udzialu. Przy okazji wyszlo, ze adsb.lol odmawia (429) takze przy odstepie 2,5 s, czyli ogranicza
**czestotliwosc**, nie tylko rownoczesnosc - wczesniejsza notatka w SOURCES.md byla niepelna.

Po **12 przelotach przez 50 minut** (270 zapytan udanych, 58 odmow, odstep regulowany
automatycznie) zebralem **32 375 obserwacji** zamiast 1571. Razem z godzina nad Baltykiem daje to
**2119 komorek z etykieta, 121 zakloconych, 105 grup przestrzennych**.

### Jak jest mierzone

- **Podzial przestrzenny, nie losowy.** Sasiednie komorki H3 dziela samoloty i dziela to, co je
  zaklocia, wiec losowy podzial pokazalby modelowi jego wlasny zbior testowy. Komorki sa grupowane
  po rodzicu res 2 i cale grupy ida do jednego foldu.
- **Dokladnosc nie jest raportowana w ogole.** Przy 121 zakloconych na 2119 przewidywanie
  "spokojnie" wszedzie daje 94% i nie znaczy nic.
- **Regula liczona na tych samych foldach.** Inaczej porownanie byloby nieuczciwe.
- **Prog "zaklocone" identyczny jak w regule** (nac_p < 8). Inny prog i porownanie nie mowiloby nic
  o modelu.

### Wynik

| | precyzja | czulosc | AP |
|---|---|---|---|
| regula (Wilson >= 0,10) | 0,857 | 0,347 | - |
| model, wszystkie cechy | 0,737 | 0,579 | 0,689 |
| **model (bez cech gestosci)** | **0,769** | **0,579** | **0,705** |

**Model wymienia precyzje na czulosc**: znajduje o 23 pkt proc. wiecej zakloconych komorek, placac
9 pkt proc. precyzji. Nie oglaszam tego zwyciestwem - ktora strona tej wymiany jest lepsza, zalezy
od tego, co kosztuje falszywy alarm, a tego skrypt nie wie.

### Test, ktory mogl to uniewaznic

Przy mniejszej probie trzy najwazniejsze cechy dotyczyly sasiedztwa, w tym `neighbour_aircraft` -
zwykla gestosc ruchu. To moglo znaczyc, ze model uczy sie **geografii**, a nie zaklocen.

Ablacja bez cech gestosci wypadla **lepiej** niz model pelny (precyzja 0,769 zamiast 0,737, AP 0,705
zamiast 0,689). Czyli te cechy nie tylko nie niosly sygnalu - lekko szkodzily. Raportowanym modelem
jest wiec ten prostszy. To nie jest dobieranie wariantu pod wynik testowy: ablacja byla hipoteza
postawiona **zanim** zobaczylem liczby.

Najwazniejsze cechy po ablacji to `mean_nac_p` (jak zle jest, nie tylko ze jest), `spread_alt_ft`
i `neighbour_share` - czyli udzial zakloconych w pierscieniu, ktorego regula z definicji nie widzi,
bo patrzy na jedna komorke naraz.

Te liczby **nie sa porownywalne** z wczesniejszymi 0,60/0,75 dla D3: inny zbior, inna doba etykiet,
inny prog minimalnej liczby samolotow.

### Czego to nie rozstrzyga

- 121 przykladow pozytywnych to nadal malo; przedzialy ufnosci sa szerokie i nie licze ich.
- Etykiety gpsjam sa z calej doby, moj pomiar z jednej godziny i jednego szerokiego odczytu -
  zgodnosc jest z natury czesciowa.
- Model nie jest nigdzie wdrozony. Regula dalej jest tym, co liczy mape i bramke.

## Zalegle znaleziska MED z audytu (2026-09-27)

Szesc z trzynastu, wybrane po wplywie na **opublikowane liczby**, nie po latwosci. Kazde odtworzone
przed przyjeciem, kazda poprawka z testem dowiedzionym mutacja.

**1. Sankcje: liczyl sie tylko pierwszy wiersz z pliku.** OpenSanctions publikuje wiersz na wpis, nie
na statek - 5976 kadlubow ma wiecej niz jeden wiersz na ten sam numer IMO. `setdefault` zachowywal
pierwszy, wiec wynik zalezal od kolejnosci w CSV. Zmierzone: w **484 przypadkach** pierwszy wiersz
nie mial sankcji, a pozniejszy mial. Po scaleniu rekordow liczba statkow Zatoki Finskiej na listach
sankcyjnych: **51 -> 59**. Osiem statkow bylo pokazywanych jako tylko skontrolowane.

**2. Anomalie: okno biezace nie mialo gornej granicy.** Znacznik z przyszlosci - zegar zrodla, blad
parsowania, zastepcze poludnie - wpadal do biezacego okna. Osiem takich zdarzen wystarczylo, zeby
samo wywolalo alarm.

**3. Dwie wersje: kazda wzmianka liczyla sie jako osobny artykul.** GDELT wystawia wiersz na kazda
WZMIANKE, wiec ten sam tekst wraca kilka razy - podwaja wplyw na srednia, przepycha strone przez
`min_articles` i **kasuje ostrzezenie o cienkiej podstawie**, czyli dokladnie to, co mialo chronic
czytelnika. Teraz jeden adres to jeden glos.

**4. Indeks przestrzenny: `nearest(max_km=None)` przeszukiwal jeden pierscien kratek.** Zwracal
`None` tam, gdzie funkcja globalna znajdowala linie 1322 km dalej. Bez promienia pytanie brzmi "co
jest najblizej na swiecie" i uczciwiej przejsc wszystko, niz udawac, ze nic nie ma.

**5. Tor wyscigowy: rownomierny okrag przepadal.** Brak dominujacej osi konczyl analize przed
sprawdzeniem krazenia - a rownomierny rozklad kierunkow to wlasnie pelna orbita. Najczystszy okrag
byl jedynym ksztaltem, ktorego detektor nie widzial.

**6. Wleczenie kotwicy: odcinek nie konczyl sie po dziurze w meldunkach.** Piec pozycji co godzine
skladalo sie w "czterogodzinny alarm", choc o tym, co statek robil miedzy nimi, dane nie mowia nic.
Doszedl `max_gap` 20 min i rozdzielanie odcinkow miedzy roznymi liniami - alarm ma dotyczyc jednego
kabla, nie tego, ze statek mijal kilka. Wynik na dobie dunskiej: **35 -> 33 alarmy**, liczba dla
statkow handlowych bez zmian (1).

Testy: **319**. Bramka regresji bez zmian.

### Wlasny blad w fiksturach

Poprawka nr 3 wywrocila istniejacy test - bo moj pomocnik `row()` dawal wszystkim wierszom **ten sam
adres artykulu**. Wczesniej bylo to nieszkodliwe; po dodaniu odsiewu powtorzen dwa rozne zrodla
wygladaly jak jeden tekst policzony dwa razy. Poprawilem fikstury, nie regule.

### Co zostaje

Siedem znalezisk MED i cztery LOW, glownie w `run.py` (atomowosc zapisu, znacznik przetworzonych
godzin) i `dark.py` (snapshot nie zapisuje wersji regul). Wszystkie dotycza potoku, ktory nie
zostal jeszcze uruchomiony z baza, wiec nie zmieniaja zadnej opublikowanej liczby.

## Bramka analityka dala sie oszukac (2026-09-28)

Na zywym przebiegu, pytana o Iran, bramka przyjela **8 z 9 zdan i ogłosila 89% przyjetych**. Notatka
wygladala tak:

```
[1] Brak danych na temat sytuacji w Iranie.
[2] Brak danych na temat sytuacji w Iranie.
...          <- osiem razy to samo, zmienial sie tylko numer
[8]          <- samo odniesienie, bez zdania
```

Kazde z tych "zdan" ma poprawny odnosnik i nie zawiera zadnej liczby, wiec obie dotychczasowe bramki
- cytowan i liczb - przepuscily je bez zastrzezen. Model pomylil format i przepisal numeracje listy
faktow, a moja bramka nazwala to notatka w 89% wiarygodna.

Doszly dwie reguly, obie mechaniczne:

- **odnosnik bez tresci** - zdanie musi miec co najmniej trzy slowa poza odnosnikami. "[8]" nie jest
  zdaniem;
- **powtorzenie** - porownywana jest TRESC zdania z pominieciem odnosnikow, bo kopie roznily sie
  wylacznie numerem. Powtorzone zdanie nie dodaje wiedzy, a osiem kopii zawyza udzial przyjetych.

Po poprawce ten sam przebieg: **1 z 9 (11%)**. Osiem kopii odrzuconych z podanym powodem, zostalo
jedno uczciwe "brak danych".

Wnioski z czterech pytan po poprawce:

| pytanie | przyjete | co to znaczy |
|---|---|---|
| walki na Ukrainie | 5 z 5 | korpus ma pokrycie, model trzyma sie faktow |
| gdzie protestuja ludzie | 4 z 4 | j.w. |
| co sie dzieje w Iranie | 1 z 9 | fakty sa, ale zbyt ogolne - model nie ma co z nich powiedziec |
| statki i kable podmorskie | 0 z 1 | nic nie przekroczylo progu; **to jest odpowiedz, nie awaria** |

Trzecia bramka w trzy dni. Za kazdym razem powod byl ten sam: bramka sprawdzala forme, a model
znalazl sposob, zeby forme spelnic bez tresci. Nie zakladam, ze teraz juz jej nie ma.

## Caly stos ruszyl po raz pierwszy (2026-09-28)

WSL2 i Docker Desktop zainstalowane przez UAC. **Restart okazal sie niepotrzebny** - WSL 2.7.14
z Ubuntu odpowiedzial od razu, demon Dockera wstal w 20 sekund.

Co to odblokowalo:

| | przed | po |
|---|---|---|
| testy C# | 22, **13 pominietych** | **40 z 40, zero pominietych** |
| testy integracyjne Pythona | niewykonalne | **4 z 4** |
| baza, ingestia, API, detektory, front | nigdy nie uruchomione | **wszystkie dzialaja** |

**1327 linii C#, ktore nigdy nie dotknely bazy, przeszly wszystkie testy za pierwszym razem.**
Migracje (wszystkie piec skryptow, w tym `0005_embeddings`), hypertable TimescaleDB, zapis pozycji
z prowenancja, endpointy, hub SignalR.

### Blad, ktory mogl wyjsc wylacznie z uruchomienia

Ingestia dostawala **403 Forbidden** z adsb.lol przy kazdym odczycie. Powod: `AddHttpClient()` bez
zadnego naglowka. Wszystkie skrypty w Pythonie przedstawialy sie przez `User-Agent` od pierwszego
dnia, warstwa C# nie - i **zaden test jednostkowy nie mogl tego zlapac, bo nie wychodza do sieci**.
Doszedl `WachtaHttp.UserAgent`, ten sam ciag co w Pythonie, zeby jedno spojrzenie w log serwera
pokazywalo wszystko, co ten projekt pobral, niezaleznie od warstwy.

### Co pokazal pierwszy przebieg

Po 15 minutach: **4618 pozycji, 426 samolotow, 170 wojskowych, 70 odczytow zrodel bez ani jednego
bledu**. API oddaje 118 zywych samolotow wojskowych (`/api/aircraft/live`), 123 tory w przelocie,
tor pojedynczego samolotu. Detektory licza co minute: D1 sprawdza ~320 samolotow, D3 przeliczyl
zamkniete godziny.

Powstaly 4 komorki zaklocen - **wszystkie z zerem zakloconych**. To nie jest wykrycie, tylko zapis
kratek z wystarczajacym ruchem, i tak ma byc. Bałtyckiego ogniska z wczesniejszego pomiaru nie widac,
bo tamten opieral sie na godzinie dedykowanego zbierania nad Baltykiem (13 781 pozycji), a tu mamy
kwadrans i zrodlo wojskowe o zasiegu globalnym.

### Czego nadal nie wiadomo

- D1 nie wyprodukowal zadnego alertu - potrzebuje modelu pokrycia, ktory wymaga zamknietych godzin.
- `coverage_hourly` jest puste z tego samego powodu.
- To sa oczekiwane zachowania przy kwadransie danych, nie dowody poprawnosci. Dowodem bedzie doba.

## Zywy potok odtworzyl ognisko zaklocen (2026-09-28)

Po 1,5 godziny samodzielnej pracy stosu: **24 484 pozycje, 994 samoloty, 378 odczytow, 105 komorek
zaklocen - w tym 46 z realnie zakloconymi samolotami**. Pierwsze 15 minut nie pokazalo nic poza
kratkami z ruchem; to bylo za malo danych, nie brak zjawiska.

Gdzie detektor wskazal zaklocenia, liczac sam, bez zadnego skryptu badawczego:

| pozycja | udzial zakloconych | co to za miejsce |
|---|---|---|
| 54,05 / 23,06 | **100%** | przesmyk suwalski, granica obwodu kaliningradzkiego |
| 54,41 / 22,96 | 100% | j.w. |
| 53,10 / 22,74 | 82% | polnocno-wschodnia Polska |
| 54,28 / 23,60 | 69% | pogranicze litewskie |
| 58,62 / 20,91 | 46% | srodkowy Baltyk na wschod od Gotlandii |
| 59,94 / 24,76 | 40% | wejscie do Zatoki Finskiej, pod Tallinem |

### Sprawdzenie niezaleznym zrodlem

Zestawienie 96 wspolnych komorek z gpsjam za **dzien poprzedni**:

- zgodnych werdyktow **80 z 96 (83%)**
- trafien 12, falszywych alarmow 12, przeoczen 4
- precyzja **0,50**, czulosc **0,75**

Korytarz kaliningradzki zgadza sie mocno (moje 100% wobec 46,7% w referencji, 82% wobec 28,6% -
te same miejsca, mocniejszy udzial, bo licze z 1,5 h, a nie z doby).

**Rozjazd, ktorego nie tlumacze:** srodkowy Baltyk. Ja mam 41-46%, gpsjam 0-3%. To moga byc
zaklocenia, ktorych wczoraj nie bylo - zjawisko zmienia sie z dnia na dzien - albo moj blad.
**Nie da sie tego rozstrzygnac**, dopoki gpsjam nie opublikuje dnia dzisiejszego. Referencja jest
z innego dnia i z calej doby, moj pomiar z poltorej godziny; to porownanie jest orientacyjne, nie
rozstrzygajace, i nie zastepuje bramki ewaluacji.

### Smieciowe znaki wywolawcze

W bazie wyladowaly `@@@@@@@@` i `ZLY41 @@`. W kodowaniu Mode-S `@` to znak **wypelniajacy** - pole
znaku wywolawczego ma osiem znakow, a samolot, ktory go nie podaje, wypelnia je `@`. Parser obcinal
tylko spacje, wiec brak identyfikatora trafial na mape jako identyfikator. Poprawione w
`AdsbV2Parser.CleanCallsign`, 5 przypadkow testowych. Znalezione przez zajrzenie do bazy po
uruchomieniu, nie przez test.

## Uwagi

- **Nic nie jest zacommitowane.** Zgodnie z Twoją zasadą nie robię commitów bez zgody. 119 plików
  czeka w poczekalni (`git status`). Gdy zaakceptujesz:
  ```bash
  cd C:\Users\grzan\wachta
  git commit -m "feat: wachta skeleton - detectors, web map, eval gate, docs"
  ```
- **Kod C# jest skompilowany i przetestowany** (2026-09-27). SDK .NET 10.0.401 zainstalowany
  **do profilu uzytkownika** (`~/.dotnet`, bez admina, bez zmian w systemie) skryptem
  `dotnet-install.ps1`. Wynik: **22 testy jednostkowe przechodza, 0 bledow, 13 pominietych**
  z jawnym powodem (wymagaja bazy w kontenerze).
- **Przegląd C# na sucho** (bez kompilatora) wyłapał jeden realny błąd: tablica `object[]` z `DBNull`
  nie mapuje się na `timestamptz[]` w zapisie kontaktów — poprawione na `DateTime?[]` w kodzie i w planie.
- **Wersje pakietów NuGet są ustawione na `*`**, bo nie mogłem sprawdzić, które istnieją. Po
  pierwszym udanym `dotnet restore` przypnij je do konkretnych wersji.
- **`uv` jest zainstalowany przez pip**, więc `uv.exe` nie jest w PATH — używaj `python -m uv`.
- W trakcie pracy zbierałem godzinę prawdziwych danych ADS-B do fixture'u ewaluacji D3
  (`eval/feasibility/collect_hour.py`); wynik w `eval/fixtures/d3_hour.json`.

## Model lokalny (qwen)

Użyty do napisania dodatkowych testów dla `geo.py` i `airports.py`: z 10 propozycji 8 przeszło,
2 były błędne (zła wartość oczekiwana odległości Gdańsk–Warszawa: 296 zamiast 292,6 km; asercja na
nieistniejącym polu). Poprawione i przepisane — plik `tests/test_geo_airports_extra.py` ma adnotację
o pochodzeniu. Wniosek zgodny z wcześniejszymi pomiarami: model lokalny nadaje się do szkiców przy
gotowej specyfikacji, ale każdą liczbę trzeba sprawdzić uruchomieniem.

---

# Domkniete zaleglosci — 2026-09-28

Cztery rzeczy zapisane wprost jako nierozwiazane. Kazda albo zrobiona, albo opisana, czemu nie.
Liczby ponizej pochodza z uruchomionego stosu, nie z szacunku.

## 1. Tryb odtwarzania `/api/replay` — DZIALA, nic nie trzeba bylo naprawiac

Endpoint nigdy nie byl sprawdzony na danych, bo baza nie miala historii. Teraz ma: **130 003
pozycje samolotow** (08:31–15:28 UTC) i **74 240 pozycji statkow**.

Pelne okno szesciogodzinne (09:00–15:00 UTC): **HTTP 200 w 0,38 s, 1 836 020 bajtow, 1 175 torow,
52 417 punktow**. Kontrola SQL-em na tym samym oknie daje **te same 1 175 samolotow i te same
52 417 kubelkow 30-sekundowych** — endpoint nie gubi nic poza zamierzonym przerzedzaniem
(68 384 surowe wiersze → 52 417 punktow). Tory sa spojne: `path` i `timestamps` tej samej dlugosci,
czasy rosnace, zaden `hex` nie powtorzony. Granice okna odrzucane poprawnie (400), strefa czasowa
uwzgledniana. Szczegoly i komendy: [URUCHOMIENIE.md](URUCHOMIENIE.md#tryb-odtwarzania--sprawdzony-na-pelnym-oknie-2026-09-28).

## 2. D5 i D7 wpiete w petle detektorow

Na tych samych zasadach co D4 i D6: wlasny interwal, wlasne okno, zapis przez `insert_alert_rows`,
`_guarded` dookola.

| Detektor | Co odpala | Interwal | Okno | Dlaczego tyle |
|---|---|---|---|---|
| **D5** przeladunek burta w burte | `offshore(find_encounters(...))` | 15 min | 12 h | `StsRules.max_duration` to 12 h, a sprawdzenie „oba statki gdzies plynely” zaglada 6 h przed spotkanie i 6 h za nie |
| **D7** tozsamosc statku | `scan()`, tylko werdykt „dwa kadluby” | 30 min | 12 h | werdykt narasta godzinami; mielenie tych samych 12 h co 10 minut daje ten sam wynik |

**Pierwszy przebieg na zywo (1 103 statki w oknie):**

```
15:46  D5: 1103 statkow w oknie, 16 spotkan poza kotwicowiskiem, 16 nowych alarmow
15:46  D7: 1103 statkow w oknie, 0 numerow wygladajacych na dwa kadluby, 0 nowych alarmow
16:02  D5: 1110 statkow w oknie, 19 spotkan poza kotwicowiskiem,  3 nowych alarmow
```

Drugi przebieg D5 pokazuje, ze odsiewanie powtorzen dziala: z 19 spotkan w oknie **nowe sa trzy**,
reszta to te same spotkania, ktore juz maja swoj wiersz (UNIQUE po `detector, entity_id, started_at`).
D7 w tym cyklu nie ruszyl — ma odstep 30 minut, wiec nastepny przebieg wypada o 16:16.

**D7 zwrocil zero i to jest wynik poprawny** — na wodach finskich nie ma w tej dobie numeru MMSI,
ktorego wlasny tor przeskakuje tam i z powrotem miedzy oddalonymi obszarami. Progi zostaly, jakie
byly. Cztery numery trafily do kategorii „bledny punkt” (pojedyncza pozycja poza torem) i **celowo
nie sa alarmem**: `identity.py` istnieje po to, zeby nie zglaszac czkawki odbiornika jako oszustwa.

**D5 dal 16 alarmow i trzeba powiedziec wprost, co to jest.** Po sprawdzeniu typow AIS: 15 z 16 par
to ruch sluzbowy — holowniki (52), pilotowki (50), jednostki holujace (31), promy (60). Jedyna para
ladunkowiec + tankowiec to ROSTRUM SOLAR (70) + AURORA (80), 42 minuty w odleglosci **745 m**, czyli
przy samej granicy `max_separation_km` (800 m) — to raczej mijanka niz przeladunek. Dokladnie to
przewidzial wczesniejszy przebieg na dobie dunskiego AIS. **Progow nie ruszalem**: filtr po typie
jednostki to osobna decyzja produktowa (jak przy D6, gdzie handlowe i robocze ida na osobne listy),
a nie strojenie detektora pod ladniejszy wynik.

## 3. Indeks wektorowy nadaza za alarmami

Bylo: jednorazowa migawka z reki. W bazie lezalo **2 000 zdarzen GDELT i 0 alarmow** — wyszukiwanie
po znaczeniu odpowiadalo „nic nie znalazlem” na kazde pytanie o to, co detektory znalazly.

Jest: krok w petli co 15 minut, przyrostowy (tylko alarmy nowsze niz ostatni udany przebieg), z
nadrobieniem 24 h po restarcie. Pelne nadrobienie tygodnia zostaje przy recznym
`python -m wachta_detectors.indexer`.

```
15:46:28  indeks wektorowy: 24 alarmow od 2026-09-27 15:45:51+00:00, zapisanych 24
16:02:42  indeks wektorowy: 21 alarmow od 2026-09-28 15:45:51+00:00, zapisanych 21
```

Pierwszy przebieg siegnal 24 h wstecz (nadrobienie po restarcie) i wzial **24 alarmy (D4: 5, D5: 16,
D6: 3)** obok 2 000 zdarzen GDELT. Drugi, kwadrans pozniej, ruszyl **od chwili poprzedniego**, nie
od doby wstecz — przyrostowosc dziala na zywo, nie tylko w tescie.

Brak Ollamy nie wywraca petli, tak samo jak brak pliku z kablami nie wywraca D6. Sa na to dwa
znaczniki, i to nie jest powtorzenie: „kiedy probowalismy” przesuwa sie zawsze, zeby padnieta Ollama
kosztowala jedno podejscie na kwadrans zamiast jednego na kazdy tick; „co juz w indeksie” przesuwa
sie wylacznie po udanym zapisie, zeby alarmy z czasu awarii nie wypadly z okna.

**Blad znaleziony dopiero na kontenerze, nie w testach.** `indexer.py` liczyl sciezke do migawki
GDELT przy imporcie (`parents[3]`), a obraz kopiuje tylko `src/python` — pakiet lezy w `/app`, wiec
tej sciezki nie ma. Od chwili, gdy petla zaczela importowac ten modul, **caly proces detektorow
wpadl w petle restartow** (`IndexError: 3`, log potwierdza). Poprawione: brak migawki ma wygladac
jak brak pliku, nie jak wyjatek.

Kontener `detectors` dostal w `compose.yaml` adres Ollamy (`WACHTA_OLLAMA_URL`) i
`host.docker.internal`, bo model chodzi na hoscie — dokladnie z tego samego powodu, dla ktorego ma
to juz `api`. `OllamaEmbedder` czyta ten adres przez `embeddings.embedder_from_env()`.

## 4. Bramka ewaluacji rozroznia progi, pod ktorymi powstala etykieta

`dark.snapshot_inputs()` zapisuje w kazdej probce D1 uzyte progi i ich odcisk (`rules_version`).
`eval/run_eval.py` tego nie czytal, wiec probki sprzed i po zmianie progu wpadaly do jednej sredniej.
Jedna liczba z dwoch konfiguracji nie opisuje zadnej z nich.

Teraz `eval_d1()` grupuje przypadki po `rules_version`:

- **naglowkowe** precyzja i recall licza sie **wylacznie z przypadkow spod obecnych progow**;
- pozostale sa raportowane obok, pod kluczem `by_rules`, razem z licznikiem `n_other_rules` — nie
  znikaja, tylko przestaja sie mieszac;
- przypadki **bez** `rules_version` to recznie napisane scenariusze regresyjne (zestaw syntetyczny);
  zadna konfiguracja ich nie wybrala, wiec licza sie zawsze;
- gdy **wszystkie** etykiety pochodza spod innych progow, wynik to `null`, a nie 1,0. `prf()` na
  zerze przypadkow zwraca komplet punktow, wiec zmiana progu przechodzilaby bramke za pomiar,
  ktorego nikt nie wykonal. Bramka traktuje `null` jako spadek (`metric_drops()`).

Poprawiony zostal takze producent etykiet: `eval/label_d1.py` przepisywal ze snapshotu tylko wejscia
detektora, wiec `rules_version` konczyl sie w bazie i nigdy nie trafial do pliku, po ktorym bramka
miala rozrozniac konfiguracje. Teraz progi jada razem z przypadkiem.

`eval/baseline.json` **nie byl ruszany** — aktualny odcisk progow zgadza sie z tym, pod ktorym
powstal zestaw syntetyczny, wiec liczby sie nie zmienily.

## Walidacja

- `python -m pytest -q` → **466 testow** (bylo 441; +25 nowych)
- `python eval/run_eval.py --check eval/baseline.json` → **0**
- Stos na zywo: D1, D3, D4, D5, D6, D7, pokrycie i indeks wektorowy przechodza w jednym cyklu

Kazde zachowanie krytyczne udowodnione mutacja (cofniecie zmiany, czerwony test, przywrocenie):
filtr `offshore()` w D5, filtr werdyktu w D7, `started_at` z pierwszego skoku, przyrostowosc
indeksowania, `_guarded` dookola indeksowania, oba znaczniki postepu, adres Ollamy z konfiguracji,
sciezka do migawki w obrazie, podzial po `rules_version`, `null` zamiast darmowego zaliczenia,
`metric_drops()` na `null`, przenoszenie progow przez `label_d1.py`.

## Czego tu nie ma

- **README.md nie zostal zaktualizowany** — plik jest poza zakresem tej pracy. Jego tabela „Poza
  stosem — kod jest, ale nic tego nie uruchamia w produkcji” jest teraz nieaktualna: D4, D5, D6 i D7
  chodza w petli, a warstwa morska ma tabele `ship_position`. Do poprawienia przy najblizszej okazji.
- **Filtr typu jednostki dla D5** — zmierzony jako potrzebny (15 z 16 alarmow to holowniki, pilotowki
  i promy), ale swiadomie nieodpalony: to decyzja produktowa, nie strojenie progu.
