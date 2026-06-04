from typing import List, Literal

from pydantic import BaseModel, Field


# =========================
# BUY ZONE
# =========================

class BuyZone(BaseModel):
    min: float = Field(
        description="Minimum preferred entry price"
    )

    max: float = Field(
        description="Maximum preferred entry price"
    )


# =========================
# ENTRY PLAN
# =========================

class EntryPlan(BaseModel):

    entry_type: Literal[
        "BREAKOUT",
        "VWAP_RECLAIM",
        "SUPPORT_BOUNCE",
        "PULLBACK_ENTRY",
        "MEAN_REVERSION",
        "TREND_CONTINUATION",
        "RANGE_BREAKOUT",
        "SPECULATIVE_REVERSAL"
    ] = Field(
        description="Primary setup classification"
    )

    buy_zone: BuyZone

    confirmation_conditions: List[str] = Field(
        description="Conditions that should occur before entering trade"
    )


# =========================
# STOPLOSS PLAN
# =========================

class StoplossPlan(BaseModel):

    hard_stoploss: float = Field(
        description="Absolute stoploss level"
    )

    soft_invalidation: List[str] = Field(
        description="Warning signals that weaken or invalidate setup"
    )


# =========================
# TARGET PLAN
# =========================

class TargetPlan(BaseModel):

    target_1: float = Field(
        description="First target level"
    )

    target_2: float = Field(
        description="Second target level"
    )

    target_3: float = Field(
        description="Third target level"
    )


# =========================
# MAIN TRADE PLAN
# =========================

class TradePlan(BaseModel):

    symbol: str = Field(
        description="Stock symbol"
    )

    decision: Literal[
        "BUY_NOW",
        "BUY_ON_CONFIRMATION",
        "HIGH_RISK_SPECULATIVE",
        "AVOID",
        "SHORT_WATCH"
    ] = Field(
        description="Final trade decision"
    )

    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence score from 0 to 100"
    )

    entry_plan: EntryPlan

    stoploss_plan: StoplossPlan

    target_plan: TargetPlan

    reasons_to_buy: List[str] = Field(
        description="Reasons supporting bullish thesis"
    )

    reasons_to_avoid: List[str] = Field(
        description="Risks or weaknesses in setup"
    )

    post_entry_watchouts: List[str] = Field(
        description="Things trader should monitor after entry"
    )

    trade_thesis: str = Field(
        description="Short overall trade thesis"
    )
