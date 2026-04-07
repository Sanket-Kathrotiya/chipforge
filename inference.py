#!/usr/bin/env python3
"""
LLM inference runner for ChipForge RTL Debugging Environment.

This script lets a chat model debug buggy Verilog RTL by choosing actions
(view code, run simulation/synthesis, edit lines, submit) against the
ChipForge HTTP server.

Examples:
  # HTTP mode against running server
  python inference.py --mode http --env-url http://localhost:8000

  # Local mode (requires Verilator + Yosys on PATH)
  python inference.py --mode local --episodes 1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Action definitions
# ---------------------------------------------------------------------------

VALID_ACTIONS = [
    "view_rtl",
    "view_testbench",
    "view_logs",
    "run_simulation",
    "run_synthesis",
    "run_lint",
    "edit_line",
    "submit",
]

DEFAULT_LLM_MODEL = os.environ.get("LLM_MODEL", "mistral-medium-2505")

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert Verilog/RTL debugging agent controlling the ChipForge environment.
Your goal is to fix buggy Verilog RTL code so it passes simulation, synthesis, and lint checks.

Available actions (return exactly ONE JSON action per turn):

1. view_rtl          — View the current RTL design code with line numbers
2. view_testbench    — View the testbench code
3. view_logs         — View tool output logs. Set log_type to "sim", "synth", or "lint"
4. run_simulation    — Compile and simulate with Verilator
5. run_synthesis     — Synthesize with Yosys
6. run_lint          — Run Verilator lint checks
7. edit_line         — Replace a single line. Requires line_number (1-indexed) and new_content
8. submit            — Submit current RTL as final solution (triggers grading)

Response format — return ONLY valid JSON:
{"action_type": "...", "line_number": null, "new_content": null, "log_type": null, "reasoning": "..."}

Strategy:
1. First, view_rtl to see the buggy code
2. Run run_simulation to see compilation/output errors
3. If there are errors, view_logs with log_type="sim" to read details
4. Use edit_line to fix the bug (one line at a time)
5. Re-run simulation to verify the fix
6. Run synthesis and lint to ensure clean results
7. Submit when everything passes

Rules:
- Return valid JSON only, no markdown
- Use null for fields that don't apply to the chosen action
- Fix bugs methodically — read errors before editing
- Minimize steps for a higher reward (step penalty of -0.01/step)
"""


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------


def build_prompt(observation: dict[str, Any]) -> str:
    """Build user prompt from the current observation."""
    parts = [f"Task: {observation.get('task_description', 'Fix the RTL bug.')}"]

    # Always show status summary
    parts.append(
        f"\nStatus: sim={observation.get('sim_status', '?')} "
        f"synth={observation.get('synth_status', '?')} "
        f"lint={observation.get('lint_status', '?')}"
    )
    parts.append(
        f"Step: {observation.get('step_count', '?')}/{observation.get('max_steps', 20)}"
    )

    if observation.get("error_summary"):
        parts.append(f"Error: {observation['error_summary']}")

    # Include content fields if populated
    if observation.get("rtl_code"):
        parts.append(f"\n--- RTL Code ---\n{observation['rtl_code']}")

    if observation.get("testbench_code"):
        parts.append(f"\n--- Testbench ---\n{observation['testbench_code']}")

    if observation.get("log_output"):
        # Truncate very long logs
        log = observation["log_output"][:1500]
        parts.append(f"\n--- Log Output ---\n{log}")

    parts.append("\nReturn your next action as JSON:")
    return "\n".join(parts)


def parse_action(text: str) -> Optional[dict[str, Any]]:
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


def validate_action(action: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the parsed action."""
    action_type = action.get("action_type", "view_rtl")
    if action_type not in VALID_ACTIONS:
        action_type = "view_rtl"

    payload: dict[str, Any] = {"action_type": action_type}

    if action_type == "edit_line":
        payload["line_number"] = action.get("line_number")
        payload["new_content"] = action.get("new_content")

    if action_type == "view_logs":
        payload["log_type"] = action.get("log_type", "sim")

    return payload


# ---------------------------------------------------------------------------
# LLM client (Mistral)
# ---------------------------------------------------------------------------


def make_mistral_client(api_key: Optional[str] = None):
    from mistralai.client import Mistral

    return Mistral(
        api_key=api_key or os.environ.get("MISTRAL_API_KEY"),
        timeout_ms=120_000,  # 120s — magistral is a reasoning model
    )


def call_llm(client, model: str, prompt: str, temperature: float, max_retries: int = 3) -> str:
    """Call the LLM with retry on timeout."""
    import time as _time

    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("LLM response missing content")

            # Some models (e.g. magistral) return content as a list of blocks
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif hasattr(block, "text"):
                        parts.append(block.text)
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(block["text"])
                    else:
                        parts.append(str(block))
                content = "\n".join(parts)

            return content

        except Exception as e:
            if attempt < max_retries - 1:
                wait = 5 * (attempt + 1)
                print(f"  ⚠️  LLM call failed ({e.__class__.__name__}), retrying in {wait}s...")
                _time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def request_json(
    url: str,
    method: str = "GET",
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Make an HTTP request and return parsed JSON."""
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Episode runners
# ---------------------------------------------------------------------------


def run_http_episode(args: argparse.Namespace) -> float:
    """Run one episode against the server using WebSocket (persistent session)."""
    import time
    import websocket  # pip install websocket-client

    llm_client = make_mistral_client(args.api_key)

    # Connect via WebSocket for persistent session state
    ws_url = args.env_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    ws = websocket.create_connection(ws_url, timeout=120)

    def ws_send(msg_type: str, data: dict = None) -> dict:
        """Send a WebSocket message and return the response."""
        payload = {"type": msg_type}
        if data is not None:
            payload["data"] = data
        ws.send(json.dumps(payload))
        return json.loads(ws.recv())

    # Reset
    reset_resp = ws_send("reset")
    obs = reset_resp.get("data", {})
    total_reward = 0.0

    print(f"  Task: {obs.get('task_description', '?')}")
    print()

    for step in range(args.max_steps):
        # Build prompt and query LLM
        prompt = build_prompt(obs)
        raw_response = call_llm(
            client=llm_client,
            model=args.model,
            prompt=prompt,
            temperature=args.temperature,
        )

        # Parse and validate
        parsed = parse_action(raw_response)
        if parsed is None:
            parsed = {"action_type": "view_rtl", "reasoning": "Failed to parse LLM response"}

        action_dict = validate_action(parsed)
        reasoning = parsed.get("reasoning", "")

        # Step via WebSocket
        step_resp = ws_send("step", action_dict)
        obs = step_resp.get("data", {}).get("observation", step_resp.get("data", {}))
        reward = float(step_resp.get("data", {}).get("reward", 0.0))
        done = step_resp.get("data", {}).get("done", False)
        total_reward = reward

        # Print step header
        print(f"\n  {'─'*56}")
        print(f"  STEP {step + 1}/{args.max_steps}")
        print(f"  {'─'*56}")

        # Print full action object
        print(f"\n  ▶ ACTION:")
        print(f"    {json.dumps(action_dict, indent=4)}")
        if reasoning:
            print(f"    reasoning: {reasoning}")

        # Print full observation/state
        print(f"\n  ◀ OBSERVATION:")
        print(f"    sim_status:       {obs.get('sim_status', '?')}")
        print(f"    synth_status:     {obs.get('synth_status', '?')}")
        print(f"    lint_status:      {obs.get('lint_status', '?')}")
        print(f"    error_summary:    {obs.get('error_summary', '')}")
        print(f"    step_count:       {obs.get('step_count', '?')}/{obs.get('max_steps', 20)}")
        print(f"    reward:           {reward:+.3f}")
        print(f"    total_reward:     {total_reward:+.3f}")
        print(f"    done:             {done}")

        if obs.get("rtl_code"):
            print(f"\n    --- RTL Code ---")
            print(f"    {obs['rtl_code'][:500]}")

        if obs.get("testbench_code"):
            print(f"\n    --- Testbench (first 300 chars) ---")
            print(f"    {obs['testbench_code'][:300]}")

        if obs.get("log_output"):
            print(f"\n    --- Log Output (first 500 chars) ---")
            print(f"    {obs['log_output'][:500]}")

        if done:
            print(f"\n  🏁 EPISODE DONE — Final reward: {total_reward:+.3f}")
            break

        # 10 second delay between steps
        print(f"\n  ⏳ Waiting 10 seconds...")
        time.sleep(10)

    ws.close()
    print(f"\n  Final reward: {total_reward:+.3f}")
    return total_reward


def run_local_episode(args: argparse.Namespace) -> float:
    """Run one episode using the local environment (needs Verilator+Yosys)."""
    import sys

    sys.path.insert(0, os.path.dirname(__file__))

    from models import ChipforgeAction
    from server.chipforge_environment import ChipforgeEnvironment

    client = make_mistral_client(args.api_key)
    env = ChipforgeEnvironment()

    obs = env.reset(seed=args.seed)
    total_reward = 0.0

    print(f"  Task: {obs.task_description}")
    print()

    for step in range(args.max_steps):
        # Build observation dict for prompt
        obs_dict = {
            "task_description": obs.task_description,
            "rtl_code": obs.rtl_code,
            "testbench_code": obs.testbench_code,
            "log_output": obs.log_output,
            "sim_status": obs.sim_status,
            "synth_status": obs.synth_status,
            "lint_status": obs.lint_status,
            "error_summary": obs.error_summary,
            "step_count": obs.step_count,
            "max_steps": obs.max_steps,
        }

        prompt = build_prompt(obs_dict)
        raw_response = call_llm(
            client=client,
            model=args.model,
            prompt=prompt,
            temperature=args.temperature,
        )

        parsed = parse_action(raw_response)
        if parsed is None:
            parsed = {"action_type": "view_rtl", "reasoning": "Failed to parse"}

        action_dict = validate_action(parsed)
        reasoning = parsed.get("reasoning", "")

        action = ChipforgeAction(**action_dict)
        obs = env.step(action)
        total_reward = obs.reward

        action_str = action_dict["action_type"]
        if action_dict["action_type"] == "edit_line":
            action_str += f"({action_dict.get('line_number', '?')})"

        print(
            f"  step={step + 1:02d}  action={action_str:25s}  "
            f"sim={obs.sim_status:8s}  "
            f"synth={obs.synth_status:8s}  "
            f"reward={obs.reward:+.3f}  done={obs.done}"
        )
        if reasoning:
            print(f"          reasoning: {reasoning[:80]}")
        if obs.error_summary:
            print(f"          error: {obs.error_summary[:80]}")

        if obs.done:
            break

    env.close()
    print(f"\n  Final reward: {total_reward:+.3f}")
    return total_reward


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an LLM agent against ChipForge RTL Debugging Environment."
    )
    parser.add_argument("--mode", choices=["local", "http"], default="http")
    parser.add_argument("--env-url", default="http://localhost:8000")
    parser.add_argument("--model", default=DEFAULT_LLM_MODEL)
    parser.add_argument("--api-key", default=os.environ.get("MISTRAL_API_KEY"))
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    total_rewards = []
    for episode in range(args.episodes):
        print(f"\n{'='*60}")
        print(f"  Episode {episode + 1}/{args.episodes}")
        print(f"{'='*60}")

        if args.mode == "local":
            reward = run_local_episode(args)
        else:
            reward = run_http_episode(args)

        total_rewards.append(reward)

    # Summary
    avg = sum(total_rewards) / len(total_rewards)
    print(f"\n{'='*60}")
    print(f"  Summary: {len(total_rewards)} episodes, avg reward: {avg:+.3f}")
    print(f"  Rewards: {[f'{r:+.3f}' for r in total_rewards]}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
