# Ready Template — std_v1 external interop protocol

**Status: template, fill in per opponent before sending.** This is the Section-16 Ready
template from `NEXT_OPPONENT_INTEROP_GUIDE_PUBLIC.md`, plus one addendum block this repo
adds on top of the spec's own text. Send the filled-in version to each external opponent
(over whatever channel you agreed — email, issue, chat) before the Section-15 compatibility
test and again before the counted series, since the tunnel URL and commit hash change per
launch.

Two placeholders below (`<...>`) can only be filled at match time; the rest — repos, this
side's own protocol behaviour — are already fixed by what `src/cop/std_v1/` actually does.

---

## Section 16 Ready block

```
READY

Group:                <OUR_GROUP_ID>                    # TODO: our real league group id
Members:               <OUR_TEAM_MEMBERS>                 # TODO
Cop repo:              https://github.com/Nagham1023/yamanagh-cop
Thief repo:            https://github.com/yamandahle/thief-peer
Cop runtime SHA:       <git rev-parse HEAD, this repo, at launch time>
Thief runtime SHA:     <same, from the paired thief-peer repo>
Public MCP endpoint:   <https://ACTIVE-TUNNEL-URL/mcp>     # from `--tunnel`'s printed URL; re-check reachable (Section 8) immediately before sending
Starting role:         <cop | thief>                        # complement of the opponent's own declared starting role
Agreed game_id:        <OUR_GROUP_ID>-vs-<THEIR_GROUP_ID>   # sorted per Appendix B — whichever group id sorts first goes first

14 signed terms match Appendix A (values and JSON types):         YES  (config/interop_spec_terms.json, byte-checked)
35-step survival semantics:                                       YES
Capture-claim = Cop post-move cell every turn, conditions A/B/C:   YES
Transport /mcp, no required bearer authentication:                YES
Canonical consensus object + SHA-256 (Section 11):                YES
Final audit + explicit series_consensus digest exchange:          YES
Server stays alive through the final audit; graceful shutdown:    YES
Public endpoint externally reachable (curl-verified):              YES  (verify again immediately before sending — Section 8's own warning: tunnels are dynamic)
```

---

## Addendum: two explicit declarations, not covered by the 14 signed terms

Two real cross-team incidents documented in a public league conformance kit
(`copthief-league-protocol`, `docs/WARNINGS.md` §6a and the game_uid case study) both share
the same shape: two implementations that were each internally consistent, computed
byte-identical hashes on everything the wire protocol actually carries, and *still*
disagreed — because the disagreement lived in an interpretation neither side had put in
writing. Stating both of ours here, before either side has played a move, costs nothing and
closes that exact failure mode.

**1. Series tie-bonus interpretation.** We compute the series tie bonus as: `+2` added once
to each side's cumulative total, applied only when the six sub-games' raw cumulative totals
(before the bonus) are equal — never per-sub-game, never replacing the total. This is the
book's own Appendix ו / Table 17 `tie_score` value (FIXED at `2`, "score to each side when
the cumulative game... ends in a tie") and matches this spec's own Section 6 worked example
(45 + 45 → 47 + 47). If your own implementation resolves the tie differently, please say so
now — Section 6 is [MATCH], and a silent difference here only surfaces after all six
sub-games are already played.

**2. Scent model.** We implement the book's own multiplicative decay-then-deposit model
(ch. 4.5's negotiation ceremony): `τ_next = min(0.9, max(0, (1 − ρ)·τ_old + δ))`, ρ = 0.10,
with the fixed 5×5 radial kernel from Figure 4 (centre 0.90; edges 0.62 / 0.42 / 0.20 / 0.14 /
0.04 per Appendix E of this spec). This is locked implicitly through the 14 signed terms'
own `smell_grid_size` / `decay_per_step` / `emit_intensity` / `min_center_intensity` values
and this spec's own fixed formula (Section 4/Appendix E) — no separate hash exchange is
needed since the formula itself isn't configurable, but we're stating the concrete worked
example here anyway, the same way ch. 4.5 itself recommends: a cell at the emission centre
carries τ = 0.9; after one full turn's decay at ρ = 0.10 with no fresh deposit, it carries
0.81.

---

## Before sending

- [ ] Fill in `<OUR_GROUP_ID>` / `<OUR_TEAM_MEMBERS>` with the real, agreed values.
- [ ] Re-run `curl -sS -o /dev/null -w '%{http_code}\n' https://<tunnel>/mcp` — Section 8's
      own reachability check — immediately before sending, not from an earlier session.
- [ ] Confirm the opponent's own Ready template states a complementary starting role and an
      identical `game_id`.
- [ ] Run the Section-15 non-counted compatibility test against their live endpoint before
      treating this as ready for a counted series.
