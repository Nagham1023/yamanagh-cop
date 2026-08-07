"""Step-0 (ch. 5.5, p.55): hardware/code declaration, signed. `code_commit_hash`
must genuinely reflect real git state, not a fixed string — "prove it's real"
discipline used by every prior PRD's own wire-is-real tests.
"""

from __future__ import annotations

import subprocess

import pytest

from cop.integrity.hardware_declaration import (
    HardwareDeclaration,
    _detect_gpu,
    _detect_ram_gb,
    detect_hardware,
)
from cop.integrity.step0 import (
    Step0Declaration,
    current_git_commit_hash,
    hash_config_file,
    sign_step0,
    verify_config_identity,
)


def _hardware(**overrides) -> HardwareDeclaration:
    base = {
        "os_name": "Linux",
        "cpu_cores": 8,
        "ram_gb": 16.0,
        "gpu_present": False,
        "gpu_vram_gb": None,
        "llm_model": "claude-sonnet-5",
    }
    base.update(overrides)
    return HardwareDeclaration(**base)


def _declaration(**overrides) -> Step0Declaration:
    base = {
        "hardware": _hardware(),
        "code_commit_hash": "a" * 40,
        "group_name": "yamanagh",
        "sub_game_number": 1,
        "config_sha256": "b" * 64,
    }
    base.update(overrides)
    return Step0Declaration(**base)


def test_detect_hardware_returns_a_real_declaration():
    declaration = detect_hardware("claude-sonnet-5")
    assert declaration.cpu_cores >= 1
    assert declaration.llm_model == "claude-sonnet-5"


def test_hardware_declaration_rejects_a_negative_gpu_vram():
    with pytest.raises(ValueError):
        _hardware(gpu_present=True, gpu_vram_gb=-1.0)


def test_detect_ram_gb_falls_back_to_zero_when_meminfo_is_absent(monkeypatch):
    import cop.integrity.hardware_declaration as hardware_module

    monkeypatch.setattr(hardware_module.Path, "exists", lambda self: False)
    assert _detect_ram_gb() == 0.0


def test_detect_ram_gb_falls_back_to_zero_on_a_malformed_meminfo(monkeypatch):
    import cop.integrity.hardware_declaration as hardware_module

    monkeypatch.setattr(hardware_module.Path, "exists", lambda self: True)
    monkeypatch.setattr(hardware_module.Path, "read_text", lambda self, encoding: "MemTotal: not-a-number kB\n")
    assert _detect_ram_gb() == 0.0


def test_detect_ram_gb_falls_back_to_zero_when_meminfo_has_no_memtotal_line(monkeypatch):
    import cop.integrity.hardware_declaration as hardware_module

    monkeypatch.setattr(hardware_module.Path, "exists", lambda self: True)
    monkeypatch.setattr(hardware_module.Path, "read_text", lambda self, encoding: "SomeOtherField: 1\n")
    assert _detect_ram_gb() == 0.0


def test_detect_gpu_returns_no_gpu_when_nvidia_smi_is_absent(monkeypatch):
    import cop.integrity.hardware_declaration as hardware_module

    def _raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi not found")

    monkeypatch.setattr(hardware_module.subprocess, "run", _raise_file_not_found)
    assert _detect_gpu() == (False, None)


def test_detect_gpu_returns_no_gpu_on_a_nonzero_return_code(monkeypatch):
    import cop.integrity.hardware_declaration as hardware_module

    def _fake_run(*args, **kwargs):
        return hardware_module.subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="error")

    monkeypatch.setattr(hardware_module.subprocess, "run", _fake_run)
    assert _detect_gpu() == (False, None)


def test_detect_gpu_returns_no_gpu_on_malformed_output(monkeypatch):
    import cop.integrity.hardware_declaration as hardware_module

    def _fake_run(*args, **kwargs):
        return hardware_module.subprocess.CompletedProcess(args, returncode=0, stdout="not-a-number\n", stderr="")

    monkeypatch.setattr(hardware_module.subprocess, "run", _fake_run)
    assert _detect_gpu() == (False, None)


def test_detect_gpu_parses_a_genuine_nvidia_smi_response(monkeypatch):
    import cop.integrity.hardware_declaration as hardware_module

    def _fake_run(*args, **kwargs):
        return hardware_module.subprocess.CompletedProcess(args, returncode=0, stdout="8192\n", stderr="")

    monkeypatch.setattr(hardware_module.subprocess, "run", _fake_run)
    assert _detect_gpu() == (True, 8.0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"cpu_cores": -1},
        {"cpu_cores": 0},
        {"ram_gb": -1.0},
        {"os_name": ""},
        {"llm_model": ""},
    ],
)
def test_hardware_declaration_rejects_nonsensical_values(overrides):
    base = {
        "os_name": "Linux",
        "cpu_cores": 8,
        "ram_gb": 16.0,
        "gpu_present": False,
        "gpu_vram_gb": None,
        "llm_model": "claude-sonnet-5",
    }
    base.update(overrides)
    with pytest.raises(ValueError):
        HardwareDeclaration(**base)


def test_step0_declaration_rejects_a_non_positive_sub_game_number():
    with pytest.raises(ValueError):
        _declaration(sub_game_number=0)


def test_step0_declaration_rejects_an_empty_group_name():
    with pytest.raises(ValueError):
        _declaration(group_name="")


def test_current_git_commit_hash_matches_real_git_state():
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert current_git_commit_hash() == expected


def test_current_git_commit_hash_raises_loudly_on_failure(monkeypatch):
    import cop.integrity.step0 as step0_module

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, returncode=128, stdout="", stderr="not a git repository")

    monkeypatch.setattr(step0_module.subprocess, "run", _fake_run)
    with pytest.raises(RuntimeError, match="git rev-parse HEAD failed"):
        current_git_commit_hash()


def test_hash_config_file_matches_check_config_scripts_own_algorithm(tmp_path):
    import hashlib

    config_file = tmp_path / "config.json"
    config_file.write_bytes(b'{"a": 1}')
    expected = hashlib.sha256(config_file.read_bytes()).hexdigest()
    assert hash_config_file(config_file) == expected


def test_sign_step0_is_deterministic_for_the_same_logical_declaration():
    assert sign_step0(_declaration()) == sign_step0(_declaration())


def test_sign_step0_changes_when_a_hardware_field_changes():
    baseline = sign_step0(_declaration())
    changed = sign_step0(_declaration(hardware=_hardware(cpu_cores=16)))
    assert baseline != changed


def test_sign_step0_changes_when_config_sha256_changes():
    baseline = sign_step0(_declaration())
    changed = sign_step0(_declaration(config_sha256="c" * 64))
    assert baseline != changed


def test_verify_config_identity_accepts_byte_identical_files(tmp_path):
    ours = tmp_path / "ours.json"
    theirs = tmp_path / "theirs.json"
    ours.write_bytes(b'{"a": 1}')
    theirs.write_bytes(b'{"a": 1}')
    assert verify_config_identity(ours, theirs) is True


def test_verify_config_identity_rejects_a_single_byte_difference(tmp_path):
    ours = tmp_path / "ours.json"
    theirs = tmp_path / "theirs.json"
    ours.write_bytes(b'{"a": 1}')
    theirs.write_bytes(b'{"a": 2}')
    assert verify_config_identity(ours, theirs) is False
