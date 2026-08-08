"""Watch PRD 9's Step-0 negotiation ceremony (ch. 5.5, rules 11/23/24/49)
run live: two real `Orchestrator`s, one calling `negotiate_step0()` against
the other's real HTTP server. Case 1 is a genuine match — both sides'
`config_sha256`/`scent_model_sha256` agree, negotiation succeeds, both
state machines reach `WAITING_FOR_OPPONENT`, and each side learns the
other's repo URLs (rule 49). Case 2 is adversarial: one side's shared
config file is tampered by a single byte — negotiation is rejected on
both ends, cleanly, as `TECHNICAL_LOSS`, not a hang and not a silent pass.

Run:
    uv run python scripts/watch_prd9_step0_negotiation.py
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from pathlib import Path

from cop.orchestrator import Orchestrator
from cop.orchestrator_step0 import Step0MismatchError
from cop.reasoning.cop_brain import CopBrain
from cop.shared.config import GameConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_peer(config, log_path, shared_config_path) -> tuple[Orchestrator, str]:
    peer = Orchestrator(
        config, CopBrain(), log_path=str(log_path), shared_config_path=str(shared_config_path)
    )
    port = _free_port()
    threading.Thread(
        target=peer.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)
    return peer, f"http://127.0.0.1:{port}/mcp"


def _run_success_case(config) -> None:
    print(f"\n{'=' * 60}")
    print("Case 1: a genuine match — both sides negotiate successfully")
    print("=" * 60)

    peer, peer_url = _start_peer(config, "/tmp/watch_prd9_peer.jsonl", CONFIG_PATH)
    client = Orchestrator(
        config, CopBrain(), log_path="/tmp/watch_prd9_client.jsonl",
        shared_config_path=str(CONFIG_PATH),
    )

    print("\n1. client.negotiate_step0(peer_url) — a real Step-0 exchange over HTTP")
    asyncio.run(client.negotiate_step0(peer_url))

    print(f"   client state machine: {client.state_machine.state}")
    print(f"   peer state machine:   {peer.state_machine.state}")
    print(f"   client learned peer's repos: {client._opponent_repos}")
    print(f"   peer learned client's repos: {peer._opponent_repos}")
    print("   (rule 11/23 locked; rule 49's repo channel is live, not hand-supplied)")


def _run_mismatch_case(config) -> None:
    print(f"\n{'=' * 60}")
    print("Case 2: adversarial — a single tampered byte in the peer's own shared config")
    print("=" * 60)

    tampered_path = Path("/tmp/watch_prd9_tampered_config.json")
    tampered_path.write_bytes(CONFIG_PATH.read_bytes() + b" ")

    peer, peer_url = _start_peer(config, "/tmp/watch_prd9_peer_bad.jsonl", tampered_path)
    client = Orchestrator(
        config, CopBrain(), log_path="/tmp/watch_prd9_client_bad.jsonl",
        shared_config_path=str(CONFIG_PATH),
    )

    print("\n1. client.negotiate_step0(peer_url) — config_sha256 will disagree")
    try:
        asyncio.run(client.negotiate_step0(peer_url))
        raise AssertionError("expected Step0MismatchError — negotiation should have been rejected")
    except Step0MismatchError as exc:
        print(f"   negotiation rejected, as expected: {exc}")

    print(f"   client state machine: {client.state_machine.state} (expected TECHNICAL_LOSS)")
    print(f"   peer state machine:   {peer.state_machine.state} (expected TECHNICAL_LOSS)")
    print("   both sides forfeited cleanly — no hang, no silent pass (rule 11 FATAL)")


def main() -> None:
    config = GameConfig.from_file(CONFIG_PATH)
    _run_success_case(config)
    _run_mismatch_case(config)
    print("\nBoth cases ran end-to-end: a genuine mutual lock, and a clean,")
    print("mutually-visible technical loss on a real config mismatch.")


if __name__ == "__main__":
    main()
