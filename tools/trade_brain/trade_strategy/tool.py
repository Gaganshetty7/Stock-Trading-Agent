from typing import Optional, Dict

from .core.payload import load_technicals_payload
from .core.pipeline import execute_trade_brain_pipeline

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
    # 1. Load the payload
    try:
        technical_data, source_file = load_technicals_payload(file_path)
    except Exception as e:
        return {"status": "error", "message": f"Failed to load payload: {str(e)}"}
        
    # 2. Execute pipeline
    try:
        output_file = await execute_trade_brain_pipeline(technical_data)
        
        return {
            "status": "success",
            "message": f"Successfully generated trade plans for {len(technical_data)} tickers.",
            "source_data_file": source_file,
            "generated_plan_file": output_file
        }
    except Exception as e:
        return {"status": "error", "message": f"Pipeline execution failed: {str(e)}"}
