"""RULE-15-16-BARRIER-DECLARATION-AT-PRD-6 and RULE-21-22-CAPTURE-CLAIM-AT-PRD-6
— forward-looking guards, same marker discipline that worked for
`RULE-27-REMOVE-AT-PRD-4` and `RULE-19-SCENT-AUDIT-AT-PRD-6` (see CLAUDE.md's
"Known trap" section).

Three mandatory channels have no delivery mechanism on the wire today. The
current surface is `receive_hint(text)` and `share_scent_map()`
(`tools/mcp_server.py`, PRD 4 "Revision 3" — `todoFullFix.md` §C) —
nothing else. Concretely missing:

- **Barrier declaration (rules 15/16, both [FATAL]).** The cop must
  truthfully announce every barrier placement and its exact cell.
  `domain/barriers.py` places barriers entirely locally
  (`GameState.barriers`) and has said so explicitly since PRD 1 ("Truthful
  *declaration* of a placement... doesn't exist yet in PRD 1's
  single-process world, so it isn't enforced here") — but four layers
  later (PRD 1 through PRD 5), that declaration still has no channel to
  travel over. This is not new PRD 6 scope in the way Commit-Reveal itself
  is; it's a debt that's been outstanding since PRD 1 with nothing
  currently tracking it as a concrete build item anywhere in `PLAN.md`.
- **Capture claim (rule 21, [FATAL]) and capture response (rule 22,
  [FATAL]).** The cop declares a capture; the thief is cryptographically
  obliged to answer truthfully. Neither declaration nor response exists on
  the wire — there is no capture-adjacent tool at all today.

Both guards name the not-yet-built PRD 6 APIs they expect and are marked
`xfail(strict=True)`: they fail today (the modules/tools don't exist),
which is expected and keeps the suite green. Once PRD 6 actually builds
each channel and it works, the corresponding guard will unexpectedly
*pass* — `strict=True` turns that XPASS into a hard suite failure, forcing
whoever builds PRD 6 to consciously delete (or adapt) each guard rather
than let it rot.
"""

from __future__ import annotations

import pytest

from cop.domain.board import Position


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RULE-15-16-BARRIER-DECLARATION-AT-PRD-6 — no wire channel exists yet "
        "for truthfully announcing a barrier placement; barriers are placed "
        "entirely locally (domain/barriers.py) and the opponent is never told. "
        "PRD 6 must add a receive_barrier_declaration-shaped tool, then this "
        "guard is expected to XPASS and should be deleted in that same commit."
    ),
)
def test_a_barrier_placement_is_declared_to_the_peer_once_prd_6_lands(config):
    import asyncio

    from fastmcp import Client

    from cop.tools.mcp_server import build_server  # the eventual tool doesn't exist yet

    mcp = build_server(config)

    async def _tool_names():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools}

    tool_names = asyncio.run(_tool_names())
    assert "receive_barrier_declaration" in tool_names


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RULE-21-22-CAPTURE-CLAIM-AT-PRD-6 — no wire channel exists yet for "
        "declaring a capture (rule 21) or cryptographically answering one "
        "truthfully (rule 22). PRD 6 must add both, then this guard is "
        "expected to XPASS and should be deleted in that same commit."
    ),
)
def test_a_capture_is_declared_and_truthfully_answered_once_prd_6_lands():
    from cop.integrity.capture_protocol import (  # doesn't exist yet
        claim_capture,
        respond_to_capture_claim,
    )

    claim = claim_capture(thief_pos=Position(3, 3), cop_pos=Position(3, 3))
    response = respond_to_capture_claim(claim, true_thief_pos=Position(3, 3))

    assert response.confirmed is True
