#!/usr/bin/env python3
"""
Inference Script for ChipForge RTL Debugging Environment
===================================
MANDATORY
- Before submitting, ensure the following variables are defined in your
  environment configuration:
    API_BASE_URL       The API endpoint for the LLM.
    MODEL_NAME         The model identifier to use for inference.
    HF_TOKEN           Your Hugging Face / API key.
    IMAGE_NAME         The name of the local image to use for the environment
                       if you are using from_docker_image() method

- Defaults are set only for API_BASE_URL and MODEL_NAME
    (and should reflect your active inference setup):
    API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
    MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")

- The inference script must be named `inference.py` and placed in the root
  directory of the project
- Participants must use OpenAI Client for all LLM calls using above variables

STDOUT FORMAT
- The script must emit exactly three line types to stdout, in this order:

    [START] task=<task_name> env=<benchmark> model=<model_name>
    [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>

  Rules:
    - One [START] line at episode begin.
    - One [STEP] line per step, immediately after env.step() returns.
    - One [END] line after env.close(), always emitted (even on exception).
    - reward and rewards are formatted to 2 decimal places.
    - done and success are lowercase booleans: true or false.
    - error is the raw last_action_error string, or null if none.
    - All fields on a single line with no newlines within a line.
    - Each task should return score in [0, 1]
"""
from __future__ import annotations

import json
import os
import re
import textwrap
import time
from typing import Any, Dict, List, Optional

import openai
import websocket
from dotenv import load_dotenv
load_dotenv()
# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY") or "placeholder_key"
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
TASK_NAME = os.getenv("CHIPFORGE_TASK", "task_easy_syntax")
BENCHMARK = os.getenv("CHIPFORGE_BENCHMARK", "chipforge")
ENV_URL = os.getenv("ENV_URL", "http://localhost:8000")  # Optional: HF Space URL for direct connection
MAX_STEPS = 20
TEMPERATURE = 0.2
MAX_TOKENS = 1024

# ---------------------------------------------------------------------------
# Structured stdout logging (MANDATORY FORMAT)
# ---------------------------------------------------------------------------

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(
    step: int, action: str, reward: float, done: bool, error: Optional[str]
) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}",
        flush=True,
    )

# ---------------------------------------------------------------------------
# Action definitions
# ---------------------------------------------------------------------------

VALID_ACTIONS = [
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

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""\
You are an expert Verilog/RTL debugging agent controlling the ChipForge environment.
Your goal is to fix buggy Verilog RTL code so it passes simulation, synthesis, and lint checks.

Available actions (return exactly ONE JSON action per turn):

1. view_design          — View the design (RTL) code
2. view_testbench       — View the testbench code
3. view_synthesis_log   — View synthesis tool logs from last run
4. view_lint_log        — View lint tool logs from last run
5. view_simulation_log  — View simulation tool logs from last run
6. run_simulation       — Compile and simulate with Verilator
7. run_synthesis        — Synthesize with Yosys
8. run_lint             — Run Verilator lint checks
9. edit_line            — Replace a single line in target file. Requires target ("design" or "testbench"), line_number (1-indexed) and new_content
10. append_line          — Append one line to target file. Requires target and new_content
11. insert_lines        — Insert multiple lines at line_number in target file. Requires target, line_number and new_content (newline separated)
12. replace_lines       — Replace multiple lines in target file. Requires target, line_number, end_line_number (inclusive), and new_content
13. write_file          — Write/overwrite the entire target file. Requires target and new_content (useful for tasks requiring generating code from scratch)
14. submit              — Submit current RTL as final solution (triggers grading)

Response format — return ONLY valid JSON:
{"action_type": "...", "target": null, "line_number": null, "end_line_number": null, "new_content": null, "reasoning": "..."}

Strategy:
1. Use view_design to inspect the current code if not in observation context
2. Run run_simulation to see compilation/output errors
3. If there are errors, use view_simulation_log to read error details
4. Use edit_line / replace_lines to fix the bug
5. Use append_line / insert_lines if a task starts with missing files
6. Re-run simulation to verify the fix
7. Run synthesis and lint to ensure clean results
8. Submit when everything passes

Rules:
- Return valid JSON only, no markdown
- Use null for fields that don't apply to the chosen action
- Fix bugs methodically — read error logs before editing
- Minimize steps for a higher reward (step penalty of -0.02/step)
""")

# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def build_prompt(obs: Dict[str, Any]) -> str:
    """Build user prompt from the current observation."""
    parts = ["Fix the RTL bug."]

    if obs.get("task_description"):
        parts.append(f"Task Description:\n{obs['task_description']}\n")

    parts.append(
        f"Step: {obs.get('step_count', '?')}/{obs.get('max_steps', 20)}"
    )

    if obs.get("task_description"):
        parts.append(f"Task: {obs['task_description']}")
    if obs.get("error_summary"):
        parts.append(f"Error: {obs['error_summary']}")
    if obs.get("last_action"):
        parts.append(f"Last action: {obs['last_action']}")
    if obs.get("action_result"):
        parts.append(f"Action result: {obs['action_result']}")

    status_line = (
        f"Status: sim={obs.get('sim_status', 'not_run')}, "
        f"synth={obs.get('synth_status', 'not_run')}, "
        f"lint={obs.get('lint_status', 'not_run')}"
    )
    parts.append(status_line)

    if obs.get("design_code"):
        parts.append(f"\n--- RTL Code ---\n{obs['design_code']}")
    elif obs.get("rtl_code"):
        parts.append(f"\n--- RTL Code ---\n{obs['rtl_code']}")

    if obs.get("testbench_code"):
        parts.append(f"\n--- Testbench ---\n{obs['testbench_code']}")

    if obs.get("log_output"):
        log = obs["log_output"][:1500]
        parts.append(f"\n--- Log Output ---\n{log}")

    parts.append("\nReturn your next action as JSON:")
    return "\n".join(parts)


def parse_action(text: str) -> Optional[Dict[str, Any]]:
    """Try to extract a JSON action from the LLM response."""
    text = text.strip()

    # Direct JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # Fenced code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Any JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return None

def validate_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize the parsed action."""
    action_type = action.get("action_type", "run_simulation")
    if action_type not in VALID_ACTIONS:
        action_type = "run_simulation"

    payload: Dict[str, Any] = {"action_type": action_type}

    if action_type in ("edit_line", "insert_lines"):
        payload["target"] = action.get("target", "design")
        payload["line_number"] = action.get("line_number")
        payload["new_content"] = action.get("new_content")
    elif action_type == "replace_lines":
        payload["target"] = action.get("target", "design")
        payload["line_number"] = action.get("line_number")
        payload["end_line_number"] = action.get("end_line_number")
        payload["new_content"] = action.get("new_content")
    elif action_type in ("append_line", "write_file"):
        payload["target"] = action.get("target", "design")
        payload["new_content"] = action.get("new_content")

    return payload

def call_llm(client: openai.OpenAI, prompt: str) -> str:
    """Call the LLM using the OpenAI Client."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 5 * (attempt + 1)
                time.sleep(wait)
            else:
                raise


def compute_score(obs: Any) -> float:
    """
    Compute a normalized score in [0, 1] from the final observation.
    """
    score = 0.0
    if isinstance(obs, dict):
        sim = obs.get("sim_status", "not_run")
        synth = obs.get("synth_status", "not_run")
        lint = obs.get("lint_status", "not_run")
    else:
        sim = getattr(obs, "sim_status", "not_run")
        synth = getattr(obs, "synth_status", "not_run")
        lint = getattr(obs, "lint_status", "not_run")

    if sim in ("pass", "fail"):
        score += 0.2
    if sim == "pass":
        score += 0.3
    if synth == "pass":
        score += 0.3
    if lint == "clean":
        score += 0.2

    return min(max(score, 0.0), 1.0)


# ---------------------------------------------------------------------------
# Main episode runner (Websockets ONLY)
# ---------------------------------------------------------------------------

def main() -> None:
    # 1. Init OpenAI LLM client
    llm_client = openai.OpenAI(
        api_key=API_KEY,
        base_url=API_BASE_URL
    )

    # 2. Connect via WebSocket for persistent session state
    ws_url = ENV_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    ws = websocket.create_connection(ws_url, timeout=120)

    def ws_send(msg_type: str, data: dict = None) -> dict:
        """Send a WebSocket message and return the response."""
        payload = {"type": msg_type}
        if data is not None:
            payload["data"] = data
        ws.send(json.dumps(payload))
        return json.loads(ws.recv())

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    
    log_start(task=TASK_NAME, env=BENCHMARK, model=MODEL_NAME)

    try:
        # Reset via ws
        reset_payload: dict[str, Any] = {}
        if TASK_NAME:
            reset_payload["task_name"] = TASK_NAME
            
        reset_resp = ws_send("reset", reset_payload if reset_payload else None)
        obs = reset_resp.get("data", {})
        
        for step in range(1, MAX_STEPS + 1):
            if obs.get("done", False):
                success = True # Assume true if it naturally exited early
                break

            # Build prompt and query LLM
            prompt = build_prompt(obs)
            raw_response = call_llm(llm_client, prompt)

            # Parse and validate action
            parsed = parse_action(raw_response)
            if parsed is None:
                parsed = {"action_type": "run_simulation"}

            action_dict = validate_action(parsed)

            # Step the environment via Websocket
            step_resp = ws_send("step", action_dict)
            obs = step_resp.get("data", {}).get("observation", step_resp.get("data", {}))
            reward = float(step_resp.get("data", {}).get("reward", 0.0))
            done = step_resp.get("data", {}).get("done", False)
            
            error = obs.get("error_summary", None)
            if error == "":
                error = None

            rewards.append(reward)
            steps_taken = step
            
            if done:
                success = True
                score = compute_score(obs)

            # Structured log (MANDATORY FORMAT)
            action_str = action_dict["action_type"]
            parts = []
            if "line_number" in action_dict and action_dict["line_number"]:
                parts.append(str(action_dict["line_number"]))
            if "end_line_number" in action_dict and action_dict["end_line_number"]:
                parts.append(str(action_dict["end_line_number"]))
            
            if parts:
                action_str += f"({'-'.join(parts)})"

            log_step(
                step=steps_taken,
                action=action_str,
                reward=reward,
                done=done,
                error=error,
            )
            
            if done:
                break

    except Exception as e:
        success = False
        import traceback
        traceback.print_exc()
    finally:
        ws.close()
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

if __name__ == "__main__":
    main()
