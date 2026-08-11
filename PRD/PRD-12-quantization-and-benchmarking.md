# PRD 12 — Quantization, Latency Benchmark & Promotion-Gate Criteria

Status: **Done.** Built via `TODO12.md`, verified by `tests/unit/` (22 new tests, 100% coverage on every new/extended module), a live run of `scripts/watch_prd12_quantization.py`, and a `rule-auditor` pass. `ruff check` clean. Builds directly on `PRD-11-rl-training-simulator.md`'s checkpoint format, extending it rather than replacing it — a PRD-11-era checkpoint still loads unchanged (backward compatibility is checked, not assumed).

## Built & verified

`scripts/watch_prd12_quantization.py` trains a fresh checkpoint (same as PRD 11), quantizes it, and reports three real, measured numbers:

- **File-size reduction: 41%** (25,867 bytes float → 15,274 bytes int8, on a 262-state table).
- **Argmax-agreement rate: 90.84%** — a genuine, honest result, not the 100% a first guess might expect. This is exactly the number PRD 13's promotion-gate checkpoint exists to have a human read before accepting a quantized checkpoint (see "Also verify" below and `PLAN.md` §8's extended checkpoint table) — quantization is a real accuracy trade-off here, not a free lunch, and the milestone's job is to surface that honestly, not to make it look clean.
- **Latency: p50 12.2µs, p95 20.4µs, p99 39.9µs**, against a `response_timeout_seconds` budget of 30s — **p99 is ~752,000x under budget**, on 5000 realistic sampled states.

## Design — quantizing a Q-table honestly

Tabular Q-learning has no neural-network weights to quantize; the analogous operation is **post-training affine (int8) quantization of the Q-table's stored values** — the same category of technique PyTorch's post-training static quantization applies to weight tensors, done by hand to a dict of floats:

```
scale = (max_q - min_q) / 255          (1.0 if max_q == min_q, avoids div-by-zero)
stored_int8 = round((q - min_q) / scale) - 128
q ≈ (stored_int8 + 128) * scale + min_q
```

One `(scale, min_q)` pair per table, not per-row — kept simple for v1, named explicitly as a v1 simplification rather than silently assumed to be the only reasonable choice.

**Stated up front, and confirmed by the measured numbers above, not discovered late:** for tabular Q-learning, lookup is already O(1) dict access — microseconds regardless of quantization. The *latency* motivation the original ask cared about ("smaller/faster model... fit comfortably inside that budget with margin") is real in principle but **not the load-bearing benefit in the tabular fork**; the p99 numbers above (39.9µs, quantized) are barely different in kind from PRD 11's own unquantized numbers (~24µs, see `PRD-11-rl-training-simulator.md`'s milestone). File-size reduction and a real, reusable, honestly-measured quantization pipeline are the actual payoffs here. Where quantization's latency benefit *would* become load-bearing — a DQN doing a real forward pass — is named explicitly in the approved plan's fork note, not built here.

## Explicitly out of scope

- Any change to `RLCopBrain._pick_move`'s control flow — quantization changes what's *inside* the checkpoint (via `load_checkpoint`'s existing dequantize-on-load path), never the masking/fallback logic PRD 11 already built. Confirmed: `rl_cop_brain.py` has zero lines changed in this layer.
- Deployment, `police_class` wiring, or the Claude Code agents/skill — PRD 13's job entirely.
- Re-deriving rule-25/I7 compliance — that's `rule-auditor`'s job, referenced by PRD 13's promotion gate, not reimplemented here.
- Per-row (per-state) quantization scales, or any quantization scheme beyond the simple per-table affine one — a real refinement if the argmax-agreement number above were ever judged too low to accept, but not built speculatively here.

## Rules owned

No rule in Appendix E is newly triggered — this stays off the graded critical path, same as PRD 11. What this layer produces is the *evidence* behind the book's own Ch. 5.5 computational-fairness framing (quoted in this project's own `RULES.md`/`PLAN.md`): a real, measured latency number next to the real budget, not an assertion that "it's probably fast enough."

## Milestone

`scripts/watch_prd12_quantization.py` loads a freshly-trained (or PRD-11-produced) checkpoint, quantizes it, and reports all three numbers above into the script's own printed output — watched directly, with an explicit assertion (`p99_seconds < response_timeout_seconds`) that fails loudly if the latency claim ever stops holding, rather than a milestone that could silently pass on a stale printed number.

## Also verify (acceptance criteria, checked once built)

- Quantize-then-dequantize recovers every value within one quantization step (`scale`) of the original — checked directly, not just "looks close."
- A table where every value is identical (zero spread) quantizes and dequantizes without dividing by zero, and recovers the value exactly.
- An empty table quantizes/dequantizes to empty without crashing.
- **The argmax-agreement metric is proven to actually catch a real divergence**, not just pass by construction: `test_quantize.py::test_argmax_agreement_catches_a_real_divergence_from_a_deliberate_near_tie` constructs a table where a large overall spread forces a coarse quantization step, and a separate state's genuine-but-tiny margin (0.0005) collapses to a quantized tie — the agreement rate measurably drops (0.5, not 1.0) on that adversarial table while staying at 1.0 on a well-separated control table. Same "prove the test guards the thing" discipline `PRD-3`'s cycle-detection retrospective already established for this repo.
- A quantized checkpoint dequantizes transparently on load — `RLCopBrain` needs zero code change to consume either format.
- **A PRD-11-era checkpoint with no `quantization` key at all (not present-and-null — genuinely absent, simulating a file written before this layer existed) still loads correctly** — real backward compatibility, checked with a hand-written payload missing the key entirely, not just re-running PRD 11's own tests.
- `sample_realistic_states` draws from real `SelfPlayEnv` traces under random exploration (not a fixed policy, and not hand-picked edge cases), and is deterministic for a fixed seed.
- The benchmark's own percentiles are internally consistent (`p50 <= p95 <= p99`) and non-negative, and don't crash on zero samples.
- No new magic numbers: the quantization bit depth (int8 → 255 levels) is a stated design choice in the code and this PRD, not a config value, the same category as `_TIE_BREAK_ORDER`/`_CLAMP_RADIUS` already occupy in this repo — not Appendix F territory.

## New dependency

None. `training/quantize.py` and `training/benchmark_latency.py` are pure standard library (`time.perf_counter`, arithmetic) — same "zero new dependency" story PRD 11 established, still true after quantization.

## Builds on

PRD 11's `src/cop/reasoning/rl_checkpoint.py` (extended, not replaced — the `quantization` field is optional and defaults to the PRD-11 shape when absent) and `rl_state_encoding.py`'s `State` type. `src/cop/reasoning/rl_checkpoint_quant.py` (new, this layer) holds `QuantizationParams`/`dequantize_q_table` — split out to stay under the 150-line house cap once quantization support landed, and to give `training/quantize.py` one authoritative dequantize implementation to import rather than re-deriving the formula (the same "avoid two-copies drift" discipline PRD 11's own design already established for the checkpoint format itself). `training/checkpoint_io.py` gains `save_quantized()` alongside PRD 11's `save()`.
