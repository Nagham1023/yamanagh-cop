"""One-time Gmail OAuth consent flow (Appendix A §1.5, referenced by
`tools/gmail_sender.py::get_service`'s own docstring but never built until
now) — run this once per machine to produce `token.json`, which every
real `email.mode = "send"` match afterward reuses automatically, with no
further browser interaction.

Reuses `gmail_sender.SCOPES` directly rather than redefining it — one
source of truth for the send-only scope (rule 30 **[FATAL]**): this
script must never request more than `gmail.send`, and a copy-pasted scope
list is exactly the kind of thing that quietly drifts.

Prerequisites (see `instructions.md` for the full walkthrough):
  1. A Google Cloud project with the Gmail API enabled.
  2. An OAuth 2.0 Desktop-app client ID, downloaded as `credentials.json`
     into this repo's root (already `.gitignore`d — never commit it).

Run:
    uv run python scripts/setup_gmail_oauth.py

Opens a browser for the one-time consent screen, then writes `token.json`
(also `.gitignore`d) next to it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from cop.tools.gmail_sender import SCOPES

REPO_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = REPO_ROOT / "credentials.json"
TOKEN_PATH = REPO_ROOT / "token.json"


def main() -> None:
    if not CREDENTIALS_PATH.exists():
        print(
            f"error: {CREDENTIALS_PATH} not found.\n"
            "Download an OAuth 2.0 Desktop-app client ID from the Google Cloud "
            "Console (APIs & Services -> Credentials) and save it there as "
            "credentials.json — see instructions.md for the exact console steps.",
            file=sys.stderr,
        )
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    credentials = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Consent granted — {TOKEN_PATH} written. Real 'send' mode is ready to use.")


if __name__ == "__main__":
    main()
