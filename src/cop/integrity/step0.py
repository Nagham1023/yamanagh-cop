"""Step-0: the pre-game declaration each side signs before a series begins
(ch. 5.5, p.55, read directly for `PRD-6-security-and-cryptography.md`'s
Design Question 3). Book's own field list, exactly: hardware spec (this
module's own `HardwareDeclaration`, split into `hardware_declaration.py`
for the 150-line cap), LLM model name (folded into that same object), code
git-commit hash (rule 53), group name, `sub_game_number`. Plus two fields
the book does not ask for by this exact name: `config_sha256` — this
repo's own extension to close rule 11's actual enforcement gap, a config
swapped *after* Step-0 becomes a catchable audit-time mismatch instead of
an unverifiable claim — and `scent_model_sha256` (`integrity/
scent_model_lock.py`), which *is* book-required (ch. 4.5, rule 23
**[FATAL]**) even though the book doesn't specify which object should
carry it; Step-0 is the natural, single pre-game declaration rather than a
second parallel signed object. Both labeled as such below.
"""

from __future__ import annotations

import hashlib
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .canonical_json import canonical_json_bytes
from .hardware_declaration import HardwareDeclaration


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive int, got {value!r}")
    return value


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")
    return value


def current_git_commit_hash() -> str:
    """Rule 53: the actual git commit `HEAD` is at when this runs —
    `git rev-parse HEAD` via `subprocess`, not an env var a deploy step could
    forget to set. Raises `RuntimeError` rather than returning a placeholder
    string on failure — a Step-0 declaration with a fabricated commit hash is
    worse than one that fails to construct at all."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        raise RuntimeError(f"git rev-parse HEAD failed: {result.stderr.strip()}")
    return result.stdout.strip()


def hash_config_file(path: str | Path) -> str:
    """The exact hash `check_config.py --identical` computes — plain
    `sha256(raw_bytes)`, no canonical-JSON reinterpretation, so this and the
    skill script always agree on the same config file (Design Question 3's
    consistency requirement)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_config_identity(ours_path: str | Path, theirs_path: str | Path) -> bool:
    """The config identity gate (rule 11, **[FATAL]**), as an explicit,
    callable precondition rather than only a standalone CLI a human might
    forget to run — PRD 6 Design Question 3: this stays an administrative
    check (the byte-identical file itself is negotiated out-of-band, before
    any code runs), not a wire tool. Same algorithm as
    `check_config.py --identical`, reused via `hash_config_file` rather than
    shelling out to the skill script, so a `Step0Declaration.config_sha256`
    built from this function's own `ours_path` hash is guaranteed
    consistent with what `check_config.py` would independently compute.
    `secrets.compare_digest`, not `==` — same primitive as every other hash
    comparison in `integrity/`, kept consistent here too even though the
    real-world timing risk is low for a publicly-negotiated config file."""
    return secrets.compare_digest(hash_config_file(ours_path), hash_config_file(theirs_path))


@dataclass(frozen=True)
class Step0Declaration:
    """The pre-game declaration object, ch. 5.5. `config_sha256` is this
    repo's own extension, not part of the book's own field list —
    `scent_model_sha256` *is* book-required (rule 23) but not under this
    exact name — see this module's own docstring and PRD 6's Design
    Question 3."""

    hardware: HardwareDeclaration
    code_commit_hash: str
    group_name: str
    sub_game_number: int
    config_sha256: str
    scent_model_sha256: str

    def __post_init__(self) -> None:
        _non_empty_string(self.code_commit_hash, "code_commit_hash")
        _non_empty_string(self.group_name, "group_name")
        _positive_int(self.sub_game_number, "sub_game_number")
        _non_empty_string(self.config_sha256, "config_sha256")
        _non_empty_string(self.scent_model_sha256, "scent_model_sha256")


def _canonical_declaration_bytes(declaration: Step0Declaration) -> bytes:
    """`ram_gb`/`gpu_vram_gb` are floats by nature — represented as strings
    at serialization time, exactly `commit_payload.py`'s own prescribed
    mitigation for "if a float has to be in there"
    (`PRD-6-prep-commit-payload-spec.md`), so this declaration never falls
    into the float-hash-drift trap that module exists to close off."""
    hardware = declaration.hardware
    payload = {
        "hardware": {
            "os_name": hardware.os_name,
            "cpu_cores": hardware.cpu_cores,
            "ram_gb": f"{hardware.ram_gb:.2f}",
            "gpu_present": hardware.gpu_present,
            "gpu_vram_gb": None if hardware.gpu_vram_gb is None else f"{hardware.gpu_vram_gb:.2f}",
            "llm_model": hardware.llm_model,
        },
        "code_commit_hash": declaration.code_commit_hash,
        "group_name": declaration.group_name,
        "sub_game_number": declaration.sub_game_number,
        "config_sha256": declaration.config_sha256,
        "scent_model_sha256": declaration.scent_model_sha256,
    }
    return canonical_json_bytes(payload)


def sign_step0(declaration: Step0Declaration) -> str:
    """SHA-256 of the declaration's canonical JSON — same discipline as
    everything else in `integrity/`."""
    return hashlib.sha256(_canonical_declaration_bytes(declaration)).hexdigest()
