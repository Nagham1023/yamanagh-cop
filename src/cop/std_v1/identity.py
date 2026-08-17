"""The negotiation identity block (spec Section 3) — every field here is
report-relevant, so it must be sent in every per-sub-game handshake, never
assumed carried over from an earlier one. Reuses `integrity/step0.py::
current_git_commit_hash` and `integrity/hardware_declaration.py::
detect_hardware` — the same real, live-detected values Step-0 already
signs for the native protocol, not a second, divergent detection path.
"""

from __future__ import annotations

from ..integrity.hardware_declaration import detect_hardware
from ..integrity.step0 import current_git_commit_hash


def build_identity(
    group_id: str,
    group_name: str,
    members: list[str],
    repos: dict[str, str],
    mcp_servers: dict[str, str],
    llm_model: str,
    scent_model_lock: dict | None = None,
) -> dict:
    """Assembles the identity block sent inside every `negotiate` offer.

    `scent_model_lock` is a strictly additive, never-required key (see
    scent_model_lock.py) -- omitted entirely when not given, and invisible
    to the Section-12 report either way since `report.py::group_details`
    only ever whitelists specific fields off this dict."""
    commit_hash = current_git_commit_hash()
    hardware = detect_hardware(llm_model)
    identity = {
        "group_id": group_id,
        "group_name": group_name,
        "git_commit_hash": commit_hash,
        "github_commit": commit_hash,
        "members": list(members),
        "repos": dict(repos),
        "mcp_servers": dict(mcp_servers),
        "llm_model": llm_model,
        "spec": {
            "os": hardware.os_name,
            "cpu_cores": hardware.cpu_cores,
            "ram_gb": hardware.ram_gb,
            "gpu": hardware.gpu_present,
            "vram_gb": hardware.gpu_vram_gb,
        },
    }
    if scent_model_lock is not None:
        identity["scent_model_lock"] = scent_model_lock
    return identity
