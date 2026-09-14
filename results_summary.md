# Podsumowanie wyników benchmarków (fidelity)

Ideał = exact_dp: pełne przeszukanie przestrzeni (layouty, dowolne
SWAP-y na krawędziach, dowolny porządek topologiczny, dokładny koszt
fidelity), liczone raz na przypadek. Żaden solver nie może go pobić,
może się tylko z nim zrównać. `gap` = fidelity_cost solwera minus
ideał przypadku: 0 = osiąga optimum, dodatnia = odległość od optimum,
ujemna = solver zszedł poniżej naszego ideału routingu (pełna
optymalizacja Qiskita, patrz `results/gap-analysis.md`).

- Przypadki testowe: 13
- Reprezentanci: 8 (z 11 porównywanych wariantów)
- Metryka: `fidelity_cost_cancelled` (true minimum), gdy jest w CSV

## Ideał (exact DP, dolne ograniczenie)

| Referencja | Średni fidelity_cost | Mediana czasu (s) | Średni czas (s) |
|---|---|---|---|
| ideał (exact DP) | 1.5953 | 0.0202 | 0.0626 |

## Reprezentanci (odległość od ideału)

| Reprezentant | Śr. fidelity_cost | Śr. gap vs ideał | std gap | Mediana czasu (s) | Śr. czas (s) | Śr. evals | Na optimum |
|---|---|---|---|---|---|---|---|
| tabu fidelity | 1.6891 | +0.0938 | 0.1871 | 0.2453 | 0.677 | 11756 | 9/13 |
| sabre (Qiskit) | 1.8075 | +0.2122 | 0.2403 | 0.0058 | 0.007 | - | 0/13 |
| brute fidelity (greedy swapy) | 1.8114 | +0.2161 | 0.3273 | 0.0179 | 0.030 | 120 | 3/13 |
| brute layout (greedy swapy) | 2.0743 | +0.4790 | 0.6130 | 0.0394 | 0.052 | 120 | 0/13 |
| tabu search | 2.1046 | +0.5092 | 0.6223 | 4.7469 | 5.567 | 19921 | 1/13 |
| Qiskit preset | 2.1169 | +0.5216 | 0.7090 | 0.0308 | 0.040 | - | 0/13 |
| genetyka | 2.1663 | +0.5710 | 0.6939 | 0.6112 | 0.725 | 2501 | 1/13 |
| greedy (identity) | 2.2495 | +0.6542 | 0.6599 | 0.0117 | 0.019 | 1 | 0/13 |

`Na optimum` = przypadki, w których |gap| <= 1e-9, czyli solver zrównał się z ideałem. Zejście poniżej ideału nie liczy się jako trafienie, bo to inna gra (patrz gap-analysis).

## Reprezentanci: co zostało scalone

Warianty w rodzinie mają ten sam algorytm i różnią się tylko startem,
więc na wykresach występuje reprezentant. Tabela pokazuje, jak bardzo
scalony wariant faktycznie różnił się od reprezentanta (po gapach, tolerancja 1e-09), żeby nic nie zniknęło pod etykietą.

| Reprezentant | Scalony wariant | Przypadki z różnicą | Max |delta| | Śr. |delta| |
|---|---|---|---|---|
| tabu fidelity | tabu fidelity (greedy) | 2/13 | 0.3354 | 0.0263 |
| tabu fidelity | tabu fidelity (sabre) | 2/13 | 0.0061 | 0.0005 |
| tabu search | tabu + sabre (nasz) | 9/13 | 0.1436 | 0.0372 |

- Dodatkowe scalenia reprezentantów: brak (żadna para nie ma identycznych wektorów fidelity_cost).

