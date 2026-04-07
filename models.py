# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for the ChipForge RTL Debugging Environment.

Designed for RL training of LLMs:
  - Observation is a self-contained Markov state (always includes RTL code)
  - Reward uses potential-based shaping for dense per-step signal
  - Action result feedback at every step
"""

from typing import Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class ChipforgeAction(Action):
    """Action for the ChipForge environment.

    Supported action_types:
        - view_testbench: View the testbench code
        - view_logs: View logs from last tool run (specify log_type)
        - run_simulation: Compile and simulate with Verilator
        - run_synthesis: Synthesize with Yosys
        - run_lint: Run Verilator lint checks
        - edit_line: Replace a single line (requires line_number + new_content)
        - submit: Submit current RTL as the final solution
    """

    action_type: str = Field(
        ...,
        description=(
            "Type of action: view_testbench, view_logs, "
            "run_simulation, run_synthesis, run_lint, edit_line, submit"
        ),
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Line number to edit (1-indexed). Required for edit_line.",
    )
    new_content: Optional[str] = Field(
        default=None,
        description="New content for the line. Required for edit_line.",
    )
    log_type: Optional[str] = Field(
        default=None,
        description="Which log to view: sim, synth, or lint. Used with view_logs.",
    )


class ChipforgeObservation(Observation):
    """Observation returned by the ChipForge environment.

    Designed as a self-contained Markov state for RL training.
    The RTL code is ALWAYS included so the agent never needs a
    separate 'view' action just to see where it is.
    """

    # ── Always populated (the Markov state) ──────────────────────────────
    rtl_code: str = Field(
        default="",
        description="Current RTL design code with line numbers (always present)",
    )
    task_description: str = Field(
        default="", description="Description of the current debugging task"
    )

    # Tool statuses (always present)
    sim_status: str = Field(
        default="not_run",
        description="Simulation status: not_run, pass, fail, error",
    )
    synth_status: str = Field(
        default="not_run",
        description="Synthesis status: not_run, pass, warning, error",
    )
    lint_status: str = Field(
        default="not_run",
        description="Lint status: not_run, clean, warning, error",
    )

    # Action feedback (what just happened)
    last_action: str = Field(
        default="reset", description="The action that produced this observation"
    )
    action_result: str = Field(
        default="",
        description="Human-readable result of the last action taken",
    )

    # ── Conditionally populated (verbose content from actions) ───────────
    testbench_code: str = Field(
        default="", description="Testbench code (populated by view_testbench)"
    )
    log_output: str = Field(
        default="",
        description="Tool output log, truncated to 2000 chars (populated by view_logs or tool runs)",
    )

    # ── RL signals ──────────────────────────────────────────────────────
    step_count: int = Field(default=0, description="Steps taken so far")
    max_steps: int = Field(default=20, description="Maximum allowed steps")
    cumulative_reward: float = Field(
        default=0.0,
        description="Total quality score so far (0.0 to 1.0)",
    )
