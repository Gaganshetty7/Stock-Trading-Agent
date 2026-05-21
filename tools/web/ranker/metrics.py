import time
from dataclasses import dataclass, field
from typing import List, Dict
import logging

# Get the ranker logger
logger = logging.getLogger("ranker")

@dataclass
class PipelineMetrics:
    total_companies: int = 0
    total_articles_in: int = 0
    total_articles_out: int = 0
    companies_with_signal: int = 0
    companies_removed: int = 0
    api_calls_made: int = 0
    quota_skipped: int = 0
    parse_failures: int = 0
    validation_failures: int = 0
    start_time: float = field(default_factory=time.time)
    latencies: List[float] = field(default_factory=list)

    def report(self, daily_usage: Dict = None, output_file: str = None):
        elapsed = time.time() - self.start_time
        avg_lat = sum(self.latencies) / len(self.latencies) if self.latencies else 0

        lines = [
            "\n" + "=" * 50,
            "INTRADAY SIGNAL EXTRACTION REPORT",
            "=" * 50,
            f"  Companies Input:      {self.total_companies}",
            f"  Companies w/ Signal:  {self.companies_with_signal}",
            f"  Companies Removed:    {self.companies_removed}",
            f"  Articles In:          {self.total_articles_in}",
            f"  Articles Out (kept):  {self.total_articles_out}",
            f"  Noise Filtered:       {self.total_articles_in - self.total_articles_out}",
            "-" * 30,
            f"  API Calls Made:       {self.api_calls_made}",
            f"  Avg Batch Latency:    {avg_lat:.2f}s",
            f"  Total Time:           {elapsed:.2f}s",
            f"  Quota Skips (429):    {self.quota_skipped}",
            f"  JSON Parse Errors:    {self.parse_failures}",
            f"  Schema Violations:    {self.validation_failures}",
            "-" * 30
        ]
        
        if daily_usage:
            summary = daily_usage.get("summary", {})
            lines.append("TOTAL DAILY API USAGE (TRACKED):")
            for model_key, count in summary.items():
                lines.append(f"  {model_key}: {count} reqs")
        
        lines.append("=" * 50)
        
        # Add the final pipeline completion style summary
        lines.append(f"PIPELINE COMPLETE IN {elapsed:.2f}s")
        lines.append(f"Companies with signals: {self.companies_with_signal}")
        lines.append(f"Companies removed (noise): {self.companies_removed}")
        lines.append(f"Total articles kept: {self.total_articles_out}")
        if output_file:
            lines.append(f"Saved to: {output_file}")
        lines.append("=" * 50 + "\n")
        
        output = "\n".join(lines)
        print(output)
        logger.info(output)
