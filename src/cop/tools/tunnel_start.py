"""`start_tunnel` — split out of `tunnel.py`, which grew past the 150-line
house cap once the "refuse a second real agent" pre-check landed. Only
`start_tunnel` moved; `tunnel.py` re-exports it so every existing import
(`from .tools.tunnel import start_tunnel, stop_tunnel`) keeps working
unchanged.
"""

from __future__ import annotations

import subprocess
import time

import httpx

from .tunnel import _DEFAULT_ADMIN_API_URL, _POLL_INTERVAL_SECONDS, Tunnel, _ngrok_command


def start_tunnel(
    port: int,
    admin_api_url: str = _DEFAULT_ADMIN_API_URL,
    timeout_seconds: float = 10.0,
    command: list[str] | None = None,
    domain: str | None = None,
    log_path: str | None = None,
) -> Tunnel:
    """Launch `ngrok http <port>` and poll its local admin API
    (`admin_api_url`) until a public HTTPS tunnel is reported.

    `log_path`: ngrok's own stdout/stderr — connection errors, rate-limit
    rejections, edge-side failures — captured here instead of silently
    discarded (`None`, the default, keeps the old `DEVNULL` behavior, e.g.
    for tests using a placeholder `command`). Found necessary diagnosing a
    real cross-machine match where a peer's calls failed with "Client
    failed to connect" and this repo's own server log showed nothing at
    all for it, because the failure was happening at the tunnel/ngrok
    level — invisible until this exists.

    `admin_api_url` and `command` are both parameters, not hardcoded,
    specifically so a test can point the poll at a local stand-in server
    and launch a harmless placeholder process — the real `ngrok` binary
    isn't installed in every dev/CI environment, so the polling/parsing
    logic is tested independently of actually having it available (found
    necessary while writing the tests: without a `command` override, every
    test would hit the same immediate "ngrok not found" error the real
    absence produces, with no way to exercise the polling logic at all).

    `domain`: a free ngrok account gets one reserved static domain
    (`https://dashboard.ngrok.com/domains`) — without it, every fresh
    `ngrok http <port>` invocation is assigned a brand-new random public
    URL, so any restart (needed for any code change, since nothing here
    hot-reloads) forces re-sharing a new URL with the opponent. Passing
    `domain` builds `ngrok http --domain=<domain> <port>` instead, so the
    same public URL survives a restart. Ignored when `command` is given
    explicitly — an explicit command always wins.

    Refuses to even launch when something is already answering
    `admin_api_url`, on the real (`command is None`) path only — found
    live: an hours-old orphaned ngrok agent was still answering the admin
    API when a later `--tunnel` launch's own subprocess failed instantly
    (ERR_NGROK_334, "already online"), yet the polling loop below found
    the *old* agent's still-valid tunnel info before ever getting a
    chance to notice this invocation's own subprocess had died —
    silently declaring success using someone else's stale, unrelated
    tunnel. Scoped to `command is None` so every existing test (which
    always overrides `command` with a harmless placeholder, precisely
    because a real ngrok binary isn't installed everywhere) is
    unaffected — those deliberately point `admin_api_url` at their own
    already-running local stub.
    """
    if command is None:
        try:
            already_running = httpx.get(admin_api_url, timeout=1.0)
        except httpx.HTTPError:
            already_running = None
        if already_running is not None and already_running.status_code == 200:
            raise RuntimeError(
                f"another ngrok agent is already answering {admin_api_url!r} — "
                "kill it first (`ps aux | grep ngrok`) before starting a new one; "
                "this function can't tell its own tunnel apart from a stale one "
                "left over from an earlier run otherwise"
            )
        command = _ngrok_command(port, domain)
    # noqa justified: this handle must outlive the function — the
    # subprocess writes to it for the tunnel's whole lifetime, and
    # `stop_tunnel` closes it once that's over, not a `with` block here.
    log_file = (
        open(log_path, "a", encoding="utf-8")  # noqa: SIM115
        if log_path is not None
        else subprocess.DEVNULL
    )
    try:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)
    except FileNotFoundError as exc:
        if log_file is not subprocess.DEVNULL:
            log_file.close()
        raise RuntimeError(
            "ngrok is not installed or not on PATH — install it separately "
            "(https://ngrok.com/download); this repo only shells out to it, "
            "it is not a Python dependency"
        ) from exc

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            # ngrok exited before ever reporting a tunnel — found live via
            # ERR_NGROK_334 ("endpoint already online"): an hours-old
            # orphaned ngrok process had silently squatted on the domain,
            # so every subsequent launch here failed instantly and
            # invisibly, because polling the admin API alone can't tell
            # "no tunnel yet" apart from "this is someone else's stale
            # tunnel" — only checking the process's own exit proves *this*
            # launch never actually started one.
            if log_path is not None:
                log_file.close()
                detail = open(log_path, encoding="utf-8").read().strip()  # noqa: SIM115
            else:
                detail = "(no log captured — pass log_path to see ngrok's own output)"
            raise RuntimeError(
                f"ngrok exited before reporting a tunnel (exit code {process.returncode}) — "
                "often another ngrok process already holds this domain; check "
                "`ps aux | grep ngrok` and kill any stray one first. ngrok's own output:\n"
                f"{detail}"
            )
        try:
            response = httpx.get(admin_api_url, timeout=1.0)
            response.raise_for_status()
            for candidate in response.json().get("tunnels", []):
                if candidate.get("proto") == "https":
                    return Tunnel(
                        process=process,
                        public_url=candidate["public_url"],
                        log_file=log_file if log_file is not subprocess.DEVNULL else None,
                    )
        except httpx.HTTPError:
            pass
        time.sleep(_POLL_INTERVAL_SECONDS)

    process.terminate()
    if log_file is not subprocess.DEVNULL:
        log_file.close()
    raise TimeoutError(f"ngrok admin API at {admin_api_url!r} never reported a public HTTPS tunnel")
