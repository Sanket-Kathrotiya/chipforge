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

from typing import Any, Dict, Literal, Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import Field, model_validator

ActionType = Literal[
    "view_testbench",
    "view_synthesis_log",
    "view_lint_log",
    "view_simulation_log",
    "run_simulation",
    "run_synthesis",
    "run_lint",
    "edit_line",
    "append_line",
    "edit_testbench_line",
    "append_testbench_line",
    "submit",
]


class ChipforgeAction(Action):
    """Action for the ChipForge environment.

    Supported action_types:
        - view_testbench: View the testbench code
        - view_synthesis_log: View synthesis log (only if run_synthesis was executed)
        - view_lint_log: View lint log (only if run_lint was executed)
        - view_simulation_log: View simulation log (only if run_simulation was executed)
        - run_simulation: Compile and simulate with Verilator
        - run_synthesis: Synthesize with Yosys
        - run_lint: Run Verilator lint checks
        - edit_line: Replace a single line (requires line_number + new_content)
        - append_line: Append one new RTL line (requires new_content)
        - edit_testbench_line: Replace a single testbench line (requires line_number + new_content)
        - append_testbench_line: Append one new testbench line (requires new_content)
        - submit: Submit current RTL as the final solution
    """

    action_type: ActionType = Field(..., description="Type of action to execute")
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
        description="Deprecated. Use view_synthesis_log, view_lint_log, or view_simulation_log instead.",
    )

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ChipforgeAction":
        is_edit = self.action_type == "edit_line"
        is_append = self.action_type == "append_line"
        is_tb_edit = self.action_type == "edit_testbench_line"
        is_tb_append = self.action_type == "append_testbench_line"
        has_line = self.line_number is not None
        has_content = self.new_content is not None

        if is_edit and (not has_line or not has_content):
            raise ValueError("edit_line requires both line_number and new_content")

        if is_tb_edit and (not has_line or not has_content):
            raise ValueError("edit_testbench_line requires both line_number and new_content")

        if (is_append or is_tb_append) and (not has_content or has_line):
            raise ValueError(
                "append_line/append_testbench_line require new_content only"
            )

        if (not is_edit and not is_tb_edit and not is_append and not is_tb_append) and (
            has_line or has_content
        ):
            raise ValueError(
                "line_number/new_content are only valid for edit_line, append_line, "
                "edit_testbench_line, append_testbench_line"
            )
        return self


class ChipforgeObservation(Observation):
    """Observation returned by the ChipForge environment.

    Designed as a self-contained Markov state for RL training.
    Always includes the current RTL code.
    Tool logs are only populated when explicitly requested via:
        - view_synthesis_log: Shows synthesis logs from last run
        - view_lint_log: Shows lint logs from last run
        - view_simulation_log: Shows simulation logs from last run
    """

    # ── Always populated (Markov state core) ─────────────────────────────
    rtl_code: str = Field(
        default="",
        description="Current RTL design code with line numbers (always present)",
    )
    sim_status: Literal["not_run", "pass", "fail", "error"] = Field(
        default="not_run",
        description="Latest simulation status for current RTL snapshot",
    )
    synth_status: Literal["not_run", "pass", "warning", "error"] = Field(
        default="not_run",
        description="Latest synthesis status for current RTL snapshot",
    )
    lint_status: Literal["not_run", "clean", "warning", "error"] = Field(
        default="not_run",
        description="Latest lint status for current RTL snapshot",
    )
    error_summary: str = Field(
        default="",
        description="One-line summary of the most relevant diagnostic",
    )
    task_description: str = Field(
        default="",
        description="Natural language description of the loaded RTL debug task",
    )

    # Action feedback (what just happened)
    last_action: str = Field(
        default="reset", description="The action that produced this observation"
    )
    action_result: str = Field(
        default="",
        description="Human-readable result of the last action taken",
    )

    # ── Conditionally populated (verbose action-specific payload) ─────────
    testbench_code: str = Field(
        default="", description="Testbench code (populated by view_testbench)"
    )
    log_output: str = Field(
        default="",
        description="Tool output log, truncated to 2000 chars (populated by view_synthesis_log, view_lint_log, view_simulation_log, or tool runs)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extra machine-readable fields for clients/prompts",
    )

    # ── RL signals ──────────────────────────────────────────────────────
    step_count: int = Field(default=0, description="Steps taken so far")
    max_steps: int = Field(default=20, description="Maximum allowed steps")
    cumulative_reward: float = Field(
        default=0.0,
        description="Total quality score so far (0.0 to 1.0)",
    )
