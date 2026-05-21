from typing import List, Optional
from pydantic import BaseModel, Field

class ScoredArticle(BaseModel):
    ticker: str
    title: str
    url: Optional[str] = None
    published: Optional[str] = None
    age: str
    confidence: float = Field(ge=0.0, le=1.0)

class BatchResponse(BaseModel):
    results: List[ScoredArticle]
