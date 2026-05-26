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

from dotenv import load_dotenv

from runforlife.agent.coordinator import Coordinator
from runforlife.config import USERS
from runforlife.storage.conversation_db import load_recent


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="RunForLife Coach")
    parser.add_argument(
        "--user",
        required=True,
        choices=USERS,
        help="Which athlete's session to start",
    )
    args = parser.parse_args()
    user: str = args.user

    history = load_recent(user, n=40)
    history_turns = len(history) // 2

    coordinator = Coordinator(user)

    print(f"\nRunForLife — {user.capitalize()}")
    print("=" * 45)
    if history_turns:
        print(f"Loaded {history_turns} previous turn(s).")
    print("Specialists: Recovery | Training | Race | Analytics")
    print("Type 'quit' to exit.\n")

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
