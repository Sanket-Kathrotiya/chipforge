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
]


class ChipforgeAction(Action):
    """Action for the ChipForge environment.

    Supported action_types:
        - view_design: View the design (RTL) code
        - view_testbench: View the testbench code
        - view_synthesis_log: View synthesis log (only if run_synthesis was executed)
        - view_lint_log: View lint log (only if run_lint was executed)
        - view_simulation_log: View simulation log (only if run_simulation was executed)
        - run_simulation: Compile and simulate with Verilator
        - run_synthesis: Synthesize with Yosys
        - run_lint: Run Verilator lint checks
        - edit_line: Replace a single line (requires target, line_number + new_content)
        - append_line: Append one new line (requires target, new_content)
        - insert_lines: Insert multiple lines starting at line_number (requires target, line_number + new_content)
        - replace_lines: Replace multiple lines from line_number to end_line_number with new_content (requires target)
        - write_file: Write the entire file (requires target and new_content)
        - submit: Submit current RTL as the final solution
    """

    action_type: ActionType = Field(..., description="Type of action to execute")
    target: Literal["design", "testbench"] = Field(
        default="design",
        description="Target file for the edit ('design' or 'testbench'). Required for edit/append/insert/replace actions.",
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Line number to edit (1-indexed). Required for edit_line, insert_lines, replace_lines.",
    )
    end_line_number: Optional[int] = Field(
        default=None,
        description="End line number to replace (1-indexed). Required for replace_lines.",
    )
    new_content: Optional[str] = Field(
        default=None,
        description="New content. Required for edit, append, insert, and replace actions.",
    )

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ChipforgeAction":
        is_edit = self.action_type == "edit_line"
        is_append = self.action_type == "append_line"
        is_insert = self.action_type == "insert_lines"
        is_replace = self.action_type == "replace_lines"
        is_write = self.action_type == "write_file"
        has_line = self.line_number is not None
        has_end_line = self.end_line_number is not None
        has_content = self.new_content is not None
        has_target = self.target in ("design", "testbench")

        if is_edit and (not has_line or not has_content or not has_target):
            raise ValueError("edit_line requires target, line_number and new_content")
            
        if is_insert and (not has_line or not has_content or not has_target):
            raise ValueError("insert_lines requires target, line_number and new_content")
            
        if is_replace and (not has_line or not has_end_line or not has_content or not has_target):
            raise ValueError("replace_lines requires target, line_number, end_line_number, and new_content")

        if is_append and (not has_content or has_line or not has_target):
            raise ValueError(
                "append_line requires target and new_content only"
            )

        if is_write and (not has_content or has_line or not has_target):
            raise ValueError(
                "write_file requires target and new_content only"
            )

        if (not is_edit and not is_append and not is_insert and not is_replace and not is_write) and (
            has_line or has_end_line or has_content
        ):
            raise ValueError(
                "line_number/end_line_number/new_content are only valid for edit/append/insert/replace/write actions"
            )
        return self


class ChipforgeObservation(Observation):
    """Observation returned by the ChipForge environment.

    Designed as a self-contained Markov state for RL training.
    Always includes the current design code.
    Tool logs are only populated when explicitly requested via:
        - view_synthesis_log: Shows synthesis logs from last run
        - view_lint_log: Shows lint logs from last run
        - view_simulation_log: Shows simulation logs from last run
    """

    # ── Always populated (Markov state core) ─────────────────────────────
    design_code: str = Field(
        default="",
        description="Current design code with line numbers (always present)",
    )
    sim_status: Literal["not_run", "pass", "fail", "error"] = Field(
        default="not_run",
        description="Latest simulation status for current design snapshot",
    )
    synth_status: Literal["not_run", "pass", "warning", "error"] = Field(
        default="not_run",
        description="Latest synthesis status for current design snapshot",
    )
    lint_status: Literal["not_run", "clean", "warning", "error"] = Field(
        default="not_run",
        description="Latest lint status for current design snapshot",
    )
    error_summary: str = Field(
        default="",
        description="One-line summary of the most relevant diagnostic",
    )
    task_description: str = Field(
        default="",
        description="Natural language description of the loaded debug task",
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
