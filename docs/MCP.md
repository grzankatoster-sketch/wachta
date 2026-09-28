# Serwer MCP — detektory jako narzędzia modelu

Model nie dostaje tu tekstu o tym, co detektory znalazły. Dostaje **narzędzia**, którymi może sam
zapytać — i sam zdecydować, o co. To jest różnica między streszczeniem a dostępem.

## Po co

Pytanie „czy coś dziwnego działo się przy Bornholmie" wymaga wybrania detektora, okna i progu.
Model wybiera je sam, wywołuje narzędzie, dostaje dane i może zapytać dalej. Bez tego trzeba było
z góry zgadnąć, co go zainteresuje, i wkleić mu to do promptu.

## Uruchomienie

```bash
cd src/python
python -m wachta_detectors.mcp_server
```

Serwer mówi po **stdio** (JSON-RPC 2.0). Logi idą na stderr, nigdy na stdout — stdout należy do
protokołu.

Zmienna `WACHTA_MCP_NO_SEARCH=1` pomija budowanie indeksu semantycznego. Indeks powstaje w pamięci
przy starcie i zajmuje około dwóch minut; bez tej zmiennej klient czeka.

## Podłączenie do Claude Code

```json
{
  "mcpServers": {
    "wachta": {
      "command": "python",
      "args": ["-m", "wachta_detectors.mcp_server"],
      "cwd": "C:/Users/grzan/wachta/src/python"
    }
  }
}
```

## Narzędzia

| narzędzie | detektor | co zwraca |
|---|---|---|
| `ciche_statki` | D4 | statki, które przestały nadawać AIS w ruchu tam, gdzie odbiorniki działały |
| `przeladunki` | D5 | pary ładunkowiec/tankowiec burta w burtę poza kotwicowiskiem |
| `tozsamosc_statkow` | D7 | numery MMSI, których tor stawia je w dwóch miejscach naraz |
| `tory_dyzurne` | D2 | samoloty chodzące po jednej linii zamiast lecieć z A do B |
| `nietypowe_skupiska` | D8 | miejsca, w których liczba doniesień złamała własny rytm |
| `dwie_wersje` | — | wydarzenia opisane inaczej przez różne strony |
| `wsparcie_ukrainy` | — | kto ile przekazał, w miliardach dolarów |
| `szukaj_zdarzen` | RAG | wyszukiwanie po znaczeniu; pytanie po polsku, zdarzenia po angielsku |

### Z żywej bazy

Te cztery pojawiają się tylko wtedy, gdy ustawiona jest zmienna `WACHTA_DB` i baza odpowiada:

| narzędzie | co zwraca |
|---|---|
| `samoloty_na_zywo` | ostatnie odebrane raporty ADS-B z zadanego okna |
| `zaklocenia_gps` | komórki H3 z udziałem zakłóconych, policzone przez D3 na bieżąco |
| `alerty_detektorow` | alarmy zapisane przez pętlę detektorów |
| `tor_samolotu` | tor jednej maszyny po numerze ICAO |

Zapytania SQL żyją w `repository.py` i są **sparametryzowane** — narzędzia ich nie sklejają.

**Zastrzeżenie przy danych z bazy jest wyliczane, nie wpisane.** Świeżo uruchomiony stos ma pustą
historię, a model nie może pomylić „nic nie zebraliśmy" z „nic się nie dzieje" — więc każda
odpowiedź podaje, ile danych faktycznie jest w oknie i z kiedy są najstarszy oraz najnowszy punkt.
Przy samolotach dochodzi druga rzecz, o której model sam by nie pomyślał: każdy wiersz to **ostatni
odebrany raport**, a nie bieżące położenie — maszyna jest już gdzie indziej.

### Degradacja

`szukaj_zdarzen` pojawia się tylko wtedy, gdy indeks udało się zbudować. Brak Ollamy kosztuje to
jedno narzędzie, nie cały serwer. Tak samo brak bazy: serwer wstaje z siedmioma narzędziami na
migawkach zamiast jedenastu, i mówi o tym na stderr. Sprawdzone na prawdziwej awarii połączenia.

## Zasada, na której to stoi

**Każda odpowiedź niesie własne zastrzeżenie.** Nie z grzeczności — model dostający listę
„podejrzanych statków" opisze je jako podejrzane statki. Ten sam model, dostając razem z listą
zdanie „awaria transpondera wygląda w danych identycznie", zwykle je powtórzy. Zastrzeżenie jedzie
razem z danymi, bo model będzie tak ostrożny, jak ostrożne jest jego wejście.

Test `test_every_real_tool_answer_carries_its_own_caveat` pilnuje, żeby żadne narzędzie nie oddało
danych bez tego zdania.

## Czego serwer nie robi

- Nie liczy detektorów na żywo — czyta migawki z `eval/fixtures`. Każda odpowiedź podaje, z kiedy są
  dane. Wersja na żywo wymaga bazy.
- Nie ma zasobów ani promptów MCP, tylko narzędzia. Protokół jest zaimplementowany wprost, bez SDK:
  cztery istotne metody mieszczą się w jednym pliku, są w całości przetestowane i nie wnoszą
  zależności do CI. Gdyby doszły zasoby albo próbkowanie, SDK zacznie się opłacać.
