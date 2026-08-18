"""std_v1's own output/reporting writers — split out of `peer_setup.py`
once `send_std_v1_report` (rule 34/35's own email dispatch, previously
entirely missing for std_v1) pushed that file past the 150-line house cap.
`peer_setup.py` keeps the pre-match construction helpers; this file is
everything that runs *after* a series has actually finished.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..policy.gatekeeper import ApiGatekeeper
from ..shared.config import GameConfig
from ..shared.private_config import PrivateConfig
from ..tools.gmail_sender import get_service, send_report_bundle
from .replay_log import merge_records, write_sub_game_log


def write_std_v1_result(result: dict, results_dir: str | Path) -> Path:
    """Section 12/18 [MUST]: filename is exactly `result_<game_id>.json`
    (no protocol prefix — this is the one submitted artifact, not an
    internal debug dump), containing `result["report"]`'s own Section-12
    shape (`std_v1/report.py::build_result_report`), not the raw
    `play_series` return value (which also carries the canonical
    consensus object and other diagnostic-only fields never part of the
    submitted report)."""
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"result_{result['game_id']}.json"
    out_path.write_text(json.dumps(result["report"], indent=2), encoding="utf-8")
    return out_path


def write_std_v1_sub_game_logs(result: dict, results_dir: str | Path) -> list[Path]:
    """Rule 20 **[FATAL]**: one `log_<game_id>_g<NN>.json` per sub-game
    that actually produced a transcript (never for a `timeout` row, which
    has none — `play_one_sub_game` already returns `None` for those).
    Written from the raw records/commits `play_series` already collected
    (`series_sub_game.py`'s `sub_game_log`), not re-derived, so this can
    never silently diverge from what was actually played and audited."""
    game_id = result["game_id"]
    written = []
    for entry in result.get("sub_game_logs", []):
        if entry is None:
            continue
        merged = merge_records(
            entry["my_records"], entry["my_commits"], entry["peer_records"], entry["peer_commits"]
        )
        written.append(write_sub_game_log(game_id, entry["sub_game_number"], merged, results_dir))
    return written


def send_std_v1_report(
    result: dict,
    result_path: Path,
    log_paths: list[Path],
    private_config: PrivateConfig,
    config: GameConfig,
    results_dir: str | Path,
) -> dict:
    """Rule 34/35 (**[FATAL]**: "each team send its own separate final
    report"), previously entirely missing for std_v1 — matches would
    finish, write real files to disk, and never email anything. Mirrors
    the native protocol's own `report_game()` dispatch (`ApiGatekeeper`
    wrapping `send_report_bundle`, ch. 9.3.1's Quota Manager -> Token
    Bucket -> DOS Detector), reusing the same `GameConfig`'s rate-limit
    fields and the same `PrivateConfig.email_mode`/`email_recipient`.
    Unconditional on `counted` -- native's own `report_game()` never gates
    the email on `is_counted` either; every completed series gets its own
    report, warm-up or not. Attachments are read back from exactly what
    was just written to disk (`write_std_v1_result`/
    `write_std_v1_sub_game_logs`'s own return values), the same "never
    re-derive, always reflect what's actually on disk" posture
    `report_bundle.py::load_log_entries` already uses natively."""
    attachments = {result_path.name: result["report"]}
    for log_path in log_paths:
        attachments[log_path.name] = json.loads(log_path.read_text(encoding="utf-8"))

    final_result = result["report"].get("final_result", {})
    subject = f"std_v1 match result — {result['game_id']}"
    body = f"Winner: {final_result.get('winner_group') or 'tie'}"

    email_mode = private_config.email_mode
    service = None if email_mode == "draft" else get_service()
    return ApiGatekeeper(config).execute(
        send_report_bundle, service, private_config.email_recipient, subject, body, attachments,
        email_mode=email_mode, draft_dir=results_dir,
    )
