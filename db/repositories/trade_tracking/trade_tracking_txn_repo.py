from sqlalchemy.orm import Session
from db.models.trade_tracking import TradeTrackingTxn, TradeEventType, TrackingStatus

class TradeTrackingTxnRepository:
    def create(self, db: Session, trade_id: int, event_type: TradeEventType, new_status: TrackingStatus, details: dict, message: str = None) -> TradeTrackingTxn:
        txn = TradeTrackingTxn(
            trade_tracking_id=trade_id,
            event_type=event_type,
            new_status=new_status,
            message=message,
            details=details
        )
        db.add(txn)
        db.flush()
        return txn
