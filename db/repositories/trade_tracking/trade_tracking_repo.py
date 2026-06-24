from sqlalchemy.orm import Session
from db.models.trade_tracking import TradeTracking, TrackingStatus

class TradeTrackingRepository:
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
            status=TrackingStatus.TRACKING
        )
        db.add(trade)
        db.flush()
        return trade
