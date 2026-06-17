from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class BuyZone:
    min: float
    max: float

@dataclass
class EntryPlan:
    entry_type: str
    buy_zone: BuyZone
    confirmation_conditions: List[str] = field(default_factory=list)

@dataclass
class StoplossPlan:
    hard_stoploss: float
    soft_invalidation: List[str] = field(default_factory=list)

@dataclass
class TargetPlan:
    target_1: float
    target_2: float
    target_3: float

@dataclass
class TrackingObject:
    symbol: str
    decision: str
    confidence: int
    entry_plan: EntryPlan
    stoploss_plan: StoplossPlan
    target_plan: TargetPlan
    reasons_to_buy: List[str] = field(default_factory=list)
    reasons_to_avoid: List[str] = field(default_factory=list)
    post_entry_watchouts: List[str] = field(default_factory=list)
    trade_thesis: str = ""

    # Tracking state
    tracking_started_at: datetime = field(default_factory=datetime.now)
    status: str = "AWAITING_ENTRY"   # AWAITING_ENTRY | IN_TRADE | COMPLETED | EXPIRED
    entry_price: float = 0.0
    alert_sent: bool = False

    def elapsed_minutes(self) -> float:
        return (datetime.now() - self.tracking_started_at).total_seconds() / 60

    def __repr__(self) -> str:
        return (
            f"TrackingObject({self.symbol} | status={self.status} | "
            f"zone={self.entry_plan.buy_zone.min}→{self.entry_plan.buy_zone.max} | "
            f"elapsed={self.elapsed_minutes():.1f}m)"
        )
