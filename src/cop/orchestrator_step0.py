"""Ch. 5.5's Step-0 negotiation ceremony, live (rules 11, 23, 24, 49) —
closes the gap `cop-team-fix-list.md` flagged and `WIRE-CONTRACT.md` line
88 already admitted: `Step0Declaration`/`verify_config_identity`
(`integrity/step0.py`) existed but were never exchanged over the wire or
called automatically before a match starts.

Both sides verify independently, not just the initiator (rule 9 —
everything a peer sends is untrusted): `negotiate_step0` (the initiator,
called once, explicitly, before `run_as_server()`/`play_game()` — same
"separate, explicit call" precedent `report_game()` set in PRD 8) and
`_on_step0_received` (the responder's `build_server` callback) both run
the exact same `_verify_peer_step0` check against their own locally
computed values. A mismatch on *either* side raises `Step0MismatchError`
and drives that side's own state machine to `TECHNICAL_LOSS` — the
responder re-raises too, so a bad payload fails the tool call itself
rather than leaving the initiator believing it succeeded while the
responder silently forfeits underneath it.
"""

from __future__ import annotations

import secrets

from .integrity.hardware_declaration import detect_hardware
from .integrity.scent_model_lock import compute_scent_model_hash
from .integrity.step0 import Step0Declaration, current_git_commit_hash, hash_config_file, sign_step0
from .integrity.step0_wire import declaration_from_wire, declaration_to_wire, validate_repos
from .planner.deadline import await_with_deadline
from .planner.state_machine import PeerStateMachine
from .tools.mcp_client_prd9 import send_step0


class Step0MismatchError(Exception):
    """Raised when Step-0 negotiation fails: a signature that doesn't match
    its own declaration, a `config_sha256` disagreement (rule 11), or a
    `scent_model_sha256` disagreement (rule 23)."""


class Step0NegotiationMixin:
    def _build_own_step0(self) -> Step0Declaration:
        return Step0Declaration(
            hardware=detect_hardware(self.private_config.model),
            code_commit_hash=current_git_commit_hash(),
            group_name=self.private_config.group_name,
            sub_game_number=self.private_config.sub_game_number,
            config_sha256=hash_config_file(self.shared_config_path),
            scent_model_sha256=compute_scent_model_hash(self.config),
        )

    def _check_hash(self, own: str, theirs: str, label: str) -> None:
        if not secrets.compare_digest(theirs, own):
            reason = f"{label} mismatch"
            self.trace.log("step0_mismatch", reason=reason, ours=own, theirs=theirs)
            raise Step0MismatchError(reason)

    def _verify_peer_step0(
        self, wire_declaration: dict, signature: str, repos: dict
    ) -> tuple[Step0Declaration, dict[str, str]]:
        """The one check both `negotiate_step0` and `_on_step0_received`
        run: malformed shape (declaration or `repos` — rule 49's channel
        is unsigned, WIRE-CONTRACT.md's own documented tradeoff, but still
        must not reach `self._opponent_repos` unvalidated), a signature
        that doesn't match its own declaration, `config_sha256` (rule 11),
        then `scent_model_sha256` (rule 23) — each raising
        `Step0MismatchError`, logged, in that order."""
        try:
            declaration = declaration_from_wire(wire_declaration)
            validated_repos = validate_repos(repos)
        except (KeyError, TypeError, ValueError) as exc:
            reason = f"malformed step0 payload: {exc}"
            self.trace.log("step0_mismatch", reason=reason)
            raise Step0MismatchError(reason) from exc

        self._check_hash(sign_step0(declaration), signature, "step0 signature")
        self._check_hash(
            hash_config_file(self.shared_config_path), declaration.config_sha256, "config_sha256"
        )
        self._check_hash(
            compute_scent_model_hash(self.config), declaration.scent_model_sha256,
            "scent_model_sha256",
        )
        return declaration, validated_repos

    def _on_step0_received(self, declaration: dict, signature: str, repos: dict) -> dict:
        """Responder side, wired as `build_server`'s `on_step0`. Resets
        this side's own state machine to `NEGOTIATING` the instant the
        first Step-0 call arrives — the ceremony genuinely begins here for
        a responder that never itself called `negotiate_step0`, so the
        `TECHNICAL_LOSS` edge below is a legal transition rather than a
        jump from whatever state `__init__` happened to leave it in."""
        self.state_machine = PeerStateMachine(state="NEGOTIATING")
        own_declaration = self._build_own_step0()
        own_signature = sign_step0(own_declaration)
        try:
            _, validated_repos = self._verify_peer_step0(declaration, signature, repos)
        except Step0MismatchError:
            self.state_machine.transition("TECHNICAL_LOSS")
            raise
        self._opponent_repos = validated_repos
        self.trace.log("step0_negotiated", role="responder")
        self.state_machine.transition("WAITING_FOR_OPPONENT")
        return {
            "declaration": declaration_to_wire(own_declaration),
            "signature": own_signature,
            "repos": dict(self.private_config.repos),
        }

    async def negotiate_step0(self, peer_url: str) -> None:
        """Initiator side — called once, explicitly, before a real match's
        first turn. Network failure/timeout reaches `TECHNICAL_LOSS` the
        same way every other peer call in this repo already does
        (`await_with_deadline`, `config.response_timeout_seconds` — never a
        literal, I6)."""
        self.state_machine = PeerStateMachine(state="NEGOTIATING")
        own_declaration = self._build_own_step0()
        own_signature = sign_step0(own_declaration)
        own_repos = dict(self.private_config.repos)

        self.trace.log("step0_negotiation_started", peer_url=peer_url)
        try:
            response = await await_with_deadline(
                send_step0(
                    peer_url, declaration_to_wire(own_declaration), own_signature, own_repos
                ),
                timeout_seconds=self.config.response_timeout_seconds,
            )
        except Exception as exc:
            self.trace.log("step0_mismatch", reason=f"network failure: {exc}")
            self.state_machine.transition("TECHNICAL_LOSS")
            raise Step0MismatchError(str(exc)) from exc

        try:
            _, validated_repos = self._verify_peer_step0(
                response["declaration"], response["signature"], response["repos"]
            )
        except (Step0MismatchError, KeyError) as exc:
            self.state_machine.transition("TECHNICAL_LOSS")
            if isinstance(exc, Step0MismatchError):
                raise
            reason = f"malformed step0 response: {exc}"
            self.trace.log("step0_mismatch", reason=reason)
            raise Step0MismatchError(reason) from exc

        self._opponent_repos = validated_repos
        self.trace.log("step0_negotiated", role="initiator")
        self.state_machine.transition("WAITING_FOR_OPPONENT")
