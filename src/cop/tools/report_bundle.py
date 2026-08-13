"""Filenames for all four Table 20 files, plus the `declaration_<game_id>.json`
builder and the raw config/log loaders. `result_<game_id>.json`'s own real,
series-scoped builder (`SubGameEntry`, `merge_into_series_result`) moved to
`report_bundle_result.py`/`report_bundle_series.py` (PRD 16) once it grew
past a flat, single-sub-game-scoped dict — this file keeps only what stayed
simple.

Composes `integrity/step0.py::Step0Declaration` (reused, not duplicated —
PRD 6's own "don't reopen the frozen spec" discipline). Rule 49's four
links now live in `result_<game_id>.json`'s own `repo_urls` field
(`report_bundle_series.py`), not here — `DeclarationBundle` carries only
this team's own two.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..integrity.step0 import Step0Declaration


def declaration_filename(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def result_filename(game_id: str) -> str:
    return f"result_{game_id}.json"


def config_filename(game_id: str, sub_game_number: int) -> str:
    return f"config_{game_id}_g{sub_game_number:02d}.json"


def log_filename(game_id: str, sub_game_number: int) -> str:
    return f"log_{game_id}_g{sub_game_number:02d}.json"


def load_config_dict(shared_config_path: str | Path) -> dict:
    """The `config_<game_id>_g<NN>.json` attachment: the negotiated shared
    config's own raw parsed content, exactly as byte-identical rule 11
    already guarantees it is on both sides — not rebuilt from `GameConfig`,
    which would risk silently diverging from what was actually agreed."""
    return json.loads(Path(shared_config_path).read_text(encoding="utf-8"))


def load_log_entries(log_path: str | Path) -> list[dict]:
    """The `log_<game_id>_g<NN>.json` attachment: `Trace`'s own JSONL file
    (`observability/trace.py`), parsed into a JSON array — `send_report_
    bundle`'s attachments are JSON-serializable payloads, not raw file
    bytes (`tools/gmail_sender.py::build_message`), so the newline-
    delimited log needs this one translation, not a re-derivation of its
    content."""
    lines = Path(log_path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _hardware_dict(step0: Step0Declaration) -> dict:
    hardware = step0.hardware
    return {
        "os_name": hardware.os_name,
        "cpu_cores": hardware.cpu_cores,
        "ram_gb": hardware.ram_gb,
        "gpu_present": hardware.gpu_present,
        "gpu_vram_gb": hardware.gpu_vram_gb,
        "llm_model": hardware.llm_model,
    }


@dataclass(frozen=True)
class DeclarationBundle:
    step0: Step0Declaration
    group_name: str
    members: tuple[str, ...]
    cop_repo_url: str
    thief_repo_url: str
    token_budget_per_series: int
    started_at: str | None
    ended_at: str | None = None


def build_declaration(bundle: DeclarationBundle) -> dict:
    return {
        "hardware": _hardware_dict(bundle.step0),
        "code_commit_hash": bundle.step0.code_commit_hash,
        "group_name": bundle.group_name,
        "sub_game_number": bundle.step0.sub_game_number,
        "config_sha256": bundle.step0.config_sha256,
        "scent_model_sha256": bundle.step0.scent_model_sha256,
        "members": list(bundle.members),
        "cop_repo_url": bundle.cop_repo_url,
        "thief_repo_url": bundle.thief_repo_url,
        "token_budget_per_series": bundle.token_budget_per_series,
        "started_at": bundle.started_at,
        "ended_at": bundle.ended_at,
    }
