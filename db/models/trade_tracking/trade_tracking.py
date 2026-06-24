from enum import Enum as PyEnum
from datetime import datetime
import pytz
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, JSON
from sqlalchemy.orm import relationship

from db.database import Base

class TrackingStatus(str, PyEnum):
    TRACKING = "TRACKING"
    BUY_ZONE_HIT = "BUY_ZONE_HIT"
    ACTIVE = "ACTIVE"
    TARGET_1_HIT = "TARGET_1_HIT"
    STOPLOSS_HIT = "STOPLOSS_HIT"
    EXPIRED = "EXPIRED"
    IGNORED = "IGNORED"

def get_ist_now():
    return datetime.now(pytz.timezone('Asia/Kolkata'))

class TradeTracking(Base):
    __tablename__ = "trade_tracking"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    status = Column(Enum(TrackingStatus), default=TrackingStatus.TRACKING, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=get_ist_now, index=True, nullable=False)

    # Plan Data
    buy_zone_min = Column(Float, nullable=False)
    buy_zone_max = Column(Float, nullable=False)
    hard_stoploss = Column(Float, nullable=False)
    target_1 = Column(Float, nullable=False)
    target_2 = Column(Float, nullable=True)
    target_3 = Column(Float, nullable=True)

    # Rich Context Data
    decision = Column(String, nullable=False)
    confidence = Column(Integer, nullable=False)
    entry_type = Column(String, nullable=False)
    trade_thesis = Column(String, nullable=False)
    confirmation_conditions = Column(JSON, nullable=False, default=list)
    post_entry_watchouts = Column(JSON, nullable=False, default=list)
    original_plan_json = Column(JSON, nullable=False, default=dict)

    # Execution Data
    entry_price = Column(Float, nullable=True)

    # Timestamps
    updated_at = Column(DateTime(timezone=True), default=get_ist_now, onupdate=get_ist_now, nullable=False)

    # Relationship
    transactions = relationship("TradeTrackingTxn", back_populates="trade_tracking", cascade="all, delete-orphan")
