"""Loads the private, per-team `config/game.toml` — deliberately a separate
loader from `GameConfig.from_file`, not a shared dataclass.

Table 21/22 are explicit that this whole file is "private per peer, not
negotiated": it must never be diffed against the opponent's copy the way
`check_config.py --identical` diffs `GameConfig`. Keeping a distinct loader
(rather than folding these fields into `GameConfig`) is what keeps that
split real instead of just documented (PRD 4 Design Question 7).

`todoFullFix.md` §B: the book's actual private file (p.130-132) is TOML —
`config/game.toml`, six sections (`[game]`/`[network]`/`[strategy]`/
`[trash_talk]`/`[llm]`/`[email]`) — not the flat, JSON, `[trash_talk]`-only
shape earlier PRDs built. `opponent_url` lives in `[network]` here — "the
only thing I know about the opponent" (the book's own words) — which is
also why it belongs in this never-negotiated, never-hashed file rather than
as a runtime-only argument. `[strategy]` is read but not yet consumed
anywhere (PRD 4's "Explicitly out of scope" note still applies; dynamic
`thief_class`/`police_class` loading is unbuilt).

PRD 10: `initiate_step0`/`step0_wait_seconds` (`[network]`) tell the CLI
(`cli_peer.py`) which side dials out first for the ch. 5.5 negotiation
ceremony — a real-match decision agreed with the peer team out-of-band,
same never-negotiated category as `opponent_url`. Both default safely
(`False`/`300.0`) via `.get()` so existing config files and test fixtures
that predate this pair keep loading unchanged.

`scent_map_retry_attempts`/`scent_map_retry_delay_seconds` (`[network]`):
found via a real cross-machine match — a free-tier ngrok tunnel dropped
for close to a second (the peer's own next call reached us again shortly
after we'd finished failing), yet `request_scent_map_from_peer`'s one-shot
call turned that into an instant forfeit. Reused (not renamed) for
`send_final_reveal_to_peer` (`orchestrator_peer_audit.py`) too, same
"reuse one robustness knob rather than add a per-call-site one" pattern
`response_timeout_seconds` already follows elsewhere in this repo
(`orchestrator_turn.py`'s own comment) — both `share_scent_map` and
`receive_final_reveal` are confirmed idempotent on the receiving side (a
pure read; a pure overwrite via `PeerTrace.record_final_reveal`'s own
`setdefault`), unlike commit/reveal/capture, which carry the
double-application risk `mcp_client_prd6.py`'s blanket no-retry policy
exists to avoid — never touched here. Default (`3`/`1.0`, ~2s of retry
headroom, still far inside the 30s `response_timeout_seconds` deadline)
via `.get()`, same backward-compatible pattern as the pair above.

`post_match_grace_seconds` (`[network]`): found via a real cross-machine
match report — this side's own terminal returned to the shell prompt
*before* the peer's, and the peer's own subsequent
`receive_final_reveal` call failed with a bare connection refusal, no
corresponding entry in this side's own server log at all. Root cause,
confirmed by reading `cli_peer_match_body.py::run_match_body`: the server runs on a
`daemon=True` thread, so the instant `report_game()` returns and
`run_match_body` itself returns, the whole process — server, tunnel,
everything — exits immediately. `_PEER_FINAL_REVEAL_WAIT_SECONDS`
(`orchestrator_peer_audit.py`) already waits 5s *inside* `report_game()`
for the peer's Final Reveal, but that figure is deliberately short so
most unit tests (which call `report_game()` directly, with no real peer)
don't each pay a near-full wait — it cannot also be this repo's answer to
"how much slower might a genuinely independent, real peer be, over a real
network." This is a second, later, CLI-only wait — `cli_peer.py`'s own
`run_match_body`, never `report_game()`/`Orchestrator` itself — so no
existing unit test that constructs an `Orchestrator` directly is
affected. Default `60.0`: generous enough for a real pacing gap between
two independently-timed peers, still bounded (rule 4 — every wait has a
deadline), an order of magnitude short of `step0_wait_seconds`'s own
300.0 default for the same "let the other side catch up" category of
wait.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PrivateConfig:
    provider: str
    every_n_steps: int
    opponent_url: str
    my_port: int
    turn_timeout_seconds: float
    initiate_step0: bool
    step0_wait_seconds: float
    scent_map_retry_attempts: int
    scent_map_retry_delay_seconds: float
    post_match_grace_seconds: float
    group_name: str
    group_id: str
    sub_game_number: int
    members: tuple[str, ...]
    repos: dict[str, str]
    model: str
    step_deadline_seconds: float
    email_recipient: str
    email_mode: str
    thief_class: str | None = None
    police_class: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrivateConfig:
        game = data["game"]
        network = data["network"]
        trash_talk = data["trash_talk"]
        llm = data["llm"]
        email = data["email"]
        strategy = data.get("strategy", {})

        provider = trash_talk["provider"]
        every_n_steps = trash_talk["every_n_steps"]
        if not isinstance(provider, str) or not provider:
            raise ValueError(f"provider must be a non-empty string, got {provider!r}")
        if (
            not isinstance(every_n_steps, int)
            or isinstance(every_n_steps, bool)
            or every_n_steps <= 0
        ):
            raise ValueError(f"every_n_steps must be a positive int, got {every_n_steps!r}")

        return cls(
            provider=provider,
            every_n_steps=every_n_steps,
            opponent_url=network["opponent_url"],
            my_port=network["my_port"],
            turn_timeout_seconds=float(network["turn_timeout_seconds"]),
            initiate_step0=bool(network.get("initiate_step0", False)),
            step0_wait_seconds=float(network.get("step0_wait_seconds", 300.0)),
            scent_map_retry_attempts=int(network.get("scent_map_retry_attempts", 3)),
            scent_map_retry_delay_seconds=float(network.get("scent_map_retry_delay_seconds", 1.0)),
            post_match_grace_seconds=float(network.get("post_match_grace_seconds", 60.0)),
            group_name=game["group_name"],
            group_id=game["group_id"],
            sub_game_number=game["sub_game_number"],
            members=tuple(game["members"]),
            repos=dict(game["repos"]),
            model=llm["model"],
            step_deadline_seconds=float(llm["step_deadline_seconds"]),
            email_recipient=email["recipient"],
            email_mode=email["mode"],
            thief_class=strategy.get("thief_class"),
            police_class=strategy.get("police_class"),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> PrivateConfig:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)
