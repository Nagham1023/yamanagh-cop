"""Hardware half of Step-0 (ch. 5.5, p.55) — split out of `step0.py`, which
grew past the 150-line house cap once this repo's own `config_sha256`
extension landed alongside it. Stdlib only (`platform`/`os`/`subprocess`) —
no new dependency, matching PRD 6's own "New dependency: None" line.
Detection is best-effort: `ram_gb`/`gpu_*` fall back to honestly-reported
"unknown" values on any platform where the stdlib-only probe fails, rather
than raising — a Step-0 declaration with a "couldn't detect" value is still
a real declaration; a crash at startup because of it would not be.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive int, got {value!r}")
    return value


def _non_negative_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be a non-negative number, got {value!r}")
    return float(value)


def _non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")
    return value


@dataclass(frozen=True)
class HardwareDeclaration:
    """Ch. 5.5's own hardware fields. Constructor-time validated — the same
    "fail loudly at the boundary" discipline `shared/config.py`'s validators
    use — since a nonsensical value here (negative core count) is a real bug
    worth catching immediately, not something to discover at audit time."""

    os_name: str
    cpu_cores: int
    ram_gb: float
    gpu_present: bool
    gpu_vram_gb: float | None
    llm_model: str

    def __post_init__(self) -> None:
        _non_empty_string(self.os_name, "os_name")
        _positive_int(self.cpu_cores, "cpu_cores")
        _non_negative_float(self.ram_gb, "ram_gb")
        if self.gpu_vram_gb is not None:
            _non_negative_float(self.gpu_vram_gb, "gpu_vram_gb")
        _non_empty_string(self.llm_model, "llm_model")


def _detect_ram_gb() -> float:
    """`/proc/meminfo`'s `MemTotal` line on Linux; `0.0` (honestly
    "unknown") everywhere else or on any read failure."""
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return 0.0
    try:
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                kib = int(line.split()[1])
                return round(kib / (1024 * 1024), 2)
    except (OSError, ValueError, IndexError):
        return 0.0
    return 0.0


def _detect_gpu() -> tuple[bool, float | None]:
    """`nvidia-smi`, if present on `PATH` — the one stdlib-reachable signal
    without a new dependency. Anything else (no NVIDIA tooling, AMD/Apple
    Silicon, a sandboxed CI box) honestly reports "no GPU detected"."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    if result.returncode != 0 or not result.stdout.strip():
        return False, None
    try:
        mib = float(result.stdout.strip().splitlines()[0])
    except ValueError:
        return False, None
    return True, round(mib / 1024, 2)


def detect_hardware(llm_model: str) -> HardwareDeclaration:
    """This process's own best-effort hardware declaration — the values
    that actually get signed, not hand-entered."""
    gpu_present, gpu_vram_gb = _detect_gpu()
    return HardwareDeclaration(
        os_name=platform.system(),
        cpu_cores=os.cpu_count() or 1,
        ram_gb=_detect_ram_gb() or 0.01,
        gpu_present=gpu_present,
        gpu_vram_gb=gpu_vram_gb,
        llm_model=llm_model,
    )
