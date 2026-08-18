# Config-matching message — send to another team before a match

Fill in `<...>` before sending. Everything else is your real, current project data.

---

Hi team,

We'd like to set up a match (native protocol). To get our configs byte-identical
before we start (rule 11), here's our side:

- **Group id / name:** `yamanagh`
- **Cop repo:** https://github.com/Nagham1023/yamanagh-cop
- **Thief repo:** https://github.com/yamandahle/thief-peer
- **Members:** Nagham Manasra, Yaman Dahle

Could you send back:

1. Your **group id**, so we can build the shared config file as
   `config_<sorted-group-ids>_g<NN>.json` (rule 3 — named per game, reconstructable).
2. Your **cop repo** and **thief repo** URLs (both go into each side's own final
   report JSON — rule 49's four links).
3. Which sub-game numbers / how many games you'd like to play (up to Table 18's cap),
   and whether this is a warm-up or a counted series.
4. Your current git commit hash at match time (goes in the Step-0 declaration
   alongside ours).
5. Who's initiating Step-0 (`initiate_step0 = true` on exactly one side — we can
   take either role).

Once we've confirmed the shared config is byte-identical on both sides (rule 11) and
exchanged public MCP endpoints, we're ready to go.

Thanks,
yamanagh
