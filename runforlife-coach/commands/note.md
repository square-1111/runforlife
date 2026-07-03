---
description: Record a short-lived context note (injury, travel, life event, supplement change) for the active athlete, with an optional expiry
argument-hint: <note text> [expires:YYYY-MM-DD]
---

# /note — capture ephemeral context for the active athlete

The note to record is: **$ARGUMENTS**

This command stores a short-lived context item (e.g. an injury, a travel stretch, a life event, a
supplement change) so the coach's advice accounts for what's currently true — and so it auto-drops
out once it expires. Follow these steps **in order**. Do not skip validation.

## 1. Validate the argument

- If `$ARGUMENTS` is empty (no note text), **STOP**. Do not write any file. Reply:

  > Nothing to record. Usage: `/note <note text> [expires:YYYY-MM-DD]`.

- Otherwise, parse the argument into two parts:
  - **content** — the note text itself (required).
  - **expiry** — optional. If the argument contains a trailing `expires:YYYY-MM-DD` token, strip it
    off and use the date as the expiry. Everything before it is the content. If no `expires:` token
    is present, there is no expiry (the item persists until pruned or deleted).
  - If an `expires:` token is present but the date is not a valid `YYYY-MM-DD`, **STOP** and reply:

    > Invalid expiry `<what they passed>`. Use `expires:YYYY-MM-DD`.

## 2. Resolve the active athlete (durable pointer)

The active athlete is stored as a single line in `~/.runforlife/active_athlete` (set by `/switch`).
Read it with Bash so the home directory is expanded:

```bash
cat ~/.runforlife/active_athlete 2>/dev/null
```

- If the file is missing or empty, **STOP**. Reply:

  > No active athlete set. Run `/switch <tezuesh|kakul>` first.

- Otherwise, use the trimmed name as the athlete for the next step.

## 3. Record the ephemeral item

Call the memory manager's `--add-ephemeral` action. Run from the repo root. Substitute the resolved
athlete name for `<athlete>` and the parsed note for `<content>`:

- **Without an expiry:**

  ```bash
  cd "$(cat ~/.runforlife/repo_path)" && uv run python ./runforlife-coach/scripts/memory_manager.py --user <athlete> --add-ephemeral --content "<content>"
  ```

- **With an expiry** (only when an `expires:YYYY-MM-DD` token was parsed):

  ```bash
  cd "$(cat ~/.runforlife/repo_path)" && uv run python ./runforlife-coach/scripts/memory_manager.py --user <athlete> --add-ephemeral --content "<content>" --expires-on YYYY-MM-DD
  ```

The script prints the new ephemeral id on success.

## 4. Confirm

Report back tersely and factually:

- The athlete the note was recorded for.
- The note content.
- The expiry, or "no expiry" if none was set.
- The new ephemeral id printed by the script.

Example:

```
Noted for tezuesh (id 4): "Right calf tight after intervals" — expires 2026-06-20.
```

Do not invent fields. Do not write any file other than via the script above.
