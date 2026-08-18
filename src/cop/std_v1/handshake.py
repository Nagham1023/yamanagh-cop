"""Mutual negotiation handshake (spec Section 3). Push-based and
idempotent, not a single request/response RPC: this side keeps re-sending
its own unchanged offer to the peer's `negotiate` tool while polling
`exchange` (via `asyncio.to_thread`, since `StdExchange` itself is a plain
blocking mailbox — see that module's own docstring for why) for the
peer's own matching one — Section 3's own "a single successful negotiate
call MUST NOT be treated as a completed handshake" requirement.
"""

from __future__ import annotations

import asyncio
import time

from ..planner.deadline import DeadlineExceededError
from .crypto import commit_of, derive_game_uid, fresh_nonce
from .exchange import StdExchange
from .terms import validate_terms
from .wire import send_negotiate


def build_offer(
    terms: dict,
    group_id: str,
    role: str,
    sub_game_number: int,
    identity: dict,
    game_uid: str,
    nonce: str,
) -> dict:
    """Assembles this side's own signed negotiation offer."""
    return {
        "terms": terms,
        "nonce": nonce,
        "signature": commit_of(terms, nonce),
        "group_id": group_id,
        "role": role,
        "sub_game_number": sub_game_number,
        "identity": identity,
        "game_uid": game_uid,
    }


def validate_offer(offer: dict, my_terms: dict) -> None:
    """Section 3's own greeting-validation rules 1-4 — rules 5/6 (missing
    `group_id`, mismatched `game_uid`) are checked by the caller, which
    alone knows the expected `game_uid` for this pairing."""
    terms = offer.get("terms")
    validate_terms(terms)
    if terms != my_terms:
        diff = {
            key: (my_terms.get(key), terms.get(key))
            for key in set(my_terms) | set(terms)
            if my_terms.get(key) != terms.get(key)
        }
        raise ValueError(
            f"peer's terms differ from ours -- refusing the greeting (rule 3): {diff}"
        )
    nonce = offer.get("nonce")
    signature = offer.get("signature")
    if not nonce or not signature:
        raise ValueError("greeting missing nonce/signature (rule 4)")
    if commit_of(terms, nonce) != signature:
        raise ValueError("greeting signature does not verify against its own terms (rule 4)")
    if not offer.get("group_id"):
        raise ValueError("greeting missing group_id (rule 5)")


async def negotiate_sub_game(
    connection,
    exchange: StdExchange,
    my_terms: dict,
    my_group_id: str,
    their_group_id: str,
    role: str,
    sub_game_number: int,
    identity: dict,
    resend_interval_sec: float = 2.0,
    ceiling_sec: float = 300.0,
    retry_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> dict:
    """Sends this side's own offer, then repeatedly re-sends the identical
    offer (same nonce/terms/identity, never regenerated on a retry — the
    spec's own explicit requirement) while polling `exchange` for the
    peer's matching one, until either it arrives or `ceiling_sec` elapses.
    Returns the peer's own validated offer. `retry_attempts`/
    `retry_delay_seconds` bound each individual `send_negotiate` call's
    own connect-only retry (`wire.py`), sourced from `PrivateConfig` at
    the real call site — I6, not a fixed default."""
    game_uid = derive_game_uid(my_terms, my_group_id, their_group_id)
    nonce = fresh_nonce()
    my_offer = build_offer(my_terms, my_group_id, role, sub_game_number, identity, game_uid, nonce)

    deadline = time.monotonic() + ceiling_sec
    while time.monotonic() < deadline:
        try:
            await send_negotiate(connection, my_offer, retry_attempts, retry_delay_seconds)
        except Exception:
            # A flaky peer (tunnel blip, a session drop on their own end)
            # must cost this one send, not the whole handshake -- found
            # live: send_negotiate's own inner connect-retry (a few
            # seconds) used to propagate straight out of this function,
            # ending the match in seconds instead of the ceiling_sec this
            # loop's own docstring promises. Never regenerates my_offer;
            # same "re-send the identical offer" contract as the
            # DeadlineExceededError branch below.
            await asyncio.sleep(min(resend_interval_sec, max(0.0, deadline - time.monotonic())))
            continue
        remaining = deadline - time.monotonic()
        wait_timeout = min(resend_interval_sec, max(0.0, remaining))
        try:
            their_offer = await asyncio.to_thread(
                exchange.wait_for_offer, sub_game_number, wait_timeout
            )
        except DeadlineExceededError:
            continue  # re-send the identical offer, never regenerated
        validate_offer(their_offer, my_terms)
        declared_uid = their_offer.get("game_uid")
        if declared_uid != game_uid:
            raise ValueError(
                f"peer's declared game_uid {declared_uid!r} != derived {game_uid!r} (rule 6)"
            )
        return their_offer

    raise DeadlineExceededError(
        f"no matching negotiation offer for sub_game {sub_game_number} within {ceiling_sec}s"
    )
