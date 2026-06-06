from typing import Literal
from pydantic import BaseModel, Field

ROUTE_OPTIONS = Literal["NewsWorker", "TechWorker", "TradeBrainWorker", "FINISH"]

class SupervisorRoutingSchema(BaseModel):
    reasoning: str = Field(description="Your thought process and reasoning for selecting the next agent or finishing.")
    next: ROUTE_OPTIONS = Field(description="The next agent to route to, or FINISH if the overall goal is achieved.")
