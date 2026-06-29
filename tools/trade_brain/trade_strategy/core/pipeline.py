import json
import asyncio
from typing import Dict
from langchain_core.messages import SystemMessage, HumanMessage

from core.llm import get_llm
from config.settings import (
    TRADE_STRATEGY_LLM_PROVIDER,
    TRADE_STRATEGY_MODEL,
    TRADE_STRATEGY_LLM_TEMPERATURE,
    TRADE_STRATEGY_API_KEY,
    TRADE_STRATEGY_MAX_RETRIES,
)
from agents.trade_brain_agent.schema import TradePlan
from tools.storage.file_writer import write_json
from core.logger import get_logger
import os

logger = get_logger("TradeStrategy")

# Uncomment the import statement below to use prompts file and comment skill path block below
# from ..llm.prompts import TRADE_BRAIN_SYSTEM_PROMPT

skill_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "llm", "SKILL.MD")
with open(skill_path, "r", encoding="utf-8") as f:
    TRADE_BRAIN_SYSTEM_PROMPT = f.read()


from db.database import SessionLocal
from db.repositories.trade_tracking.trade_tracking_repo import TradeTrackingRepository
from db.repositories.trade_tracking.trade_tracking_txn_repo import TradeTrackingTxnRepository
from db.models.trade_tracking import TradeEventType, TrackingStatus

def _push_plan_to_db(plan: TradePlan, raw_plan_dict: dict) -> None:
    """Push an actionable TradePlan to PostgreSQL."""
    ACTIONABLE_DECISIONS = {"BUY_NOW", "BUY_ON_CONFIRMATION", "HIGH_RISK_SPECULATIVE"}
    if plan.decision not in ACTIONABLE_DECISIONS:
        logger.info(f"Skipping DB insert for {plan.symbol} due to non-actionable decision: {plan.decision}")
        return

    plan_data = {
        "symbol": plan.symbol,
        "decision": plan.decision,
        "confidence": plan.confidence,
        "entry_type": plan.entry_plan.entry_type,
        "trade_thesis": plan.trade_thesis,
        "confirmation_conditions": plan.entry_plan.confirmation_conditions,
        "post_entry_watchouts": plan.post_entry_watchouts,
        "original_plan_json": raw_plan_dict,
        "buy_zone_min": plan.entry_plan.buy_zone.min,
        "buy_zone_max": plan.entry_plan.buy_zone.max,
        "hard_stoploss": plan.stoploss_plan.hard_stoploss,
        "target_1": plan.target_plan.target_1,
        "target_2": plan.target_plan.target_2,
        "target_3": plan.target_plan.target_3,
    }

    tracking_repo = TradeTrackingRepository()
    txn_repo = TradeTrackingTxnRepository()

    try:
        with SessionLocal() as db:
            trade = tracking_repo.create(db, plan_data)
            txn_repo.create(
                db=db,
                trade_id=trade.id,
                event_type=TradeEventType.TRADE_CREATED,
                new_status=TrackingStatus.TRACKING,
                details=raw_plan_dict,
                message=f"AI Trade Plan created with decision: {plan.decision}"
            )
            db.commit()
            logger.info(f"Successfully pushed plan for {plan.symbol} to DB (Trade ID: {trade.id})")
    except Exception as e:
        logger.error(f"Failed to push plan for {plan.symbol} to DB: {e}")

async def execute_trade_brain_pipeline(market_context: Dict, technical_data: Dict) -> str:
    """
    Iterates through technical data, invoking the LLM with strict TradePlan
    schema enforcement for each ticker, and saves the final result.
    """
    llm = get_llm(
        provider=TRADE_STRATEGY_LLM_PROVIDER,
        model=TRADE_STRATEGY_MODEL,
        temperature=TRADE_STRATEGY_LLM_TEMPERATURE,
        api_key=TRADE_STRATEGY_API_KEY,
    )
    structured_llm = llm.with_structured_output(TradePlan)

    final_results = {}
    max_retries = TRADE_STRATEGY_MAX_RETRIES

    for ticker, data in technical_data.items():
        logger.info(f"Processing ticker: {ticker}")
        prompt_content = (
            f"--- GLOBAL MARKET CONTEXT (NIFTY 50) ---\n"
            f"{json.dumps(market_context, indent=2)}\n\n"
            f"--- STOCK TO ANALYZE: {ticker} ---\n"
            f"{json.dumps(data, indent=2)}"
        )
        messages = [
            SystemMessage(content=TRADE_BRAIN_SYSTEM_PROMPT),
            HumanMessage(content=prompt_content)
        ]

        plan_dict = None
        for attempt in range(max_retries + 1):
            try:
                plan: TradePlan = await structured_llm.ainvoke(messages)
                plan_dict = plan.model_dump()
                logger.info(f"Successfully generated plan for {ticker}")
                _push_plan_to_db(plan, plan_dict)
                break
            except Exception as e:
                if attempt < max_retries:
                    backoff = 5.0 * (2 ** attempt)
                    logger.debug(f"Retrying {ticker} (attempt {attempt + 1}) after error: {str(e)}")
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Failed to generate plan for {ticker} after {max_retries} retries: {str(e)}")
                    plan_dict = {"error": f"Failed to generate plan after {max_retries} retries: {str(e)}"}

        final_results[ticker] = plan_dict
    output_filepath = await write_json(
        filename_prefix="TradeBrainAgent/trade_strategy/plan",
        data=final_results,
        overwrite=False
    )

    return output_filepath
