import json
import logging
from typing import Dict

from ..models.tracking_object import (
    TrackingObject, EntryPlan, BuyZone, StoplossPlan, TargetPlan
)


logger = logging.getLogger(__name__)


def load_plan(plan_path: str) -> Dict[str, TrackingObject]:
    """
    Read a plan JSON file.
    Skip any stock with decision == 'AVOID' or missing required fields.
    Return a dict of symbol → TrackingObject for all trackable stocks.
    """
    logger.debug(f"[PLAN] Reading: {plan_path}")

    with open(plan_path, "r") as f:
        raw: dict = json.load(f)

    watchlist: Dict[str, TrackingObject] = {}

    for symbol, data in raw.items():
        decision = str(data.get("decision", "")).upper()

        if decision == "AVOID":
            logger.debug(f"[SKIP]   {symbol:<20} decision=AVOID")
            continue

        try:
            buy_zone = BuyZone(
                min=float(data["entry_plan"]["buy_zone"]["min"]),
                max=float(data["entry_plan"]["buy_zone"]["max"])
            )
            entry_plan = EntryPlan(
                entry_type=data["entry_plan"].get("entry_type", ""),
                buy_zone=buy_zone,
                confirmation_conditions=data["entry_plan"].get("confirmation_conditions", [])
            )
            stoploss_plan = StoplossPlan(
                hard_stoploss=float(data["stoploss_plan"]["hard_stoploss"]),
                soft_invalidation=data["stoploss_plan"].get("soft_invalidation", [])
            )
            target_plan = TargetPlan(
                target_1=float(data["target_plan"]["target_1"]),
                target_2=float(data["target_plan"]["target_2"]),
                target_3=float(data["target_plan"]["target_3"])
            )

            obj = TrackingObject(
                symbol=symbol,
                decision=decision,
                confidence=int(data.get("confidence", 0)),
                entry_plan=entry_plan,
                stoploss_plan=stoploss_plan,
                target_plan=target_plan,
                reasons_to_buy=data.get("reasons_to_buy", []),
                reasons_to_avoid=data.get("reasons_to_avoid", []),
                post_entry_watchouts=data.get("post_entry_watchouts", []),
                trade_thesis=data.get("trade_thesis", "")
            )

            watchlist[symbol] = obj
            logger.debug(
                f"[LOAD]   {symbol:<20} zone=₹{obj.entry_plan.buy_zone.min}→₹{obj.entry_plan.buy_zone.max}  "
                f"sl=₹{obj.stoploss_plan.hard_stoploss}"
            )
        except KeyError as e:
            logger.warning(f"[SKIP]   {symbol:<20} missing required field: {e}")
        except Exception as e:
            logger.warning(f"[SKIP]   {symbol:<20} failed to parse: {e}")

    logger.info(
        f"[PLAN]   {len(watchlist)} stock(s) loaded for tracking  "
        f"({len(raw) - len(watchlist)} skipped)"
    )
    return watchlist
