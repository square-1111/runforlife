---
description: Switch the active athlete (tezuesh or kakul) and prime the coach with their profile + active context
argument-hint: <tezuesh|kakul>
---

# /switch — change the active athlete

The requested athlete is: **$ARGUMENTS**

Follow these steps **in order**. Do not skip validation.

## 1. Validate the argument

The only supported athletes are `tezuesh` and `kakul`.

- If `$ARGUMENTS` is empty, or is anything other than exactly `tezuesh` or `kakul`
  (case-sensitive, no extra whitespace), **STOP**. Do not write any file. Reply:

  > Invalid athlete `<what they passed>`. Usage: `/switch <tezuesh|kakul>`.

- Only continue past this step once the argument is confirmed to be one of the two valid names.

## 2. Persist the active athlete (durable pointer)

Write the validated name as a single line to `~/.runforlife/active_athlete`. Use Bash so the
home directory is expanded and the parent dir exists:

```bash
mkdir -p ~/.runforlife && printf '%s\n' "$ARGUMENTS" > ~/.runforlife/active_athlete
```

This pointer is sticky — it survives across sessions until the next `/switch`.

## 3. Prune expired ephemeral context for the new athlete

Run a fresh prune so stale travel/injury/life notes never poison advice. Run from the repo root:

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python /Users/tezueshvarshney/work/test/runforlife/runforlife-coach/scripts/memory_manager.py --user $ARGUMENTS --prune-expired
```

Report how many entries were pruned (the script prints this).

## 4. Surface the athlete's profile + active context (prime the coach)

Read these two files so the coaching session starts already grounded in who the athlete is and
what's currently true for them:

- Profile (static — name, age, watch, goals, prefs):
  `~/.runforlife/athletes/$ARGUMENTS/profile.json`
- Active ephemeral context (only non-expired items, after the prune above):
  `~/.runforlife/athletes/$ARGUMENTS/ephemeral.json`

Use the Read tool on each path. If `profile.json` is missing, note that the athlete has not been
initialized yet and suggest running the init/migration scripts. If `ephemeral.json` is missing or
has no items, say there is no active ephemeral context.

## 5. Confirm

Print the banner exactly:

```
[ACTIVE: $ARGUMENTS]
```

Then give a short primer the coach can use immediately:

- The athlete's name, age, watch, and primary goal(s) from `profile.json`.
- Any active (non-expired) ephemeral items — e.g. travel, injury, or life context — so advice
  accounts for what's currently going on.
- A one-line readiness cue, e.g. "Ready to coach <name>. Ask me anything."

Keep the summary tight and factual. Do not invent fields that aren't in the files.
