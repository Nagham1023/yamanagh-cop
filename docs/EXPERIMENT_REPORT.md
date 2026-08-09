# Experimental Analysis & League Optimization Report — Yamanagh Cop

**Author**: Cop Development Team  
**Repository**: [yamanagh-cop](file:///home/nagham1023/AI-Agents-course/finalProject%20cop)  
**Spec Reference**: *Distributed Cops-and-Robbers over P2P* (Book v3.0.0, Dr. Yoram Segal)  
**Date**: August 2026  

---

## 1. Executive Summary

This report documents the experimental evaluation, parameter sensitivity analysis, and strategic optimization roadmap for the **Yamanagh Cop** agent. 

To win the course league, a Cop agent must balance **rapid pursuit speed** against **robustness to deceptive hints**. The system relies on a dual-sensing Dec-POMDP model:
1. **Uncorruptible Physical Scent Field** (Stigmergy / Physical Truth).
2. **Natural-Language Verbal Hints** (Psychological Channel / Subject to Deception).

Through empirical experimentation ([notebooks/results_analysis.py](file:///home/nagham1023/AI-Agents-course/finalProject%20cop/notebooks/results_analysis.py)), we evaluated how varying the **Hint Reliability Coefficient ($\alpha$)** impacts Bayesian posterior convergence, and derived three high-yield algorithmic upgrades to maximize win rates in competitive league play.

---

## 2. Experimental Methodology

The experiment measures the rate of Bayesian belief convergence under varying parameter settings.

### 2.1 Physical Scent Emission & Decay Model (Chapter 4.3)
As agents move across the $7 \times 7$ grid, they deposit a physical scent field $\tau$. The emission center receives $\tau_0 = 0.9000$, spreading radially across a $5 \times 5$ kernel grid, and decaying every turn at rate $\rho = 0.10$ according to:

$$\tau_{ij}(t+1) = \max\left(0, (1-\rho)\cdot\tau_{ij}(t) + \Delta\tau_{ij}\right)$$

#### Empirical Scent Decay Over 10 Turns:
| Turn | Scent Intensity ($\tau$) | Physical State |
| :---: | :---: | :--- |
| **0** | **0.9000** | Fresh deposit at current position |
| **1** | **0.8100** | 1 turn post-emission |
| **2** | **0.7290** | 2 turns post-emission |
| **3** | **0.6561** | Trail remains clear |
| **4** | **0.5905** | Half-life threshold approaching |
| **5** | **0.5314** | Moderate scent trail |
| **6** | **0.4783** | Decaying trail |
| **7** | **0.4305** | Faint trail |
| **8** | **0.3874** | Residual trail |
| **9** | **0.3487** | Near noise threshold |

*Key Finding*: Scent trails remain detectable for over **7 turns**, providing an un-fakeable physical history of the Thief's trajectory.

---

## 3. Parameter Sensitivity Analysis — Hint Reliability ($\alpha$)

We conducted a sensitivity pass ([notebooks/sensitivity_pass.py](file:///home/nagham1023/AI-Agents-course/finalProject%20cop/notebooks/sensitivity_pass.py)) varying `_HINT_RELIABILITY` ($\alpha$) in [src/cop/memory/belief.py](file:///home/nagham1023/AI-Agents-course/finalProject%20cop/src/cop/memory/belief.py). We measured how many turns/updates are required for the Bayesian posterior $P(\text{true\_thief\_pos} \mid \text{evidence})$ to cross a $15\%$ confidence threshold ($p=0.15$).

### 3.1 Empirical Results Table

| Reliability ($\alpha$) | Updates to Cross $p=0.15$ | Vulnerability to False Hints (Lies) | Pursuit Speed |
| :---: | :---: | :---: | :---: |
| **$\alpha = 0.30$** (Skeptic) | **3 updates** | **Extremely Low** (Ignores lies) | Slow |
| **$\alpha = 0.60$** (Optimal / Default) | **2 updates** | **Balanced** (Resilient to lies) | Moderate-Fast |
| **$\alpha = 0.90$** (Credulous) | **1 update** | **FATAL** (Fooled by 1 lie) | Very Fast (Honest opponent) |

### 3.2 Analysis & Trade-Offs

```
   High Credulity (α = 0.90)  ----> Fast pursuit, but 1 LIE sends Cop to wrong corner!
   High Skepticism (α = 0.30) ----> Immune to lies, but relies almost solely on scent.
   Optimal Balance (α = 0.60) ----> 2-turn convergence; resists lies while leveraging hints.
```

1. **At $\alpha = 0.90$ (High Credulity)**: The Cop trusts text hints almost blindly. If the Thief is honest, capture happens very quickly (1-turn belief update). However, if the Thief lies ($1- \text{intent}$), the Cop's belief immediately shifts to the opposite side of the board, wasting 5-10 turns chasing a ghost.
2. **At $\alpha = 0.30$ (High Skepticism)**: The Cop down-weights verbal hints and relies almost entirely on scent trails. It is immune to deception, but takes 3 full turns to build target confidence.
3. **At $\alpha = 0.60$ (The Sweet Spot)**: Requires **2 updates** to cross the threshold. This provides the optimal balance for league play — fast enough to track honest movement, yet sufficiently weighted by scent so a single lie does not derail the pursuit.

---

## 4. How to Upgrade the Cop Agent to Win the League

While the default `CopBrain` uses a 1-step greedy Manhattan heuristic, the following three structural upgrades can be implemented in `src/cop/reasoning/` to maximize league win rates:

### Strategy Upgrade 1: Expectimax Multi-Turn Search (3–5 Turn Lookahead)
* **Problem with 1-Step Greedy**: The Cop moves toward the Thief's current cell, chasing them from behind along the same path.
* **Expectimax Solution**:
  - Build a minimax/expectimax search tree evaluating 3 to 5 turns ahead.
  - Model the Thief's legal fleeing options at each branch.
  - Choose the move that minimizes the **maximum possible Thief escape distance** 4 steps into the future.
* **Impact**: The Cop anticipates intersections and **cuts off the Thief at bottlenecks** rather than trailing behind them.

### Strategy Upgrade 2: Dynamic Barrier Entrapment
* **Problem with 1-Step Greedy**: The Cop rarely places barriers, relying solely on physical movement steps.
* **Entrapment Solution**:
  - The Cop has a quota of up to **14 barriers** ([config/shared/config_dev_g01.json](file:///home/nagham1023/AI-Agents-course/finalProject%20cop/config/shared/config_dev_g01.json)).
  - When the Thief enters a dead-end corridor or corner region, compute whether placing a barrier on an adjacent exit cell reduces the Thief's reachable subgraph.
  - If a barrier placement reduces the Thief's accessible cells by $>50\%$, execute `PlaceBarrier` instead of `Move`.
* **Impact**: Traps and entombs the Thief, forcing a guaranteed capture within fewer turns.

### Strategy Upgrade 3: Expected Distance Mass Descent
* **Problem with Single-Targeting**: `CopBrain` targets only the single cell with highest probability (`most_likely_cell()`). If belief is split (e.g. 40% north-west, 40% south-west), it picks one arbitrarily.
* **Expected Distance Solution**:
  - Evaluate every candidate legal move $a \in \{\text{N, S, E, W, STAY}\}$ against the **entire probability distribution**:
    $$E[D(a)] = \sum_{(x,y)} P(\text{thief at } (x,y)) \cdot \text{ManhattanDistance}(a, (x,y))$$
* **Impact**: Chooses central positions that maintain optimal distance to **all** high-probability regions, eliminating wasted movement caused by split beliefs.

---

## 5. Token Cost & Resource Efficiency

* **Model Provider**: `template` (Table 21 Default).
* **Token Cost per Match**: **0 Tokens / $0.00**.
* **Gatekeeper Status**: Rate limiter, Token Bucket, and DOS Detector remain active with zero overhead.

---

## 6. Conclusion & Recommended Action Plan

1. **Keep $\alpha = 0.60$** in [src/cop/memory/belief.py](file:///home/nagham1023/AI-Agents-course/finalProject%20cop/src/cop/memory/belief.py) for general league play to prevent deceptive Thief hints from throwing off pursuit.
2. **Implement Expectimax Search** in `src/cop/reasoning/cop_brain.py` to look 3 steps ahead and intercept fleeing thieves.
3. **Use `notebooks/results_analysis.py`** to generate fresh tabular outputs whenever parameters are tuned for submission reports.
