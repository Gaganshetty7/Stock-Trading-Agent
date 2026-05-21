from typing import List, Optional, Literal
from pydantic import BaseModel, Field


Trend = Literal["bullish", "bearish", "neutral"]


class ScoredArticle(BaseModel):
    ticker: str
    title: str
    url: Optional[str] = None
    published: Optional[str] = None
    age: str

    confidence: float = Field(ge=0.0, le=1.0)

    impact_score: float = Field(ge=0.0, le=1.0)

    trend: Trend


class BatchResponse(BaseModel):
    results: List[ScoredArticle]
