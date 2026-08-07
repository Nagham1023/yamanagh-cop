"""Commit-Reveal primitives (PRD 6, Table 3's ch. 5 mapping). Only
`commit_payload.py`'s canonical State serializer exists here so far —
frozen ahead of PRD 6 itself per `PRD-6-prep-commit-payload-spec.md`, so
PRD 6's hashing code has a single, already-tested primitive to build on
rather than re-deriving the float/ordering trap from scratch.
"""
