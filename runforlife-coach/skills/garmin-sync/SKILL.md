---
name: garmin-sync
description: Pull latest Garmin data for an athlete into their local metrics.db.
---

# garmin-sync

Fetches the latest Garmin Connect data for an athlete and ingests it into that
athlete's local `metrics.db` at `~/.runforlife/athletes/<athlete>/metrics.db`.

## When to use

Run this **on-demand** whenever the athlete's local DB is stale or empty —
for example, a specialist asks for "today's" readiness/HRV/sleep but the most
recent row in `metrics.db` is several days old, or there are no rows at all for
the requested date. Sync first, then read.

A per-athlete **nightly launchd job** also runs this same command automatically
(Phase 2), so during normal use the DB stays fresh on its own. Treat the manual
sync as a catch-up for gaps (missed nights, fresh date ranges, first-time setup).

## Command

Run from the repo root:

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.sync.nightly --user <athlete> [--start YYYY-MM-DD --end YYYY-MM-DD]
```

- `<athlete>` — `tezuesh` or `kakul` (use the active athlete unless told otherwise).
- With no date flags, it syncs **yesterday** only (the nightly default).
- `--start` / `--end` sync an inclusive date range, e.g. to backfill a gap:

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.sync.nightly --user tezuesh --start 2026-05-25 --end 2026-06-02
```

Already-ingested days are skipped automatically, so re-running is safe and cheap.
Garmin is rate-limited (≈0.3s/call within a day, 0.5s between days), so a long
range can take a few minutes.

## First-time authentication (MFA)

The sync uses cached Garmin tokens and will **not** prompt for credentials. Before
the very first sync for an athlete, authentication must be done **once,
interactively**, because Garmin may require MFA (an emailed/authenticator code that
cannot be answered headlessly). Run:

```bash
cd /Users/tezueshvarshney/work/test/runforlife && uv run python -m runforlife.auth <athlete>
```

This reads `GARMIN_EMAIL_<ATHLETE>` / `GARMIN_PASSWORD_<ATHLETE>` from `.env`,
walks through the MFA prompt if needed, and writes the token store. After that,
sync runs unattended and refreshes tokens on its own.

If a sync fails with an auth error (e.g. `[AUTH FAILED]`), the tokens have likely
expired or were never created — re-run `runforlife.auth <athlete>` interactively,
then retry the sync.

## Tokens

Cached Garmin tokens live at:

```
~/.runforlife/athletes/<athlete>/tokens/
```

This directory is created with mode `0700` and individual token files `0600`.
Tokens are per-athlete and are **never** committed to the repo.
