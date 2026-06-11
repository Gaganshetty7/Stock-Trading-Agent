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
from ..llm.prompts import TRADE_BRAIN_SYSTEM_PROMPT


async def execute_trade_brain_pipeline(technical_data: Dict) -> str:
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
        messages = [
            SystemMessage(content=TRADE_BRAIN_SYSTEM_PROMPT),
            HumanMessage(content=f"Technical data for {ticker}:\n{json.dumps(data, indent=2)}")
        ]

        plan_dict = None
        for attempt in range(max_retries + 1):
            try:
                plan: TradePlan = await structured_llm.ainvoke(messages)
                plan_dict = plan.model_dump()
                break
            except Exception as e:
                if attempt < max_retries:
                    backoff = 5.0 * (2 ** attempt)
                    await asyncio.sleep(backoff)
                else:
                    plan_dict = {"error": f"Failed to generate plan after {max_retries} retries: {str(e)}"}

        final_results[ticker] = plan_dict

    output_filepath = await write_json(
        filename_prefix="trade_strategy/plan",
        data=final_results,
        overwrite=False
    )

    return output_filepath
