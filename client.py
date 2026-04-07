# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""ChipForge Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import ChipforgeAction, ChipforgeObservation


class ChipforgeEnv(
    EnvClient[ChipforgeAction, ChipforgeObservation, State]
):
    """
    Client for the ChipForge RTL Debugging Environment.

    This client maintains a persistent WebSocket connection to the environment
    server, enabling efficient multi-step interactions with lower latency.

    Example:
        >>> with ChipforgeEnv(base_url="http://localhost:8000") as client:
        ...     result = client.reset()
        ...     print(result.observation.task_description)
        ...
        ...     # View the buggy RTL
        ...     result = client.step(ChipforgeAction(action_type="view_rtl"))
        ...     print(result.observation.rtl_code)
        ...
        ...     # Run simulation
        ...     result = client.step(ChipforgeAction(action_type="run_simulation"))
        ...     print(result.observation.sim_status)
        ...
        ...     # Edit a line
        ...     result = client.step(ChipforgeAction(
        ...         action_type="edit_line",
        ...         line_number=13,
        ...         new_content="assign sum = x1 ^ cin;"
        ...     ))

    Example with Docker:
        >>> client = ChipforgeEnv.from_docker_image("chipforge-env:latest")
        >>> try:
        ...     result = client.reset()
        ...     result = client.step(ChipforgeAction(action_type="view_rtl"))
        ... finally:
        ...     client.close()
    """

    def _step_payload(self, action: ChipforgeAction) -> Dict:
        """
        Convert ChipforgeAction to JSON payload for step message.

        Args:
            action: ChipforgeAction instance

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        payload = {"action_type": action.action_type}

        if action.line_number is not None:
            payload["line_number"] = action.line_number
        if action.new_content is not None:
            payload["new_content"] = action.new_content
        if action.log_type is not None:
            payload["log_type"] = action.log_type

        return payload

    def _parse_result(self, payload: Dict) -> StepResult[ChipforgeObservation]:
        """
        Parse server response into StepResult[ChipforgeObservation].

        Args:
            payload: JSON response data from server

        Returns:
            StepResult with ChipforgeObservation
        """
        obs_data = payload.get("observation", {})
        observation = ChipforgeObservation(
            rtl_code=obs_data.get("rtl_code", ""),
            testbench_code=obs_data.get("testbench_code", ""),
            log_output=obs_data.get("log_output", ""),
            sim_status=obs_data.get("sim_status", "not_run"),
            synth_status=obs_data.get("synth_status", "not_run"),
            lint_status=obs_data.get("lint_status", "not_run"),
            error_summary=obs_data.get("error_summary", ""),
            task_description=obs_data.get("task_description", ""),
            step_count=obs_data.get("step_count", 0),
            max_steps=obs_data.get("max_steps", 20),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        """
        Parse server response into State object.

        Args:
            payload: JSON response from state request

        Returns:
            State object with episode_id and step_count
        """
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
