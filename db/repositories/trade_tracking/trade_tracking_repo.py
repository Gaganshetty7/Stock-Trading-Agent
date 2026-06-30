from typing import List, Optional
from datetime import datetime
import pytz
from sqlalchemy.orm import Session

from db.models.trade_tracking import TradeTracking, TrackingStatus, TradeTrackingTxn, TradeEventType

def get_ist_now():
    return datetime.now(pytz.timezone('Asia/Kolkata'))

class TradeTrackingRepository:
    # Saves a brand new trade plan to the database.
    def create(self, db: Session, plan_data: dict) -> TradeTracking:
        trade = TradeTracking(
            symbol=plan_data.get('symbol'),
            decision=plan_data.get('decision'),
            confidence=plan_data.get('confidence'),
            entry_type=plan_data.get('entry_type'),
            trade_thesis=plan_data.get('trade_thesis'),
            confirmation_conditions=plan_data.get('confirmation_conditions', []),
            post_entry_watchouts=plan_data.get('post_entry_watchouts', []),
            original_plan_json=plan_data.get('original_plan_json', {}),
            buy_zone_min=plan_data.get('buy_zone_min'),
            buy_zone_max=plan_data.get('buy_zone_max'),
            hard_stoploss=plan_data.get('hard_stoploss'),
            target_1=plan_data.get('target_1'),
            target_2=plan_data.get('target_2'),
            target_3=plan_data.get('target_3'),
            run_batch=plan_data.get('run_batch'),
            status=TrackingStatus.TRACKING
        )
        db.add(trade)
        db.flush()
        return trade

    # Fetches all trades currently in the ACTIVE state.
    def get_active_trades(self, db: Session) -> List[TradeTracking]:
        return db.query(TradeTracking).filter(TradeTracking.status == TrackingStatus.ACTIVE).all()

    # Fetches the entire history of trades for a specific stock ticker.
    def get_trades_by_symbol(self, db: Session, symbol: str) -> List[TradeTracking]:
        return db.query(TradeTracking).filter(TradeTracking.symbol == symbol).all()

    # Fetches all trades generated since midnight today.
    def get_trades_created_today(self, db: Session) -> List[TradeTracking]:
        today_start = get_ist_now().replace(hour=0, minute=0, second=0, microsecond=0)
        return db.query(TradeTracking).filter(TradeTracking.created_at >= today_start).all()

    # Fetches both pending (TRACKING) and live (ACTIVE) trades so the background scheduler can monitor them.
    def get_active_and_tracking_trades(self, db: Session) -> List[TradeTracking]:
        return db.query(TradeTracking).filter(
            TradeTracking.status.in_([TrackingStatus.TRACKING, TrackingStatus.ACTIVE])
        ).all()

    # Safely changes a trade's status while automatically saving a permanent record of the change to the transaction ledger.
    def update_trade_status(
        self, 
        db: Session, 
        trade_id: int, 
        new_status: TrackingStatus, 
        event_type: TradeEventType, 
        event_message: str = None, 
        event_details: dict = None, 
        telegram_message_id: str = None, 
        alert_sent: bool = False
    ) -> TradeTracking:
        
        trade = db.query(TradeTracking).with_for_update().filter(TradeTracking.id == trade_id).first()
        if not trade:
            raise ValueError(f"TradeTracking with id {trade_id} not found.")

        old_status = trade.status
        trade.status = new_status
        db.flush()

        txn = TradeTrackingTxn(
            trade_tracking_id=trade.id,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            message=event_message,
            telegram_message_id=telegram_message_id,
            alert_sent=alert_sent,
            details=event_details
        )
        db.add(txn)
        
        return trade

    # A shortcut method that specifically marks a trade as BUY_ZONE_HIT and logs the Telegram alert.
    def mark_buy_zone_hit(self, db: Session, trade_id: int, message_id: str, current_price: float) -> TradeTracking:
        return self.update_trade_status(
            db=db,
            trade_id=trade_id,
            new_status=TrackingStatus.BUY_ZONE_HIT,
            event_type=TradeEventType.BUY_ZONE_HIT,
            event_message="Buy zone hit.",
            event_details={"ltp": current_price},
            telegram_message_id=message_id,
            alert_sent=True
        )

    # Safely updates the actual entry price of the trade once it gets executed.
    def record_execution(self, db: Session, trade_id: int, entry_price: float) -> TradeTracking:
        trade = db.query(TradeTracking).with_for_update().filter(TradeTracking.id == trade_id).first()
        if not trade:
            raise ValueError(f"TradeTracking with id {trade_id} not found.")
        
        trade.entry_price = entry_price
        db.flush()
        return trade

    # Fetches specific trades by their IDs (used for snooze re-evaluation).
    def get_trades_by_ids(self, db: Session, trade_ids: List[int]) -> List[TradeTracking]:
        if not trade_ids:
            return []
        return db.query(TradeTracking).filter(TradeTracking.id.in_(trade_ids)).all()

    # Fetches all trades that are NOT in a terminal state (for market close bulk update).
    def get_all_non_terminal_trades(self, db: Session) -> List[TradeTracking]:
        terminal_statuses = [
            TrackingStatus.TARGET_1_HIT,
            TrackingStatus.STOPLOSS_HIT,
            TrackingStatus.EXPIRED,
            TrackingStatus.IGNORED,
            TrackingStatus.MARKET_CLOSED,
        ]
        return db.query(TradeTracking).filter(
            TradeTracking.status.notin_(terminal_statuses)
        ).all()
