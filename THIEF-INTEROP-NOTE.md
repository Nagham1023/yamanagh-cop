# Interop test results — 2026-08-09

Ran a real local match: `uv run python -m cop peer` (this repo) against `uv run python -m thief_peer run` (yours, `opponent_protocol = "cop_v1"`), both on `127.0.0.1`. Short version: **the wiring itself works** — Step-0 negotiation, config-identity check, and ten real committed-and-revealed turns all went cleanly, against your actual code, not a stub. Two things need attention before either of us risks a real *counted* game on this, both of which your own `docs/PRD_9_cop_interop.md` already names as known/deferred — this is just the first time either of them has been observed actually happening, not a new report.

## 1. Capture claims never get a response

I claimed a capture at step 10 (belief target `(4,5)`) via `receive_capture_claim`. Your side acked receipt, as documented, but `receive_capture_response` never came back. My side waited the full `response_timeout_sec` (30s, from the shared config) and then technical-lost:

```
{"event": "capture_claimed", "step": 10, "thief_pos": "Position(col=4, row=5)", ...}
{"event": "technical_loss", "exception_type": "DeadlineExceededError", "reason": "opponent did not respond within 30.0s", "state": "AWAITING_REVEAL", ...}
```

Concretely, in the same run, my side recorded a technical loss (0-0) while your own `results/result_yamandahle-thief-vs-dev-team.json` independently recorded:

```json
{"final_result": {"winner_group": "Yamandahle-Thief", ...}}
```

That's two reports of the same match already disagreeing — rule 35 voids a game and zeroes both sides on exactly this condition. Whether my capture claim was actually correct is almost beside the point; right now there's no path for it to ever be confirmed *or* denied from your side, so every claim I make will time out the same way.

## 2. Final Reveal / mutual audit never runs on your side

Confirmed directly from your own `results/log_yamandahle-thief-vs-dev-team_g01.json`:

```json
"audit": {"passed": false, "self_audited_by_opponent": {"verified_steps": 0, ...}, "opponent_audited_by_me": {"verified_steps": 0, ...}}
```

Zero verified steps in either direction, even though the match itself ran cleanly up to that point. I think this is the same thing your `cop_send_final_reveal` being defined-but-never-called describes — matches what I'd expect if `finalize_match` genuinely skips the exchange in `cop_v1` mode.

## What worked cleanly, for the record

- Step-0: real negotiation, `config_sha256` match confirmed (`sha256sum` on both our copies of `config_dev_g01.json`/`game.json` is identical), scent-lock hash match, both sides logged success.
- 10 real turns: commit → reveal → scent-share round trips, all correct shape, no schema errors.
- My own replay verifier (`uv run python -m cop replay --log <path>`) confirms steps 1-9 `Verified OK` cryptographically — genuinely checked, not just "didn't crash." Step 10 shows `TAMPERED`, but only because that turn's own nonce never got revealed once the capture-response wait timed out mid-turn — an honest artifact of an incomplete match, not a real tamper.
- One tool-shape mismatch, cosmetic only: your `receive_barrier_declaration` acks `{"ok": true}`, mine acks `{"acknowledged": true}` — my client never inspects the ack content so this didn't cause any issue, but worth aligning for exactness if you're touching that code anyway.

## Recommendation

Both gaps look like real, addressable follow-ups on your side rather than anything ambiguous, and I don't think either is a big lift given the machinery (the tool, the outbound call) already exists — it's the auto-triggering that's missing. Happy to run this exact test again once you've got a fix in for either one. Until then I'd treat any match between us as a warm-up only, not a counted one — a real counted match today would likely end in a voided, zero-zero result for both of us over the report mismatch in #1 alone.

One small thing on my own side, found by the same run: my `report_game()` doesn't yet handle your process disappearing mid-Final-Reveal gracefully (it happened here because your own run crashed first, on an unrelated Gmail auth error in my local test setup — not a real match condition) — raw traceback instead of a clean exit. Fixing that on my end regardless, not something you need to do anything about.

Full trace of both sides' logs available if useful — happy to send the raw files.
