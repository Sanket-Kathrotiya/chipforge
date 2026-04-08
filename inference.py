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

import asyncio
import json
import os
import re
import textwrap
from typing import Any, Dict, List, Optional

from mistralai import Mistral
from chipforge import ChipforgeAction, ChipforgeEnv

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

IMAGE_NAME = os.getenv("IMAGE_NAME")  # Docker image name
API_KEY = os.getenv("MISTRAL_API_KEY") or os.getenv("HF_TOKEN") or os.getenv("API_KEY")

API_BASE_URL = os.getenv("API_BASE_URL") or "https://api.mistral.ai/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "mistral-large-latest"
TASK_NAME = os.getenv("CHIPFORGE_TASK", "task_easy_syntax")
BENCHMARK = os.getenv("CHIPFORGE_BENCHMARK", "chipforge")
ENV_URL = os.getenv("ENV_URL")  # Optional: HF Space URL for direct connection
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
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""\
You are an expert Verilog/RTL debugging agent controlling the ChipForge environment.
Your goal is to fix buggy Verilog RTL code so it passes simulation, synthesis, and lint checks.

Available actions (return exactly ONE JSON action per turn):

1. view_testbench       — View the testbench code
2. view_synthesis_log   — View synthesis tool logs from last run
3. view_lint_log        — View lint tool logs from last run
4. view_simulation_log  — View simulation tool logs from last run
5. run_simulation       — Compile and simulate with Verilator
6. run_synthesis        — Synthesize with Yosys
7. run_lint             — Run Verilator lint checks
8. edit_line            — Replace a single line. Requires line_number (1-indexed) and new_content
9. append_line          — Append one RTL line. Requires new_content
10. edit_testbench_line — Replace a single testbench line. Requires line_number and new_content
11. append_testbench_line — Append one testbench line. Requires new_content
12. submit              — Submit current RTL as final solution (triggers grading)

Response format — return ONLY valid JSON:
{"action_type": "...", "line_number": null, "new_content": null, "reasoning": "..."}

Strategy:
1. The observation always includes the current RTL code — you don't need to view it separately
2. Run run_simulation to see compilation/output errors
3. If there are errors, use view_simulation_log to read error details
4. Use edit_line to fix the bug (one line at a time)
5. Re-run simulation to verify the fix
6. Run synthesis and lint to ensure clean results
7. Submit when everything passes

Rules:
- Return valid JSON only, no markdown
- Use null for fields that don't apply to the chosen action
- Fix bugs methodically — read error logs before editing
- Minimize steps for a higher reward (step penalty of -0.02/step)
""")


# ---------------------------------------------------------------------------
# LLM helpers (using OpenAI Client — MANDATORY)
# ---------------------------------------------------------------------------


def build_prompt(obs: Dict[str, Any]) -> str:
    """Build user prompt from the current observation."""
    parts = ["Fix the RTL bug."]

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

    if obs.get("rtl_code"):
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


VALID_ACTIONS = [
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


def validate_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize the parsed action."""
    action_type = action.get("action_type", "run_simulation")
    if action_type not in VALID_ACTIONS:
        action_type = "run_simulation"

    payload: Dict[str, Any] = {"action_type": action_type}

    if action_type in ("edit_line", "edit_testbench_line"):
        payload["line_number"] = action.get("line_number")
        payload["new_content"] = action.get("new_content")
    elif action_type in ("append_line", "append_testbench_line"):
        payload["new_content"] = action.get("new_content")

    return payload


def call_llm(client: Mistral, prompt: str) -> str:
    """Call the LLM using the Mistral Client."""
    try:
        completion = client.chat.complete(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        text = (completion.choices[0].message.content or "").strip()
        return text if text else '{"action_type": "run_simulation"}'
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", flush=True)
        return '{"action_type": "run_simulation"}'


def obs_to_dict(obs: Any) -> Dict[str, Any]:
    """Convert a ChipforgeObservation to a dict for prompt building."""
    return {
        "rtl_code": getattr(obs, "rtl_code", ""),
        "testbench_code": getattr(obs, "testbench_code", ""),
        "log_output": getattr(obs, "log_output", ""),
        "sim_status": getattr(obs, "sim_status", "not_run"),
        "synth_status": getattr(obs, "synth_status", "not_run"),
        "lint_status": getattr(obs, "lint_status", "not_run"),
        "last_action": getattr(obs, "last_action", "reset"),
        "action_result": getattr(obs, "action_result", ""),
        "error_summary": getattr(obs, "error_summary", ""),
        "task_description": getattr(obs, "task_description", ""),
        "metadata": getattr(obs, "metadata", {}),
        "step_count": getattr(obs, "step_count", 0),
        "max_steps": getattr(obs, "max_steps", 20),
    }


def compute_score(obs: Any) -> float:
    """
    Compute a normalized score in [0, 1] from the final observation.

    Score breakdown (matches the environment's quality potential):
      +0.2  code compiles (sim != error)
      +0.3  simulation passes
      +0.3  synthesis clean
      +0.2  lint clean
    """
    score = 0.0
    sim = getattr(obs, "sim_status", "not_run")
    synth = getattr(obs, "synth_status", "not_run")
    lint = getattr(obs, "lint_status", "not_run")

    if sim in ("pass", "fail"):
        score += 0.2  # compiles
    if sim == "pass":
        score += 0.3  # simulation passes
    if synth == "pass":
        score += 0.3  # synthesis clean
    if lint == "clean":
        score += 0.2  # lint clean

    return min(max(score, 0.0), 1.0)


# ---------------------------------------------------------------------------
# Main episode runner
# ---------------------------------------------------------------------------


async def main() -> None:
    llm_client = Mistral(api_key=API_KEY)

    # Connect to environment
    if IMAGE_NAME:
        env = await ChipforgeEnv.from_docker_image(IMAGE_NAME)
    elif ENV_URL:
        env = ChipforgeEnv(base_url=ENV_URL)
    else:
        raise RuntimeError(
            "Set IMAGE_NAME (for Docker) or ENV_URL (for HF Space) to connect to the environment."
        )

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    final_obs = None

    log_start(task=TASK_NAME, env=BENCHMARK, model=MODEL_NAME)

    try:
        result = await env.reset(task_name=TASK_NAME)
        obs = result.observation
        final_obs = obs

        for step in range(1, MAX_STEPS + 1):
            if result.done:
                break

            # Build prompt and query LLM
            obs_dict = obs_to_dict(obs)
            prompt = build_prompt(obs_dict)
            raw_response = call_llm(llm_client, prompt)

            # Parse and validate action
            parsed = parse_action(raw_response)
            if parsed is None:
                parsed = {"action_type": "run_simulation"}

            action_dict = validate_action(parsed)

            # Step the environment
            action = ChipforgeAction(**action_dict)
            result = await env.step(action)
            obs = result.observation
            final_obs = obs

            reward = result.reward or 0.0
            done = result.done
            error = getattr(obs, "error_summary", None)
            if error == "":
                error = None

            rewards.append(reward)
            steps_taken = step

            # Structured log (MANDATORY)
            action_str = action_dict["action_type"]
            if action_dict["action_type"] in ("edit_line", "edit_testbench_line"):
                action_str += f"({action_dict.get('line_number', '?')})"

            log_step(
                step=step,
                action=action_str,
                reward=reward,
                done=done,
                error=error,
            )

            if done:
                break

        # Compute score from final observation tool statuses
        if final_obs is not None:
            score = compute_score(final_obs)
        success = score >= 0.5

    finally:
        try:
            await env.close()
        except Exception as e:
            print(f"[DEBUG] env.close() error: {e}", flush=True)
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


if __name__ == "__main__":
    asyncio.run(main())
