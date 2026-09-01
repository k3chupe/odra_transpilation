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
| optymalny routing (exact DP) | 1.6916 | 0.0723 |

## Porównywane solvery (odległość od ideału)

| Solver | Śr. fidelity_cost | Śr. gap vs ideał | std gap | Śr. czas (s) | Śr. evals |
|---|---|---|---|---|---|
| tabu fidelity | 1.8354 | +0.1438 | 0.2849 | 0.424 | 4877 |
| tabu fidelity (greedy) | 1.8172 | +0.1256 | 0.2291 | 0.430 | 4918 |
| tabu fidelity (sabre) | 1.8342 | +0.1427 | 0.2856 | 0.433 | 4936 |
| tabu search | 2.2194 | +0.5278 | 0.5933 | 5.603 | 19921 |
| tabu + sabre (nasz) | 2.2248 | +0.5332 | 0.5943 | 5.576 | 19921 |
| genetyka | 2.2746 | +0.5830 | 0.6651 | 0.727 | 2501 |
| sabre (Qiskit) | 1.8680 | +0.1765 | 0.2142 | 0.005 | -1 |
| Qiskit preset | 2.1091 | +0.4175 | 0.6182 | 0.036 | -1 |
| greedy (identity) | 2.3599 | +0.6683 | 0.6287 | 0.012 | 1 |
| brute layout (greedy swapy) | 2.1837 | +0.4921 | 0.5799 | 0.045 | 120 |
| brute fidelity (greedy swapy) | 1.9925 | +0.3009 | 0.4475 | 0.023 | 120 |

## Przypadki z najlepszym wynikiem (tylko porównywane solvery)

- tabu fidelity (sabre): 6/13
- tabu fidelity (greedy): 6/13
- tabu fidelity: 5/13
- Qiskit preset: 5/13
- brute fidelity (greedy swapy): 2/13
- sabre (Qiskit): 1/13

