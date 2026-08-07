"""RULE-19-SCENT-AUDIT-AT-PRD-6 — forward-looking guard, same marker
discipline that worked for `RULE-27-REMOVE-AT-PRD-4` (see CLAUDE.md's
"Known trap" section).

PRD 4 "Revision 3" (`todoFullFix.md` §C8) changed *how* the scent data
crosses the wire (a Tool call, `share_scent_map`, returning the sender's
real `ScentField.full_field()` — see `PRD-4-language-and-scent.md`'s
"Revision 3" section) but not *whether* it's trusted: the receiving side
still has no cryptographic check that the returned field genuinely matches
the sender's actual internal `ScentField` state, only honest-by-
construction good faith (`Intent` never applies to this channel, but
nothing stops a malicious peer's tool implementation from fabricating a
response). PRD 6's Commit-Reveal + mutual log audit is where that becomes a
real, catchable rule 19 (**[FATAL]**: any hash mismatch at audit is a
technical forfeit) violation instead of an honesty convention.

This test names the not-yet-built PRD 6 API it expects
(`cop.integrity.audit.verify_scent_map_against_commit`) and is marked
`xfail(strict=True)`: it fails today (the module doesn't exist), which is
expected and keeps the suite green. Once PRD 6 actually builds that
verification and it correctly catches a tampered scent map, this test will
unexpectedly *pass* — `strict=True` turns that XPASS into a hard suite
failure, forcing whoever builds PRD 6 to consciously delete (or adapt) this
guard rather than let it rot, exactly as
`test_the_numeric_position_tool_is_gone_once_prd4_lands` was.
"""

from __future__ import annotations

import pytest

from cop.domain.board import Position


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RULE-19-SCENT-AUDIT-AT-PRD-6 — no commit-hash/mutual-log-audit "
        "machinery exists yet to catch a tampered scent map; PRD 6 must "
        "build it, then this guard is expected to XPASS and should be "
        "deleted in that same commit, exactly as RULE-27-REMOVE-AT-PRD-4 was."
    ),
)
def test_a_tampered_scent_map_fails_the_mutual_log_audit_once_prd_6_lands():
    from cop.integrity.audit import verify_scent_map_against_commit  # PRD 6 — doesn't exist yet

    # A scent map claiming a concentration at a cell the agent's real,
    # committed ScentField never actually deposited near — exactly the kind
    # of fabrication the Tool-based channel is supposed to make impossible
    # once rule 19 backs it: the claimed field must hash to the value
    # committed earlier in the turn, or the audit rejects it.
    tampered_field = {Position(6, 6): 0.9}
    commit_hash_of_the_genuine_field = "placeholder-hash-of-Position(2,2)-0.9"

    assert not verify_scent_map_against_commit(tampered_field, commit_hash_of_the_genuine_field)
