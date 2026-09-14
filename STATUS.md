# STATUS: odra-router (repo: odra_transpilation)

Stan na 2026-09-04 (sekcja o fazie 2 na dole; starsze sekcje 1-7 to historia z 2026-08-31). Repo: `git@github.com:k3chupe/odra_transpilation.git`, lokalnie `/workspace/repos/odra_transpilation`.
Nota: ten dokument jest po polsku, bo to status dla zespołu; kod i reszta dokumentacji są po angielsku.

## 1. O co chodzi

Kwantowy transpiler dla topologii ODRA5 (IQM Adonis), gwiazdy o 5 kubitach z centrum w kubicie 2. Budujemy własne stage'y **routingu** (wybór układu kubitów i wstawianie SWAP-ów, żeby bramki dwukubitowe lądowały na sąsiednich fizycznych kubitach) i porównujemy je z transpilerem Qiskit 1.2 (przypięty `qiskit==1.2.4`).

Każdy solver rejestruje się przez kontrakt (`src/odra_router/contract.py`), a testy automatycznie sprawdzają każdy zarejestrowany solver. Solver zwraca `RoutingSolution` (layout początkowy + harmonogram SWAP-ów), nigdy nie modyfikuje wejściowego obwodu.

## 2. Solvery i benchmarki

| Solver | Co robi | Rola |
|---|---|---|
| `greedy_shortest_path` | greedy na layoutcie identycznościowym | najprostszy punkt odniesienia |
| `brute_force_layout` | sprawdza wszystkie 120 layoutów z greedy SWAP-ami | baseline (per-interakcyjne greedy, NIE ideał) |
| `exact_dp` | pełne przeszukanie (Dijkstra: layouty + dowolne SWAP-y na krawędziach + dowolny porządek topologiczny, dokładny koszt fidelity) | **prawdziwe dolne ograniczenie** (nie do pobicia) |
| `tabu_fidelity` | move-based tabu po (layout, wybory SWAP-ów, pełny porządek topologiczny) z lookahead greedy i polishingiem | metaheurystyka fidelity |
| `tabu_fidelity_greedy` | jak wyżej, warm start z layoutu identycznościowego | metaheurystyka fidelity |
| `tabu_fidelity_sabre` | jak wyżej, warm start z layoutu SabreLayout | metaheurystyka fidelity |
| `brute_fidelity_layout` | najlepszy z 120 layoutów z greedy SWAP-ami, DAG order | baseline (NIE ideał) |
| `tabu_search` | tabu po layoutach, start losowy | metaheurystyka |
| `tabu_sabre_start` | tabu, start z layoutu wybranego przez jeden przebieg Sabre | metaheurystyka, test warm startu |
| `genetic_search` | minimalny GA po layoutach (turniej, OX1, mutacja) | bazowy punkt odniesienia dla metaheurystyk |
| `genetic.py` | stub, nie zarejestrowany | prawdziwy GA, pisze go kolega |
| `sabre_baseline` | TrivialLayout + SabreSwap; naprawiony, ale harmonogramu swapów nie da się zmapować na kontrakt per-interakcyjny | wyłączony z benchmarków; uczciwy sabre to `qiskit_sabre` w benchmarku fidelity |
| `qiskit_preset` | pełny preset transpilera Qiskit na target ODRA5 | baseline zewnętrzny |
| `qiskit_sabre` | SabreLayout + SabreSwap, liczone na poziomie obwodu (wiersz w benchmarku fidelity) | baseline zewnętrzny, czysty sabre |

Benchmarki (wszystkie w `src/odra_router/bench.py`, wyniki do `results/`):

- `odra-router-bench` - syntetyczne obwody z `benchmarks/suite.json` -> `results/benchmark.csv`
- `odra-router-bench-queko` - obwody QUEKO ze znanym optimum 0 SWAP-ów -> `results/queko.csv`
- `odra-router-bench-sweat` - budżetowy sweep (czas x powtórzenia) na hard/gęstych/głębokich instancjach -> `results/sweat.csv` + `results/sweat-summary.md`

Metryki: `swap_count` (logiczne SWAP-y), `cz_cost` (bramki dwukubitowe po przeliczeniu na basis natywny, SWAP = 3 CZ), `depth`, `evals` (liczba ewaluacji layoutów w jednym solve), `seconds`.

## 3. Co się udało

1. **Tabu search nad layoutami** w dwóch wariantach: `tabu_search` (start losowy) i `tabu_sabre_start` (warm start z layoutu SabreLayout, fallback na random przy błędzie). Oba zarejestrowane, otestowane i w benchmarkach.
2. **Algorytm Genetyczny po layoutach** (`genetic_search`) — minimalna heurystyka w `routing/genetic.py` z celowaniem w liczbę swapów.
3. **Zaawansowany algorytm genetyczny** (`genetic_fidelity`) — pełne kodowanie (layout, swapy, flagi) z natywnym celem fidelity w `routing/genetic_fidelity.py`.
3. **Uczciwa metryka `cz_cost`**. Wcześniej `qiskit_preset` raportował zawsze 0 SWAP-ów (gwiazda nie ma natywnego SWAP, Qiskit rozkłada go na 3 CZ), przez co wyglądał na "zawsze optymalny". Teraz każdy solver ma wspólny koszt w basisie natywnym.
4. **Naprawa buga w `exact_dp`**. Mapa CouplingMap ODRA5 jest skierowana, a `cm.neighbors()` zwraca tylko krawędzie wychodzące, przez co DP wpadał w ślepą uliczkę na obwodach wymagających SWAP-ów i cicho zwracał wynik greedy (na hard_8r: 34 zamiast prawdziwych 32). Po naprawie (nieskierowani sąsiedzi) exact_dp jest dokładny; są testy regresyjne.
5. **Benchmark "pocenia" `odra-router-bench-sweat`**: sweep budżetu czasowego (0.05-1.0 s) x 5 powtórzeń na ~10 instancjach, z referencją brute force i kolumną `evals` (solvery raportują, ile layoutów faktycznie oceniły).
6. **Hard generator `hard_circuit`**: cykl po 6 parach niekrawędziowych gwiazdy, wymusza ciągły routing przez centrum. Gęste obwody losowe nie wystarczają, bo nasycają się (greedy = brute = dp).
7. **Wszystko zielone i wypchnięte**: 45 testów przechodzi, commity `a8d27a0` i `f59c50d` są na `main`.

## 4. Co wiemy (najważniejsze wnioski)

- **Dla każdego obwodu na gwieździe ODRA5 dokładnie 24 z 120 layoutów osiąga optimum** (4! permutacji liści, symetria gwiazdy). Losowe próbkowanie trafia optymalny layout z prawdopodobieństwem 20% na próbę.
- Skutek: **jakość nasyca się**. `brute_force_layout` = `exact_dp` = `tabu` = `GA` co do liczby SWAP-ów (sprawdzone na hard i losowych instancjach). Jedyny odstający to `greedy` (layout identycznościowy): na hard instancjach gap 1-2 SWAP-y i 0% trafień w optimum.
- To, co naprawdę odróżnia solvery na 5 kubitach, to **narzut czasowy i ewaluacyjny**: pełny przebieg tabu to ~16 tys. ewaluacji layoutów, GA ~2.5 tys., brute 120, greedy 1. Czas przy tej samej jakości: brute/exact_dp ~0.02-0.09 s, tabu/GA ~0.05-0.14 s.
- **Warm start z Sabre nie daje mierzalnej przewagi na ODRA5** (przy 24/120 optymalnych layoutów każdy start zbiega szybko; wcześniejsza ablacja na QUEKO 11/15 na korzyść warm startu, na syntetyku remis).
- `qiskit_preset` ma niższy `cz_cost` niż nasze solvery na syntetykach, bo preset robi pełną optymalizację (m.in. anulowanie bramek), a nasz projekt na razie robi tylko routing.
- **Kolejność bramek (przestawianie/komutacja)**: nie analizujemy jej, kolejność jest ustalona (kolejność topologiczna DAG-a), a `exact_dp` jest optymalny tylko dla ustalonej kolejności (caveat w `docs/contract.md`). Szybki test (400 poprawnych topologicznie przestawień na przypadek, instancje hard/random/QUEKO): przestawianie niezależnych bramek nie obniżyło optimum layoutowego w żadnym przypadku (0/400). Natomiast **anulowanie sąsiednich identycznych CX (CX-CX = I) daje realny zysk nawet w ustalonej kolejności**: rand20_s0 6->5 SWAP-ów i 2 bramki mniej, rand40_s0 12->11. To argument za fazą 2 (`optimize/cancel.py`, na razie stub) i częściowo tłumaczy niższy `cz_cost` u `qiskit_preset`.

## 5. Czego nie da się zrobić na 5 kubitach

Nie da się sprawić, żeby algorytmy szukające layoutów "pociły się" na gwieździe ODRA5: przestrzeń to 120 layoutów, a 24 z nich są zawsze optymalne, więc metaheurystyki zbiegają niemal natychmiast. Prawdziwe "pocenie" wymaga:

- większej liczby kubitów (przestrzeń layoutów rośnie jak n!), albo
- zmiany przestrzeni poszukiwań: przeszukiwanie sekwencji SWAP-ów zamiast layoutów (przestrzeń wykładnicza w liczbie interakcji; dokładnie to robi exact_dp, ale tylko dla ustalonej kolejności bramek i tylko na małych instancjach).

## 6. Co jest do zrobienia

Proponowane priorytety:

1. **Ruch wielokrotny w tabu**: pozostałe luki do `exact_dp` (dense_1 +21%, medium_1 +11%, dense_0 +10%, hard_8r +9%) to lokalne minima, których pojedyncze ruchy nie przeskakują; blok zmian (np. dwa wybory SWAP-ów naraz) albo selektywny re-greedy po najlepszym rozwiązaniu.
2. **Faza 2 optymalizacji**: `optimize/cancel.py` i `optimize/baseline.py` to nadal stuby. Anulowanie sąsiednich SWAP-ów, CX-CX i CZ-CZ daje mierzalne zyski (patrz sekcja 4: anulowanie CX-CX obniża optimum nawet w ustalonej kolejności); to największa dziura w projekcie i część luki do `qiskit_preset`. Z fazą 3 ma sens liczyć też zysk w `fidelity_cost`.
3. **Prawdziwe dane fidelity**: podmienić `odra5_default_fidelity()` na prawdziwą kalibrację IQM, gdy będzie dostępna.
4. **Prawdziwy GA** w `routing/genetic.py` (pisze go kolega).
5. ~~**Wykresy** z wyników (`visualize_results.py`)~~ zrobione 2026-09-14: reprezentant rodziny zamiast 12 prawie identycznych wariantów, 5 wykresów, ideał jako odniesienie (sekcja na końcu).

Świadomie odłożone: większe topologie i więcej kubitów (poza zakresem ODRA5), QASMBench/MQT Bench (za duże albo niezgodne z qiskit 1.2).

## 7. Co robimy teraz

Faza 3 (fidelity-aware move-based tabu) wdrożona i zmierzona; benchmark `odra-router-bench-fidelity`. `exact_dp` jest teraz **prawdziwym dolnym ograniczeniem**: pełne przeszukanie (layouty, dowolne SWAP-y na krawędziach, dowolny porządek topologiczny z przeplotami, dokładny koszt fidelity), nie do pobicia przez żaden solver, w tym przez Qiskit sabre (wcześniej sabre wygrywał 4 przypadki; po naprawie exact_dp bije/wyrównuje go wszędzie). Stare brute'y to baselines "greedy swapy", nie ideał. `tabu_fidelity` wzmocnione: pełny porządek topologiczny jako reprezentacja (zamiana niezależnych par, restart losowym porządkiem), lookahead greedy (kubit z większą przyszłą użytecznością do środka), polishing, warm start od SabreLayout. Efekt: 8/13 przypadków dokładnie na optimum, średnio +0.13 od optimum, tabu fidelity bije Qiskit sabre 6/13 vs 1/13. Pozostałe luki (dense_1 +21%, medium_1 +11%) to lokalne minima (patrz sekcja 6). 64 testy zielone.

## 8. Gdzie co jest

| Co | Gdzie |
|---|---|
| Solvery routingowe | `src/odra_router/routing/` (baseline.py, exact_dp.py, tabu.py, genetic.py, genetic_fidelity.py, tabu_fidelity.py) |
| Kontrakt i metryki | `src/odra_router/contract.py` |
| Topologia ODRA5 | `src/odra_router/arch.py` |
| Generatory obwodów | `src/odra_router/generator.py` (random_circuit, hard_circuit, layered_random_circuit, CLI odra-router-gen) |
| QUEKO (znane optimum) | `src/odra_router/queko.py` |
| Benchmarki (5 komend) | `src/odra_router/bench.py` |
| Fidelity (faza 3) | `src/odra_router/fidelity.py` (model, koszty, `calc_goal_function`, `cancelled_fidelity_cost`) |
| Move-based tabu (faza 3) | `src/odra_router/routing/tabu_fidelity.py` |
| Optymalizacja (faza 2) | `src/odra_router/optimize/` (cancel.py: `cancel_adjacent`, `reduce_input`; baseline.py: `OptimizationPass`) |
| Wyniki (gitignored) | `results/` (benchmark.csv, queko.csv, sweat.csv, sweat-summary.md, benchmark-fidelity.csv, fidelity-summary.md, long.csv, long-summary.md, gap-analysis.csv/md, crossover.csv/md, tabu-sweep.csv/md) |
| Skrypty analiz (2026-09-14) | `scripts/gap_analysis.py`, `scripts/crossover.py`, `scripts/tabu_sweep.py` |
| Wizualizacja (faza 3) | `visualize_results.py` -> `plots/` (gitignored) + `results_summary.md` |
| Dokumentacja | `README.md`, `AGENTS.md`, `docs/contract.md`, `docs/split.md`, `docs/benchmarks.md`, ten plik |
| Testy | `tests/` (m.in. test_contract.py, test_exact_dp.py, test_tabu_warmstart.py, test_sweat.py) |

## 9. Jak uruchomić

```bash
cd odra_transpilation
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
odra-router-bench          # syntetyki        -> results/benchmark.csv
odra-router-bench-queko    # QUEKO            -> results/queko.csv
odra-router-bench-sweat    # budżetowy sweep  -> results/sweat.csv + results/sweat-summary.md
odra-router-bench-fidelity # fidelity (faza 3) -> results/benchmark-fidelity.csv + fidelity-summary.md
odra-router-bench-long     # dłuższe instancje -> results/long.csv + long-summary.md
odra-router-gen --out benchmarks/generated   # partia losowych obwodów (QASM + manifest)
pip install -e ".[analysis]"  # tylko do wizualizacji
python visualize_results.py   # wykresy -> plots/*.png + results_summary.md
# analizy z 2026-09-14 (wyniki -> results/, gitignored):
python scripts/gap_analysis.py   # czemu Qiskit preset schodzi pod exact_dp
python scripts/crossover.py      # crossover: exact_dp vs budżetowe tabu vs rozmiar
python scripts/tabu_sweep.py     # sweep parametrów tabu_fidelity (po jednym knobie)
```

## Stan na 2026-09-04: faza 2 anulowania, true minimum, domknięcie medium_1

Cztery commity na `main` (32cc4aa..6588da3). 88 testów zielonych.

### 1. Anulowanie bramek (optimize/cancel.py)

- `cancel_adjacent()` usuwa sąsiednie samoodwracalne pary dwukubitowe
  (CX-CX w tej samej orientacji, CZ-CZ, SWAP-SWAP) na tej samej parze
  fizycznej, tylko gdy nic na tych drutach nie leży między nimi; pętla do
  punktu stałego (usunięcie pary może ujawnić kolejną). `reduce_input()` to
  ten sam pass na wejściu (pre-routing).
- `OptimizationPass.run()` (optimize/baseline.py) przestał być tożsamością.
- `contract.cancelled_metrics()` i `fidelity.cancelled_fidelity_cost()`:
  metryki po anulowaniu.
- Efekt pre-routingowy (zmierzony): rand40_s1 traci 4 bramki, SWAP-y spadają
  16 -> 13; przykład deterministyczny cx(0,1) cx(0,1) cx(3,4): 2 -> 1 SWAP.

### 2. True minimum (ideał szuka minimum po anulowaniu)

- Benchmark fidelity i wszystkie solvery działają na `reduce_input(circuit)`,
  a wynik każdego solvera jest dodatkowo punktowany po anulowaniu
  (kolumny `*_cancelled` w CSV, podsumowanie liczy `fidelity_cost_cancelled`).
- Brama weryfikacyjna (zmierzona na całej suicie): żaden solver po
  anulowaniu nie bije `exact_dp` na zredukowanym problemie, a własne wyjście
  `exact_dp` jest już wolne od anulowalnych par. Dolne ograniczenie trzyma,
  więc rozszerzanie stanu DP o anulowanie jest zbędne (test regresyjny w
  tests/test_cancelled_ideal.py).
- Redukcja wejścia obniża ideał na small_1, medium_0, medium_1, heavy_1,
  dense_0, dense_1 (np. dense_0: 3.7288 -> 3.2023 po redukcji i anulowaniu).

### 3. Tabu: domknięcie medium_1, diagnoza reszty luk

- Diagnoza (wszystko zmierzone skryptami ad hoc): luki `dense_0` +8%,
  `dense_1` +12.6%, `hard_8r` +8.9% (metryka true minimum) to optima
  globalnie skoordynowane. Nie leżą w obrazie greedy nawet własnego
  (layout, order) (16 różnic), są nieosiągalne pojedynczymi ruchami z żadnego
  z 12 ziaren, ILS z podwójnymi kopnięciami (400), VNS po layoutach i
  orderach z głębokim suffix descent (534 iteracje), brute force po 120
  layoutach z tożsamościowym orderem ani dłuższe losowe wędrówki tabu
  (240k iteracji). Wniosek: tych luk nie domyka się ruchami sąsiedztwa;
  `exact_dp` (0.02-1.2 s) przeszukuje całą przestrzeń stanów.
- `medium_1` (+0.5%) to minimum lokalne parowe (ten sam layout, ten sam
  order, ta sama liczba SWAP-ów, inne interakcje): polish dostał skan par
  wyborów z capem ewaluacji (25k) i domyka je do 0.00% we wszystkich
  wariantach tabu (test regresyjny w tests/test_tabu_fidelity.py).
- Wyniki na metryce true minimum (13 przypadków, gap do `exact_dp`):
  tabu_fidelity = 0% na 9/13 (tiny_x, small_x, medium_0/1, heavy_0/1,
  hard_2r). Resztki: hard_4r +0.5-0.8%, dense_0 +7.9%, hard_8r +8.9%,
  dense_1 +12.6-19.9%. Wzorzec utrzymuje się na dłuższych instancjach
  (`odra-router-bench-long`: tabu 10-17% ponad exact_dp, greedy/brute
  31-56%). Qiskit sabre: 1.5-48% ponad ideał. `qiskit_preset` bywa niżej od
  naszego ideału na small_0/heavy_1, bo pełna optymalizacja Qiskita anuluje
  więcej niż nasz pass; nasz ideał to optimum routingu plus anulowania
  sąsiedniego, nie pełna optymalizacja obwodu.

### 4. Generator i dłuższe testy

- `odra-router-gen`: deterministyczna partia obwodów (random + hard) jako
  QASM 2.0 plus manifest.json; `layered_random_circuit()` (warstwy
  z rozłącznymi bramkami 2Q, bliżej prawdziwych obwodów).
- `odra-router-bench-long`: hard do 16 rund (96 interakcji), random do 160
  bramek, QUEKO d32. exact_dp kończy w mniej niż 1.2 s, więc ideał jest
  dostępny jako referencja.
- Nowe testy: anulowanie (13), true minimum (3), domknięcie medium_1 (1),
  generator (3), długie i różnorodne (4). Razem 88 zielonych.

### Uwaga o wynikach

`results/` są gitignored: benchmark-fidelity.csv i long.csv z podsumowaniami
zostały przeliczone według nowej metryki (zredukowane wejście plus kolumny
`*_cancelled`). Stare surowe wyniki nie są wprost porównywalne z nowymi.

## Stan na 2026-09-14: czemu tabu, gdy exact_dp jest lepsze i szybsze (branch `analysis/why-tabu`)

Pytanie z zespołu: po co tabu, skoro `exact_dp` jest dokładny i szybszy.
Odpowiedź: na 5-kubitowej gwieździe faktycznie jest, w całym obecnym
zakresie (0.02-1.2 s na 13 przypadkach fidelity). Trzy analizy mierzą, gdzie
ta wygoda się kończy i co tabu daje poza nią. Wyniki w `results/`
(gitignored), skrypty w `scripts/`.

### 1. Gap analysis: czemu Qiskit preset schodzi pod nasz ideał

- `results/gap-analysis.md`, `scripts/gap_analysis.py`.
- `exact_dp` to dolne ograniczenie naszej gry (layout + SWAP-y po krawędziach
  + dowolny porządek topologiczny + anulowanie dosłownie sąsiednich par).
  Preset gra w szerszą grę (komutacja, resynteza 1Q i bloków 2Q, CX na CZ),
  więc ma prawo zejść niżej i nie jest to błąd ideału.
- Zmierzone: preset schodzi pod ideał w 3 z 13 przypadków (small_0, medium_1,
  heavy_1), zawsze na poziomie L2 albo wyżej, a mechanizmem jest komutacja
  nieprzylegających bramek, nie anulowanie.
- Nasz cancel nie tłumaczy żadnej części tej przewagi: `our-cancel` = 0 na
  wszystkich przypadkach (Qiskit nie zostawia dosłownie sąsiednich par).
  Redukcja wejścia obniża nasz własny ideał na 6 przypadkach, ale nie pomaga
  przeciw presetowi.
- Każdy przypadek z przewagą Qiskita ma przypisaną przyczynę, `other` nie
  występuje ani raz. Preset jest liczony jako najlepszy z 5 ziaren
  (`qiskit_baseline` dostał parametr `seed`; wcześniej jedno losowanie).

### 2. Crossover: gdzie `exact_dp` przestaje być darmowy

- `results/crossover.md`, `scripts/crossover.py`.
- Drabinka `hard_circuit(r)` (cykl po 6 parach niekrawędziowych, każda
  interakcja wymaga SWAP-a), od 24 do 530 interakcji. Przestrzeń stanu DP to
  (frontier, layout), szerokość frontieru <= 2, więc koszt rośnie w
  przybliżeniu kwadratowo w liczbie interakcji.
- Punkty przecięcia: przy budżecie 0.05 s ideał dojeżdża do hard_4r, przy
  0.25-0.5 s do hard_8r, przy 1 s do hard_16r. Na hard_96r sam ideał liczy
  111 s, a tabu w budżecie 1 s ma gap około +15.6.
- Tabu nie dogania ideału w żadnym budżecie na tej drabince (najlepszy gap od
  +0.011 na hard_4r do +15.1 na hard_96r), ale jako jedyny odpowiada w stałym
  czasie. Te resztki to minima lokalne, nie brak budżetu.
- Wniosek: tabu ma sens jako zamiennik o stałym koszcie, gdy DP przestaje się
  mieścić. Dla obecnych 13 przypadków fidelity DP jest tańszy i dokładny,
  więc tabu jest tam wyłącznie punktem odniesienia dla przyszłych topologii.

### 3. Sweep parametrów tabu: czego nie da się dokręcić

- `results/tabu-sweep.md`, `scripts/tabu_sweep.py`. Baseline plus 11 wariantów
  po jednym knobie (`tenure`, `max_iterations`, `stagnation_limit`, `polish`),
  13 przypadków, 2 ziarna, budżet 30 s.
- Żaden knob nie zamyka resztkowych luk (dense_0, dense_1, hard_8r): to
  strukturalne minima lokalne gwiazdy, nie artefakt strojenia. Zakres
  średniego gapu po wszystkich konfiguracjach: +0.098 do +0.129.
- Najbardziej czuły knob to `polish`: wyłączenie podnosi średni gap o +0.022
  i pogarsza najgorszy przypadek do +0.97. `max_iterations=500` podnosi
  średni gap o +0.010 i ścina trafienia w optimum z 69% do 50%. `tenure=32`
  i `stagnation_limit=1000` obniżają średni gap o około 0.008, czyli w
  granicach szumu.
- Knoby kupują albo kosztują czas (mediana od 0.05 s dla
  `max_iterations=500` do 0.72 s dla 20000), jakość na tej topologii i tak
  się nasyca.

### 4. Rzetelność budżetu

- `polish` w `tabu_fidelity` ignorował `budget_s` (do 15.6 s polerowania przy
  budżecie 0.25 s na obwodzie o 270 interakcjach), przez co sweepy budżetowe
  mierzyły coś innego, niż deklarowały. Deadline jest teraz respektowany także
  w polish, a przekroczenie widać w kolumnie `deadline_hit`.
- `exact_dp` dostał flagę `last_hit_budget`: przy przekroczeniu budżetu spada
  na greedy, a bez tej flagi nie da się odróżnić prawdziwego ograniczenia od
  fallbacku (kolumna `dp hit` w crossover).

### 5. Wykresy i podsumowanie

- `visualize_results.py` wybiera jednego reprezentanta na rodzinę (warianty
  różnią się tylko startem), scala rodziny o identycznych wektorach kosztu i
  wypisuje, ile scalony wariant faktycznie się różnił (dla `tabu_fidelity`
  maks. 0.34 na 2/13 przypadków), żeby nic nie zniknęło pod etykietą.
- 5 wykresów: gap do ideału, jakość vs czas (skala log), heatmapa gap per
  przypadek, szczegół przypadków oraz crossover (czas i gap vs liczba
  interakcji). `plots/` jest gitignored, `results_summary.md` jest w repo.
- 88 testów zielonych.
