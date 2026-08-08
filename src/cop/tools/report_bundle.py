"""Builds `declaration_<game_id>.json` and `result_<game_id>.json` (Table
20; the other two of the four mandatory files, `config_<game_id>_g<NN>.json`
and `log_<game_id>_g<NN>.json`, already exist since PRD 1/PRD 6).

Composes `integrity/step0.py::Step0Declaration` (reused, not duplicated —
PRD 6's own "don't reopen the frozen spec" discipline) with the
league-facing fields ch. 9.3.3 additionally requires. Rule 49's four links
are textually tied to the **result** file (`PRD-7-reporting-shell.md`'s
Design Question 8 addendum, ch. 9.4) — `DeclarationBundle` carries only
this team's own two.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..integrity.step0 import Step0Declaration


def declaration_filename(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def result_filename(game_id: str) -> str:
    return f"result_{game_id}.json"


def config_filename(game_id: str, sub_game_number: int) -> str:
    return f"config_{game_id}_g{sub_game_number:02d}.json"


def log_filename(game_id: str, sub_game_number: int) -> str:
    return f"log_{game_id}_g{sub_game_number:02d}.json"


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
    started_at: str
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


@dataclass(frozen=True)
class ResultBundle:
    sub_game_scores: dict[str, int]
    cumulative_score: int
    code_commit_hash: str
    total_tokens: int
    cop_repo_url: str
    thief_repo_url: str
    opponent_cop_repo_url: str
    opponent_thief_repo_url: str
    self_audit_passed: bool
    peer_audit_passed: bool


def build_result(bundle: ResultBundle) -> dict:
    return {
        "sub_game_scores": dict(bundle.sub_game_scores),
        "cumulative_score": bundle.cumulative_score,
        "code_commit_hash": bundle.code_commit_hash,
        "total_tokens": bundle.total_tokens,
        "cop_repo_url": bundle.cop_repo_url,
        "thief_repo_url": bundle.thief_repo_url,
        "opponent_cop_repo_url": bundle.opponent_cop_repo_url,
        "opponent_thief_repo_url": bundle.opponent_thief_repo_url,
        "self_audit_passed": bundle.self_audit_passed,
        "peer_audit_passed": bundle.peer_audit_passed,
    }
