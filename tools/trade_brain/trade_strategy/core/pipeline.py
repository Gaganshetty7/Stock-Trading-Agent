import json
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage

from core.llm import get_llm
from config.settings import (
    TRADE_STRATEGY_LLM_PROVIDER,
    TRADE_STRATEGY_MODEL,
    TRADE_STRATEGY_LLM_TEMPERATURE,
    TRADE_STRATEGY_API_KEY
)
from agents.trade_brain_agent.schema import TradePlan
from tools.storage.file_writer import write_json
from ..llm.prompts import TRADE_BRAIN_SYSTEM_PROMPT
from core.logger import get_logger

logger = get_logger("TradeStrategy")

async def execute_trade_brain_pipeline(technical_data: Dict) -> str:
    """
    Iterates through technical data, invoking the LLM with strict TradePlan
    schema enforcement for each ticker, and saves the final result.
    """
    llm = get_llm(
        provider=TRADE_STRATEGY_LLM_PROVIDER,
        model=TRADE_STRATEGY_MODEL,
        temperature=TRADE_STRATEGY_LLM_TEMPERATURE,
        api_key=TRADE_STRATEGY_API_KEY
    )
    structured_llm = llm.with_structured_output(TradePlan)
    
    final_results = {}
    
    # Process each ticker
    for ticker, data in technical_data.items():
        try:
            logger.info(f"Processing ticker: {ticker}")
            # Prepare messages
            messages = [
                SystemMessage(content=TRADE_BRAIN_SYSTEM_PROMPT),
                HumanMessage(content=f"Technical data for {ticker}:\n{json.dumps(data, indent=2)}")
            ]
            
            # Invoke LLM with strict schema output
            plan: TradePlan = await structured_llm.ainvoke(messages)
            
            final_results[ticker] = plan.model_dump()
            logger.info(f"Successfully generated plan for {ticker}")
            
        except Exception as e:
            logger.error(f"Failed to generate plan for {ticker}: {str(e)}")
            final_results[ticker] = {"error": f"Failed to generate plan: {str(e)}"}
            
    # Save the aggregated results
    output_filepath = await write_json(
        filename_prefix="trade_strategy/plan",
        data=final_results,
        overwrite=False
    )
    
    return output_filepath
