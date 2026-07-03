"""
RunForLife — CLI entry point

Run with:
  uv run python -m runforlife.main --user tezuesh
  uv run python -m runforlife.main --user kakul

Each message is automatically routed to the right specialist:
  [Recovery Specialist]  — sleep, HRV, readiness, injury risk
  [Training Planner]     — mileage, load, workouts, streaks
  [Race Strategist]      — VO2max, goal progress, race prep
  [Data Analyst]         — correlations, patterns, custom SQL
"""

import argparse
from datetime import date

from dotenv import load_dotenv

from runforlife.agent.coordinator import Coordinator
from runforlife.storage.conversation_db import load_recent
from runforlife.storage.metrics_store import has_checkin_today, upsert_subjective


def _run_checkin(user: str, today: str) -> None:
    """Prompt for today's subjective check-in if not already done."""
    print("\n── Daily Check-in ──────────────────────────")
    while True:
        try:
            raw = input("How are you feeling today? (1–10): ").strip()
            readiness = int(raw)
            if 1 <= readiness <= 10:
                break
            print("  Please enter a number between 1 and 10.")
        except (ValueError, EOFError):
            print("  Please enter a number between 1 and 10.")

    try:
        context = input("Anything going on this week? (stress, travel, illness, or 'all good'): ").strip()
    except EOFError:
        context = "all good"

    upsert_subjective(user, today, readiness, context or "all good")
    print("── Got it. ─────────────────────────────────\n")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="RunForLife Coach")
    parser.add_argument(
        "--user",
        required=True,
        help="Which athlete's (handle) session to start",
    )
    args = parser.parse_args()
    user: str = args.user
    today = date.today().isoformat()

    history = load_recent(user, n=40)
    history_turns = len(history) // 2

    coordinator = Coordinator(user)

    print(f"\nRunForLife — {user.capitalize()}")
    print("=" * 45)
    if history_turns:
        print(f"Loaded {history_turns} previous turn(s).")
    print("Specialists: Recovery | Training | Race | Analytics")
    print("Type 'quit' to exit.")

    if not has_checkin_today(user, today):
        _run_checkin(user, today)
    else:
        print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        print()
        specialist, response = coordinator.chat(user_input)
        print(f"[{specialist}]\n{response}\n")


if __name__ == "__main__":
    main()
