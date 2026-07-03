# RunForLife — Friend Onboarding Design

**Date:** 2026-07-02
**Status:** DRAFT — awaiting user review (scope assumed "Full"; see Open Questions)
**Goal:** A friend can install the plugin on their own machine, be **asked questions**, and end up with a working, personalized coach — no hand-editing of files or code.

> Layer 3 (§4–§8) was refined by a CRO workflow (onboarding-cro, signup-flow-cro, form-cro, marketing-psychology → synthesis), with agents verifying claims against the codebase.

---

## 1. Why this isn't possible today

Three blockers, in dependency order. The wizard (the fun part) can't work until the first two are done.

1. **Hard-wired paths** — 22 files under `runforlife-coach/` contain the literal path `/Users/tezueshvarshney/work/test/runforlife`; every command/skill runs `cd /Users/tezueshvarshney/... && uv run …`. On a friend's laptop those `cd` into a missing directory. (The `pre_tool_use` hook already uses `${CLAUDE_PLUGIN_ROOT}` — the pattern exists, it's just not applied to commands.)
2. **Athletes are a hardcoded enum** — `config.py: USERS = ("tezuesh","kakul")`, echoed in ~60 files: `auth.py::main()` rejects any handle not in that tuple, all 10 command playbooks say the handle "MUST be exactly `tezuesh` or `kakul`", `--user {tezuesh,kakul,all}` argparse `choices=`, the write-guard hook, agent prompts. **A friend's handle is refused everywhere → activation is literally 0 until this is fixed.**
3. **No interactive setup** — `scripts/athlete_init.py` writes a *skeleton* profile ("flesh out by hand") whose shape has drifted from what the playbooks actually read; creds are `.env` vars. Nothing asks anything.

## 2. Scope (assumed: Full)

Deliver all three layers so a friend goes **install → asked questions → working coach**, built in dependency order:

- **Layer 1 — Portability** (prerequisite)
- **Layer 2 — Dynamic athletes** (prerequisite, and the #1 P0)
- **Layer 3 — `/onboard` wizard** (the ask; CRO-refined below)

## 3. Layers 1 & 2 (prerequisites)

### Layer 1 — Portability
- Replace the 22 absolute-path refs with `${CLAUDE_PLUGIN_ROOT}/..` (plugin root = `runforlife-coach/`, so repo root = its parent). Commands become `cd ${CLAUDE_PLUGIN_ROOT}/.. && uv run python -m …`.
- **Packaging reality:** the plugin is NOT self-contained — it needs the sibling `src/runforlife` package + `pyproject.toml` + a `uv` env. "Install" = clone repo, add the local marketplace (`.claude-plugin/`), `uv sync`. Documented in README; `/onboard` preflights it.

### Layer 2 — Dynamic athletes (the gate — P0 before everything)
- `config.py`: replace `USERS` tuple with `list_athletes()` (reads `~/.runforlife/athletes/*/` dirs that contain a valid `profile.json`) + `is_valid_athlete(name)`. `RUNFORLIFE_HOME` override already supports sandboxed tests.
- De-enum every gate: `auth.py::main()`, `sync/nightly.py` (`--user` free string validated against `list_athletes()` + the `all` sentinel), `skills/data/garmin_auth.py` input_schema enum, the 10 command playbooks' "MUST be exactly tezuesh|kakul" checks, and `pre_tool_use.py`'s write-guard (compare against active + listing, not literals).
- Credentials keep `GARMIN_EMAIL_<HANDLE>` / `GARMIN_PASSWORD_<HANDLE>` (uppercased) — already name-agnostic.
- **Smoke-test `/daily-plan <newhandle>`** as part of `/onboard`'s final self-validate — this is how we prove the gate is truly gone.

---

# Layer 3 — `/onboard` (CRO-refined)

## 4. Grounding facts that shape the wizard (verified in-repo)

- **The gate (Layer 2) is P0-before-everything.** A flawless playbook still yields a coach that answers every command "Invalid athlete." Ship Layer 2 first; nothing in `/onboard` matters until it lands.
- **Token path (corrected).** Both `auth.py` and the session layer `skills/data/garmin_auth.py` read/write `repo/tokens/<handle>/garmin_tokens.json` (`config.TOKENS_DIR = _PROJECT_ROOT/"tokens"`) — they already agree. The *dead* dir is the `~/.runforlife/athletes/<handle>/tokens` that `athlete_init.py` provisions and nothing reads. → `/onboard` polls **`repo/tokens/<handle>/garmin_tokens.json`** for auth success; drop the dead dir from `athlete_init.py`.
- **Handle is doubly constrained** (a directory *and* an env-var stem: `GARMIN_EMAIL_<HANDLE.upper()>`). Validate `^[a-z][a-z0-9_]{1,20}$`.
- **Profile schema drift is a live risk.** `athlete_init.py::_template_profile` emits only `{name, age, watch, goals, prefs}`, but playbooks read a much richer shape (`gender`, `garmin_user`, `goals.{half_marathon,hyrox,annual_run_days,north_star.pillars…}`, `context`, `training_directives`, `hr_zones`, `current_benchmarks`). `/onboard` must write the **real** shape and self-validate it.
- **Coaching style is normally *learned*.** `personality.json` only influences output above a confidence threshold, so a fresh user gets generic coaching for weeks unless `/onboard` **seeds `personality.json`** from the answers with confidence above threshold.
- **Sandbox rule:** the playbook honors `RUNFORLIFE_HOME`; its self-test runs against a throwaway home, never real data.

## 5. The aha moment & shortest path

**Activation target:** the friend sees a **brutally-honest, personalized coaching verdict built on their OWN synced Garmin numbers** — the first `/daily-plan` auto-run *inside* `/onboard`. "Synced 47 runs" is the precursor; the *verdict* is the aha.

**Core structural move (all four lenses agree): stop serializing.** The two slow costs — the Garmin MFA hand-off and the rate-limited backfill — must **overlap the interview**. Fire auth early; the instant the token file appears, start the backfill **in the background**; ask goals + style **while it runs**.

**Minimum required before first value:** display name → derived handle, gender, Garmin email+password, one commitment question (primary race + rough date), coaching tone + units.

**Deferred until after first value:** target times (escape-hatch "predict from my data"), secondary races, annual run-days, north-star + pillars + station checklist, hard-rules, weight/benchmarks, HR zones, watch model (auto-detected).

**Happy path (~4 min, one manual command, zero file editing):** type name → confirm handle → pick gender → paste Garmin creds → run one MFA command → (sync starts silently) → answer race card + tone/units card → watch their own numbers become a coached call.

## 6. Refined end-to-end `/onboard` script

> **[CARD]** = AskUserQuestion multiple-choice (≤4 opts, "Other"→free-text); **[TEXT]** = plain prompt. Write `profile.json` incrementally so the flow is **resumable**. Header each step: `Step N/6 · <label> · ~M min left`.

**Opener (hook + commitment, no checklist).** Print the payoff, then immediately fire the race card:
> **Let's build your coach.** ~4 minutes from now you'll have a running coach that knows your real Garmin data and your goal race — numbers-first, no fluff. First, so I know what we're chasing:

- **[CARD] primary race** — "What are you training for?" `Half Marathon · Marathon · Hyrox · 5K/10K · Other`. Multi-select; first pick = primary.
- **[TEXT]** "Roughly when? (a date or 'spring 2026' is fine)" → store raw + normalized `YYYY-MM-DD` if parseable; **no target time yet.**
- Echo: *"Got it — <race> around <date>. Let's get your coach seeing your data so it can hold you to that."*

**Step 1/6 — Preflight (silent; agent-run).** Agent runs `uv --version`, `uv sync`, ensures gitignored `.env` exists, confirms plugin present. On success: one line `Environment ready.` On failure only: the single copy-paste fix, then re-check. Never show a green checklist.

**Step 2/6 — Identity (one batched AskUserQuestion call).**
- **[TEXT]** "What name should the coach call you?" → `name`.
- **Derive handle**, then **[CARD]** confirm: *"I'll set your data up under `sam` — it becomes your folder and an env-var name. Keep it?"* `Keep 'sam' · Type a different one`. Validate `^[a-z][a-z0-9_]{1,20}$` + no collision. Error: *"Handles are lowercase letters/numbers/underscores, start with a letter. Try `sam` or `sam_r`."*
- **[CARD]** gender: `Male · Female · Other · Prefer not to say` (physiology defaults only).
- **Watch: not asked** — default `context.watch="Garmin Forerunner 165"`, auto-overwrite from Garmin after first sync.

**Step 3/6 — Garmin connect (trust copy → creds → the one manual MFA step).** Trust framing *before* the ask:
> Your email + password go into a **local `.env` on this machine only** — gitignored, never committed, never sent anywhere but Garmin. After login they're replaced by cached tokens. I write the file; I can't read it back. Delete `.env` anytime to revoke.

- **[TEXT]** Garmin email → typo detection (*"Did you mean `sam@gmail.com`?"*).
- **[TEXT]** Garmin password (never echoed).
- Agent writes `GARMIN_EMAIL_<HANDLE>` / `GARMIN_PASSWORD_<HANDLE>` to `.env`.
- **The one manual step** — one copy-paste block, handle pre-filled, framed as security-not-breakage:
  > One thing only you can do: Garmin will prompt YOU for a login code (I never see it). Run this, enter the code:
  > ```
  > ! uv run python -m runforlife.auth <handle>
  > ```
  > You'll know it worked when you see: `Authenticated successfully! Display name: <you>`.
- Agent **polls `repo/tokens/<handle>/garmin_tokens.json`** and auto-resumes the moment it appears — no "type done." If absent after ~90s: `Retry the command · Skip Garmin for now (explore, sync later)`.

**Step 4/6 — Background sync starts (invisible; overlaps 5–6).** The instant the token file exists, launch the backfill in the background (`run_in_background`, ~90 days). One line: `Pulling your last 90 days in the background — keep going, this runs while we talk.` Do not block.

**Step 5/6 — Coaching style (one batched card call; seeds personality.json).**
- **[CARD]** tone → `communication`: `Brutally honest — just the gap (direct_blunt) · Supportive (supportive_narrative) · Balanced`.
- **[CARD]** units → `prefs.units`: `Metric · Imperial` (default Metric).
- **[CARD]** depth → `data_depth`: `Just the numbers (low) · Numbers + brief why (medium) · Deep analysis (high)`.
- Write to `personality.json` with `confidence` above the activation threshold + matching `signal_counts`, so the chosen voice shows on the first plan.

**Step 6/6 — Scaffold + confirm.**
- Run `athlete_init.py --user <handle>` for empty seed files, then **overwrite `profile.json` with the full real schema** (`name`, `gender`, `garmin_user=<handle>`, `goals.<primary_race>`, `context.watch`, defaults for the rest). Set active: `printf '%s\n' "<handle>" > ~/.runforlife/active_athlete`.
- **[CARD]** review: *"Setting up `<handle>` — <race> ~<date>, <tone>, <units>. Looks right?"* `Looks good · Change something`.
- **Self-validate** (sandboxed): dry-run the profile read `/daily-plan` uses; if a required field is missing, fail loudly with the exact fix rather than shipping a silently-broken profile.

**Finish — end ON the aha (peak-end), never a stats dump.** Join the background sync, report concretely, then auto-run the coached read:
> Synced 90 days: **14 runs, 118 km, latest 10.2 km @ 5:38/km, avg HR 152, ACWR 1.06.**
> First read from your coach: *your easy pace has crept ~15 s/km over 6 weeks — classic drift. For <race> by <date> you're one lever short: volume.*
> → running your first session now…

Then auto-invoke `/daily-plan <handle>` and list next commands (`/panel`, `/weekly-plan`, `/goal-status`, `/chart`).

**Sparse/empty-data fallback:** if the backfill returned little, still deliver forward motion (*"Only 3 runs so far — baseline set. Come back after this week and I'll have real trends."*) and point to `/goal-status`, not analytics that aren't there.

## 7. Friction & drop-off risk table (ranked)

| # | Step | Risk | Mitigation |
|---|------|------|------------|
| 1 | **Hardcoded athlete gate** | New handle rejected everywhere → activation 0 | **P0, ship first:** dir-existence validation replacing the allow-list + all exact-match checks + `auth.py::main()`; smoke-test `/daily-plan <newhandle>` in the self-validate. |
| 2 | **Preflight: clone + `uv sync`** (before `/onboard`) | Fails silently → "plugin is broken" | One-line README bootstrap with the same payoff promise; `/onboard` auto-runs `uv sync`, surfaces failures with copy-paste fixes. |
| 3 | **Garmin MFA hand-off** | Highest single abandonment: context-switch + "did it work?" | Reframe as security ("only you can"), one pre-filled block, exact success string, **poll the token file to auto-resume**, retry line, skip-and-explore escape. |
| 4 | Credential trust | Password-in-terminal anxiety → bail | Trust copy before the ask: local, gitignored, never sent, deletable, "I can't read it back." |
| 5 | First sync (backfill) | Rate-limited multi-minute wait reads as hung | Background right after auth, overlaps Steps 5–6; report count + date-range on completion. |
| 6 | Handle/slug | Invalid/colliding handle → dir/env failures | Derive from name, Enter-to-accept, validate + collision-check inline. |
| 7 | Goals / target time | Doesn't know goal time / `mm:ss` vs `h:mm:ss` garbage | Defer target time; "predict from my data" (`target_time:null`); soft-warn, never discard. |
| 8 | Profile schema drift | Writes a shape playbooks don't read → silent wrong answers | Write full real schema; end with sandboxed self-validate dry-running `/daily-plan`. |
| 9 | Coaching style ignored | Learned-only → generic for weeks | Seed `personality.json` above threshold. |
| 10 | Mid-flow interruption | External MFA makes it likely; restart = abandon | Incremental `profile.json` + early active pointer; `/onboard` detects partial profile and resumes. |
| 11 | Finish = stats dump | Wastes peak-end | End on blunt coached verdict + auto-run `/daily-plan`. |

## 8. Progressive onboarding — deferred items & where they're collected

| Deferred item | Captured later at | Trigger |
|---|---|---|
| Target time(s) per race | first `/daily-plan` or `/goal-status` | *"No goal time yet — predict from your data, or set it?"* (predicts by default) |
| North-star + pillars + station checklist | `/goal-status` | *"Optional but powerful — the big goal 18 months out?"* skippable |
| Annual run-days | `/weekly-plan` / `/goal-status` | [CARD] `200 · 250 · 300 · 365`, default 300 |
| Secondary races | `/goal-status` | reuse the race card |
| Hard-rules (e.g. no-heat, intensity caps) | after ~1 week / on first violation | [CARD multi-select] recognition-over-recall |
| Watch / HR zones / weight / benchmarks | auto-detected post-sync; `/note` to correct | silent unless detection fails |
| Coaching-style refinement | existing learned-personality loop | self-tunes from real signals |

## 9. Suggested build order (P0 punch-list first)

1. **Layer 2 — generalize the athlete gate** (config `list_athletes()` + de-enum CLIs/playbooks/guard). *Nothing else matters until this lands.*
2. **Layer 1 — portability** (`${CLAUDE_PLUGIN_ROOT}` in the 22 files).
3. **`athlete_init.py` upgrade** — write the full real `profile.json` from args; drop the dead tokens dir; idempotent.
4. **`/onboard` playbook** — the CRO flow in §6, incl. background-sync overlap, token-file polling, `personality.json` seeding, self-validate, auto-run `/daily-plan`.
5. **`session_start.py` trigger** — detect zero athletes → point to `/onboard`.
6. **Prose sweep + README** — genericize the ~60 tezuesh/kakul mentions; one-line install bootstrap with the payoff promise.

## 10. Conflicts resolved by the workflow
- **Goals up front vs deferred:** ask only the one race + rough date as a motivating opener; defer times/pillars/run-days.
- **Watch model:** default + auto-detect, no card.
- **Gender:** keep one cheap card (physio defaults use it).
- **Demo sample athlete:** good "value before auth" but a heavier lift; deferred as nice-to-have since the background-sync + auto-`/daily-plan` finale already reaches the aha in-session.

## 11. Open questions (for review)
1. **Scope** — confirm "Full" (assumed).
2. **Multi-athlete-per-install** — keep it (onboarding = "add an athlete; the first also does first-run setup")? (Assumed yes.)
3. **Packaging** — OK that a friend clones the whole repo (backend + plugin)? (Recommended.)
4. **MFA** — OK with the single manual `! uv run python -m runforlife.auth <handle>` step?
5. **Prose de-hardcoding** — all ~60 mentions now, or functional enums first and prose sweep later?
6. **Demo athlete** — include the bundled sample-data mode (P1), or defer?
