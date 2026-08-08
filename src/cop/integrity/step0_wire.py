"""Wire (de)serialization for `Step0Declaration` (`integrity/step0.py`) —
split out of `orchestrator_step0.py`, which grew past the 150-line house
cap once the negotiation ceremony itself landed alongside this. Same shape
`tools/scent_wire.py` already established for the scent-map tool: a plain
JSON-safe dict in, a real dataclass out (or a raised error on a malformed
shape — rule 9, never trust what a peer sends).
"""

from __future__ import annotations

from .hardware_declaration import HardwareDeclaration
from .step0 import Step0Declaration

_REPO_ROLES = ("cop", "thief")


def declaration_to_wire(declaration: Step0Declaration) -> dict:
    hardware = declaration.hardware
    return {
        "hardware": {
            "os_name": hardware.os_name,
            "cpu_cores": hardware.cpu_cores,
            "ram_gb": hardware.ram_gb,
            "gpu_present": hardware.gpu_present,
            "gpu_vram_gb": hardware.gpu_vram_gb,
            "llm_model": hardware.llm_model,
        },
        "code_commit_hash": declaration.code_commit_hash,
        "group_name": declaration.group_name,
        "sub_game_number": declaration.sub_game_number,
        "config_sha256": declaration.config_sha256,
        "scent_model_sha256": declaration.scent_model_sha256,
    }


def declaration_from_wire(data: dict) -> Step0Declaration:
    """Rule 9: a peer's payload is untrusted structure, not just untrusted
    values — a missing/wrong-shaped field raises `KeyError`/`TypeError`/
    `ValueError`, which `orchestrator_step0.py::_verify_peer_step0` already
    catches and turns into a clean `Step0MismatchError`, never an uncaught
    crash."""
    hardware = HardwareDeclaration(**data["hardware"])
    return Step0Declaration(
        hardware=hardware,
        code_commit_hash=data["code_commit_hash"],
        group_name=data["group_name"],
        sub_game_number=data["sub_game_number"],
        config_sha256=data["config_sha256"],
        scent_model_sha256=data["scent_model_sha256"],
    )


def validate_repos(repos: dict) -> dict[str, str]:
    """Rule 49's repo-URL channel rides alongside the signed declaration,
    not inside it (WIRE-CONTRACT.md's own documented tradeoff — the
    book's Step-0 field list doesn't include it, same "logically separate
    data" category `receive_reveal` already established for `hint_text`
    riding beside `move`). Unsigned does not mean unchecked, though: a
    malformed shape here must not reach `Orchestrator._opponent_repos` and
    surface as an uncaught `KeyError` inside `report_game()` at the end of
    a real match — raises `ValueError`, caught the same way
    `declaration_from_wire`'s own malformed-shape errors already are."""
    if not isinstance(repos, dict) or set(repos) != set(_REPO_ROLES):
        raise ValueError(f"repos must have exactly the keys {_REPO_ROLES}, got {repos!r}")
    for role in _REPO_ROLES:
        url = repos[role]
        if not isinstance(url, str) or not url:
            raise ValueError(f"repos[{role!r}] must be a non-empty string, got {url!r}")
    return dict(repos)
