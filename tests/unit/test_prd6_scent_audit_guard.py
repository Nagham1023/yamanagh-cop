"""RULE-19-SCENT-AUDIT-AT-PRD-6 — forward-looking guard, same marker
discipline that worked for `RULE-27-REMOVE-AT-PRD-4` (see CLAUDE.md's
"Known trap" section).

Revision 1's scent report (`reasoning/hint.py::generate_scent_report`) is
trusted by the receiver on honest-by-construction grounds only — the
sender's own code never applies the `Intent` flag to it, but nothing today
cryptographically verifies that a received scent report actually matches
the sender's real trail. PRD 6's Commit-Reveal + mutual log audit is where
that becomes a real, catchable rule 19 (**[FATAL]**: any hash mismatch at
audit is a technical forfeit) violation instead of an honesty convention.

This test names the not-yet-built PRD 6 API it expects
(`cop.integrity.audit.verify_scent_report_against_commit`) and is marked
`xfail(strict=True)`: it fails today (the module doesn't exist), which is
expected and keeps the suite green. Once PRD 6 actually builds that
verification and it correctly catches a tampered scent report, this test
will unexpectedly *pass* — `strict=True` turns that XPASS into a hard
suite failure, forcing whoever builds PRD 6 to consciously delete (or
adapt) this guard rather than let it rot, exactly as
`test_the_numeric_position_tool_is_gone_once_prd4_lands` was.
"""

from __future__ import annotations

import pytest

from cop.domain.board import Position


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RULE-19-SCENT-AUDIT-AT-PRD-6 — no commit-hash/mutual-log-audit "
        "machinery exists yet to catch a tampered scent report; PRD 6 must "
        "build it, then this guard is expected to XPASS and should be "
        "deleted in that same commit, exactly as RULE-27-REMOVE-AT-PRD-4 was."
    ),
)
def test_a_tampered_scent_report_fails_the_mutual_log_audit_once_prd_6_lands():
    from cop.integrity.audit import verify_scent_report_against_commit  # PRD 6 — doesn't exist yet

    true_pos = Position(2, 2)
    # A scent report claiming the opposite direction of the agent's real,
    # committed trail — exactly the kind of lie the "declared-truthful"
    # channel is supposed to make impossible once rule 19 backs it.
    tampered_scent_report = "Scent strongest to the south east."

    assert not verify_scent_report_against_commit(true_pos, tampered_scent_report, commit_hash="placeholder")
