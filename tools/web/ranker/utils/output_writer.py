from typing import Dict, Optional
from tools.storage.file_writer import write_json
from .logger import logger


async def save_ranker_output(
    output_data: Dict,
    output_subdir: str = "ranker",
    elapsed_time: Optional[float] = None,
    metrics: object | None = None,
) -> str:
    """
    Save final ranker output to JSON, plus full pipeline metadata when metrics are available.
    Uses the shared file_writer utility for storage.
    """
    if elapsed_time is not None:
        output_data.setdefault("metadata", {})
        output_data["metadata"]["pipeline_time_seconds"] = round(elapsed_time, 2)

    # Save main ranker output
    # filename_prefix includes the subdirectory
    output_file = await write_json(f"{output_subdir}/intraday_signals", output_data)

    # Save metadata if metrics are available
    if metrics is not None and hasattr(metrics, "generate_metadata"):
        metadata_payload = metrics.generate_metadata()
        
        # Merge metadata from output_data if present
        if "metadata" in output_data:
            for k, v in output_data["metadata"].items():
                if k not in metadata_payload:
                    metadata_payload[k] = v
        
        await write_json("metadata/pipeline_metadata", metadata_payload)

    logger.info("=" * 60)
    return output_file
