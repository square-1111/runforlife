"""
User profile storage and system prompt generation.

Profiles are JSON files in data/{user}/profile.json.
They're seeded with known facts and can be updated as we learn more.
"""

import json
from datetime import date

from runforlife.storage.paths import profile_path

_SEED_PROFILES: dict[str, dict] = {
    "tezuesh": {
        "name": "Tezuesh Varshney",
        "gender": "male",
        "garmin_user": "tezuesh",
        "goals": {
            "half_marathon": {
                "target_time": "1:28:00",
                "race_date": "2026-09-28",
                "notes": "Hyrox prep run, also standalone HM",
            },
            "hyrox": {
                "category": "Mixed Doubles",
                "partner": "Kakul Shrivastava",
                "race_date": "2026-09-28",
            },
            "annual_run_days": {
                "target": 300,
                "year": 2026,
            },
        },
        "context": {
            "job": "software engineer (sedentary)",
            "sleep_time": "~01:00",
            "dinner_time": "~21:00",
            "preferred_run_days_per_week": 6,
            "weight_training_sessions_per_week": 4,
            "watch": "Garmin Forerunner 165",
        },
        "hr_zones": {
            "note": "Use Garmin's auto-calculated zones until confirmed",
        },
    },
    "kakul": {
        "name": "Kakul Shrivastava",
        "gender": "female",
        "garmin_user": "kakul",
        "goals": {
            "half_marathon": {
                "target_time": "2:00:00",
                "race_date": "2026-09-28",
                "notes": "Hyrox prep run, also standalone HM",
            },
            "hyrox": {
                "category": "Mixed Doubles",
                "partner": "Tezuesh Varshney",
                "race_date": "2026-09-28",
            },
            "annual_run_days": {
                "target": 300,
                "year": 2026,
            },
        },
        "context": {
            "job": "software engineer (sedentary)",
            "sleep_time": "~01:00",
            "dinner_time": "~21:00",
            "preferred_run_days_per_week": 6,
            "weight_training_sessions_per_week": 4,
            "watch": "Garmin Forerunner 165",
        },
        "hr_zones": {
            "note": "Use Garmin's auto-calculated zones until confirmed",
        },
    },
}


def load_profile(user: str) -> dict:
    """Load profile from disk, seeding from defaults if it doesn't exist."""
    path = profile_path(user)
    if path.exists():
        return json.loads(path.read_text())

    profile = _SEED_PROFILES[user]
    save_profile(user, profile)
    return profile


def save_profile(user: str, profile: dict) -> None:
    path = profile_path(user)
    path.write_text(json.dumps(profile, indent=2))


def get_hyrox_stations(user: str) -> dict:
    """Return the per-station Hyrox targets/PBs map, or {} if unset.

    The hyrox goal MAY carry an optional "stations" map, e.g.::

        "hyrox": {
            "category": "Mixed Doubles",
            "stations": {
                "ski_erg":  {"target_sec": 220, "pb_sec": 235},
                "sled_push": {"target_sec": 90},
                ...
            }
        }

    This is intentionally NOT seeded — no real profile.json is written here.
    A future Hyrox specialist can populate it via save_profile and read it back
    through this safe accessor (missing keys yield {} rather than raising).
    """
    profile = load_profile(user)
    return profile.get("goals", {}).get("hyrox", {}).get("stations", {})


def build_system_prompt(user: str, memories: list[str] | None = None, inject_memories: bool = True) -> str:
    """
    Build a personalized system prompt from the user's profile.

    If inject_memories=True (default), active memories are auto-loaded from
    the memory store and appended — so the coach always has full context
    without needing an explicit recall_memory call.
    """
    from runforlife.storage.memory_store import load_active_memories  # late import avoids circular

    profile = load_profile(user)
    today = date.today().isoformat()

    name = profile["name"]
    gender = profile["gender"]
    ctx = profile["context"]
    goals = profile["goals"]

    hm = goals["half_marathon"]
    hyrox = goals["hyrox"]

    prompt = f"""\
You are RunForLife Coach, a personal running and Hyrox training assistant.

## Athlete Profile
- Name: {name} ({gender})
- Watch: {ctx['watch']}
- Job: {ctx['job']}
- Sleep schedule: dinner ~{ctx['dinner_time']}, bed ~{ctx['sleep_time']}

## Current Goals (as of {today})
- Half Marathon: sub {hm['target_time']} by {hm['race_date']}
- Hyrox Mixed Doubles: with {hyrox['partner']}, race {hyrox['race_date']}
- Annual running days: {goals['annual_run_days']['target']} days in {goals['annual_run_days']['year']}

## Coaching Rules
1. Always authenticate with Garmin (garmin_auth) before fetching any data.
2. Use actual data — never guess numbers.
3. Be specific: paces, distances, heart rates, zones.
4. Injury risk is the top priority — flag ACWR > 1.3 and HRV downtrends.
5. Coaching advice should reference the data, not generic advice.
6. Be concise and actionable.\
"""

    # Merge explicitly passed memories with auto-loaded ones
    if inject_memories:
        active = load_active_memories(user)
        all_memories = list(memories or []) + [m for m in active if m not in (memories or [])]
    else:
        all_memories = list(memories or [])

    if all_memories:
        prompt += "\n\n## What I Remember About You\n"
        prompt += "\n".join(f"- {m}" for m in all_memories)

    return prompt
