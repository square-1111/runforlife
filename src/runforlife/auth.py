"""
Interactive pre-authentication for Garmin Connect.

Run this ONCE per user to create cached tokens before using the agent.
Handles MFA (multi-factor authentication) interactively.

Usage:
    uv run python -m runforlife.auth tezuesh
    uv run python -m runforlife.auth kakul
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin

TOKENS_DIR = Path(__file__).parent.parent.parent / "tokens"


def authenticate(user: str) -> None:
    load_dotenv()

    key = user.upper()
    email = os.environ.get(f"GARMIN_EMAIL_{key}")
    password = os.environ.get(f"GARMIN_PASSWORD_{key}")

    if not email or not password:
        print(f"ERROR: Set GARMIN_EMAIL_{key} and GARMIN_PASSWORD_{key} in .env")
        sys.exit(1)

    token_path = TOKENS_DIR / user
    token_file = token_path / "garmin_tokens.json"

    print(f"Authenticating {user} ({email})...")

    # Try existing tokens first
    if token_file.exists():
        print("Found cached tokens — attempting token refresh...")
        garmin = Garmin(email, password)
        try:
            garmin.login(tokenstore=str(token_path))
            garmin.client.dump(str(token_path))
            print(f"Tokens refreshed successfully. Display name: {garmin.display_name}")
            return
        except Exception as e:
            print(f"Token refresh failed ({e}), doing fresh login...")

    # Fresh login — may trigger MFA
    garmin = Garmin(email, password, return_on_mfa=True)
    mfa_status, mfa_session = garmin.login()

    if mfa_status == "needs_mfa":
        print(f"\nMFA required. Check your email/authenticator app for the code.")
        mfa_code = input("Enter MFA code: ").strip()
        garmin.resume_login(mfa_session, mfa_code)

    token_path.mkdir(parents=True, exist_ok=True)
    garmin.client.dump(str(token_path))
    print(f"\nAuthenticated successfully!")
    print(f"Display name: {garmin.display_name}")
    print(f"Tokens saved to: {token_file}")
    print(f"\nThe agent can now use '{user}' without re-entering credentials.")


def main() -> None:
    # Accept any syntactically-valid handle — auth runs BEFORE the athlete dir
    # exists during onboarding, so we validate shape only, not configured-ness.
    from runforlife.storage.paths import valid_handle

    if len(sys.argv) != 2 or not valid_handle(sys.argv[1]):
        print("Usage: uv run python -m runforlife.auth <handle>")
        print("  <handle>: lowercase letters/numbers/underscores, starts with a letter (2-21 chars)")
        sys.exit(1)

    authenticate(sys.argv[1])


if __name__ == "__main__":
    main()
