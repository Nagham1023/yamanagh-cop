"""Rule 54: total tokens consumed, in the final JSON report."""

from __future__ import annotations

import json

from cop.observability.cost import aggregate_tokens


def test_an_all_zero_log_rolls_up_to_zero_honestly(tmp_path):
    log_path = tmp_path / "trace.jsonl"
    entries = [
        {"event": "hint_generated", "tokens_used": 0},
        {"event": "hint_generated", "tokens_used": 0},
        {"event": "computed_move"},  # no tokens_used field at all — must not crash
    ]
    log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    totals = aggregate_tokens(log_path)

    assert totals.total_tokens == 0
    assert totals.turns_counted == 2


def test_a_blank_line_in_the_log_is_skipped_not_a_json_error(tmp_path):
    log_path = tmp_path / "trace.jsonl"
    log_path.write_text(
        '{"event": "hint_generated", "tokens_used": 5}\n'
        "\n"  # a genuinely blank line — must be skipped, not json.loads()'d
        '{"event": "hint_generated", "tokens_used": 7}\n',
        encoding="utf-8",
    )

    totals = aggregate_tokens(log_path)

    assert totals.total_tokens == 12
    assert totals.turns_counted == 2


def test_a_synthetic_non_zero_log_rolls_up_correctly(tmp_path):
    # Simulates a future claude_api/claude_cli run — proves the aggregation
    # math works even though no live provider produces this data yet.
    log_path = tmp_path / "trace.jsonl"
    entries = [
        {"event": "hint_generated", "tokens_used": 42},
        {"event": "hint_generated", "tokens_used": 58},
        {"event": "hint_generated", "tokens_used": 100},
    ]
    log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    totals = aggregate_tokens(log_path)

    assert totals.total_tokens == 200
    assert totals.turns_counted == 3


def test_a_real_take_turn_logs_a_zero_token_hint_generated_event(config, tmp_path):
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

    port = _free_port()
    server = Orchestrator(config, CopBrain(), log_path=str(tmp_path / "server_trace.jsonl"))
    threading.Thread(
        target=server.run_as_server, kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    ).start()
    time.sleep(0.5)

    client_log = tmp_path / "client_trace.jsonl"
    client = Orchestrator(config, CopBrain(), log_path=str(client_log))
    asyncio.run(client.take_turn(f"http://127.0.0.1:{port}/mcp"))

    totals = aggregate_tokens(client_log)
    assert totals.total_tokens == 0
    assert totals.turns_counted == 1
