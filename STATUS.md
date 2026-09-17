# STATUS: odra-router (repo: odra_transpilation)

Stan na 2026-09-17 (najnowsze sekcje na dole: analiza "czemu tabu" z torami A-D i reguła wyboru solvera; wcześniej faza 2 z 2026-09-04; starsze sekcje 1-7 to historia z 2026-08-31). Repo: `git@github.com:k3chupe/odra_transpilation.git`, lokalnie `/workspace/repos/odra_transpilation`.
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
| `genetic_fidelity` | pełne kodowanie (layout, wybory SWAP-ów, flagi) z natywnym celem fidelity, start losowy | metaheurystyka fidelity |
| `genetic_fidelity_greedy` | jak wyżej, warm start z layoutu identycznościowego | metaheurystyka fidelity |
| `genetic_fidelity_sabre` | jak wyżej, warm start z layoutu SabreLayout | metaheurystyka fidelity |
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
4. **Uczciwa metryka `cz_cost`**. Wcześniej `qiskit_preset` raportował zawsze 0 SWAP-ów (gwiazda nie ma natywnego SWAP, Qiskit rozkłada go na 3 CZ), przez co wyglądał na "zawsze optymalny". Teraz każdy solver ma wspólny koszt w basisie natywnym.
5. **Naprawa buga w `exact_dp`**. Mapa CouplingMap ODRA5 jest skierowana, a `cm.neighbors()` zwraca tylko krawędzie wychodzące, przez co DP wpadał w ślepą uliczkę na obwodach wymagających SWAP-ów i cicho zwracał wynik greedy (na hard_8r: 34 zamiast prawdziwych 32). Po naprawie (nieskierowani sąsiedzi) exact_dp jest dokładny; są testy regresyjne.
6. **Benchmark "pocenia" `odra-router-bench-sweat`**: sweep budżetu czasowego (0.05-1.0 s) x 5 powtórzeń na ~10 instancjach, z referencją brute force i kolumną `evals` (solvery raportują, ile layoutów faktycznie oceniły).
7. **Hard generator `hard_circuit`**: cykl po 6 parach niekrawędziowych gwiazdy, wymusza ciągły routing przez centrum. Gęste obwody losowe nie wystarczają, bo nasycają się (greedy = brute = dp).
8. **Wszystko zielone i wypchnięte**: 45 testów przechodzi, commity `a8d27a0` i `f59c50d` są na `main`.

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
4. ~~**Prawdziwy GA** w `routing/genetic.py` (pisze go kolega)~~ zrobione 2026-09-14: branch `feature/genetic-solver-fidelity` (24ea63f, autor Comprex) zmergowany do `main`; GA po layoutach siedzi w `routing/genetic.py` (`genetic_search`), a pełny GA fidelity w `routing/genetic_fidelity.py` (`genetic_fidelity*`).
5. ~~**Wykresy** z wyników (`visualize_results.py`)~~ zrobione 2026-09-14: reprezentant rodziny zamiast 12 prawie identycznych wariantów, 5 wykresów, ideał jako odniesienie (sekcja na końcu).

Świadomie odłożone: większe topologie i więcej kubitów (poza zakresem ODRA5), QASMBench/MQT Bench (za duże albo niezgodne z qiskit 1.2).

Odłożone po pomiarach z 2026-09-14 (patrz "Tor C" i "Tor D", punkty 7-8 na końcu, powtórzone 2026-09-17):

6. **DP z wolnym porządkiem bramek**: plan zakładał, że uwolnienie komutacji rozsadzi przestrzeń stanów. Pomiar tego nie potwierdza (liczba porządków rośnie o 1e9.8 na hard_16r, ale zbiór osiągalnych stanów tylko się podwaja: ~26 tys. stanów razy 120 layoutów). Nadal odłożone, ale jako realna opcja, nie jako "za drogie": wymaga osobnego przejścia dla bramek 1Q i walidacji unitarnej.
7. **N kubitów**: poza zakresem ODRA5. Zmierzone (star i line, n = 5..8): `exact_dp` przestaje się mieścić w 60 s dopiero przy n = 8 (40320 layoutów), na n = 7 liczy 7.5 s. To argument za metaheurystykami na większych topologiach, nie powód do rozszerzania projektu teraz.

## 7. Co robimy teraz

Faza 3 (fidelity-aware move-based tabu) wdrożona i zmierzona; benchmark `odra-router-bench-fidelity`. `exact_dp` jest teraz **prawdziwym dolnym ograniczeniem**: pełne przeszukanie (layouty, dowolne SWAP-y na krawędziach, dowolny porządek topologiczny z przeplotami, dokładny koszt fidelity), nie do pobicia przez żaden solver, w tym przez Qiskit sabre (wcześniej sabre wygrywał 4 przypadki; po naprawie exact_dp bije/wyrównuje go wszędzie). Stare brute'y to baselines "greedy swapy", nie ideał. `tabu_fidelity` wzmocnione: pełny porządek topologiczny jako reprezentacja (zamiana niezależnych par, restart losowym porządkiem), lookahead greedy (kubit z większą przyszłą użytecznością do środka), polishing, warm start od SabreLayout. Efekt: 8/13 przypadków dokładnie na optimum, średnio +0.13 od optimum, tabu fidelity bije Qiskit sabre 6/13 vs 1/13. Pozostałe luki (dense_1 +21%, medium_1 +11%) to lokalne minima (patrz sekcja 6). 64 testy zielone.

Kiedy brać `exact_dp`, a kiedy tabu (i który wariant tabu jest domyślny): punkt 9 sekcji "Stan na 2026-09-17" na końcu, z liczbami z torów A, C i D.

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
| Wyniki (gitignored) | `results/` (benchmark.csv, queko.csv, sweat.csv, sweat-summary.md, benchmark-fidelity.csv, fidelity-summary.md, long.csv, long-summary.md, gap-analysis.csv/md, crossover.csv/md, tabu-sweep.csv/md, scale-probe.csv/md, order-free-probe.csv/md, n-qubit-crossover.csv/md) |
| Skrypty analiz (2026-09-14) | `scripts/gap_analysis.py`, `scripts/crossover.py`, `scripts/tabu_sweep.py`, `scripts/scale_probe.py` |
| Eksperymenty poza ODRA5 (`experiments/`) | `order_free_probe.py` (tor C), `n_qubit_crossover.py` (tor D) |
| Wizualizacja (faza 3) | `visualize_results.py` -> `plots/` (gitignored) + `results_summary.md` |
| Dokumentacja | `README.md`, `AGENTS.md`, `docs/contract.md`, `docs/split.md`, `docs/benchmarks.md`, ten plik |
| Testy | `tests/` (m.in. test_contract.py, test_exact_dp.py, test_tabu_warmstart.py, test_sweat.py, test_ideal_boundary.py, test_n_qubit.py) |

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
python scripts/scale_probe.py    # tor A: która oś rozmiaru płaci za ideał
# eksperymenty poza zakresem ODRA5 (wyniki -> results/, gitignored):
python experiments/order_free_probe.py    # tor C: wolny porządek bramek vs stan DP
python experiments/n_qubit_crossover.py   # tor D: gwiazda i linia, n = 5..8
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
- `odra-router-bench-long`: trzy rodziny instancji (patrz "Tor A" na końcu):
  hard do 64 rund (360 interakcji), random do 512 bramek, layered do 256
  warstw (634 bramki), plus QUEKO d32. `exact_dp` dojeżdża do kilkudziesięciu
  sekund na najdłuższych (liczby w "Tor A"), więc referencja jest nadal
  dostępna; kolumna `budget_hit` mówi, kiedy spadł na greedy.
- Nowe testy: anulowanie (13), true minimum (3), domknięcie medium_1 (1),
  generator (3), długie i różnorodne (4). Razem 88 zielonych.

### Uwaga o wynikach

`results/` są gitignored: benchmark-fidelity.csv i long.csv z podsumowaniami
zostały przeliczone według nowej metryki (zredukowane wejście plus kolumny
`*_cancelled`). Stare surowe wyniki nie są wprost porównywalne z nowymi.

## Stan na 2026-09-17: czemu tabu, gdy exact_dp jest lepsze i szybsze

Pytanie z zespołu: po co tabu, skoro `exact_dp` jest dokładny i szybszy.
Odpowiedź: na 5-kubitowej gwieździe faktycznie jest, w całym obecnym
zakresie (0.02-1.2 s na 13 przypadkach fidelity). Trzy analizy (punkty 1-3)
mierzą, gdzie ta wygoda się kończy i co tabu daje poza nią, trzy tory
(punkty 6-8) domykają pytanie o skalę i granice referencji, a punkt 9 to
reguła wyboru solvera i domyślny wariant tabu. Granica ideału jest spisana
w `docs/contract.md`. Wyniki w `results/` (gitignored), skrypty w `scripts/`
i `experiments/`. Kod z obu branchy (`analysis/why-tabu` i
`wip/tor-a-d-2026-09-14`) jest w `main`.

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
- Granica ideału jest spisana w `docs/contract.md` (sekcja "Ideal boundary
  (decision: variant A)"): co dokładnie gra ideał, co jest poza jego grą i
  dlaczego nie rozszerzamy referencji. Pinują to 4 testy
  w `tests/test_ideal_boundary.py` (m.in. sprawdzają, że na small_0 preset
  naprawdę schodzi pod ideał, a nasz pass sąsiedni nie zabiera z tej przewagi
  nic).

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
- `exact_dp` dostał flagę `last_hit_budget`: budżet jest sprawdzany co iterację
  Dijkstry, a przy jego przekroczeniu solver spada na greedy i wynik jest równy
  greedy. Bez tej flagi nie da się odróżnić prawdziwego ograniczenia od
  fallbacku (kolumna `dp hit` w crossover). Przykład: hard_64r potrzebuje około
  33 s, więc przy capie 30 s wpada w fallback (30.8 s, `hit=1`), a przy capie
  300 s domyka w 33.2 s; rand512_s0 domyka się w 29.1 s, o włos pod capem 30 s.
  Flaga znaczy "to jest fallback greedy", a nie "nie zmieściło się w budżecie".

### 5. Wykresy i podsumowanie

- `visualize_results.py` wybiera jednego reprezentanta na rodzinę (warianty
  różnią się tylko startem), scala rodziny o identycznych wektorach kosztu i
  wypisuje, ile scalony wariant faktycznie się różnił (dla `tabu_fidelity`
  maks. 0.34 na 2/13 przypadków), żeby nic nie zniknęło pod etykietą.
- 5 wykresów: gap do ideału, jakość vs czas (skala log), heatmapa gap per
  przypadek, szczegół przypadków oraz crossover (czas i gap vs liczba
  interakcji). `plots/` jest gitignored, `results_summary.md` jest w repo.
- 108 testów zielonych na tym branchu: 99 po merge genetyka plus 4 testy granicy
  ideału, 4 testy N kubitów i 1 test obu osi rozmiaru.

### 6. Tor A: co naprawdę płaci za ideał (rozszerzone `long_cases`)

- Wyniki: `results/scale-probe.md`, `results/long.csv` i `long-summary.md`;
  kod: `scripts/scale_probe.py` plus rozszerzone `long_cases()` w `bench.py`.
- `long_cases()` ma trzy rodziny, żeby dało się rozdzielić dwie osie rozmiaru:
  hard do 64 rund (360 interakcji po redukcji), random do 512 bramek, layered
  do 256 warstw (634 bramki, 215 interakcji) i QUEKO d32.
- Czas ideału idzie za liczbą interakcji, nie za liczbą bramek: od 0.019 s
  (queko_d32, 15 interakcji) do 33.2 s (hard_64r, 360 interakcji) na 12
  przypadkach, które zmieściły się w capie 300 s.
- Grupa kontrolna się trzyma: layered256 ma 634 bramki (najwięcej bramek w
  zestawie ma rand512_s0, 664) i tylko 215 interakcji, kosztuje 14.0 s, mniej
  niż hard_64r (384 bramki, 360 interakcji, 33.2 s). Bramki 1Q są dla
  wyszukiwania darmowe, a 120 layoutów to stała, więc sama liczba bramek nie
  wycenia ideału.
- W benchmarku long (cap 30 s) najdroższą domkniętą referencją jest rand512_s0
  (29.1 s), a hard_64r cap już łapie: ideał potrzebuje tam około 33 s, więc
  schodzi na greedy (`hit=1`, 30.8 s) i wiersze z tego bloku nie są
  ograniczeniem. Kolumna `budget_hit` istnieje właśnie po to, żeby takich
  wierszy nie cytować jako granicy. Struktura obu osi rozmiaru jest pinowana
  testem `test_long_cases_separate_the_two_size_axes`.

### 7. Tor C: ile kosztowałby DP z wolnym porządkiem bramek

- Wyniki: `results/order-free-probe.md`; kod: `experiments/order_free_probe.py`.
  Bez zmian w solverach: eksperyment liczy dwa posety (ustalony porządek, czyli
  gra `exact_dp`: każda para interakcji dzieląca kubit jest uporządkowana;
  wolny porządek: krawędź zostaje tylko wtedy, gdy bramki dzielą kubit i nie
  komutują, sprawdzane checkerem komutacji Qiskita), estymuje liczbę rozszerzeń
  liniowych estymatorem Knutha (200 próbek) i liczy dokładnie liczbę
  osiągalnych stanów posetu.
- Liczba porządków rzeczywiście eksploduje: na hard_4r/8r/16r rośnie o 1e0.8,
  1e3.8 i 1e9.8. Zbiór osiągalnych stanów (done-setów) rośnie jednak tylko
  z 30/59/116 do 39/95/223, czyli mniej więcej się podwaja. Stan DP to done-set
  razy 120 layoutów, więc cała przestrzeń rośnie z 1e3.6 do 1e3.7, z 1e3.9 do
  1e4.1 i z 1e4.1 do 1e4.4 (około 27 tys. stanów na hard_16r).
- Szerokość posetu (największy antyłańcuch) rośnie z 2 do 3 na hard_4r i hard_8r
  oraz z 2 do 5 na hard_16r, czyli gotowych interakcji naraz jest więcej, ale
  nadal kilka.
- Wniosek: założenie z planu ("wolny porządek rozsadzi przestrzeń stanów") jest
  fałszywe na pięciu kubitach, jeśli stanem DP jest done-set, a nie pełny
  porządek. Punkt 6 listy "do zrobienia" zostaje odłożony, ale jako tańszy niż
  zakładano, nie jako zbyt drogi. Warunek wstępny: osobne przejście dla bramek
  1Q (probe liczy samą grę routingową) i walidacja unitarna wyniku.

### 8. Tor D: gdzie ideał przestaje się mieścić (N kubitów)

- Wyniki: `results/n-qubit-crossover.md`; kod: `experiments/n_qubit_crossover.py`;
  testy: `tests/test_n_qubit.py`.
- Topologie syntetyczne (gwiazda i linia, n = 5..8), losowe obwody po 40 bramek,
  model fidelity w zakresie wartości placeholdera ODRA5. `exact_dp` z capem 60 s,
  `tabu_fidelity` z budżetem 1 s, greedy za darmo jako baseline.
- Gwiazda: 0.06 s (n=5), 0.59 s (n=6), 7.5 s (n=7), a na n=8 (40320 layoutów)
  60.9 s z przekroczeniem capa i zejściem na greedy. Linia tak samo (7.5 s na
  n=7, 60.9 s na n=8). Crossover to skok z 5040 na 40320 layoutów, czyli silnia
  po liczbie kubitów, a nie liczba interakcji (wszystkie przypadki mają 23-26
  interakcji, bo obwody są tej samej długości).
- Tabu w stałym budżecie 1 s odpowiada na każdym n: gap 10.3% (n=5), 6.6% (n=6),
  6.3% (n=7); na n=8 gapu nie ma, bo nie ma już zweryfikowanego ograniczenia
  (ideał zszedł na greedy), a tabu i tak odpowiada w 1.0 s.
- Na linii `tabu_fidelity` jest raportowane jako n/a: koduje jeden SWAP na
  interakcję, co jest zupełne tylko na topologii z centrum. To ograniczenie
  reprezentacji, nie błąd pomiaru.
- Do tego eksperymentu biblioteka musiała przestać zakładać ODRA5:
  `FidelityModel` przyjmuje dowolną topologię, `exact_dp` i `tabu_fidelity`
  przyjmują model w konstruktorze, a `tabu_fidelity` bierze listę SWAP-ów
  z coupling mapy. Na ODRA5 historyczna numeracja krawędzi i sąsiedztwo pięciu
  wyborów zostają bez zmian, pilnują tego `tests/test_fidelity.py`
  i `tests/test_n_qubit.py`.

### 9. Reguła wyboru solvera i domyślny tabu

Kolejność decyzji:

1. Referencja: `exact_dp` na zredukowanym wejściu, dopóki się mieści. Na 13
   przypadkach fidelity (do 96 interakcji) to 0.02-1.2 s; w scale-probe
   (cap 300 s) 0.43 s przy I=72, 0.87 s przy I=96, 4.9 s przy I=184, 14 s przy
   I=215 i 33 s przy I=360. Punkty przecięcia z `crossover.md`: przy budżecie
   0.05 s ideał dojeżdża do I=24, przy 0.25 s do I=48, przy 1 s do I=96.
   Praktyczny próg: I do około 100 interakcji albo budżet rzędu kilku sekund.
   Czasu sekundowego nie traktujemy jak stałej: ten sam hard_64r (I=360) wyszedł
   33 s w scale-probe i 55 s w crossover, więc liczy się rząd wielkości.
2. Twardy budżet (0.1-1 s na solve) albo I ponad około 150: `tabu_fidelity`
   z budżetem, z jawnym zapisem, że wynik nie jest ograniczeniem. Gap rośnie
   od +1.5 (I=96) do +15.1 (I=530).
3. Gapy, wykresy i "wygrane z Qiskitem" liczymy tylko z wierszy, w których
   wiersz ideału ma `budget_hit=0`. Przy fladze 1 ideał to greedy, więc gap
   jest mierzony do fallbacku, a nie do ograniczenia.
4. Poza ODRA5 (n = 8 na gwieździe albo na linii, setki interakcji) ideał
   przestaje być darmowy (Tor D), a tabu odpowiada w stałym budżecie. Tam
   metaheurystyki mają realną robotę.
5. Tabu po layoutach (`tabu_search`, `tabu_sabre_start`) nie jest domyślnym
   wyborem nigdzie: na gwieździe 24 z 120 layoutów są optymalne, więc nie ma
   czego szukać, a narzut jest realny (pełny przebieg to około 16 tys.
   ewaluacji layoutów, sekcja 4). Zostają zarejestrowane jako warianty
   historyczne.

Domyślny wariant tabu: `tabu_fidelity`, start losowy, domyślne knoby
(`tenure=8`, `max_iterations=6000`, `stagnation_limit=500`, `polish=True`).
Wybór idzie z reguły reprezentanta w `scripts/tabu_sweep.py`: Pareto na parze
(średni gap, mediana czasu), pasmo jakości 0.02 średniego gapu, remisy
rozstrzygane na korzyść krótszego czasu. Wynik na ziarnach 0,1:
baseline zostaje, bo najszybsza konfiguracja w pasmie (`max_iterations=500`,
mediana 0.066 s) ma średni gap gorszy od baseline o 0.0098, czyli poniżej
progu. Replikacja na ziarnach 2,3,4 (`results/cross-seed/`) jest powodem, dla
którego pasmo ma 0.02, a nie 0.005: przy węższym pasmie reguła promowała
`tenure=32` (lepszy o 0.0077 na ziarnach 0,1), ale na ziarnach 2,3,4 ten sam
wariant wypadł o 0.0005 gorzej od baseline, a pojedyncze konfiguracje
przesunęły się o do 0.017 średniego gapu. Promocja knoba na różnicy tej
wielkości byłaby dopasowaniem szumu.
Warm start nie daje mierzalnej przewagi (warianty greedy i sabre siedzą w tym
samym pasmie, na fidelity suite różnice są w granicach szumu), a `polish` jest
najczulszym knobem (wyłączenie podnosi średni gap o 0.022), więc zostaje
włączony. Warianty `tabu_fidelity_greedy` i `tabu_fidelity_sabre` zostają
zarejestrowane jako warianty warm startu, ale nowy kod domyślnie bierze
`tabu_fidelity`.
