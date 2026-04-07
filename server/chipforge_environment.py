# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
ChipForge RTL Debugging Environment — RL-optimized.

Key RL design decisions:
  1. OBSERVATION is a self-contained Markov state:
     - RTL code always included (agent never wastes steps viewing)
     - All tool statuses always present
     - Action result feedback at every step

  2. REWARD uses potential-based shaping (Andrew Ng's theorem):
     - per_step_reward = new_potential - old_potential - step_cost
     - Potential = quality score based on tool statuses (0.0 to 1.0)
     - Gives dense learning signal without changing optimal policy
     - Terminal bonus on submit

  3. STATUS is NOT reset on edit:
     - Prevents reward hacking (edit → artificially drop potential → re-run → gain)
     - Agent must re-run tools to confirm fix worked
     - On submit, all stale tools are automatically re-run
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

try:
    from ..models import ChipforgeAction, ChipforgeObservation
except ImportError:
    from models import ChipforgeAction, ChipforgeObservation


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_STEPS = 20
LOG_TRUNCATE = 2000  # max chars in observation logs
TOOL_TIMEOUT = 30  # seconds
STEP_COST = 0.02  # per-step penalty to encourage efficiency

# Tool paths — absolute for OSS CAD Suite in Docker
VERILATOR = os.environ.get("VERILATOR_PATH", "/opt/oss-cad-suite/bin/verilator")
YOSYS = os.environ.get("YOSYS_PATH", "/opt/oss-cad-suite/bin/yosys")

VALID_ACTIONS = {
    "view_testbench",
    "view_logs",
    "run_simulation",
    "run_synthesis",
    "run_lint",
    "edit_line",
    "submit",
}

TASKS_DIR = Path(__file__).parent / "tasks"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _discover_tasks() -> List[Path]:
    """Return sorted list of task directories under TASKS_DIR."""
    if not TASKS_DIR.is_dir():
        return []
    return sorted(
        p for p in TASKS_DIR.iterdir() if p.is_dir() and (p / "task.json").exists()
    )


def _run_tool(cmd: List[str], cwd: str, timeout: int = TOOL_TIMEOUT) -> Dict[str, Any]:
    """Run a shell command and return stdout, stderr, returncode."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1,
        }
    except FileNotFoundError as e:
        return {
            "stdout": "",
            "stderr": f"Tool not found: {e}",
            "returncode": -1,
        }


def _extract_error_summary(stderr: str, stdout: str = "") -> str:
    """Extract a one-line error summary from tool output."""
    combined = stderr + "\n" + stdout
    for line in combined.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(kw in lower for kw in ("error", "syntax", "warning", "latch", "fail")):
            return line[:200]
    for line in stderr.splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class ChipforgeEnvironment(Environment):
    """
    RTL Debugging Environment for RL training.

    Quality potential (φ) breakdown:
      +0.2  code compiles (no syntax errors)
      +0.3  simulation output matches expected
      +0.3  synthesis clean (no warnings/errors)
      +0.2  lint clean

    Per-step reward = φ(s') - φ(s) - step_cost
    Terminal bonus on submit = +0.1 if all pass, -0.2 if premature
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self) -> None:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._tasks = _discover_tasks()

        # Episode state
        self._rtl_lines: List[str] = []
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

        # Working directory
        self._workdir: Optional[str] = None

        # Episode signals
        self._done: bool = False
        self._potential: float = 0.0  # current quality potential
        self._cumulative_reward: float = 0.0  # sum of per-step rewards

    # -----------------------------------------------------------------------
    # Potential-based reward
    # -----------------------------------------------------------------------

    def _compute_potential(self) -> float:
        """
        Quality potential φ(s) based on current tool statuses.
        Range: [0.0, 1.0]. Only counts tools that have been run.
        """
        phi = 0.0

        # +0.2 if code compiles (sim ran and didn't error)
        if self._sim_status in ("pass", "fail"):
            phi += 0.2

        # +0.3 if simulation passes
        if self._sim_status == "pass":
            phi += 0.3

        # +0.3 if synthesis is clean
        if self._synth_status == "pass":
            phi += 0.3

        # +0.2 if lint is clean
        if self._lint_status == "clean":
            phi += 0.2

        return phi

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
            random.seed(seed)

        if not self._tasks:
            raise RuntimeError(f"No tasks found in {TASKS_DIR}")

        # Pick task
        task_name = kwargs.get("task_name")
        if task_name:
            task_dir = TASKS_DIR / task_name
            if not task_dir.is_dir():
                raise ValueError(f"Task not found: {task_name}")
        else:
            task_dir = random.choice(self._tasks)

        # Load files
        with open(task_dir / "task.json") as f:
            self._task_meta = json.load(f)
        with open(task_dir / "design_buggy.v") as f:
            self._rtl_lines = f.read().splitlines()
        with open(task_dir / "testbench.v") as f:
            self._testbench_code = f.read()
        with open(task_dir / "design_golden.v") as f:
            self._golden_code = f.read()

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
        self._done = False
        self._potential = 0.0
        self._cumulative_reward = 0.0

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
        action_type = action.action_type.strip().lower()

        if action_type not in VALID_ACTIONS:
            return self._make_obs(
                last_action=action_type,
                action_result=f"Unknown action. Valid: {sorted(VALID_ACTIONS)}",
                step_reward=-STEP_COST,
            )

        # Snapshot potential BEFORE action
        old_potential = self._potential

        # Dispatch action
        obs_extras: Dict[str, Any] = {}
        action_result = ""

        if action_type == "view_testbench":
            obs_extras["testbench_code"] = self._testbench_code
            action_result = f"Testbench loaded ({self._testbench_code.count(chr(10))+1} lines)."

        elif action_type == "view_logs":
            log_type = (action.log_type or "sim").strip().lower()
            log_map = {"sim": self._sim_log, "synth": self._synth_log, "lint": self._lint_log}
            log = log_map.get(log_type, "")
            obs_extras["log_output"] = log[:LOG_TRUNCATE]
            action_result = f"Viewing {log_type} log ({len(log)} chars)."

        elif action_type == "run_simulation":
            self._do_simulation()
            obs_extras["log_output"] = self._sim_log[:LOG_TRUNCATE]
            action_result = f"Simulation: {self._sim_status}. {self._error_summary}"

        elif action_type == "run_synthesis":
            self._do_synthesis()
            obs_extras["log_output"] = self._synth_log[:LOG_TRUNCATE]
            action_result = f"Synthesis: {self._synth_status}. {self._error_summary}"

        elif action_type == "run_lint":
            self._do_lint()
            obs_extras["log_output"] = self._lint_log[:LOG_TRUNCATE]
            action_result = f"Lint: {self._lint_status}. {self._error_summary}"

        elif action_type == "edit_line":
            action_result = self._do_edit(action.line_number, action.new_content)

        elif action_type == "submit":
            action_result = self._do_submit()

        # Compute new potential
        new_potential = self._compute_potential()
        self._potential = new_potential

        # Per-step reward = potential delta - step cost + terminal bonus
        step_reward = (new_potential - old_potential) - STEP_COST

        # Terminal bonus/penalty on submit
        if action_type == "submit":
            if new_potential >= 1.0:
                step_reward += 0.1  # bonus for perfect fix
            elif new_potential >= 0.5:
                step_reward += 0.0  # partial fix, no bonus
            else:
                step_reward -= 0.2  # premature submit penalty

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

    def _do_simulation(self) -> None:
        """Compile + run with Verilator."""
        if not self._workdir:
            self._error_summary = "No working directory."
            return

        # Write current files
        design_path = os.path.join(self._workdir, "design.v")
        tb_path = os.path.join(self._workdir, "testbench.v")
        with open(design_path, "w") as f:
            f.write("\n".join(self._rtl_lines) + "\n")
        with open(tb_path, "w") as f:
            f.write(self._testbench_code)

        # Clean previous build
        obj_dir = os.path.join(self._workdir, "obj_dir")
        if os.path.isdir(obj_dir):
            shutil.rmtree(obj_dir, ignore_errors=True)

        # Compile
        compile_result = _run_tool(
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
        )

        if compile_result["returncode"] != 0:
            self._sim_status = "error"
            self._sim_log = (
                "=== COMPILATION FAILED ===\n"
                + compile_result["stderr"] + "\n"
                + compile_result["stdout"]
            )
            self._error_summary = _extract_error_summary(
                compile_result["stderr"], compile_result["stdout"]
            )
            self._code_dirty = False
            return

        # Run simulation
        sim_binary = os.path.join(self._workdir, "obj_dir", "Vsim")
        if not os.path.isfile(sim_binary):
            self._sim_status = "error"
            self._sim_log = "Simulation binary not found."
            self._error_summary = "Simulation binary not found."
            return

        run_result = _run_tool([sim_binary], cwd=self._workdir)
        self._sim_log = run_result["stdout"] + run_result["stderr"]
        self._code_dirty = False

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

    def _do_synthesis(self) -> None:
        """Run Yosys synthesis."""
        if not self._workdir:
            self._error_summary = "No working directory."
            return

        design_path = os.path.join(self._workdir, "design.v")
        with open(design_path, "w") as f:
            f.write("\n".join(self._rtl_lines) + "\n")

        yosys_script = (
            "read_verilog design.v; "
            "hierarchy -auto-top; "
            "proc; opt; memory; opt; fsm; opt; "
            "write_verilog synth_out.v"
        )

        result = _run_tool(
            [YOSYS, "-p", yosys_script],
            cwd=self._workdir,
        )

        full_log = result["stdout"] + "\n" + result["stderr"]
        self._synth_log = full_log

        if result["returncode"] != 0:
            self._synth_status = "error"
            self._error_summary = _extract_error_summary(
                result["stderr"], result["stdout"]
            )
        else:
            lower_log = full_log.lower()
            warning_patterns = ["latch inferred", "found and reported", "warning:"]
            has_warning = any(p in lower_log for p in warning_patterns)

            if has_warning:
                self._synth_status = "warning"
                self._error_summary = _extract_error_summary(
                    result["stderr"], result["stdout"]
                ) or "Synthesis completed with warnings."
            else:
                self._synth_status = "pass"
                self._error_summary = "Synthesis clean."

    def _do_lint(self) -> None:
        """Run Verilator lint."""
        if not self._workdir:
            self._error_summary = "No working directory."
            return

        design_path = os.path.join(self._workdir, "design.v")
        with open(design_path, "w") as f:
            f.write("\n".join(self._rtl_lines) + "\n")

        result = _run_tool(
            [VERILATOR, "--lint-only", "design.v"],
            cwd=self._workdir,
        )

        lint_output = result["stderr"] + "\n" + result["stdout"]
        self._lint_log = lint_output

        if result["returncode"] != 0:
            lower = lint_output.lower()
            self._lint_status = "error" if "error" in lower else "warning"
            self._error_summary = _extract_error_summary(
                result["stderr"], result["stdout"]
            )
        else:
            if "warning" in lint_output.lower():
                self._lint_status = "warning"
                self._error_summary = _extract_error_summary(
                    result["stderr"], result["stdout"]
                )
            else:
                self._lint_status = "clean"
                self._error_summary = "Lint clean."

    def _do_edit(self, line_number: Optional[int], new_content: Optional[str]) -> str:
        """Edit a single line. Returns action_result string."""
        if line_number is None or new_content is None:
            self._error_summary = "edit_line requires line_number and new_content."
            return self._error_summary

        if line_number < 1 or line_number > len(self._rtl_lines):
            self._error_summary = (
                f"Invalid line_number {line_number}. "
                f"Valid range: 1–{len(self._rtl_lines)}."
            )
            return self._error_summary

        old_line = self._rtl_lines[line_number - 1]
        self._rtl_lines[line_number - 1] = new_content
        self._code_dirty = True

        result = (
            f"Line {line_number} updated. "
            f"Old: '{old_line.strip()}' → New: '{new_content.strip()}'"
        )
        self._error_summary = result

        # NOTE: We do NOT reset tool statuses here.
        # This is intentional for RL — the potential stays the same
        # after edit, so reward delta = -step_cost. The agent must
        # re-run tools to measure the impact of the edit.
        return result

    def _do_submit(self) -> str:
        """Submit solution. Re-runs any stale tools, then marks done."""
        self._done = True

        # Force re-run all tools on the current (possibly edited) code
        self._do_simulation()
        self._do_synthesis()
        self._do_lint()

        return (
            f"Submitted. sim={self._sim_status}, "
            f"synth={self._synth_status}, lint={self._lint_status}."
        )

    # -----------------------------------------------------------------------
    # Observation builder
    # -----------------------------------------------------------------------

    def _numbered_rtl(self) -> str:
        """Return RTL code with line numbers."""
        return "\n".join(f"{i:3d}: {line}" for i, line in enumerate(self._rtl_lines, 1))

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
            rtl_code=self._numbered_rtl(),
            task_description=self._task_meta.get("description", ""),
            sim_status=self._sim_status,
            synth_status=self._synth_status,
            lint_status=self._lint_status,

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
        )

    def close(self) -> None:
        """Clean up."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None
