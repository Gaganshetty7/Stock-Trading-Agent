from typing import Dict, Optional
from pathlib import Path
from tools.storage.file_writer import write_json
import json
from .logger import logger
from core.logger import RUN_TIMESTAMP

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
        
        metadata_save_dir = Path("logs/ranker/batch_logs")
        metadata_save_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = metadata_save_dir / f"pipeline_metadata_{RUN_TIMESTAMP}.json"
        
        with open(metadata_path, "w") as f:
            json.dump(metadata_payload, f, indent=2)

    logger.info("=" * 60)
    return output_file
