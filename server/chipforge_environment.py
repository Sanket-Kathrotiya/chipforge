# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
ChipForge Design Environment — RL-optimized.
This environment trains autonomous agents to write, debug, and optimize Verilog (RTL) code.
The tasks range from fixing subtle logic bugs in existing code to generating complete designs and testbenches from scratch.

Key RL Design Decisions:
  1. OBSERVATION is a self-contained Markov state:
     - Design code is always included (the agent never wastes steps viewing files).
     - Tool statuses are continuously available.
     - Every step provides immediate action result feedback.

    2. REWARD is a discrete history-based step reward mapping into [0, 1]:
       - Passing tools gives positive rewards (0.3 on 1st try, 0.2 on 2nd, 0.1 later).
       - Failing tools penalizes the RL state (-0.5).
       - Running tools on already-passed unmodified code penalizes (-0.05).
       - General actions carry a fixed negative step cost.
       - A mock LLM judge rewards the final submission.

  3. STATUS is explicitly NOT reset upon code edits:
     - Prevents reward hacking (e.g., editing just to force score modifications).
     - Forces the agent to re-run tools to verify that its modifications worked.
     - On submit, all tools are automatically re-run on the latest code to prevent stale state submissions.
"""

import json
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from .constants import (
    LOG_TRUNCATE,
    MAX_STEPS,
    STEP_COST,
    TASKS_DIR,
    TOOL_TIMEOUT,
    VALID_ACTIONS,
    VERILATOR,
    YOSYS,
)
from .reward import eval_tool_reward, eval_llm_submit, normalize_reward
from .utils import categorize_tasks, discover_tasks, extract_error_summary, run_tool

try:
    from ..models import ChipforgeAction, ChipforgeObservation
except ImportError:
    from models import ChipforgeAction, ChipforgeObservation


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class ChipforgeEnvironment(Environment):
    """
    RTL Debugging Environment for RL training.

    Reward calculation uses a discrete, history-based mapping:
      +0.3  tool sequence passed (1st attempt)
      +0.2  tool sequence passed (2nd attempt)
      +0.1  tool sequence passed (3+ attempts)
      -0.5  tool sequence failed
      -0.05 re-running already successful tools

    Step rewards are evaluated, reduced by fixed step cost, and normalized to [0, 1].
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = False

    def __init__(self) -> None:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._tasks = discover_tasks()
        self._rng = random.Random()
        self._episode_num = 0

        # Categorize tasks
        self._categorized_tasks = categorize_tasks(self._tasks)

        # Episode state
        self._design_lines: List[str] = []
        self._testbench_code: str = ""
        self._task_meta: Dict[str, Any] = {}
        self._golden_code: str = ""
        self._expected_output: str = ""

        # Tool statuses & logs
        self._sim_status: str = "not_run"
        self._synth_status: str = "not_run"
        self._lint_status: str = "not_run"
        self._sim_log: str = ""
        self._synth_log: str = ""
        self._lint_log: str = ""
        self._error_summary: str = ""

        # Track if code has been edited since last tool run
        self._code_dirty: bool = False
        self._code_hash: str = ""
        self._sim_validated_hash: str = ""
        self._synth_validated_hash: str = ""
        self._lint_validated_hash: str = ""

        # Working directory
        self._workdir: Optional[str] = None

        # Episode signals
        self._done: bool = False
        self._cumulative_reward: float = 0.0  # sum of per-step rewards

        # Tool attempt states
        self._sim_attempts: int = 0
        self._synth_attempts: int = 0
        self._lint_attempts: int = 0

    # -----------------------------------------------------------------------
    # Utils
    # -----------------------------------------------------------------------

    def _current_code_hash(self) -> str:
        return str(hash("\n".join(self._design_lines) + "\n" + self._testbench_code))

    # -----------------------------------------------------------------------
    # OpenEnv Interface
    # -----------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> ChipforgeObservation:
        """Load a task and return initial observation with RTL code."""

        # Clean up
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)

        if seed is not None:
            self._rng.seed(seed)

        if not self._tasks:
            raise RuntimeError(f"No tasks found in {TASKS_DIR}")

        # Increment episode count
        self._episode_num += 1

        # Pick task
        task_name = kwargs.get("task_name")
        if task_name:
            task_dir = TASKS_DIR / task_name
            if not task_dir.is_dir():
                raise ValueError(f"Task not found: {task_name}")
        else:
            # Curriculum learning: probabilistically pick difficulty based on episode
            if self._episode_num <= 20:
                weights = {"easy": 0.8, "medium": 0.2, "hard": 0.0}
            elif self._episode_num <= 50:
                weights = {"easy": 0.4, "medium": 0.5, "hard": 0.1}
            else:
                weights = {"easy": 0.2, "medium": 0.4, "hard": 0.4}

            choices = ["easy", "medium", "hard"]
            probs = [weights[c] for c in choices]
            
            chosen_diff = self._rng.choices(choices, weights=probs, k=1)[0]
            if not self._categorized_tasks.get(chosen_diff):
                task_dir = self._rng.choice(self._tasks)
            else:
                task_dir = self._rng.choice(self._categorized_tasks[chosen_diff])

        # Load files
        with open(task_dir / "task.json") as f:
            self._task_meta = json.load(f)

        design_buggy = task_dir / "design_buggy.v"
        if design_buggy.is_file():
            with open(design_buggy) as f:
                self._design_lines = f.read().splitlines()
        else:
            self._design_lines = []

        testbench = task_dir / "testbench.v"
        if testbench.is_file():
            with open(testbench) as f:
                self._testbench_code = f.read()
        else:
            self._testbench_code = ""

        design_golden = task_dir / "design_golden.v"
        if design_golden.is_file():
            with open(design_golden) as f:
                self._golden_code = f.read()
        else:
            self._golden_code = ""

        self._expected_output = self._task_meta.get("expected_sim_output", "")

        # Reset state
        eid = episode_id or str(uuid4())
        self._state = State(episode_id=eid, step_count=0)
        self._sim_status = "not_run"
        self._synth_status = "not_run"
        self._lint_status = "not_run"
        self._sim_log = ""
        self._synth_log = ""
        self._lint_log = ""
        self._error_summary = ""
        self._code_dirty = False
        self._code_hash = self._current_code_hash()
        self._sim_validated_hash = ""
        self._synth_validated_hash = ""
        self._lint_validated_hash = ""
        self._done = False
        self._cumulative_reward = 0.0
        self._sim_attempts = 0
        self._synth_attempts = 0
        self._lint_attempts = 0

        # Fresh workdir
        self._workdir = tempfile.mkdtemp(prefix="chipforge_")

        return self._make_obs(
            last_action="reset",
            action_result=f"Loaded task: {self._task_meta.get('description', '')}",
            step_reward=0.0,
        )

    def step(  # type: ignore[override]
        self,
        action: ChipforgeAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> ChipforgeObservation:
        """Execute one action and return observation with per-step reward."""

        if self._done:
            return self._make_obs(
                last_action="none",
                action_result="Episode already finished. Call reset().",
                step_reward=0.0,
            )

        self._state.step_count += 1
        timeout = TOOL_TIMEOUT if timeout_s is None else max(1, int(timeout_s))
        action_type = action.action_type.strip().lower()

        if action_type not in VALID_ACTIONS:
            return self._make_obs(
                last_action=action_type,
                action_result=f"Unknown action. Valid: {sorted(VALID_ACTIONS)}",
                step_reward=-STEP_COST,
            )

        # Dispatch action
        obs_extras: Dict[str, Any] = {}
        action_result = ""
        raw_reward = 0.0

        if action_type == "view_design":
            # RTL code is returned by default in ChipforgeObservation
            action_result = f"Design loaded ({len(self._design_lines)} lines)."

        elif action_type == "view_testbench":
            obs_extras["testbench_code"] = self._testbench_code
            action_result = f"Testbench loaded ({self._testbench_code.count(chr(10))+1} lines)."

        elif action_type == "view_synthesis_log":
            obs_extras["log_output"] = self._synth_log[:LOG_TRUNCATE]
            action_result = f"Viewing synthesis log ({len(self._synth_log)} chars)."

        elif action_type == "view_lint_log":
            obs_extras["log_output"] = self._lint_log[:LOG_TRUNCATE]
            action_result = f"Viewing lint log ({len(self._lint_log)} chars)."

        elif action_type == "view_simulation_log":
            obs_extras["log_output"] = self._sim_log[:LOG_TRUNCATE]
            action_result = f"Viewing simulation log ({len(self._sim_log)} chars)."

        elif action_type == "run_simulation":
            sim_fresh = (self._sim_validated_hash == self._code_hash)
            if sim_fresh and self._sim_status == "pass":
                raw_reward = -0.05
                action_result = f"Simulation already passed for this code. (-0.05 reward)"
                obs_extras["log_output"] = self._sim_log[:LOG_TRUNCATE]
            else:
                self._sim_attempts += 1
                self._do_simulation(timeout=timeout)
                raw_reward = eval_tool_reward(self._sim_status, self._sim_attempts)
                obs_extras["log_output"] = self._sim_log[:LOG_TRUNCATE]
                action_result = f"Simulation: {self._sim_status}. {self._error_summary}"

        elif action_type == "run_synthesis":
            synth_fresh = (self._synth_validated_hash == self._code_hash)
            if synth_fresh and self._synth_status == "pass":
                raw_reward = -0.05
                action_result = f"Synthesis already passed for this code. (-0.05 reward)"
                obs_extras["log_output"] = self._synth_log[:LOG_TRUNCATE]
            else:
                self._synth_attempts += 1
                self._do_synthesis(timeout=timeout)
                raw_reward = eval_tool_reward(self._synth_status, self._synth_attempts)
                obs_extras["log_output"] = self._synth_log[:LOG_TRUNCATE]
                action_result = f"Synthesis: {self._synth_status}. {self._error_summary}"

        elif action_type == "run_lint":
            lint_fresh = (self._lint_validated_hash == self._code_hash)
            if lint_fresh and self._lint_status == "clean":
                raw_reward = -0.05
                action_result = f"Lint already clean for this code. (-0.05 reward)"
                obs_extras["log_output"] = self._lint_log[:LOG_TRUNCATE]
            else:
                self._lint_attempts += 1
                self._do_lint(timeout=timeout)
                raw_reward = eval_tool_reward(self._lint_status, self._lint_attempts)
                obs_extras["log_output"] = self._lint_log[:LOG_TRUNCATE]
                action_result = f"Lint: {self._lint_status}. {self._error_summary}"

        elif action_type == "edit_line":
            action_result = self._do_edit(action.target, action.line_number, action.new_content)

        elif action_type == "append_line":
            action_result = self._do_append(action.target, action.new_content)
            
        elif action_type == "insert_lines":
            action_result = self._do_insert_lines(action.target, action.line_number, action.new_content)
            
        elif action_type == "replace_lines":
            action_result = self._do_replace_lines(action.target, action.line_number, action.end_line_number, action.new_content)

        elif action_type == "write_file":
            action_result = self._do_write_file(action.target, action.new_content)

        elif action_type == "submit":
            action_result = self._do_submit(timeout=timeout)
            raw_reward = eval_llm_submit(
                design_code="\n".join(self._design_lines),
                testbench_code=self._testbench_code,
                golden_code=self._golden_code,
                task_desc=self._task_meta.get("description", "")
            )

        # Base step cost is universally applied to raw logic
        raw_reward -= STEP_COST

        # Normalize logic maps [-1.0, 1.0] to [0.0, 1.0] if requested, explicitly leaving boundaries intact
        step_reward = normalize_reward(raw_reward)

        self._cumulative_reward += step_reward

        # Check step limit
        if self._state.step_count >= MAX_STEPS and not self._done:
            self._done = True
            action_result += " Step limit reached."

        return self._make_obs(
            last_action=action_type,
            action_result=action_result.strip(),
            step_reward=step_reward,
            **obs_extras,
        )

    @property
    def state(self) -> State:
        return self._state

    # -----------------------------------------------------------------------
    # Action Handlers
    # -----------------------------------------------------------------------

    def _do_simulation(self, timeout: int = TOOL_TIMEOUT) -> None:
        """Compile + run with Verilator."""
        if not self._workdir:
            self._error_summary = "No working directory."
            return

        if not self._design_lines:
            self._sim_status = "error"
            self._sim_log = "No RTL design present. Build design first."
            self._error_summary = "No RTL design present. Add lines with append_line."
            self._sim_validated_hash = self._code_hash
            return

        if not self._testbench_code.strip():
            self._sim_status = "error"
            self._sim_log = "No testbench present. Build testbench first."
            self._error_summary = (
                "No testbench present. Add lines with append_testbench_line."
            )
            self._sim_validated_hash = self._code_hash
            return

        # Write current files
        design_path = os.path.join(self._workdir, "design.v")
        tb_path = os.path.join(self._workdir, "testbench.v")
        with open(design_path, "w") as f:
            f.write("\n".join(self._design_lines) + "\n")
        with open(tb_path, "w") as f:
            f.write(self._testbench_code)

        # Clean previous build
        obj_dir = os.path.join(self._workdir, "obj_dir")
        if os.path.isdir(obj_dir):
            shutil.rmtree(obj_dir, ignore_errors=True)

        # Compile
        compile_result = run_tool(
            [
                VERILATOR,
                "--prefix", "Vsim",
                "--binary",
                "--build-jobs", "0",
                "--build",
                "--quiet-build",
                "-Wno-fatal",
                "--timescale", "1ns/1ns",
                "design.v",
                "testbench.v",
            ],
            cwd=self._workdir,
            timeout=timeout,
        )

        if compile_result["returncode"] != 0:
            self._sim_status = "error"
            self._sim_log = (
                "=== COMPILATION FAILED ===\n"
                + compile_result["stderr"] + "\n"
                + compile_result["stdout"]
            )
            self._error_summary = extract_error_summary(
                compile_result["stderr"], compile_result["stdout"]
            )
            self._code_dirty = False
            self._sim_validated_hash = self._code_hash
            return

        # Run simulation
        sim_binary = os.path.join(self._workdir, "obj_dir", "Vsim")
        if not os.path.isfile(sim_binary):
            self._sim_status = "error"
            self._sim_log = "Simulation binary not found."
            self._error_summary = "Simulation binary not found."
            return

        run_result = run_tool([sim_binary], cwd=self._workdir, timeout=timeout)
        self._sim_log = run_result["stdout"] + run_result["stderr"]
        self._code_dirty = False
        self._sim_validated_hash = self._code_hash

        # Compare output
        if self._expected_output:
            actual = [
                l.strip() for l in run_result["stdout"].splitlines()
                if l.strip() and not l.strip().startswith("-")
            ]
            expected = [
                l.strip() for l in self._expected_output.splitlines()
                if l.strip() and not l.strip().startswith("-")
            ]
            if actual == expected:
                self._sim_status = "pass"
                self._error_summary = "Simulation passed — output matches expected."
            else:
                self._sim_status = "fail"
                self._error_summary = "Simulation output does not match expected."
        else:
            self._sim_status = "pass" if run_result["returncode"] == 0 else "fail"
            self._error_summary = ""

    def _do_synthesis(self, timeout: int = TOOL_TIMEOUT) -> None:
        """Run Yosys synthesis."""
        if not self._workdir:
            self._error_summary = "No working directory."
            return

        design_path = os.path.join(self._workdir, "design.v")
        with open(design_path, "w") as f:
            f.write("\n".join(self._design_lines) + "\n")

        yosys_script = (
            "read_verilog design.v; "
            "hierarchy -auto-top; "
            "proc; opt; memory; opt; fsm; opt; "
            "write_verilog synth_out.v"
        )

        result = run_tool(
            [YOSYS, "-p", yosys_script],
            cwd=self._workdir,
            timeout=timeout,
        )

        full_log = result["stdout"] + "\n" + result["stderr"]
        self._synth_log = full_log
        self._code_dirty = False

        if result["returncode"] != 0:
            self._synth_status = "error"
            self._error_summary = extract_error_summary(
                result["stderr"], result["stdout"]
            )
            self._synth_validated_hash = self._code_hash
        else:
            lower_log = full_log.lower()
            warning_patterns = ["latch inferred", "found and reported", "warning:"]
            has_warning = any(p in lower_log for p in warning_patterns)

            if has_warning:
                self._synth_status = "warning"
                self._error_summary = extract_error_summary(
                    result["stderr"], result["stdout"]
                ) or "Synthesis completed with warnings."
            else:
                self._synth_status = "pass"
                self._error_summary = "Synthesis clean."
            self._synth_validated_hash = self._code_hash

    def _do_lint(self, timeout: int = TOOL_TIMEOUT) -> None:
        """Run Verilator lint."""
        if not self._workdir:
            self._error_summary = "No working directory."
            return

        design_path = os.path.join(self._workdir, "design.v")
        with open(design_path, "w") as f:
            f.write("\n".join(self._design_lines) + "\n")

        result = run_tool(
            [VERILATOR, "--lint-only", "design.v"],
            cwd=self._workdir,
            timeout=timeout,
        )

        lint_output = result["stderr"] + "\n" + result["stdout"]
        self._lint_log = lint_output
        self._code_dirty = False

        if result["returncode"] != 0:
            lower = lint_output.lower()
            self._lint_status = "error" if "error" in lower else "warning"
            self._error_summary = extract_error_summary(
                result["stderr"], result["stdout"]
            )
            self._lint_validated_hash = self._code_hash
        else:
            if "warning" in lint_output.lower():
                self._lint_status = "warning"
                self._error_summary = extract_error_summary(
                    result["stderr"], result["stdout"]
                )
            else:
                self._lint_status = "clean"
                self._error_summary = "Lint clean."
            self._lint_validated_hash = self._code_hash

    def _do_edit(self, target: str, line_number: Optional[int], new_content: Optional[str]) -> str:
        """Edit a single line. Returns action_result string."""
        if line_number is None or new_content is None:
            self._error_summary = "edit_line requires line_number and new_content."
            return self._error_summary

        lines = self._design_lines if target == "design" else self._testbench_code.splitlines()

        if line_number < 1 or line_number > len(lines):
            self._error_summary = (
                f"Invalid line_number {line_number} for {target}. "
                f"Valid range: 1–{len(lines)}."
            )
            return self._error_summary

        old_line = lines[line_number - 1]
        lines[line_number - 1] = new_content
        
        if target == "design":
            self._design_lines = lines
        else:
            self._testbench_code = "\n".join(lines) + "\n"
            
        self._code_dirty = True
        self._code_hash = self._current_code_hash()

        result = (
            f"[{target}] Line {line_number} updated. "
            f"Old: '{old_line.strip()}' → New: '{new_content.strip()}'"
        )
        self._error_summary = result

        # NOTE: We do NOT reset tool statuses here.
        # This forces the agent to re-run tools to measure the impact of the edit and
        # avoids breaking the episode logic.
        return result

    def _do_append(self, target: str, new_content: Optional[str]) -> str:
        """Append a single line."""
        if new_content is None:
            self._error_summary = "append_line requires new_content."
            return self._error_summary

        lines = self._design_lines if target == "design" else self._testbench_code.splitlines()
        lines.append(new_content)
        
        if target == "design":
            self._design_lines = lines
        else:
            self._testbench_code = "\n".join(lines) + "\n"
            
        self._code_dirty = True
        self._code_hash = self._current_code_hash()
        result = f"[{target}] line appended at {len(lines)}."
        self._error_summary = result
        return result

    def _do_insert_lines(self, target: str, line_number: Optional[int], new_content: Optional[str]) -> str:
        """Insert multiple lines starting at line_number."""
        if line_number is None or new_content is None:
            self._error_summary = "insert_lines requires line_number and new_content."
            return self._error_summary

        lines = self._design_lines if target == "design" else self._testbench_code.splitlines()

        if line_number < 1 or line_number > len(lines) + 1:
            self._error_summary = (
                f"Invalid line_number {line_number} for {target}. "
                f"Valid range: 1–{len(lines) + 1}."
            )
            return self._error_summary
        
        insert_idx = line_number - 1
        lines_to_add = new_content.splitlines()
        lines[insert_idx:insert_idx] = lines_to_add
        
        if target == "design":
            self._design_lines = lines
        else:
            self._testbench_code = "\n".join(lines) + "\n"
            
        self._code_dirty = True
        self._code_hash = self._current_code_hash()
        
        result = f"[{target}] Inserted {len(lines_to_add)} lines at line {line_number}."
        self._error_summary = result
        return result

    def _do_replace_lines(self, target: str, line_number: Optional[int], end_line_number: Optional[int], new_content: Optional[str]) -> str:
        """Replace lines from line_number to end_line_number (inclusive) with new_content."""
        if line_number is None or end_line_number is None or new_content is None:
            self._error_summary = "replace_lines requires line_number, end_line_number, and new_content."
            return self._error_summary

        lines = self._design_lines if target == "design" else self._testbench_code.splitlines()

        if line_number < 1 or end_line_number > len(lines) or line_number > end_line_number:
            self._error_summary = (
                f"Invalid line range {line_number} to {end_line_number} for {target}. "
                f"Valid range: 1–{len(lines)}."
            )
            return self._error_summary

        start_idx = line_number - 1
        end_idx = end_line_number
        lines_to_add = new_content.splitlines()
        
        lines[start_idx:end_idx] = lines_to_add

        if target == "design":
            self._design_lines = lines
        else:
            self._testbench_code = "\n".join(lines) + "\n"
            
        self._code_dirty = True
        self._code_hash = self._current_code_hash()
        
        result = f"[{target}] Replaced {end_line_number - line_number + 1} lines (lines {line_number}-{end_line_number}) with {len(lines_to_add)} new lines."
        self._error_summary = result
        return result

    def _do_write_file(self, target: str, new_content: Optional[str]) -> str:
        """Write the entire file with new_content."""
        if new_content is None:
            self._error_summary = "write_file requires new_content."
            return self._error_summary

        lines = new_content.splitlines()
        if target == "design":
            self._design_lines = lines
        else:
            self._testbench_code = "\n".join(lines) + "\n"
            
        self._code_dirty = True
        self._code_hash = self._current_code_hash()
        
        result = f"[{target}] Wrote entire file ({len(lines)} lines)."
        self._error_summary = result
        return result

    def _do_submit(self, timeout: int = TOOL_TIMEOUT) -> str:
        """Submit solution. Re-runs any stale tools, then marks done."""
        self._done = True

        # Force re-run all tools on the current (possibly edited) code
        self._do_simulation(timeout=timeout)
        self._do_synthesis(timeout=timeout)
        self._do_lint(timeout=timeout)

        return (
            f"Submitted. sim={self._sim_status}, "
            f"synth={self._synth_status}, lint={self._lint_status}."
        )

    # -----------------------------------------------------------------------
    # Observation builder
    # -----------------------------------------------------------------------

    def _numbered_design(self) -> str:
        """Return RTL code with line numbers."""
        if not self._design_lines:
            return "  1: // RTL is currently empty. Use append_line to create it."
        return "\n".join(f"{i:3d}: {line}" for i, line in enumerate(self._design_lines, 1))

    def _make_obs(
        self,
        last_action: str,
        action_result: str,
        step_reward: float,
        **extra: Any,
    ) -> ChipforgeObservation:
        """Build a self-contained observation."""
        return ChipforgeObservation(
            # Always included — the Markov state
            design_code=self._numbered_design(),
            sim_status=self._sim_status,
            synth_status=self._synth_status,
            lint_status=self._lint_status,
            error_summary=self._error_summary,
            task_description=self._task_meta.get("description", ""),

            # Action feedback
            last_action=last_action,
            action_result=action_result,

            # Conditionally populated
            testbench_code=extra.get("testbench_code", ""),
            log_output=extra.get("log_output", ""),

            # RL signals
            step_count=self._state.step_count,
            max_steps=MAX_STEPS,
            reward=step_reward,
            cumulative_reward=self._cumulative_reward,
            done=self._done,
            metadata={
                "task_mode": self._task_meta.get("task_type", "debug_rtl"),
                "missing_files": {
                    "design_buggy.v": not bool(self._design_lines),
                    "testbench.v": not bool(self._testbench_code.strip()),
                    "design_golden.v": not bool(self._golden_code.strip()),
                },
                "code_dirty": self._code_dirty,
                "tool_freshness": {
                    "simulation": self._sim_validated_hash == self._code_hash,
                    "synthesis": self._synth_validated_hash == self._code_hash,
                    "lint": self._lint_validated_hash == self._code_hash,
                },
                "logs_available": {
                    "simulation": bool(self._sim_log),
                    "synthesis": bool(self._synth_log),
                    "lint": bool(self._lint_log),
                },
            },
        )

    def close(self) -> None:
        """Clean up."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None
