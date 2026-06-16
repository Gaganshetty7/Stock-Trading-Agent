from typing import List
from pydantic import BaseModel, Field

class TechnicalAnalystInputSchema(BaseModel):
    tickers: List[str] = Field(
        ...,
        description="A list of stock tickers to fetch technical analysis for (e.g., ['RELIANCE', 'TCS'])."
    )
