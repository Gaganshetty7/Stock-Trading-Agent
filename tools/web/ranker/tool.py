import time
from typing import Dict, Optional

from .core.pipeline import execute_ranker_pipeline
from .utils.output_writer import save_ranker_output



async def rank_news_payload(payload_file: Optional[str] = None) -> Dict:
    final_result, metrics = await execute_ranker_pipeline(
        payload_file=payload_file,
    )

    await save_ranker_output(
        final_result,
        elapsed_time=time.time() - metrics.start_time if hasattr(metrics, "start_time") else None,
        metrics=metrics,
    )


    return final_result
