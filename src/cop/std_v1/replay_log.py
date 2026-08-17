"""Per-sub-game replay log for std_v1 matches (rule 20 **[FATAL]**: "Build
a viewer application that replays and verifies the game log"). Distinct
from `observability/replay_viewer.py`, which only understands the native
protocol's own commit-reveal scheme (`integrity/commit_reveal.py`) — std_v1
seals turns with a different construction (`crypto.py::commit_of`,
`sealing.py`), so a std_v1 match needs its own log shape and its own
verifier, following the same "merge the commit witnessed live with the
later-revealed record, recompute, compare" idea rule 20 requires, applied
to this protocol's own fields. Reuses `sealing.verify_record` rather than
re-deriving the hash check, so the two never silently diverge.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.report_bundle import log_filename
from .sealing import verify_record


def merge_records(
    my_records: list[dict], my_commits: dict[int, str],
    peer_records: list[dict], peer_commits: dict[int, str],
) -> list[dict]:
    """One step-ordered list covering both sides of the sub-game. Each
    record already carries its own `sender` (`build_audit_record`'s own
    field set); `live_commit` is the commit that side actually sent/
    witnessed *live*, added here so a later, standalone verifier never has
    to trust a record's own claims about itself."""
    merged = [{**r, "live_commit": my_commits.get(r["step"], "")} for r in my_records]
    merged += [{**r, "live_commit": peer_commits.get(r["step"], "")} for r in peer_records]
    return sorted(merged, key=lambda r: r["step"])


def write_sub_game_log(game_id: str, sub_game_number: int, merged: list[dict], out_dir: str | Path) -> Path:
    """Writes `log_<game_id>_g<NN>.json` (Table 20's own naming, shared
    with the native protocol via `report_bundle.log_filename` rather than
    a second copy of the same f-string). A single JSON object tagged
    `"protocol": "std_v1"` — unlike the native protocol's JSONL event
    stream — so `cli_replay.py` can tell the two dialects apart on load."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    log_path = out_path / log_filename(game_id, sub_game_number)
    log_path.write_text(
        json.dumps(
            {"protocol": "std_v1", "game_id": game_id, "sub_game_number": sub_game_number, "records": merged},
            indent=2,
        ),
        encoding="utf-8",
    )
    return log_path


def verify_sub_game_log(log_path: str | Path) -> dict:
    """Rule 20's own replay verdict, recomputed from a saved log alone --
    no live process needed. Re-hashes every record's own public+hidden
    fields with its own revealed nonce and compares against the
    `live_commit` stored alongside it — never a commit the record merely
    claims for itself, the same non-negotiable check `audit.py::
    verify_peer_records` already applies live, during the match."""
    data = json.loads(Path(log_path).read_text(encoding="utf-8"))
    steps = [
        {"step": record["step"], "verified": verify_record(record, record.get("live_commit", ""))}
        for record in data.get("records", [])
    ]
    return {"passed": all(step["verified"] for step in steps), "steps": steps}


def is_std_v1_log(log_path: str | Path) -> bool:
    """Format sniff for `cli_replay.py`: a std_v1 log is one JSON object
    tagged `"protocol": "std_v1"`; the native protocol's log is JSONL
    (one JSON value per line), which never parses as a single object."""
    try:
        data = json.loads(Path(log_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(data, dict) and data.get("protocol") == "std_v1"
