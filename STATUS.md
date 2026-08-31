# STATUS: qtrans (odra_transpilation)

Stan na 2026-08-31. Repo: `git@github.com:k3chupe/odra_transpilation.git`, lokalnie `/workspace/repos/odra_transpilation`.
Nota: ten dokument jest po polsku, bo to status dla zespołu; kod i reszta dokumentacji są po angielsku.

## 1. O co chodzi

Kwantowy transpiler dla topologii ODRA5 (IQM Adonis), gwiazdy o 5 kubitach z centrum w kubicie 2. Budujemy własne stage'y **routingu** (wybór układu kubitów i wstawianie SWAP-ów, żeby bramki dwukubitowe lądowały na sąsiednich fizycznych kubitach) i porównujemy je z transpilerem Qiskit 1.2 (przypięty `qiskit==1.2.4`).

Każdy solver rejestruje się przez kontrakt (`src/qtrans/contract.py`), a testy automatycznie sprawdzają każdy zarejestrowany solver. Solver zwraca `RoutingSolution` (layout początkowy + harmonogram SWAP-ów), nigdy nie modyfikuje wejściowego obwodu.

## 2. Solvery i benchmarki

| Solver | Co robi | Rola |
|---|---|---|
| `greedy_shortest_path` | greedy na layoutcie identycznościowym | najprostszy punkt odniesienia |
| `brute_force_layout` | sprawdza wszystkie 120 layoutów z greedy SWAP-ami | **referencja** (odległość od ideału) |
| `exact_dp` | dokładny dla ustalonej kolejności bramek (DP po layoutach i SWAP-ach) | **referencja** (dolne ograniczenie) |
| `tabu_search` | tabu po layoutach, start losowy | metaheurystyka |
| `tabu_sabre_start` | tabu, start z layoutu wybranego przez jeden przebieg Sabre | metaheurystyka, test warm startu |
| `genetic_trivial` | minimalny GA po layoutach (turniej, OX1, mutacja) | placeholder do porównania |
| `genetic.py` | stub, nie zarejestrowany | prawdziwy GA, pisze go kolega |
| `sabre_baseline` | zepsuty, wyłączony z benchmarków i testów | do naprawy albo usunięcia |
| `qiskit_preset` | pełny preset transpilera Qiskit na target ODRA5 | baseline zewnętrzny |

Benchmarki (wszystkie w `src/qtrans/bench.py`, wyniki do `results/`):

- `qtrans-bench` - syntetyczne obwody z `benchmarks/suite.json` -> `results/benchmark.csv`
- `qtrans-bench-queko` - obwody QUEKO ze znanym optimum 0 SWAP-ów -> `results/queko.csv`
- `qtrans-bench-sweat` - budżetowy sweep (czas x powtórzenia) na hard/gęstych/głębokich instancjach -> `results/sweat.csv` + `results/sweat-summary.md`

Metryki: `swap_count` (logiczne SWAP-y), `cz_cost` (bramki dwukubitowe po przeliczeniu na basis natywny, SWAP = 3 CZ), `depth`, `evals` (liczba ewaluacji layoutów w jednym solve), `seconds`.

## 3. Co się udało

1. **Tabu search nad layoutami** w dwóch wariantach: `tabu_search` (start losowy) i `tabu_sabre_start` (warm start z layoutu SabreLayout, fallback na random przy błędzie). Oba zarejestrowane, otestowane i w benchmarkach.
2. **Trywialny GA** (`genetic_trivial`) jako punkt porównania, celowo minimalny. Plik `routing/genetic.py` zostaje nietknięty dla kolegi, który pisze prawdziwy GA.
3. **Uczciwa metryka `cz_cost`**. Wcześniej `qiskit_preset` raportował zawsze 0 SWAP-ów (gwiazda nie ma natywnego SWAP, Qiskit rozkłada go na 3 CZ), przez co wyglądał na "zawsze optymalny". Teraz każdy solver ma wspólny koszt w basisie natywnym.
4. **Naprawa buga w `exact_dp`**. Mapa CouplingMap ODRA5 jest skierowana, a `cm.neighbors()` zwraca tylko krawędzie wychodzące, przez co DP wpadał w ślepą uliczkę na obwodach wymagających SWAP-ów i cicho zwracał wynik greedy (na hard_8r: 34 zamiast prawdziwych 32). Po naprawie (nieskierowani sąsiedzi) exact_dp jest dokładny; są testy regresyjne.
5. **Benchmark "pocenia" `qtrans-bench-sweat`**: sweep budżetu czasowego (0.05-1.0 s) x 5 powtórzeń na ~10 instancjach, z referencją brute force i kolumną `evals` (solvery raportują, ile layoutów faktycznie oceniły).
6. **Hard generator `hard_circuit`**: cykl po 6 parach niekrawędziowych gwiazdy, wymusza ciągły routing przez centrum. Gęste obwody losowe nie wystarczają, bo nasycają się (greedy = brute = dp).
7. **Wszystko zielone i wypchnięte**: 45 testów przechodzi, commity `a8d27a0` i `f59c50d` są na `main`.

## 4. Co wiemy (najważniejsze wnioski)

- **Dla każdego obwodu na gwieździe ODRA5 dokładnie 24 z 120 layoutów osiąga optimum** (4! permutacji liści, symetria gwiazdy). Losowe próbkowanie trafia optymalny layout z prawdopodobieństwem 20% na próbę.
- Skutek: **jakość nasyca się**. `brute_force_layout` = `exact_dp` = `tabu` = `GA` co do liczby SWAP-ów (sprawdzone na hard i losowych instancjach). Jedyny odstający to `greedy` (layout identycznościowy): na hard instancjach gap 1-2 SWAP-y i 0% trafień w optimum.
- To, co naprawdę odróżnia solvery na 5 kubitach, to **narzut czasowy i ewaluacyjny**: pełny przebieg tabu to ~16 tys. ewaluacji layoutów, GA ~2.5 tys., brute 120, greedy 1. Czas przy tej samej jakości: brute/exact_dp ~0.02-0.09 s, tabu/GA ~0.05-0.14 s.
- **Warm start z Sabre nie daje mierzalnej przewagi na ODRA5** (przy 24/120 optymalnych layoutów każdy start zbiega szybko; wcześniejsza ablacja na QUEKO 11/15 na korzyść warm startu, na syntetyku remis).
- `qiskit_preset` ma niższy `cz_cost` niż nasze solvery na syntetykach, bo preset robi pełną optymalizację (m.in. anulowanie bramek), a nasz projekt na razie robi tylko routing.

## 5. Czego nie da się zrobić na 5 kubitach

Nie da się sprawić, żeby algorytmy szukające layoutów "pociły się" na gwieździe ODRA5: przestrzeń to 120 layoutów, a 24 z nich są zawsze optymalne, więc metaheurystyki zbiegają niemal natychmiast. Prawdziwe "pocenie" wymaga:

- większej liczby kubitów (przestrzeń layoutów rośnie jak n!), albo
- zmiany przestrzeni poszukiwań: przeszukiwanie sekwencji SWAP-ów zamiast layoutów (przestrzeń wykładnicza w liczbie interakcji; dokładnie to robi exact_dp, ale tylko dla ustalonej kolejności bramek i tylko na małych instancjach).

## 6. Co jest do zrobienia

Proponowane priorytety:

1. **Move-based tabu**: przeszukiwanie sekwencji SWAP-ów zamiast samych layoutów. To tam naprawdę jest co porównywać i gdzie metaheurystyki mają sens. Naturalna kontynuacja tabu (w kodzie jest ponytail o tym jako przyszłym rozszerzeniu).
2. **Faza 2 optymalizacji**: `optimize/cancel.py` i `optimize/baseline.py` to nadal stuby. Anulowanie sąsiednich SWAP-ów i komutacja CZ dają realne zyski w depth po routingu; to największa dziura w projekcie.
3. **Prawdziwy GA** w `routing/genetic.py` (pisze go kolega).
4. **`sabre_baseline`**: naprawa albo usunięcie (obecnie zepsuty, wyłączony z benchmarków i testów).
5. **Wykresy** z wyników (wymaga `pip install -e ".[analysis]"`; na razie raporty tekstowe/CSV).

Świadomie odłożone: większe topologie i więcej kubitów (poza zakresem ODRA5), QASMBench/MQT Bench (za duże albo niezgodne z qiskit 1.2).

## 7. Co robimy teraz

Stoimy w punkcie decyzyjnym. Routing na ODRA5 jest domknięty i zmierzony, a wniosek z sekcji 5 jest taki, że dalsza praca nad metaheurystykami po layoutach nie ma sensu na tej topologii. Rekomendacja: wybrać jedną z dwóch dróg z sekcji 6, czyli move-based tabu albo fazę 2 optymalizacji.

## 8. Gdzie co jest

| Co | Gdzie |
|---|---|
| Solvery routingowe | `src/qtrans/routing/` (baseline.py, exact_dp.py, tabu.py, genetic_trivial.py, genetic.py) |
| Kontrakt i metryki | `src/qtrans/contract.py` |
| Topologia ODRA5 | `src/qtrans/arch.py` |
| Generatory obwodów | `src/qtrans/generator.py` (random_circuit, hard_circuit) |
| QUEKO (znane optimum) | `src/qtrans/queko.py` |
| Benchmarki (3 komendy) | `src/qtrans/bench.py` |
| Optymalizacja (faza 2, stuby) | `src/qtrans/optimize/` |
| Wyniki (gitignored) | `results/` (benchmark.csv, queko.csv, sweat.csv, sweat-summary.md, ablacja-warm-start.md) |
| Dokumentacja | `README.md`, `AGENTS.md`, `docs/contract.md`, `docs/split.md`, `docs/benchmarks.md`, ten plik |
| Testy | `tests/` (m.in. test_contract.py, test_exact_dp.py, test_tabu_warmstart.py, test_sweat.py) |

## 9. Jak uruchomić

```bash
cd odra_transpilation
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
qtrans-bench          # syntetyki        -> results/benchmark.csv
qtrans-bench-queko    # QUEKO            -> results/queko.csv
qtrans-bench-sweat    # budżetowy sweep  -> results/sweat.csv + results/sweat-summary.md
```
