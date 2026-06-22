from typing import Optional, Dict

from .core.payload import load_technicals_payload
from .core.pipeline import execute_trade_brain_pipeline
from core.logger import get_logger

logger = get_logger("trade_strategy")

async def trade_strategy(file_path: Optional[str] = None) -> Dict:
    """
    Locates the technical analysis batch file, processes each ticker using
    an institutional trade reasoning engine, and saves the generated trade plans.
    
    Args:
        file_path (str, optional): The absolute path to the JSON file containing 
                                   technical analysis data. If not provided, it 
                                   will auto-locate the latest file.
                                   
    Returns:
        Dict: An observation summarizing the execution and the saved file path.
    """
    logger.info("Starting trade strategy execution...")
    
    # 1. Load the payload
    try:
        market_context, technical_data, source_file = load_technicals_payload(file_path)
        logger.info(f"Loaded payload from: {source_file}")
    except Exception as e:
        logger.error(f"Failed to load payload: {str(e)}")
        return {"status": "error", "message": f"Failed to load payload: {str(e)}"}
        
    # 2. Execute pipeline
    try:
        logger.info(f"Executing pipeline for {len(technical_data)} tickers...")
        output_file = await execute_trade_brain_pipeline(market_context, technical_data)
        logger.info(f"Pipeline execution complete. Results saved to: {output_file}")
        
        return {
            "status": "success",
            "message": f"Successfully generated trade plans for {len(technical_data)} tickers.",
            "source_data_file": source_file,
            "generated_plan_file": output_file
        }
    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}")
        return {"status": "error", "message": f"Pipeline execution failed: {str(e)}"}
