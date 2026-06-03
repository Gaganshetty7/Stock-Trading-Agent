import json
import uuid
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

from core.llm import get_llm
from core.tool import get_tool, describe_tools
from core.logger import get_logger, log_thought, log_action, log_observation, log_error, log_info
from config.settings import MAX_REACT_ITERATIONS

MAX_OBSERVATION_LENGTH = 8000


# ── ReAct step schema ─────────────────────────────────────────────────────────
class ReActStep(BaseModel):
    thought: str
    action: str
    action_input: dict[str, Any] | None = Field(None, description="Input for the tool action.")
    final_output: dict[str, Any] | None = Field(None, description="The final result to return when action is 'FINISH'. For NewsAgent, this must include the 'signals' list.")


class BaseAgent(ABC):

    def __init__(self) -> None:
        self.llm = get_llm()
        self.logger = get_logger(self.name)
        self._system_prompt: str | None = None

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def skill_path(self) -> str: ...

    @property
    @abstractmethod
    def tool_names(self) -> list[str]: ...

    @abstractmethod
    def parse_output(self, final_output: dict[str, Any]) -> Any: ...

    def _build_system_prompt(self) -> str:
        if self._system_prompt:
            return self._system_prompt

        with open(self.skill_path, "r") as f:
            skill = f.read()

        self._system_prompt = (
            f"{skill}\n\n"
            f"## Available Tools\n{describe_tools(self.tool_names)}\n\n"
            f"## Response Format\n"
            f"To call a tool: {{\"thought\": \"...\", \"action\": \"tool_name\", \"action_input\": {{...}}}}\n"
            f"To finish:      {{\"thought\": \"...\", \"action\": \"FINISH\", \"final_output\": {{...}}}}\n\n"
            f"IMPORTANT: Always include all results in 'final_output' when calling 'FINISH'."
        )
        return self._system_prompt

    async def run(self, task: dict[str, Any] | None = None) -> dict[str, Any]:
        run_id = str(uuid.uuid4())[:8]
        log_info(self.name, f"Starting run [{run_id}]")

        structured_llm = self.llm.with_structured_output(ReActStep)

        kickoff = json.dumps(task) if task else "Begin."

        messages = [
            SystemMessage(content=self._build_system_prompt()),
            HumanMessage(content=kickoff),
        ]

        for iteration in range(MAX_REACT_ITERATIONS):
            log_info(self.name, f"Iteration {iteration + 1}")

            try:
                step: ReActStep = await structured_llm.ainvoke(messages)
            except Exception as e:
                log_error(self.name, f"LLM call failed: {e}")
                return {"status": "failed", "error": str(e)}

            log_thought(self.name, step.thought)
            log_action(self.name, step.action, step.action_input or {})

            if step.action == "FINISH":
                final_output = step.final_output or step.action_input or {}
                output = self.parse_output(final_output)
                log_info(self.name, f"Run [{run_id}] completed.")
                return {"status": "completed", "output": output}

            observation = await self._call_tool(step.action, step.action_input or {})
            log_observation(self.name, observation)

            messages.append(AIMessage(content=step.model_dump_json()))
            messages.append(HumanMessage(content=f"Observation: {observation}"))

        log_error(self.name, f"Run [{run_id}] hit max iterations.")
        return {"status": "max_iterations", "error": "Max iterations reached"}

    async def _call_tool(self, name: str, inputs: dict[str, Any]) -> str:
        try:
            tool = get_tool(name)
            result = await tool(**inputs)
            serialized = json.dumps(result) if not isinstance(result, str) else result
            if len(serialized) > MAX_OBSERVATION_LENGTH:
                serialized = serialized[:MAX_OBSERVATION_LENGTH] + "\n...[truncated]"
            return serialized
        except KeyError as e:
            return str(e)
        except Exception as e:
            log_error(self.name, f"Tool '{name}' error: {e}")
            return f"ERROR: {e}"
