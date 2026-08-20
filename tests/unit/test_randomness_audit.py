"""PRD 6 prep, item 5: grep for `random` across the repo now, while the
answer is short. Two rules from the audit: nothing that gets hashed may be
irreproducible without being logged (checked: `decide_intent`'s chosen
value is the *same* variable reused for both `generate_hint` and
`trace.log("hint_generated", intent=...)` in `orchestrator_turn.py` —
never recomputed, so it can't silently diverge from what got logged); and
`random` must never be anywhere near a nonce. `rule-auditor.md` already
carries "`random` rather than `secrets` anywhere near nonce generation
(18)" as its first "what to look for" bullet — this file is the
code-level, always-run complement to that prompt-level reminder: an
explicit allowlist that fails immediately if any new file imports
`random`, rather than relying on an LLM audit remembering to check.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "cop"

# Every legitimate site, with why. Add to this deliberately, one line at a
# time, not by widening the pattern below.
_ALLOWED_RANDOM_FILES = {
    SRC_ROOT / "orchestrator.py",  # self._rng = random.Random() — feeds decide_intent, never a nonce
    SRC_ROOT / "reasoning" / "hint.py",  # decide_intent(lie_probability, rng) — Table 21's Intent policy
    # random_source default for the 90/10 RL/heuristic mix — a move-choice
    # weighting, not a nonce or anything that gets hashed/committed.
    SRC_ROOT / "reasoning" / "weighted_cop_brain.py",
    # self._rng = random.Random() — same role as orchestrator.py's own
    # entry above: feeds decide_intent for std_v1's own turn cycle, never
    # a nonce (std_v1/crypto.py uses secrets.token_hex, not this rng).
    SRC_ROOT / "std_v1" / "turn_handler.py",
    # PLAN.md Stage 11.4: self._rng = random.Random() drives softmax
    # sampling among near-tied move/barrier candidates only (move-choice
    # weighting, same category as weighted_cop_brain.py's own entry above)
    # -- so behavior isn't perfectly repeatable match to match. Never
    # touches a nonce or anything that gets hashed/committed; sealing
    # stays on std_v1/crypto.py's own secrets.token_hex, untouched by this
    # class entirely.
    SRC_ROOT / "reasoning" / "adaptive_cop_brain.py",
}

_RANDOM_IMPORT_PATTERN = re.compile(r"^\s*import random\b|^\s*from random\b", re.MULTILINE)


def test_random_module_usage_stays_on_the_documented_allowlist():
    offending = [
        str(path.relative_to(SRC_ROOT))
        for path in SRC_ROOT.rglob("*.py")
        if _RANDOM_IMPORT_PATTERN.search(path.read_text(encoding="utf-8")) and path not in _ALLOWED_RANDOM_FILES
    ]
    assert offending == [], (
        f"random imported outside the documented allowlist: {offending} — if this is legitimate, "
        "add it to _ALLOWED_RANDOM_FILES with a reason; if it's anywhere near nonce/commit-hash "
        "code, it must be secrets instead (rule 18, FATAL)"
    )


def test_the_allowlist_itself_still_matches_reality():
    # The inverse check: an allowlist entry for a file that no longer
    # imports random is exactly the kind of stale exception that quietly
    # widens scope later without anyone noticing.
    for path in _ALLOWED_RANDOM_FILES:
        assert path.exists(), f"allowlisted file no longer exists: {path}"
        assert _RANDOM_IMPORT_PATTERN.search(path.read_text(encoding="utf-8")), (
            f"{path} is allowlisted but no longer imports random — remove the stale entry"
        )


def test_secrets_not_random_is_what_integrity_code_would_use_for_a_nonce():
    # No nonce-generating code exists yet (PRD 6) — this documents the
    # expectation ahead of time and starts actually checking real files
    # the moment any exist in src/cop/integrity/, rather than being
    # written retroactively after PRD 6 lands and might already be wrong.
    integrity_root = SRC_ROOT / "integrity"
    assert integrity_root.exists(), "src/cop/integrity/ should already exist (commit_payload.py)"
    for path in integrity_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not _RANDOM_IMPORT_PATTERN.search(text), f"{path} imports random — must be secrets (rule 18)"


def test_decide_intents_chosen_value_is_the_same_variable_logged_not_recomputed():
    # Read the actual source rather than asserting on behavior alone: a
    # bug where hint_generated's logged intent came from a *second*,
    # independent decide_intent() call (instead of reusing the value that
    # decided the hint's content) would be invisible to
    # test_take_turn_logs_the_intent_flag (which only checks the logged
    # value is a bool, not that it's the *right* bool) but would mean
    # Intent going into PRD 6's eventual commit doesn't actually match
    # what was sent — exactly the "irreproducible without being logged"
    # risk item 5 names.
    text = (SRC_ROOT / "orchestrator_turn.py").read_text(encoding="utf-8")
    assert text.count("decide_intent(") == 1, (
        "decide_intent() must be called exactly once per turn and its result reused for both "
        "generate_hint() and the hint_generated trace log entry — a second call site risks the "
        "logged Intent silently diverging from the Intent that actually shaped the hint"
    )
