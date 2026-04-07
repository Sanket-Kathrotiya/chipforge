---
title: ChipForge RTL Debugging Environment
emoji: 🔧
colorFrom: purple
colorTo: green
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
  - verilog
  - rtl
  - semiconductor
---

# ChipForge — RTL Debugging Environment

An OpenEnv environment where an AI agent debugs buggy Verilog RTL code using real EDA tools (**Verilator** for simulation/lint, **Yosys** for synthesis).

The agent receives buggy Verilog, inspects code, runs tools, reads error logs, edits lines to fix bugs, and submits the corrected design for grading.

## Quick Start

```python
from chipforge import ChipforgeAction, ChipforgeEnv

try:
    env = ChipforgeEnv.from_docker_image("chipforge-env:latest")

    # Start a new episode (loads a random buggy RTL task)
    result = env.reset()
    print(f"Task: {result.observation.task_description}")

    # View the buggy RTL
    result = env.step(ChipforgeAction(action_type="view_rtl"))
    print(result.observation.rtl_code)

    # Run simulation to see errors
    result = env.step(ChipforgeAction(action_type="run_simulation"))
    print(f"Status: {result.observation.sim_status}")
    print(f"Error: {result.observation.error_summary}")

    # Fix the bug
    result = env.step(ChipforgeAction(
        action_type="edit_line",
        line_number=13,
        new_content="assign sum = x1 ^ cin;"
    ))

    # Verify the fix
    result = env.step(ChipforgeAction(action_type="run_simulation"))
    print(f"Status: {result.observation.sim_status}")

    # Submit solution
    result = env.step(ChipforgeAction(action_type="submit"))
    print(f"Reward: {result.observation.reward}")

finally:
    env.close()
```

## Action Space

| Action | Parameters | Description |
|--------|-----------|-------------|
| `view_rtl` | — | View current RTL code with line numbers |
| `view_testbench` | — | View the testbench code |
| `view_logs` | `log_type`: sim/synth/lint | View output from last tool run |
| `run_simulation` | — | Compile + simulate with Verilator |
| `run_synthesis` | — | Synthesize with Yosys |
| `run_lint` | — | Run Verilator lint checks |
| `edit_line` | `line_number`, `new_content` | Replace a single line of RTL |
| `submit` | — | Submit fix and get final reward |

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `rtl_code` | str | Current RTL (populated by `view_rtl`) |
| `testbench_code` | str | Testbench (populated by `view_testbench`) |
| `log_output` | str | Tool output (populated by `view_logs`) |
| `sim_status` | str | `not_run` / `pass` / `fail` / `error` |
| `synth_status` | str | `not_run` / `pass` / `warning` / `error` |
| `lint_status` | str | `not_run` / `clean` / `warning` / `error` |
| `error_summary` | str | One-line error hint |
| `task_description` | str | Description of the current task |
| `step_count` | int | Steps taken so far |
| `max_steps` | int | Maximum allowed steps (20) |

## Reward

| Component | Value | Condition |
|-----------|-------|-----------|
| Compiles | +0.2 | No syntax errors |
| Simulation passes | +0.3 | Output matches expected truth table |
| Synthesis clean | +0.3 | No warnings (e.g., no latches) |
| Lint clean | +0.2 | No lint warnings |
| Step penalty | -0.01/step | Encourages efficiency |

Maximum reward: **1.0** (all checks pass, minimal steps).

## Tasks

| # | Name | Difficulty | Bug Type |
|---|------|-----------|----------|
| 1 | `task_easy_syntax` | Easy | Incomplete XOR expression |
| 2 | `task_easy_missing_semicolon` | Easy | Missing semicolon on wire declaration |
| 3 | `task_medium_logic_bug` | Medium | Wrong operator in sum computation |
| 4 | `task_medium_wrong_operator` | Medium | XOR instead of AND in carry logic |
| 5 | `task_hard_latch_inference` | Hard | Missing else branch → latch inferred |

## Tools Used

| Tool | Role | Installed via |
|------|------|--------------|
| **Verilator** | Simulation + Linting | OSS CAD Suite |
| **Yosys** | Synthesis | OSS CAD Suite |

Both tools are bundled in the Docker image via [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build).

## Building & Running

```bash
# Build Docker image
docker build -t chipforge-env:latest -f server/Dockerfile .

# Run locally (for development)
uvicorn chipforge.server.app:app --reload

# Deploy to Hugging Face Spaces
openenv push
```

## Project Structure

```
chipforge/
├── __init__.py              # Module exports
├── models.py                # Action + Observation models
├── client.py                # ChipforgeEnv client
├── openenv.yaml             # OpenEnv manifest
├── pyproject.toml           # Dependencies
└── server/
    ├── app.py               # FastAPI application
    ├── chipforge_environment.py  # Core environment logic
    ├── Dockerfile           # Container with Verilator + Yosys
    └── tasks/               # RTL debugging tasks
        ├── task_easy_syntax/
        ├── task_easy_missing_semicolon/
        ├── task_medium_logic_bug/
        ├── task_medium_wrong_operator/
        └── task_hard_latch_inference/
```

## Example Agent Episode

```
reset()  →  Task: "Fix the syntax error in the full adder RTL"

view_rtl  →  see buggy code with line numbers
run_simulation  →  sim_status="error", error_summary="syntax error near '^'"
edit_line(13, "assign sum = x1 ^ cin;")  →  "Line 13 updated"
run_simulation  →  sim_status="pass"
run_synthesis  →  synth_status="pass"
submit  →  reward=0.93
```
