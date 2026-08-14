"""Orchestrator.take_turn (PRD 3): proves the brain is genuinely wired, not that
the algorithm works — algorithm correctness is reasoning/subgame.py's job
(PRD-3-blind-strategy.md, Design Question 3).

PRD 4 "Revision 3" (todoFullFix.md §C8): take_turn() now pulls the peer's
scent map via a Tool call *before* computing the move — every test that
calls take_turn() against a live peer now genuinely exercises that pull
too, not just the hint exchange.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import socket
import threading
import time
from unittest.mock import patch

from cop.domain.board import Position
from cop.integrity.capture_protocol import CaptureClaim, respond_to_capture_claim
from cop.memory.belief import BeliefMap
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import BrainBase, Move, PlaceBarrier
from cop.reasoning.cop_brain import CopBrain
from cop.reasoning.hint import interpret_hint
from cop.shared.private_config import PrivateConfig
from cop.tools.mcp_client_prd6 import send_capture_response


class _AlwaysProposesAnOffBoardMove(BrainBase):
    """A deliberately buggy brain — proves take_turn() catches a brain/action
    failure the same way commit_and_reveal_to_peer catches a network one,
    instead of stranding the state machine in COMPUTING_MOVE with nothing
    logged."""

    def _pick_move(self, own_pos, target_pos, board, barriers) -> str:
        return "N"

    def _decide_move(self, own_pos, target_pos, board, barriers) -> Move:
        return Move(direction="N")


class _NeverReturns(BrainBase):
    """A brain whose own decision computation never finishes on its own —
    proves `_decide_and_apply_move`'s deadline wrap actually bounds local
    compute time, not just network waits. Sleeps well past the test's own
    shrunk `response_timeout_seconds` rather than looping forever, so a
    misbehaving test run still terminates even if the deadline wrap were
    somehow broken."""

    def _pick_move(self, own_pos, target_pos, board, barriers) -> str:
        time.sleep(1.5)
        return "E"


class _AlwaysPlacesABarrierOnItsOwnCell(BrainBase):
    """todoFullFix.md §E1/§E2: a brain that always forgoes movement to
    place a barrier on its own current cell — proves take_turn() re-syncs
    BeliefMap's barrier-zero-belief after every placement, not just at
    construction."""

    def _pick_move(self, own_pos, target_pos, board, barriers) -> str:
        return "STAY"

    def _decide_move(self, own_pos, target_pos, board, barriers) -> PlaceBarrier:
        return PlaceBarrier(target=own_pos)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(config, tmp_path, name: str) -> tuple[Orchestrator, int]:
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / f"{name}_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return server, port


def _client_url_for(port: int) -> str:
    return f"http://127.0.0.1:{port}/mcp"


def _make_capture_responder(answer_to_url: str):
    """Test-only stand-in for the thief's own rule 21/22 obligation (book
    ch. 3.4: only the thief is ever obligated to answer a Capture Claim,
    never the cop). Production `_on_capture_claim_received` stays a
    deliberate no-op — giving the cop's own live code this capability
    would let any peer extract its exact position on demand, since
    `CaptureResponse` always carries `true_thief_pos` unconditionally (see
    `TODO.md`'s "capture-claim collision" entry for the full reasoning and
    the reverted production attempt). This repo's own bilateral self-play
    tests have no thief on either end (rule 1/2: no thief brain exists
    here) — used only via `_start_server_answering`, patched onto the
    *class* for the duration of constructing the one `Orchestrator`
    standing in as the peer, not onto any instance afterward (a bound
    method captured inside `Orchestrator.__init__` is fixed at
    construction time — patching the instance later has no effect).

    Plain `def`, not `async def`: production `receive_capture_claim`
    (`mcp_server_prd6.py`) calls its `on_capture_claim` callback
    synchronously and discards any return value — an `async def` callback
    would just create an unawaited, never-run coroutine here. Same
    sync-callback-spawns-a-thread shape `test_orchestrator_capture.py`'s
    own `_start_thief_peer` already uses for the identical reason."""

    def _answer(self, thief_col, thief_row, cop_col, cop_row, claimed_at_step):
        claim = CaptureClaim(
            thief_pos=Position(thief_col, thief_row),
            cop_pos=Position(cop_col, cop_row),
            claimed_at_step=claimed_at_step,
        )
        response = respond_to_capture_claim(claim, true_thief_pos=self.game_state.own_pos)

        def _send() -> None:
            # best-effort test double — an unreachable caller just times out
            with contextlib.suppress(Exception):
                asyncio.run(
                    send_capture_response(
                        answer_to_url,
                        response.confirmed,
                        response.true_thief_pos.col,
                        response.true_thief_pos.row,
                    )
                )

        threading.Thread(target=_send, daemon=True).start()

    return _answer


def _start_server_answering(config, tmp_path, name: str, answer_to_url: str) -> tuple[Orchestrator, int]:
    """Like `_start_server`, but the peer it starts can actually resolve a
    Capture Claim sent to it — needed by any test whose brain always/often
    fires one (`_AlwaysPlacesABarrierOnItsOwnCell`'s barrier claims
    unconditionally, rule 46; a fresh belief map's `most_likely_cell()`
    also ties to `cop_start` here, so even plain `CopBrain` can land on it
    turn one). `answer_to_url` is the calling client's own address —
    reserve its port with `_free_port()` before calling this, since the
    client needs to be listening there by the time the peer answers."""
    port = _free_port()
    with patch.object(
        Orchestrator, "_on_capture_claim_received", _make_capture_responder(answer_to_url)
    ):
        server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / f"{name}_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return server, port


def _start_client_as_server(
    config, brain, tmp_path, name: str, port: int, private_config=None
) -> Orchestrator:
    """Starts a peer as a real listening server too (not just a caller) —
    needed so `_start_server_answering`'s own peer can route its Capture
    Claim response back to it. `port` must be reserved by the caller
    beforehand so `_start_server_answering`'s `answer_to_url` can name it
    before this client exists."""
    client = Orchestrator(
        config, brain, log_path=str(tmp_path / f"{name}_trace.jsonl"), private_config=private_config
    )
    threading.Thread(
        target=client.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return client


def _sent_hint_text(trace_path) -> str:
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    (revealed_event,) = [e for e in events if e["event"] == "revealed"]
    return revealed_event["hint_text"]


def test_take_turn_moves_according_to_the_brains_own_decision_not_a_fixed_position(config, tmp_path):
    # The ack (`{"accepted": bool, "word_count": int}`) no longer echoes back
    # enough to distinguish outcomes by content — PRD 4's wire protocol is
    # language, not a position round-trip. Observe the client's own state
    # and trace log instead, same as PRD 3's discipline, adapted to what's
    # actually observable now.
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.game_state.own_pos = Position(3, 3)
    client.game_state.target_pos = Position(3, 0)  # due north — CopBrain must pick "N"

    result = asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert result["accepted"] is True
    assert result["word_count"] == len(_sent_hint_text(tmp_path / "client_trace.jsonl").split())
    assert client.game_state.own_pos == Position(3, 2)
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"


def test_take_turn_with_a_different_target_produces_a_different_outgoing_position(config, tmp_path):
    # The wiring-is-real proof: two otherwise-identical orchestrators with
    # different targets must apply different moves and send different hint
    # text — if take_turn() silently ignored self.brain and sent a fixed
    # position instead, this would fail.
    _, port = _start_server(config, tmp_path, "server")

    north_client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "north_trace.jsonl"))
    north_client.game_state.own_pos = Position(3, 3)
    north_client.game_state.target_pos = Position(3, 0)

    east_client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "east_trace.jsonl"))
    east_client.game_state.own_pos = Position(3, 3)
    east_client.game_state.target_pos = Position(6, 3)

    asyncio.run(north_client.take_turn(f"http://127.0.0.1:{port}/mcp"))
    asyncio.run(east_client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert north_client.game_state.own_pos == Position(3, 2)
    assert east_client.game_state.own_pos == Position(4, 3)
    north_text = _sent_hint_text(tmp_path / "north_trace.jsonl")
    east_text = _sent_hint_text(tmp_path / "east_trace.jsonl")
    assert north_text != east_text


def test_take_turn_from_an_illegal_starting_state_raises_via_the_state_machine(config, tmp_path):
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "client_trace.jsonl"))
    client.state_machine.state = "TECHNICAL_LOSS"  # terminal — nothing is legal from here

    try:
        asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))
        raised = False
    except ValueError:
        raised = True

    assert raised, "take_turn must not bypass rule 5's illegal-transition enforcement"


def test_take_turn_with_a_brain_that_proposes_an_illegal_action_reaches_technical_loss(
    config, tmp_path
):
    # cop_start is (0, 0) — "N" is off-board, so GameState.apply raises.
    # A real live peer is needed here now: take_turn() pulls the peer's
    # scent map *before* computing the move (todoFullFix.md §C4's
    # ordering) — without one, the failure would be a network error, not
    # this brain bug.
    _, port = _start_server(config, tmp_path, "server")
    client = Orchestrator(
        config, _AlwaysProposesAnOffBoardMove(), log_path=str(tmp_path / "trace.jsonl")
    )

    try:
        asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert client.state_machine.state == "TECHNICAL_LOSS"
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "technical_loss" in events


def test_take_turn_with_a_brain_that_never_finishes_deciding_reaches_technical_loss(config, tmp_path):
    # Appendix F defines no separate compute-time budget, so this reuses
    # response_timeout_seconds (shrunk here so the test doesn't take
    # anywhere near the real 30s) rather than a new, ungrounded config
    # field — same reasoning as the README's note on this.
    fast_config = dataclasses.replace(config, response_timeout_seconds=0.2)
    _, port = _start_server(fast_config, tmp_path, "server")
    client = Orchestrator(fast_config, _NeverReturns(), log_path=str(tmp_path / "trace.jsonl"))

    # A plain run_until_complete, not asyncio.run(): asyncio.run()'s own
    # cleanup calls shutdown_default_executor(), which blocks until the
    # runaway worker thread finishes — that's real, but it's a process-exit
    # concern, not what this test measures. What matters here is whether
    # take_turn() itself returns control within the deadline, which is
    # exactly what a long-running peer process (never torn down mid-match)
    # actually experiences.
    loop = asyncio.new_event_loop()
    start = time.monotonic()
    try:
        loop.run_until_complete(client.take_turn(f"http://127.0.0.1:{port}/mcp"))
        raised = False
    except Exception:  # noqa: BLE001 - DeadlineExceededError, asserted via the trace below
        raised = True
    finally:
        elapsed = time.monotonic() - start
        loop.close()

    assert raised
    assert elapsed < 1.0, "must not have waited anywhere near the brain's own 1.5s sleep"
    assert client.state_machine.state == "TECHNICAL_LOSS"
    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    technical_loss_events = [e for e in events if e["event"] == "technical_loss"]
    assert technical_loss_events
    assert technical_loss_events[0]["exception_type"] == "DeadlineExceededError"


def test_take_turn_against_an_unreachable_peer_reaches_technical_loss_before_computing_a_move(
    config, tmp_path
):
    # The new failure mode PRD 4 "Revision 3" introduces: the scent-map
    # pull happens first, so an unreachable peer must fail there, before
    # the brain (a perfectly legal one here) ever gets a chance to run.
    dead_url = f"http://127.0.0.1:{_free_port()}/mcp"  # nothing listens here
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    try:
        asyncio.run(client.take_turn(dead_url))
        raised = False
    except Exception:  # noqa: BLE001 - any connection failure counts
        raised = True

    assert raised
    assert client.state_machine.state == "TECHNICAL_LOSS"
    assert client.game_state.own_pos == Position(*config.cop_start), "must not have moved at all"


def test_take_turn_updates_belief_map_and_scent_field_not_just_game_state(config, tmp_path):
    client_port = _free_port()
    _, port = _start_server_answering(config, tmp_path, "server", _client_url_for(client_port))
    client = _start_client_as_server(config, CopBrain(), tmp_path, "client", client_port)
    belief_before = client.belief_map.probability(client.game_state.own_pos)
    scent_before = client.scent_field.sample(client.game_state.own_pos, client.board)

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert client.belief_map.probability(client.game_state.own_pos) != belief_before
    assert client.scent_field.sample(client.game_state.own_pos, client.board) != scent_before


def test_take_turn_zeroes_belief_at_a_newly_placed_barrier(config, tmp_path):
    # todoFullFix.md §E1: "whenever the barrier set changes," not just at
    # construction — placing a barrier this turn must immediately zero the
    # belief map's own probability there, live, not only after a fresh
    # BeliefMap gets built.
    client_port = _free_port()
    _, port = _start_server_answering(config, tmp_path, "server", _client_url_for(client_port))
    client = _start_client_as_server(
        config, _AlwaysPlacesABarrierOnItsOwnCell(), tmp_path, "client", client_port
    )
    own_pos = client.game_state.own_pos
    assert client.belief_map.probability(own_pos) > 0.0
    # PRD 8: a fresh uniform belief's most_likely_cell() happens to tie-break
    # to own_pos here — pointed elsewhere so this belief-zeroing test isn't
    # also incidentally asserting something about capture-claim confirmation,
    # which isn't this test's own concern (the peer now genuinely answers
    # every claim honestly, via _start_server_answering).
    client.game_state.target_pos = Position(
        (own_pos.col + 3) % config.board_size, (own_pos.row + 3) % config.board_size
    )

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert own_pos in client.game_state.barriers.placed
    assert client.belief_map.probability(own_pos) == 0.0
    assert client.belief_map.most_likely_cell() != own_pos


def test_take_turn_logs_the_intent_flag(config, tmp_path):
    client_port = _free_port()
    _, port = _start_server_answering(config, tmp_path, "server", _client_url_for(client_port))
    client = _start_client_as_server(config, CopBrain(), tmp_path, "client", client_port)

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    events = [
        json.loads(line)
        for line in (tmp_path / "client_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (hint_event,) = [e for e in events if e["event"] == "hint_generated"]
    assert hint_event["intent"] in (True, False)


def test_take_turn_pulls_and_applies_the_peers_real_scent_map(config, tmp_path):
    # PRD 4 "Revision 3": take_turn() must genuinely call the peer's
    # share_scent_map tool and fold real numeric data into belief — not a
    # fixed placeholder or a skipped step. The server's own ScentField is
    # primed with a real trail so there's something nonzero to pull and
    # observe the effect of.
    client_port = _free_port()
    server, port = _start_server_answering(config, tmp_path, "server", _client_url_for(client_port))
    server.scent_field.advance(Position(6, 6), server.board)

    client = _start_client_as_server(config, CopBrain(), tmp_path, "client", client_port)
    belief_before = client.belief_map.probability(Position(6, 6))

    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    assert client.belief_map.probability(Position(6, 6)) > belief_before
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "client_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "requesting_scent_map" in events
    assert "scent_map_received" in events


def test_take_turn_logs_the_received_scent_maps_max_value_not_just_its_cell_count(config, tmp_path):
    # Found missing while diagnosing a real match: cell_count alone can't
    # distinguish "genuine strong signal" from "many cells, all near zero" —
    # added specifically so a future run can tell those apart from the log.
    client_port = _free_port()
    server, port = _start_server_answering(config, tmp_path, "server", _client_url_for(client_port))
    server.scent_field.advance(Position(6, 6), server.board)

    client = _start_client_as_server(config, CopBrain(), tmp_path, "client", client_port)
    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    events = [
        json.loads(line)
        for line in (tmp_path / "client_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (scent_event,) = [e for e in events if e["event"] == "scent_map_received"]
    assert scent_event["max_value"] > 0.0


def test_take_turn_logs_the_belief_target_and_its_probability_every_turn(config, tmp_path):
    # The other missing piece from the same diagnosis: without this, there
    # was no way to see whether belief was ever migrating toward the real
    # scent trail turn by turn, only where the cop's own feet ended up.
    client_port = _free_port()
    server, port = _start_server_answering(config, tmp_path, "server", _client_url_for(client_port))
    server.scent_field.advance(Position(6, 6), server.board)

    client = _start_client_as_server(config, CopBrain(), tmp_path, "client", client_port)
    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    events = [
        json.loads(line)
        for line in (tmp_path / "client_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (belief_event,) = [e for e in events if e["event"] == "belief_target_updated"]
    assert belief_event["target_pos"] == [client.game_state.target_pos.col, client.game_state.target_pos.row]
    assert 0.0 < belief_event["target_probability"] <= 1.0


def test_on_reveal_received_applies_the_tactical_claim(config, tmp_path):
    # PRD 4 "Revision 3": _on_reveal_received's hint_text still only feeds
    # the tactical claim — scent-map corroboration is take_turn's own pull.
    # PRD 6: `move` itself is an unverified claim (Design Question 2), not
    # consumed by this callback at all.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    claim_focal = interpret_hint("Near the south east side.", client.board)
    claim_before = client.belief_map.probability(claim_focal)

    client._on_reveal_received(
        {"type": "move", "direction": "NORTH"}, "Near the south east side.", time.time(), time.time() + 30.0
    )

    assert client.belief_map.probability(claim_focal) > claim_before


def test_on_reveal_received_leaves_belief_unchanged_for_a_direction_less_hint(config, tmp_path):
    # The actual fix, at the orchestrator level: a hint with no direction
    # word must leave belief genuinely untouched, not fall back to a
    # fabricated north-west pull (the real bug this closed — see
    # orchestrator_reveal_received.py's module docstring). Same "compare
    # against a never-updated control" proof `does_not_apply_an_over_limit_claim`
    # already uses below.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    control = BeliefMap.uniform(client.board)

    client._on_reveal_received(
        {"type": "move", "direction": "NORTH"},
        "Ask anyone near New York -- they haven't seen me.",
        time.time(),
        time.time() + 30.0,
    )

    assert client.belief_map._probabilities == control._probabilities


def test_on_reveal_received_does_not_apply_an_over_limit_claim(config, tmp_path):
    # rule-auditor finding (I9): receive_reveal's ack flags an over-limit
    # hint to the sender, but the ack alone doesn't stop the *content* from
    # reaching this callback — it must be gated before touching belief
    # state. Compared against a control BeliefMap that's never updated at
    # all: if the over-limit claim contributed nothing, the two end up
    # byte-identical.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    over_limit_text = " ".join(["south", "east"] * config.hint_word_limit)

    control = BeliefMap.uniform(client.board)

    client._on_reveal_received(
        {"type": "move", "direction": "NORTH"}, over_limit_text, time.time(), time.time() + 30.0
    )

    assert client.belief_map._probabilities == control._probabilities


def test_a_fresh_orchestrator_has_no_last_hint_received_yet(config, tmp_path):
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    assert client._last_hint_received is None


def test_on_reveal_received_mirrors_the_hint_text_for_the_live_gui(config, tmp_path):
    # PRD 7 round-2 (Local Truth): the live GUI needs the actual hint text,
    # not just its effect on belief -- a real, persistent attribute, not a
    # local variable this callback throws away once it's done with it.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))

    client._on_reveal_received(
        {"type": "move", "direction": "NORTH"}, "Near the south east side.", time.time(), time.time() + 30.0
    )

    assert client._last_hint_received == "Near the south east side."


def test_on_reveal_received_mirrors_the_hint_text_even_when_over_the_word_limit(config, tmp_path):
    # The display mirror is unconditional -- unlike the belief-map gate
    # above, an over-limit hint still genuinely arrived and should still
    # show up in the GUI, even though it's correctly excluded from belief.
    client = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "trace.jsonl"))
    over_limit_text = " ".join(["south", "east"] * config.hint_word_limit)

    client._on_reveal_received(
        {"type": "move", "direction": "NORTH"}, over_limit_text, time.time(), time.time() + 30.0
    )

    assert client._last_hint_received == over_limit_text


def _private_config_pointing_at(port: int) -> PrivateConfig:
    """todoFullFix.md §B3: a PrivateConfig whose [network].opponent_url
    points at a real running peer, for proving take_turn() falls back to it."""
    return PrivateConfig(
        provider="template", every_n_steps=1,
        opponent_url=f"http://127.0.0.1:{port}/mcp", my_port=0, turn_timeout_seconds=180.0,
        initiate_step0=False, step0_wait_seconds=300.0,
        group_name="dev-team", group_id="dev-team", sub_game_number=1, members=("dev-1",),
        repos={"cop": "https://example.com/cop", "thief": "https://example.com/thief"},
        model="claude-sonnet-5", step_deadline_seconds=30.0,
        email_recipient="dev@example.com", email_mode="draft",
    )


def test_take_turn_without_an_explicit_peer_url_uses_the_private_configs_opponent_url(config, tmp_path):
    client_port = _free_port()
    _, port = _start_server_answering(config, tmp_path, "server", _client_url_for(client_port))
    client = _start_client_as_server(
        config, CopBrain(), tmp_path, "client", client_port,
        private_config=_private_config_pointing_at(port),
    )

    result = asyncio.run(client.take_turn())  # no peer_url argument at all

    assert result["accepted"] is True
    assert client.state_machine.state == "WAITING_FOR_OPPONENT"
