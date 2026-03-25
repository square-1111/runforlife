"""
RunForLife — Entry Point
=========================
Run with: uv run python -m runforlife.main

Starts an interactive chat with your running coach agent.
"""

from dotenv import load_dotenv

from runforlife.agent.core import Agent
from runforlife.skills.registry import create_default_registry


def main() -> None:
    load_dotenv()

    registry = create_default_registry()
    agent = Agent(registry)

    print("RunForLife Coach")
    print("=" * 40)
    print("Ask about your running, training, or Hyrox prep.")
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
        response = agent.chat(user_input)
        print(f"Coach: {response}\n")


if __name__ == "__main__":
    main()
