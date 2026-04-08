"""
Helper utilities for the ChipForge server environment.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .constants import TASKS_DIR, TOOL_TIMEOUT


def discover_tasks() -> List[Path]:
    """Return sorted list of task directories under TASKS_DIR (recursive)."""
    if not TASKS_DIR.is_dir():
        return []
    return sorted(
        p.parent
        for p in TASKS_DIR.rglob("task.json")
        if p.is_file() and p.parent.is_dir()
    )


def categorize_tasks(tasks: List[Path]) -> Dict[str, List[Path]]:
    """Organize tasks into difficulty categories."""
    categorized_tasks = {"easy": [], "medium": [], "hard": []}
    for task in tasks:
        try:
            with open(task / "task.json", "r") as f:
                meta = json.load(f)
                diff = meta.get("difficulty", "medium").lower()
                if diff in categorized_tasks:
                    categorized_tasks[diff].append(task)
                else:
                    categorized_tasks["medium"].append(task)
        except Exception:
            categorized_tasks["medium"].append(task)
    return categorized_tasks


def run_tool(cmd: List[str], cwd: str, timeout: int = TOOL_TIMEOUT) -> Dict[str, Any]:
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


def extract_error_summary(stderr: str, stdout: str = "") -> str:
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
