import json
import uuid
from abc import ABC, abstractmethod
from typing import Annotated, Any, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
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
    final_output: dict[str, Any] | None = Field(None, description="The final result to return when action is 'FINISH'.")


# ── LangGraph State ──────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    latest_step: ReActStep | None
    final_output: dict[str, Any]
    error: str | None


class BaseAgent(ABC):

    def __init__(self) -> None:
        self.llm = get_llm()
        self.logger = get_logger(self.name)
        self._system_prompt: str | None = None
        self._graph = self._compile_graph()

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

    def _compile_graph(self) -> StateGraph:
        """Builds and compiles the LangGraph StateGraph representing the ReAct loop."""
        workflow = StateGraph(AgentState)

        # Define the nodes
        workflow.add_node("agent", self._call_agent)
        workflow.add_node("tools", self._execute_tool)

        # Define flow edges
        workflow.add_edge(START, "agent")
        
        # Define conditional edges
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "tools": "tools",
                "finish": END,
                "error": END
            }
        )
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    async def _call_agent(self, state: AgentState) -> dict[str, Any]:
        """Node for executing the LLM and generating the next ReActStep."""
        structured_llm = self.llm.with_structured_output(ReActStep)
        
        # Build the current message list, including the dynamic system prompt
        messages = [SystemMessage(content=self._build_system_prompt())] + list(state["messages"])

        try:
            step: ReActStep = await structured_llm.ainvoke(messages)
            log_thought(self.name, step.thought)
            log_action(self.name, step.action, step.action_input or {})
            
            # Store the latest step and append the LLM's response to the conversation
            return {
                "latest_step": step,
                "messages": [AIMessage(content=step.model_dump_json())]
            }
        except Exception as e:
            log_error(self.name, f"LLM invocation failed: {e}")
            return {
                "error": str(e),
                "latest_step": None
            }

    async def _execute_tool(self, state: AgentState) -> dict[str, Any]:
        """Node for calling tools based on the ReActStep action."""
        step = state["latest_step"]
        if not step:
            return {"messages": [HumanMessage(content="ERROR: No active step to execute.")]}

        action_name = step.action
        action_input = step.action_input or {}

        try:
            tool = get_tool(action_name)
            
            # Since tools are LangChain BaseTools, call them asynchronously
            result = await tool.ainvoke(action_input)
            
            serialized = json.dumps(result) if not isinstance(result, str) else result
            if len(serialized) > MAX_OBSERVATION_LENGTH:
                serialized = serialized[:MAX_OBSERVATION_LENGTH] + "\n...[truncated]"
                
            log_observation(self.name, serialized)
            return {"messages": [HumanMessage(content=f"Observation: {serialized}")]}
        except Exception as e:
            error_msg = f"ERROR executing tool '{action_name}': {e}"
            log_error(self.name, error_msg)
            return {"messages": [HumanMessage(content=error_msg)]}

    def _should_continue(self, state: AgentState) -> str:
        """Conditional routing logic for LangGraph."""
        if state.get("error"):
            return "error"
            
        step = state.get("latest_step")
        if not step:
            return "error"

        if step.action == "FINISH":
            return "finish"

        return "tools"

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        run_id = str(uuid.uuid4())[:8]
        log_info(self.name, f"Starting LangGraph run [{run_id}]")

        initial_state = {
            "messages": [HumanMessage(content=json.dumps(task))],
            "latest_step": None,
            "final_output": {},
            "error": None
        }

        # Run the graph asynchronously
        final_state = await self._graph.ainvoke(initial_state)

        if final_state.get("error"):
            return {"status": "failed", "error": final_state["error"]}

        step = final_state.get("latest_step")
        if step and step.action == "FINISH":
            final_output = step.final_output or step.action_input or {}
            output = self.parse_output(final_output)
            log_info(self.name, f"Run [{run_id}] completed successfully.")
            return {"status": "completed", "output": output}

        log_error(self.name, f"Run [{run_id}] ended unexpectedly without finishing.")
        return {"status": "failed", "error": "Graph terminated without a FINISH action."}
