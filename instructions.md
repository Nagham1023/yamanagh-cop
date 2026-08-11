# instructions.md — running a real match and finishing submission

Everything in this file needs a human: a browser, a real Google account, a real ngrok account, a real conversation with the thief-repo team, a machine with an actual display, and the Moodle site. Nothing here can be automated by an AI agent working inside this repo — that's exactly why it's written down as a checklist instead of a script.

Work through the sections in order. Each one says what "done" looks like before you move to the next.

---

## 0. Where things stand right now

Confirmed working, as of PRD 10 (commit history has the details):

- `uv sync`, `uv run pytest` (batched — see §1), `uv run ruff check .`, `uv run python .claude/skills/spec-guard/scripts/check_config.py config/shared/config_dev_g01.json` — all green.
- `uv run python -m cop peer` and `uv run python -m cop replay --log <path>` both exist and work (two real local processes reach a full negotiated, played, and reported match through the CLI itself — see §6).
- `report_game()` attaches all four Table 20 files (`declaration_`, `config_`, `log_`, `result_`) to one email, in `email.mode = "draft"` (nothing actually sent yet — see §3).
- `WIRE-CONTRACT.md` is a complete draft but its own Status log still says **"not yet sent to the teammate"** and **"not yet confirmed compatible against a real thief-repo peer"** — §2 below is the first real gap to close.

Not done, and not something this session could do for you: real Gmail credentials, a real ngrok account, an actual conversation with the thief-repo team, a display to screenshot a GUI, or anything on Moodle.

---

## 1. Pre-flight (confirm your own machine matches this session's starting point)

```bash
uv sync
uv run pytest tests/unit -q          # run in 3-5 batches if it's slow on your machine — see note below
uv run pytest tests/integration -q
uv run ruff check .
uv run python .claude/skills/spec-guard/scripts/check_config.py config/shared/config_dev_g01.json
git log --all --full-history -- '*credentials*' '*token.json*' '*.env'   # must print nothing
```

**Note on batching:** the full unit suite spins up dozens of real local HTTP servers (every bilateral test uses two real `Orchestrator`s) and can be slow or flaky as one single `pytest` invocation depending on your machine. If it hangs, split alphabetically into 3-5 groups and run each separately — this was already necessary during development and isn't specific to your machine.

If any of the above isn't clean, stop and fix it before continuing — everything below assumes a genuinely green baseline.

---

## 2. Coordinate with the real thief-repo team

This has to happen before any wire is opened between the two processes.

1. **Send them `WIRE-CONTRACT.md`** as-is. It's a complete proposal of every MCP tool this repo's server exposes (`receive_reveal`, `share_scent_map`, `receive_commit`, `receive_step0`, ...) — they need to build a client that matches it, or tell you where their own proposal differs.
2. **Agree the byte-identical shared config file** (rule 11, **[FATAL]** — "Config voided for broken symmetry" if this isn't exact). Whoever's config is used, both sides must end up with the literal same bytes on disk. Verify it yourself:
   ```bash
   uv run python .claude/skills/spec-guard/scripts/check_config.py --identical config/shared/config_dev_g01.json path/to/their/copy.json
   ```
   Also re-run the parameter check on whatever the final agreed file is — `check_config.py <path>` — before trusting it.
3. **Agree who sets `initiate_step0 = true`.** Exactly one side. This is a coin-flip/convention decision with the other team, not something either side can unilaterally decide — the passive side will otherwise sit in `await_passive_step0` until `step0_wait_seconds` expires and reach a clean `TECHNICAL_LOSS`.
4. **Exchange each side's real MCP server URL** — this becomes `[network].opponent_url` in your own `config/game.toml` (§5). If you're both behind ngrok, this is the `https://*.ngrok-free.app/mcp`-shaped URL from §4, not a `127.0.0.1` address.
5. **Confirm the scent-model ceremony (ch. 4.5).** `WIRE-CONTRACT.md`'s own section on this recommends sending them `src/cop/memory/scent.py` directly, not just a written description — two independently-typed implementations of the same formula are exactly the kind of thing that silently drifts. This is now moot for the *cryptographic* lock itself (PRD 9's `negotiate_step0` catches a real mismatch automatically at match start either way) but still worth doing so a real mismatch doesn't cost you a whole warm-up game to discover.

**Done when:** both teams have a written (email/Slack/whatever) confirmation of the wire contract, the identical config file, who initiates, and each other's real URLs.

---

## 3. Gmail OAuth (one-time, needed before `email.mode = "send"` works)

`config/game.toml`'s `email.mode` is currently `"draft"` — the report gets built correctly but never actually sent. You need real credentials before switching it to `"send"`.

1. **Google Cloud Console** (`console.cloud.google.com`):
   - Create a project (or reuse one).
   - APIs & Services → Library → enable **Gmail API**.
   - APIs & Services → OAuth consent screen → External (or Internal if using a Workspace account) → fill the minimum required fields → add your own Google account as a test user if the app stays in "Testing" mode.
   - APIs & Services → Credentials → Create Credentials → OAuth client ID → Application type **Desktop app** → Create.
   - Download the JSON → save it as `credentials.json` in this repo's **root** (already `.gitignore`d — confirmed in §1's secret sweep; never commit it).
2. **Run the one-time consent flow:**
   ```bash
   uv run python scripts/setup_gmail_oauth.py
   ```
   This opens a browser, asks you to sign in and approve the **send-only** Gmail scope (rule 30, **[FATAL]** if this is ever wider), then writes `token.json` next to `credentials.json`. You will not see this browser prompt again — every match after this reuses `token.json` automatically.
3. **Confirm both files are ignored:**
   ```bash
   git status   # credentials.json and token.json must NOT appear
   ```

**Done when:** `token.json` exists in the repo root, `git status` doesn't show either credential file, and you're ready to flip `email.mode` in §5.

---

## 4. ngrok (needed for a real cross-machine match — rule 10)

1. Install ngrok: https://ngrok.com/download (or your OS package manager).
2. Sign up for a free ngrok account, copy your authtoken from the dashboard.
3. One-time setup:
   ```bash
   ngrok config add-authtoken <your-authtoken>
   ```
4. Smoke-test it against this repo directly — `run_as_server(use_tunnel=True)` is exercised by:
   ```bash
   uv run python scripts/watch_prd5_tunnel.py
   ```
   Watch for a real `https://*.ngrok-free.app` URL printed and a successful round trip through it. If ngrok isn't on `PATH` or the authtoken isn't set, `tools/tunnel.py` raises a clear, specific error naming the problem — read it, don't guess.

**Done when:** the smoke-test script prints a real public HTTPS URL and completes without error.

---

## 5. Real `config/game.toml` edits

This file is **private, hand-edited, never negotiated, never committed with real secrets in it** — but its non-secret values do need to be real before a real match. Edit `[network]` and `[email]`:

```toml
[network]
my_port = 8801                                   # whatever port you're exposing via ngrok
opponent_url = "https://<their-real-tunnel>.ngrok-free.app/mcp"   # from §2 step 4
turn_timeout_seconds = 180
initiate_step0 = true                            # or false — from §2 step 3, exactly one side is true
step0_wait_seconds = 300                          # raise this if you expect a slow handshake with the other team

[email]
recipient = "rmisegal+uoh26finalgame@gmail.com"   # confirm this is still the correct grading address
mode = "draft"                                    # flip to "send" only once you're ready for a real send (§3 must be done first)
```

Also confirm `[game].sub_game_number` is correct for the specific match you're about to run — it feeds the log/config/declaration/result filenames directly (`config_<game_id>_g<NN>.json`, etc.), so a stale number here means a real match's report lands under the wrong sub-game's filename.

**Done when:** `opponent_url` is a real reachable URL (not `127.0.0.1`), `initiate_step0` is agreed with the peer team, and you've decided whether this run should send for real or stay in draft.

---

## 6. Running a match

**Start ngrok first** (or pass `--tunnel` and let `run_as_server` start it for you — same underlying call):

```bash
uv run python -m cop peer --tunnel
```

- **Warm-up (uncounted) run** — no `--counted` flag. Do this first against a new opponent, always — it's the protocol shakeout PLAN.md's own risk register expects, and it costs nothing (rule 52 only limits *counted* games per opponent).
- **Real counted run** — add `--counted`:
  ```bash
  uv run python -m cop peer --tunnel --counted
  ```
  Only do this once per opponent (rule 52, **[FATAL]** if repeated — `--counted` wires straight into `league_ledger.record_counted_game`, which will refuse a second one for the same `opponent_id` if you try).
- **Local smoke test with no real peer at all** — run two terminals on the same machine, one `config/game.toml` with `initiate_step0 = true` pointed at `127.0.0.1:<other-port>`, the other `false`, neither passing `--tunnel`. This is exactly what this session's own CLI tests do (`tests/unit/test_cli_peer.py`) and is the cheapest way to confirm your own local setup works before involving a real opponent.

Each run writes `logs/log_<game_id>_g<NN>.json` — that's the file §8 and the replay verifier both need.

**Done when:** the process exits cleanly, prints (or you can confirm from the log) a real `Outcome`, and — if `email.mode = "send"` — you receive the report email with all four attachments.

---

## 7. Capturing the three still-open screenshots

`README.md` and `TODO.md` both name these exact files, still missing:

- `screenshots/live_gui_verified.png`
- `screenshots/replay_verified_ok.png`
- `screenshots/replay_tampered.png`

The `screenshots/` directory doesn't exist yet — create it (`mkdir screenshots`).

Both GUIs are real Tkinter windows (stdlib, no browser) — they need an actual display. **If you're on WSL2 with WSLg** (default on a recent Windows 10/11 install with WSL), Tkinter windows already forward straight to your Windows desktop with no extra setup — just run the commands below and use the normal Windows Snipping Tool (`Win+Shift+S`) or `PrtScn` to capture the window. If you're on plain Linux with a desktop already running, it just works. If you're on a truly headless Linux box with no display at all, set up a lightweight X server first (e.g. `Xvfb` + a VNC viewer, or just run this step from a machine that has a real desktop — it's a one-time task, not worth automating for three screenshots).

```bash
# Live GUI — belief-map rendering across a few real turns:
uv run python scripts/watch_prd7_live_gui.py
# → screenshot the window while it's open, save as screenshots/live_gui_verified.png
```

```bash
# Replay Viewer — both the honest and tampered cases:
uv run python scripts/watch_prd7_replay.py
```
This script calls `window.close()` right after each case to move on to the next — pause it before that happens (add a `input("press enter to continue")` right before each `.close()` call, temporarily, or just comment the `.close()` calls out for this one run) so the window actually stays open long enough to screenshot. Capture the honest run as `screenshots/replay_verified_ok.png` and the tampered run as `screenshots/replay_tampered.png`.

Alternatively, run a real match via `uv run python -m cop replay --log <path-from-§6> --gui` — same `ReplayViewerWindow`, using a genuine match you just played instead of the demo script's synthetic one.

**Done when:** all three PNGs exist under `screenshots/`, referenced correctly from `README.md` (it already has the right filenames in its own `TODO:` marker — just remove that marker once the files exist).

---

## 8. Verifying a completed match

```bash
uv run python -m cop replay --log logs/log_<game_id>_g<NN>.json
```

Prints `Overall: Verified OK` (exit code `0`) on a genuine, untampered match. Add `--gui` to also see it in a window (§7's third screenshot can come from this). If you ever get `TAMPERED` or an error about a missing `nonces_revealed` event on a match you expected to be clean, treat that as a real finding, not a fluke — either the log was genuinely altered, or the match never reached Final Reveal (check whether `report_game()` actually completed for that run).

---

## 9. Final submission checklist (rules 41-45)

- [ ] **Rule 41 — tag the submission.** Once everything above is done and you're ready to freeze the version the lecturer inspects:
  ```bash
  git tag -a v1.0-submission -m "Final submission"
  git push origin v1.0-submission
  ```
- [ ] **Rule 42 — academic report.** Already written, inside `README.md` (per its own ch. 9.4.2 sections — model description, dilemmas, strategy). The one open item is the three screenshots from §7; once those exist, remove the `TODO:` marker in `README.md` that currently names them.
- [ ] **Rule 43 — Moodle submission form.** Download it from the course's Moodle page, fill it in, save as PDF. Don't alter or move any existing fields.
- [ ] **Rule 44 — individual submission.** Every team member submits on Moodle separately — a single shared submission doesn't count for members who didn't personally submit.
- [ ] **Rule 45 — team code.** Choose one unique eight-character code (no spaces) and use it identically everywhere it's asked for (Moodle form, any report metadata) — this is what lets automated report attribution work at all.
- [ ] **Rule 31/52 — opponent minimum, one counted game each.** Confirm you've played the minimum required number of *different* opponents, each exactly once for the counted slot (warm-ups don't count toward or against this).
- [ ] **Rule 37/38 — honest game-count declaration.** Whatever you declare as "games played so far" at the start of each match must be accurate — `league_ledger.counted_game_count()` is this repo's own source of truth for your own side of that number.
- [ ] **Self-score write-up (rule 55).** Code quality only — not the league result. A short, honest note on what you'd grade in your own code if you were reviewing it cold.

**Done when:** every box above is checked, in order — don't tag the submission (rule 41) before the screenshots and any last-minute fixes are actually in the commit you're tagging.
