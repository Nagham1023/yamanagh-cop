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
message but stops short of calling Gmail's `send`, `"send"` performs it —
callers (`tools/report_bundle.py`, end-of-game orchestration) never need
to branch on it themselves.
"""

from __future__ import annotations

import base64
import json
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Least-privilege scope (Appendix A §1.3): send only, never read or modify.
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


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


def send_report(
    service: Any,
    to_addr: str,
    subject: str,
    body: str,
    json_bundle: dict,
    attachment_filename: str,
    email_mode: str = "send",
) -> dict | None:
    """A single-file report. `email_mode="draft"` builds the message but
    returns `None` without calling Gmail at all."""
    message = build_message(to_addr, subject, body, {attachment_filename: json_bundle})
    if email_mode == "draft":
        return None
    return send_message(service, message)


def send_report_bundle(
    service: Any,
    to_addr: str,
    subject: str,
    body: str,
    attachments: dict[str, dict],
    email_mode: str = "send",
) -> dict | None:
    """The real end-of-game call (ch. 9.3.3): all four Table 20 files
    attached to **one** message — `attachments` already carries their
    correct names (`declaration_<game_id>.json`, etc.; `report_bundle.py`
    owns that naming, not this module)."""
    message = build_message(to_addr, subject, body, attachments)
    if email_mode == "draft":
        return None
    return send_message(service, message)
