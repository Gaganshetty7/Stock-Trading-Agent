import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pytz

from ..utils.logger import logger


def save_ranker_output(
    output_data: Dict,
    output_subdir: str = "outputs/ranker",
    elapsed_time: Optional[float] = None,
    metrics: object | None = None,
) -> str:
    """
    Save final ranker output to JSON, plus full pipeline metadata when metrics are available.
    """
    ist = pytz.timezone("Asia/Kolkata")
    timestamp = datetime.now(ist).strftime("%Y%m%d_%H%M%S")

    output_dir = Path(output_subdir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"intraday_signals_{timestamp}.json"

    if elapsed_time is not None:
        output_data.setdefault("metadata", {})
        output_data["metadata"]["pipeline_time_seconds"] = round(elapsed_time, 2)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    if metrics is not None and hasattr(metrics, "generate_metadata"):
        metadata_dir = Path("outputs/metadata")
        metadata_dir.mkdir(parents=True, exist_ok=True)
        metadata_payload = metrics.generate_metadata()
        metadata_payload.update(
            {
                k: v
                for k, v in output_data.get("metadata", {}).items()
                if k not in metadata_payload
            }
        )
        metadata_file = metadata_dir / f"pipeline_metadata_{timestamp}.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata_payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved pipeline metadata → {metadata_file}")

    logger.info(f"Saved ranker output → {output_file}")
    logger.info("=" * 60)
    return str(output_file)
