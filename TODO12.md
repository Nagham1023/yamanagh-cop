# TODO12 — Build Checklist for PRD 12 (Quantization, Latency Benchmark & Promotion-Gate Criteria)

Status: **Done.** Read `PRD/PRD-12-quantization-and-benchmarking.md` in full first — its "Built & verified" section records the real, measured milestone numbers (41% size reduction, 90.84% argmax-agreement, p99 ~752,000x under the response-timeout budget), not illustrative placeholders.

## 1. `src/cop/reasoning/rl_checkpoint_quant.py` — quantization format (new file)

- [x] `QuantizationParams` frozen dataclass (`dtype`, `scale`, `min_q`).
- [x] `dequantize_q_table(quantized, params) -> dict[State, dict[str, float]]` — the one authoritative decode implementation, imported by both `rl_checkpoint.py` (production, load-time) and `training/quantize.py` (its own `argmax_agreement_rate`), never re-derived twice.
- [x] Test: applies the documented affine formula exactly.
- [x] Test: empty table dequantizes to empty.
- [x] Test: every state/action key is preserved through dequantization.

## 2. `src/cop/reasoning/rl_checkpoint.py` — extended format

- [x] `save_checkpoint` gains an optional `quantization: QuantizationParams | None = None` — `None` (the PRD 11 shape) means `q_values` are already real floats; given, means they're int codes.
- [x] `load_checkpoint` dequantizes transparently via `raw.get("quantization")` — absent or `null` both mean "load as PRD 11 already did," no version branch needed.
- [x] Test: a quantized checkpoint dequantizes transparently on load, ranking preserved.
- [x] Test: a hand-written PRD-11-era payload with the `quantization` key **entirely absent** (not present-and-null) still loads correctly — real backward compatibility, not just re-running old tests unchanged.
- [x] File re-measured against the 150-line cap after the extension (109 lines) — no split needed beyond the new `rl_checkpoint_quant.py` file itself.

## 3. `training/quantize.py` — the encode direction (new file)

- [x] `quantize_q_table(q_values) -> (quantized, QuantizationParams)` — per-table affine int8, `scale=1.0` fallback on zero spread (avoids divide-by-zero, dequantizes exactly in that case).
- [x] `argmax_agreement_rate(original, quantized, params) -> float` — reuses `dequantize_q_table` from the production module rather than re-deriving the formula.
- [x] Test: round-trip recovers values within one `scale` step.
- [x] Test: a single-identical-value table dequantizes exactly.
- [x] Test: empty table doesn't divide by zero.
- [x] Test: agreement is 1.0 on a well-separated table.
- [x] **Found only by deliberately constructing an adversarial case, not assumed**: agreement rate is provably < 1.0 (0.5 exactly) on a table with one large-spread state and one genuine-but-tiny-margin near-tie elsewhere — the metric actually detects the failure mode it exists to catch, not just returns 1.0 on every table handed to it.
- [x] Test: agreement on an empty table is 1.0, not a crash.

## 4. `training/benchmark_latency.py` — the latency instrument (new file)

- [x] `sample_realistic_states(...)` — drives `SelfPlayEnv` with *random* legal moves (not a fixed policy), so sampled states cover a realistic spread rather than one deterministic trajectory or hand-picked edge cases.
- [x] `benchmark_pick_move_latency(brain, samples) -> LatencyMetrics` — times `_pick_move` directly with `time.perf_counter`, reports p50/p95/p99.
- [x] Test: sampling returns exactly the requested count and is deterministic for a fixed seed.
- [x] Test: percentiles are ordered (`p50 <= p95 <= p99`) and non-negative.
- [x] Test: zero samples produces zeroed metrics, not a crash.

## 5. `training/checkpoint_io.py` — `save_quantized()`

- [x] Added alongside PRD 11's `save()` — quantizes via `training/quantize.py` then writes via the production `save_checkpoint`, keeping `checkpoint_io.py` the one training-side entry point for both formats.
- [x] Test: round-trips through the production loader, ranking preserved.
- [x] Test: a quantized file is measurably smaller than the float original for a table with non-round values (the realistic worst case for JSON size).

## 6. `scripts/watch_prd12_quantization.py`

- [x] Trains a fresh checkpoint (same config as PRD 11), quantizes it, prints file-size delta and argmax-agreement rate, then benchmarks the *quantized* checkpoint's `_pick_move` latency over 5000 realistic sampled states against the real `response_timeout_seconds`.
- [x] Run and watched: 41% size reduction, 90.84% argmax-agreement, p50/p95/p99 = 12.2/20.4/39.9µs, p99 ~752,000x under the 30s budget. An explicit `assert` on the latency claim, not just a printed number a human might not check.

## Cleanup and final verification

- [x] Every new/changed file checked against the 150-line house cap: `rl_checkpoint_quant.py` 43, `rl_checkpoint.py` 109 (was 87, extended not split further), `quantize.py` 66, `benchmark_latency.py` 79, `checkpoint_io.py` 26.
- [x] `uv run ruff check` on every new/changed file — clean (two trivial import-order issues auto-fixed during the build).
- [x] `uv run pytest` on the new PRD-12 suite: 22 passed, 100% coverage on every new/extended module; full PRD-11+12 suite together: 65 passed.
- [x] `rule-auditor` pass — see `PRD/PRD-12-quantization-and-benchmarking.md`'s Status line for the result.
- [x] `git log --all --full-history -- '*credentials*' '*token.json*' '*.env'` — still empty.
- [x] `TODO.md`'s own master checklist — PRD 12 row added.
- [x] `PRD/PRD-12-quantization-and-benchmarking.md` written, built, and verified against this checklist; commit.
