import json
import os
import uuid
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

from core.llm import get_llm
from core.tool import get_tool, describe_tools
from core.logger import get_logger, log_thought, log_action, log_observation, log_error, log_info
from config.settings import LLM_MODEL, MAX_REACT_ITERATIONS


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

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:

        run_id = str(uuid.uuid4())[:8]

        log_info(self.name, f"Starting run [{run_id}]")


        # Shortcut mode: skip LLM-driven planning and run the standard
        # tool sequence directly. Useful for testing when LLM quota is exhausted.
        if os.environ.get("AGENT_SKIP_LLM", "0").lower() in ("1", "true", "yes"):
            try:
                fetch_tool = get_tool("fetch_broad_market_rss")
                rank_tool = get_tool("rank_news_payload")
                # Default fetch window is 6 hours (same as run_test.py)
                fetched = await fetch_tool(max_age_hours=6)
                ranked = await rank_tool(payload=fetched)
                output = self.parse_output(ranked)
                return {"status": "completed", "output": output}
            except Exception as e:
                log_error(self.name, f"Skip-LLM run failed: {e}")
                return {"status": "failed", "error": str(e)}

        messages = [
            SystemMessage(content=self._build_system_prompt()),
            HumanMessage(content=json.dumps(task)),
        ]

        last_tool_result = None

        for iteration in range(MAX_REACT_ITERATIONS):

            log_info(self.name, f"Iteration {iteration + 1}")
            structured_llm = self.llm.with_structured_output(ReActStep)

            try:
                step: ReActStep = await structured_llm.ainvoke(messages)

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    log_error(self.name, f"LLM quota exhausted: {e}")
                    return {
                        "status": "failed",
                        "error": "LLM Quota Exhausted (429)"
                    }


                log_error(self.name, f"LLM call failed: {e}")

                return {
                    "status": "failed",
                    "error": str(e)
                }

            log_thought(self.name, step.thought)
            log_action(self.name, step.action, step.action_input or {})

            # ─────────────────────────────────────────────
            # FINISH
            # ─────────────────────────────────────────────
            if step.action == "FINISH":

                # Priority 1: Raw tool results with signals (matches run_test.py pattern)
                # Priority 2: Structured LLM output (if no tool result or specially formatted)
                final_output = step.final_output or {}
                if last_tool_result and isinstance(last_tool_result, dict) and "signals" in last_tool_result:
                    final_output = last_tool_result
                elif not final_output:
                    final_output = last_tool_result or step.action_input or {}



                output = self.parse_output(final_output)

                log_info(
                    self.name,
                    f"Run [{run_id}] completed."
                )

                return {
                    "status": "completed",
                    "output": output
                }

            # ─────────────────────────────────────────────
            # AUTO TOOL CHAINING
            # ─────────────────────────────────────────────
            if (
                step.action == "rank_news_payload"
                and last_tool_result is not None
            ):

                # Prefer the most recent written mapped_news file if the
                # in-memory last_tool_result has empty or null mapped_news.
                payload_to_pass = last_tool_result

                try:
                    mapped = None
                    if isinstance(last_tool_result, dict):
                        mapped = last_tool_result.get("mapped_news")

                    if mapped is None or (isinstance(mapped, dict) and len(mapped) == 0):
                        from pathlib import Path

                        outputs_dir = Path("outputs")
                        candidates = sorted(outputs_dir.glob("mapped_news_*.json"))
                        if candidates:
                            latest = candidates[-1]
                            try:
                                with open(latest, "r", encoding="utf-8") as fh:
                                    payload_to_pass = json.load(fh)
                            except Exception:
                                payload_to_pass = last_tool_result

                except Exception:
                    payload_to_pass = last_tool_result

                step.action_input = {"payload": payload_to_pass}

    # ─────────────────────────────────────────────
    # CALL TOOL
    # ─────────────────────────────────────────────
            observation = await self._call_tool(
                step.action,
                step.action_input or {}
            )

            log_observation(self.name, observation)

            # ─────────────────────────────────────────────
            # SAVE RAW RESULT
            # ─────────────────────────────────────────────
            try:

                last_tool_result = (
                    json.loads(observation)
                    if isinstance(observation, str)
                    else observation
                )

            except Exception:

                last_tool_result = observation

            # ─────────────────────────────────────────────
            # CHAT HISTORY
            # ─────────────────────────────────────────────
            messages.append(
                AIMessage(content=step.model_dump_json())
            )

            messages.append(
                HumanMessage(
                    content=f"Observation: {observation[:MAX_OBSERVATION_LENGTH]}"
                )
            )

        log_error(
            self.name,
            f"Run [{run_id}] hit max iterations."
        )

        return {
    "status": "max_iterations",
    "error": "Max iterations reached"
}


    async def _call_tool(self, name: str, inputs: dict[str, Any]) -> str:
        try:
            tool = get_tool(name)
            result = await tool(**inputs)
            serialized = json.dumps(result) if not isinstance(result, str) else result
            # Return full serialized result so callers can parse it safely.
            return serialized
        except KeyError as e:
            return str(e)
        except Exception as e:
            log_error(self.name, f"Tool '{name}' error: {e}")
            return f"ERROR: {e}"
