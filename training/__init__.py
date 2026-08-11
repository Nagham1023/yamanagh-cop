"""Offline, sandbox-only training tooling for the cop's RL movement policy (PRD 11).

Dependency edge is one-directional: this package imports from
`src/cop/domain/` (pure board rules) and `src/cop/reasoning/` (the shared
state-encoding and checkpoint format, PRD 11's own production files) —
**nothing under `src/cop/` ever imports `training/`**, enforced by
`tests/unit/test_training_boundary.py`. This is what makes it structurally
impossible for anything in here to run in, or leak into, a real match: even
if a curriculum sparring opponent's *behavior* superficially resembles a
real thief, it cannot be reached from any real game path (rules 1/2).

The synthetic sparring opponents in `opponent_policies.py` are plain
functions, never a `BrainBase`/`ThiefBrain` subclass, and are a deliberate,
documented duplication of `tests/support/greedy_thief_mover.py`'s algorithm
rather than an import of it — see that module's own docstring and PRD-3's
Design Question 5 for why a thief-shaped fixture is never promoted into (or
shared with) `src/cop/`. Everything in this package runs off the live
per-turn critical path, between games, exactly like `PLAN.md` §6's
"orchestrated between-game learning" framing.
"""

from __future__ import annotations
