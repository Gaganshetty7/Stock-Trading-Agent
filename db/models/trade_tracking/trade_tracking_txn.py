from enum import Enum as PyEnum
from datetime import datetime
import pytz
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship

from db.database import Base
from .trade_tracking import TrackingStatus

class TradeEventType(str, PyEnum):
    # Trade lifecycle
    TRADE_CREATED = "TRADE_CREATED"

    # Tracking phase
    BUY_ZONE_HIT = "BUY_ZONE_HIT"

    # Profit milestones
    TARGET_1_HIT = "TARGET_1_HIT"

    # Risk / exit events
    STOPLOSS_HIT = "STOPLOSS_HIT"

    # Trade termination
    TRADE_CLOSED = "TRADE_CLOSED"
    EXPIRED = "EXPIRED"
    IGNORED = "IGNORED"

def get_ist_now():
    return datetime.now(pytz.timezone('Asia/Kolkata'))

class TradeTrackingTxn(Base):
    __tablename__ = "trade_tracking_txn"

    id = Column(Integer, primary_key=True, index=True)
    trade_tracking_id = Column(Integer, ForeignKey('trade_tracking.id'), index=True, nullable=False)
    event_type = Column(Enum(TradeEventType), nullable=False)
    
    old_status = Column(Enum(TrackingStatus), nullable=True)
    new_status = Column(Enum(TrackingStatus), nullable=True)
    
    message = Column(String, nullable=True)
    telegram_message_id = Column(String, nullable=True)
    alert_sent = Column(Boolean, default=False, nullable=False)
    
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=get_ist_now, nullable=False)

    # Relationship
    trade_tracking = relationship("TradeTracking", back_populates="transactions")
