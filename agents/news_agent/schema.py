from enum import Enum
from typing import Dict
from pydantic import BaseModel, Field, RootModel


class Direction(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Source(BaseModel):
    title: str
    description: str  # per-article summary
    url: str          # article's link field
    published: str    # article's published field


class Signal(BaseModel):
    stock: str
    catalyst: str
    direction: Direction
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[Source] = Field(default_factory=list, max_length=3)


class NewsAgentOutput(RootModel):
    root: Dict[str, Signal]
