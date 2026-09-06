# Podsumowanie wyników benchmarków (fidelity)

Ideał = exact_dp: pełne przeszukanie przestrzeni (layouty, dowolne
SWAP-y na krawędziach, dowolny porządek topologiczny, dokładny koszt
fidelity), liczone raz na przypadek. Żaden solver nie może go pobić,
może się tylko z nim zrównać. `gap` = fidelity_cost solwera minus
ideał przypadku: 0 = osiąga optimum, dodatnia = odległość od optimum.

- Przypadki testowe: 13

## Ideał (exact DP, dolne ograniczenie)

| Referencja | Średni fidelity_cost | Średni czas (s) |
|---|---|---|
| optymalny routing (exact DP) | 1.5953 | 0.0707 |

## Porównywane solvery (odległość od ideału)

| Solver | Śr. fidelity_cost | Śr. gap vs ideał | std gap | Śr. czas (s) | Śr. evals |
|---|---|---|---|---|---|
| tabu fidelity | 1.6891 | +0.0938 | 0.1871 | 0.721 | 11756 |
| tabu fidelity (greedy) | 1.7145 | +0.1192 | 0.2656 | 0.718 | 11695 |
| tabu fidelity (sabre) | 1.6887 | +0.0934 | 0.1874 | 0.731 | 11808 |
| tabu search | 2.1046 | +0.5092 | 0.6223 | 6.116 | 19921 |
| tabu + sabre (nasz) | 2.1167 | +0.5214 | 0.6320 | 6.105 | 19921 |
| genetyka | 2.1663 | +0.5710 | 0.6939 | 0.808 | 2501 |
| sabre (Qiskit) | 1.8075 | +0.2122 | 0.2403 | 0.010 | -1 |
| Qiskit preset | 2.1067 | +0.5114 | 0.6643 | 0.054 | -1 |
| greedy (identity) | 2.2495 | +0.6542 | 0.6599 | 0.024 | 1 |
| brute layout (greedy swapy) | 2.0743 | +0.4790 | 0.6130 | 0.058 | 120 |
| brute fidelity (greedy swapy) | 1.8114 | +0.2161 | 0.3273 | 0.031 | 120 |

## Przypadki z najlepszym wynikiem (tylko porównywane solvery)

- tabu fidelity: 10/13
- tabu fidelity (greedy): 10/13
- tabu fidelity (sabre): 10/13
- brute fidelity (greedy swapy): 2/13
- Qiskit preset: 2/13

