"""Guardrails, permissions, and audit-trail layer (PRD 7) — the Gatekeeper
pattern's three accumulating protections (`token_bucket.py`, `quota_manager.py`,
`dos_detector.py`), composed by `gatekeeper.py::ApiGatekeeper`, plus league
bookkeeping (`league_ledger.py`). Nothing outside `tools/gmail_sender.py`
should call an external API without routing through `ApiGatekeeper.execute()`.
"""
