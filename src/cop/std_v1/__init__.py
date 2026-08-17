"""The P2P Cop-Thief Match Interoperability Specification adapter — a
third wire protocol, distinct from this repo's own PRD 1-16 native
protocol (`tools/mcp_server*.py`, `integrity/commit_reveal.py`), built
specifically to play against an *unpaired* team's own independently-built
Cop/Thief agents (rule 31/52's "play several distinct teams" requirement).
This repo plays the Cop role only, mirroring `thief-peer`'s own
`interop/std_v1/` package for the Thief role — the two were designed
together so the crypto formulas and wire shapes match bit-for-bit; see
`std_v1/crypto.py`'s own docstring for the exact reasons this cannot
reuse `integrity/commit_reveal.py`.
"""
