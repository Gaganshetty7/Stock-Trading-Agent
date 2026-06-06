import operator
from langchain_core.messages import BaseMessage
from typing import Sequence, Annotated, TypedDict

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next: str
    final_output: str
    run_id: str
    step_count: Annotated[int, operator.add]
