"""
Constants used across the ChipForge server environment.
"""

import os
from pathlib import Path

MAX_STEPS = 30  # max steps per episode
LOG_TRUNCATE = 2000  # max chars in observation logs
TOOL_TIMEOUT = 30  # seconds
STEP_COST = 0.02  # per-step penalty to encourage efficiency

# Tool paths — absolute for OSS CAD Suite in Docker
VERILATOR = "/opt/oss-cad-suite/bin/verilator"
YOSYS = "/opt/oss-cad-suite/bin/yosys"

VALID_ACTIONS = {
    "view_design",
    "view_testbench",
    "view_synthesis_log",
    "view_lint_log",
    "view_simulation_log",
    "run_simulation",
    "run_synthesis",
    "run_lint",
    "edit_line",
    "append_line",
    "insert_lines",
    "replace_lines",
    "write_file",
    "submit",
}

TASKS_DIR = Path(__file__).parent / "tasks"
