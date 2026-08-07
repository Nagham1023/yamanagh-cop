"""PRD 6 prep: the step index both sides will bind a commit to. `GameState.steps_taken`
is a purely local counter (incremented once per this agent's own `apply()` call,
never from anything the peer reports) — this proves that property holds under
a real, alternating, live two-orchestrator exchange rather than assuming it
from reading the code alone. A dozen rounds, both sides real `Orchestrator`
instances with real HTTP servers, alternating `take_turn()` calls against
each other (both are cop-role code — this repo can't run a thief brain, but
the step-counting mechanism itself doesn't care which brain is on the other
end, only that its own moves are applied and counted correctly).
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

from cop.orchestrator import Orchestrator
from cop.reasoning.cop_brain import CopBrain


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start(config, tmp_path, name: str) -> tuple[Orchestrator, str]:
    orchestrator = Orchestrator(config, CopBrain(), log_path=str(tmp_path / f"{name}_trace.jsonl"))
    port = _free_port()
    threading.Thread(
        target=orchestrator.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return orchestrator, f"http://127.0.0.1:{port}/mcp"


def test_step_index_stays_in_lockstep_across_a_dozen_alternating_rounds(config, tmp_path):
    peer_a, url_a = _start(config, tmp_path, "a")
    peer_b, url_b = _start(config, tmp_path, "b")

    rounds = 12
    for round_number in range(1, rounds + 1):
        asyncio.run(peer_a.take_turn(url_b))
        asyncio.run(peer_b.take_turn(url_a))

        assert peer_a.game_state.steps_taken == round_number, (
            f"peer_a drifted at round {round_number}: {peer_a.game_state.steps_taken}"
        )
        assert peer_b.game_state.steps_taken == round_number, (
            f"peer_b drifted at round {round_number}: {peer_b.game_state.steps_taken}"
        )
        assert peer_a.game_state.steps_taken == peer_b.game_state.steps_taken

    assert peer_a.game_state.steps_taken == rounds
    assert peer_b.game_state.steps_taken == rounds


def test_a_failed_attempt_does_not_advance_one_sides_step_count_without_the_other_knowing(config, tmp_path):
    # The real finding worth pinning down: GameState.apply() (which
    # increments steps_taken) runs *before* the network send in
    # take_turn() — a move is counted locally the instant it's decided,
    # regardless of whether the accompanying hint ever reaches the peer.
    # This is by design (TECHNICAL_LOSS is terminal, PRD 5's own Design
    # Question 1 — nothing "continues" after a failed send to get out of
    # sync with), but it's exactly the kind of asymmetry PRD 6's commit
    # binding needs to know about, not discover at audit time.
    peer_a, url_a = _start(config, tmp_path, "a")
    peer_b, url_b = _start(config, tmp_path, "b")

    asyncio.run(peer_a.take_turn(url_b))
    asyncio.run(peer_b.take_turn(url_a))
    assert peer_a.game_state.steps_taken == peer_b.game_state.steps_taken == 1

    dead_url = f"http://127.0.0.1:{_free_port()}/mcp"  # nothing listens here
    peer_a.state_machine.transition("COMPUTING_MOVE")
    try:
        asyncio.run(peer_a.send_to_peer(dead_url, "a test hint"))
        raised = False
    except Exception:
        raised = True

    assert raised
    assert peer_a.state_machine.state == "TECHNICAL_LOSS"
    # peer_a's own steps_taken is untouched by this failed send (send_to_peer
    # doesn't call GameState.apply() at all — only take_turn() does, and it
    # wasn't called here) — the counter only ever advances alongside a real,
    # locally-applied move, confirming the risk is specifically about
    # take_turn()'s own apply-then-maybe-fail-to-send ordering, not about
    # send_to_peer somehow double-counting.
    assert peer_a.game_state.steps_taken == 1
    assert peer_b.game_state.steps_taken == 1
