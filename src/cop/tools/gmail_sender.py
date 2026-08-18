"""OAuth 2.0 send-only Gmail delivery (Appendix A, rule 30 **[FATAL]**).
`SCOPES` is a module-level constant, deliberately narrow — least-privilege
(Appendix A §1.3): send-only, never read/modify.

Rule 34 (**[FATAL]**): the report is an *attached* JSON file, never body
text — a deliberate deviation from ch. 9.3's own illustrative `MIMEText`
sketch (`PRD-7-reporting-shell.md`'s Design Question 10), which only
demonstrates the OAuth mechanics, not the actual required report shape.

Every call here is a thin, direct function — no retry, no rate-limiting
(that's `policy/gatekeeper.py::ApiGatekeeper.execute()`'s job, wrapping
these at the call site, not inside this module — `tools/` stays a thin
transport layer, rule 3/I2). `email_mode` (`config/game.toml`'s
`[email].mode`) is handled here and only here: `"draft"` builds the real
message but stops short of calling Gmail at all, `"send"` performs the
real send — callers (`tools/report_bundle.py`, end-of-game orchestration)
never need to branch on it themselves.

`"draft"` is *not* a real Gmail draft (`users().drafts().create()`) —
that endpoint needs the broader `gmail.compose` scope, which rule 30
forbids (send-only, no exceptions; confirmed against a public league
conformance kit's own warning: "Send-only scope cannot create drafts").
Instead it writes the exact constructed message to a local `.eml` file a
human can open directly in any mail client to inspect — same "never
touches the Gmail API" guarantee draft mode always had, just no longer
silent about it.
"""

from __future__ import annotations

import base64
import json
import re
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Least-privilege scope (Appendix A §1.3): send only, never read or modify.
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

DRAFT_PREVIEW_DIR = "logs"


def get_service(token_path: str = "token.json") -> Any:
    """Reuses `token.json` (created by the one-time consent flow, Appendix A
    §1.5) — no browser interaction here, this is the fully-automatic path
    every game after the first uses."""
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build("gmail", "v1", credentials=creds)


def build_message(to_addr: str, subject: str, body: str, attachments: dict[str, dict]) -> MIMEMultipart:
    """`attachments` maps a filename to its JSON-serializable payload —
    each becomes its own `application/json` attachment part; `body` stays
    a short, human-readable summary, never the report itself (rule 34)."""
    message = MIMEMultipart()
    message["to"] = to_addr
    message["subject"] = subject
    message.attach(MIMEText(body))
    for filename, payload in attachments.items():
        part = MIMEApplication(
            json.dumps(payload, sort_keys=True).encode("utf-8"), _subtype="json"
        )
        part.add_header("Content-Disposition", "attachment", filename=filename)
        message.attach(part)
    return message


def send_message(service: Any, message: MIMEMultipart) -> dict:
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def write_draft_preview(message: MIMEMultipart, out_dir: str | Path = DRAFT_PREVIEW_DIR) -> Path:
    """`email_mode="draft"`'s real behavior — see the module docstring for
    why this is a local `.eml` file rather than a real Gmail draft. Written
    with `message.as_string()` (the exact bytes a real send would have
    based `raw` on), so opening it in any mail client shows precisely what
    would have gone out — never approximated or re-derived."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe_subject = re.sub(r"[^A-Za-z0-9_-]+", "_", message["subject"] or "draft").strip("_") or "draft"
    draft_path = out_path / f"draft_{safe_subject}.eml"
    draft_path.write_text(message.as_string(), encoding="utf-8")
    return draft_path


def send_report(
    service: Any,
    to_addr: str,
    subject: str,
    body: str,
    json_bundle: dict,
    attachment_filename: str,
    email_mode: str = "send",
    draft_dir: str | Path = DRAFT_PREVIEW_DIR,
) -> dict:
    """A single-file report. `email_mode="draft"` writes a local preview
    (see `write_draft_preview`) instead of calling Gmail at all. `draft_dir`
    defaults to the bare `"logs"` relative path for direct/CLI callers;
    end-of-game orchestration passes its own already-computed `reports_dir`
    instead, so a draft preview lands next to that match's other artifacts,
    not wherever the process happened to be launched from."""
    message = build_message(to_addr, subject, body, {attachment_filename: json_bundle})
    if email_mode == "draft":
        return {"draft_path": str(write_draft_preview(message, draft_dir))}
    return send_message(service, message)


def send_report_bundle(
    service: Any,
    to_addr: str,
    subject: str,
    body: str,
    attachments: dict[str, dict],
    email_mode: str = "send",
    draft_dir: str | Path = DRAFT_PREVIEW_DIR,
) -> dict:
    """The real end-of-game call (ch. 9.3.3): all four Table 20 files
    attached to **one** message — `attachments` already carries their
    correct names (`declaration_<game_id>.json`, etc.; `report_bundle.py`
    owns that naming, not this module). `email_mode="draft"` writes a
    local preview (see `write_draft_preview`) instead of calling Gmail;
    `draft_dir` — see `send_report`'s own docstring."""
    message = build_message(to_addr, subject, body, attachments)
    if email_mode == "draft":
        return {"draft_path": str(write_draft_preview(message, draft_dir))}
    return send_message(service, message)
