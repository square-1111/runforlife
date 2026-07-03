"""
Central configuration for RunForLife.

Keep all magic numbers, paths, and model names here.
"""

import os
from pathlib import Path

# Project root = src/runforlife/../../../  (three parents up from this file)
_PROJECT_ROOT = Path(__file__).parent.parent.parent

# All persistent data lives here (outside src/, never committed)
DATA_DIR = _PROJECT_ROOT / "data"

# Auth tokens (already exists)
TOKENS_DIR = _PROJECT_ROOT / "tokens"

# Athlete data root — all per-athlete data lives here (outside the repo, never committed).
# Overridable via RUNFORLIFE_HOME so tests and agents can sandbox to a throwaway dir
# instead of touching the real ~/.runforlife (the 2026-06 data-loss failure class).
RUNFORLIFE_HOME = Path(os.environ.get("RUNFORLIFE_HOME") or (Path.home() / ".runforlife"))

# Athletes are discovered dynamically from disk — see
# runforlife.storage.paths.list_athletes() (was a hardcoded USERS tuple).

# Anthropic model
MODEL = "claude-sonnet-4-20250514"

# Conversation history: how many past turns to load into context
CONVERSATION_WINDOW = 40

# ACWR (Acute:Chronic Workload Ratio) thresholds
ACWR_SAFE_MIN = 0.8
ACWR_SAFE_MAX = 1.3
ACWR_HIGH_RISK = 1.5

# HRV: 7-day slope (ms/day) below which we flag a downtrend
HRV_SLOPE_WARNING = -1.0  # ms/day

# Sleep efficiency delta vs baseline below which we flag
SLEEP_EFFICIENCY_DELTA_WARNING = -5.0  # percentage points
