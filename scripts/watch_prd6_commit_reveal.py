"""Watch PRD 6's milestone run live: a real commit/reveal round trip
between two Orchestrators, Step-0's own signed hardware declaration, and
the adversarial case — a tampered commit entry caught by the mutual audit,
not just asserted in a test.

Run:
    uv run python scripts/watch_prd6_commit_reveal.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from pathlib import Path

from cop.integrity.audit import run_mutual_audit
from cop.integrity.hardware_declaration import detect_hardware
from cop.integrity.step0 import (
    Step0Declaration,
    current_git_commit_hash,
    hash_config_file,
    sign_step0,
)
from cop.orchestrator import Orchestrator
from cop.reasoning.brain_base import Move
from cop.reasoning.cop_brain import CopBrain
from cop.shared.config import GameConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "shared" / "config_dev_g01.json"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    config = GameConfig.from_file(CONFIG_PATH)
    log_path = Path("/tmp/watch_prd6_trace.jsonl")
    log_path.unlink(missing_ok=True)

    print("1. Step-0: a real, signed hardware/code declaration (ch. 5.5)")
    hardware = detect_hardware("claude-sonnet-5")
    declaration = Step0Declaration(
        hardware=hardware,
        code_commit_hash=current_git_commit_hash(),
        group_name="yamanagh",
        sub_game_number=1,
        config_sha256=hash_config_file(CONFIG_PATH),
    )
    print(f"  hardware: os={hardware.os_name} cores={hardware.cpu_cores} ram_gb={hardware.ram_gb}")
    print(f"  code_commit_hash={declaration.code_commit_hash}")
    print(f"  config_sha256={declaration.config_sha256}")
    print(f"  Step0 signature: {sign_step0(declaration)}")

    print("\n2. A real commit -> ack -> reveal -> ack round trip (ch. 5.3.1/5.3.2)")
    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(log_path.with_suffix(".server.jsonl")))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client = Orchestrator(config, CopBrain(), log_path=str(log_path))
    client.state_machine.transition("COMPUTING_MOVE")
    result = asyncio.run(
        client.commit_and_reveal_to_peer(
            f"http://127.0.0.1:{port}/mcp", Move(direction="NORTH"), False, "quiet by the river"
        )
    )
    print(f"  reveal ack: {result}")
    print(f"  state machine ended at: {client.state_machine.state}")
    print(f"  nonce retained for step 0: {'0' in {str(k) for k in client._pending_nonces}}")

    print("\n3. The honest-path mutual audit (rule 19)")
    honest_result = run_mutual_audit(log_path, client._pending_nonces)
    print(f"  passed={honest_result.passed}, mismatches={honest_result.mismatches}")

    print("\n4. The adversarial case: tamper one committed field, confirm the audit REJECTS it")
    lines = log_path.read_text(encoding="utf-8").splitlines()
    tampered_lines = []
    for line in lines:
        entry = json.loads(line)
        if entry["event"] == "committing":
            entry["move"] = {"type": "move", "direction": "SOUTH"}  # tampered after the fact
        tampered_lines.append(json.dumps(entry))
    tampered_log = log_path.with_suffix(".tampered.jsonl")
    tampered_log.write_text("\n".join(tampered_lines) + "\n", encoding="utf-8")

    tampered_result = run_mutual_audit(tampered_log, client._pending_nonces)
    print(f"  passed={tampered_result.passed} (must be False)")
    print(f"  mismatches={tampered_result.mismatches}")
    assert tampered_result.passed is False, "the adversarial tamper must be caught, not silently accepted"

    print("\nAll PRD 6 milestone behaviours ran end-to-end.")


if __name__ == "__main__":
    main()
