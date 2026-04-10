"""
Discrete reward logic for the ChipForge environment.
"""

import os
import openai
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("API_KEY")
base_url = os.environ.get("API_BASE_URL")
model = os.environ.get("MODEL_NAME")

from .constants import STEP_COST

def eval_tool_reward(status: str, attempts: int) -> float:
    """
    Evaluates raw step reward based on tool pass/fail and attempt count.
    Pass conditions: run_simulation uses 'pass', run_lint uses 'clean',
    run_synthesis uses 'pass'.
    """
    if status in ("pass", "clean"):
        if attempts == 1:
            return 0.3
        elif attempts == 2:
            return 0.2
        else:
            return 0.1
    return -0.5

def eval_llm_submit(design_code: str, testbench_code: str, golden_code: str, task_desc: str) -> float:
    """
    Uses an LLM judge to evaluate the design and testbench against the goal.
    Returns a score between -1.0 and 1.0. 
    """

    if not api_key:
        print("WARNING: API_KEY not found. Falling back to length-based heuristic.")
        return 0.5 if (len(design_code.strip()) > 10 and len(testbench_code.strip()) > 10) else -1.0

    client = openai.OpenAI(api_key=api_key , base_url=base_url)
    
    system_prompt = (
        "You are an expert Verilog evaluation judge. Evaluate the provided design code and testbench against the task description and golden code. "
        "Return ONLY a single float value between -1.0 and 1.0 representing the quality and correctness of the submission. "
        "1.0 = Perfect, entirely correct. 0.0 = Partially correct. -1.0 = Completely incorrect. Do not output any other text."
    )
    
    user_prompt = (
        f"Task Description:\n{task_desc}\n\n"
        f"Golden Reference Code:\n{golden_code}\n\n"
        f"Submitted Design Code:\n{design_code}\n\n"
        f"Submitted Testbench Code:\n{testbench_code}"
    )
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=10
        )
        score_str = response.choices[0].message.content.strip()
        score = float(score_str)
        print(f"LLM Evaluation Score: {score}")
        return max(-1.0, min(1.0, score))
    except Exception as e:
        print(f"LLM Evaluation failed: {e}")
        # Fallback to basic length validation if LLM fails
        if len(design_code.strip()) > 10 and len(testbench_code.strip()) > 10:
            return 0.5
        return -1.0

def normalize_reward(raw_reward: float) -> float:
    """
    Maps the raw reward into a [0, 1] scale across the action bounds.
    Theoretical limits: raw [-1.0, 1.0] -> normalized [0.0, 1.0]
    """
    mapped = (raw_reward + 1.0) / 2.0
    return max(0.0, min(1.0, mapped))
    # return raw_reward  # For now, we return the raw reward directly and let the inference script handle scaling
