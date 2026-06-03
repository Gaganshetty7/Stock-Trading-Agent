# helpers/metrics.py

import time
from dataclasses import dataclass, field
from typing import List, Dict
from tools.web.ranker.utils.logger import logger



@dataclass
class PipelineMetrics:

    # ─────────────────────────────
    # PIPELINE COUNTERS
    # ─────────────────────────────
    total_companies: int = 0
    total_articles_in: int = 0
    total_articles_out: int = 0

    companies_with_signal: int = 0
    companies_removed: int = 0

    # ─────────────────────────────
    # API / LLM METRICS
    # ─────────────────────────────
    api_calls_made: int = 0
    success_count: int = 0
    failure_count: int = 0
    quota_skipped: int = 0
    
    parse_failures: int = 0
    validation_failures: int = 0

    # ─────────────────────────────
    # TIMING
    # ─────────────────────────────
    start_time: float = field(default_factory=time.time)

    latencies: List[float] = field(default_factory=list)

    request_timestamps: List[float] = field(default_factory=list)

    total_stagger_wait_seconds: float = 0.0

    # ─────────────────────────────
    # TOKEN TRACKING
    # ─────────────────────────────
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0

    # ─────────────────────────────
    # BATCH DETAILS
    # ─────────────────────────────
    batch_details: List[dict] = field(default_factory=list)

    # ─────────────────────────────
    # REPORT
    # ─────────────────────────────
    def report(self, daily_usage: Dict = None):

        elapsed = time.time() - self.start_time

        avg_latency = (
            sum(self.latencies) / len(self.latencies)
            if self.latencies else 0
        )

        fastest = min(self.latencies) if self.latencies else 0
        slowest = max(self.latencies) if self.latencies else 0

        rpm_avg = (
            (self.api_calls_made / elapsed) * 60
            if elapsed > 0 else 0
        )

        peak_rpm = self.calculate_peak_rpm()

        lines = [
            "",
            "=" * 60,
            "RANKER PIPELINE REPORT",
            "=" * 60,

            f"Companies Input           : {self.total_companies}",
            f"Companies With Signal     : {self.companies_with_signal}",
            f"Companies Removed         : {self.companies_removed}",

            f"Articles Input            : {self.total_articles_in}",
            f"Articles Output           : {self.total_articles_out}",

            "-" * 60,

            f"API Calls Made            : {self.api_calls_made}",
            f"  - Successes             : {self.success_count}",
            f"  - Failures              : {self.failure_count}",
            f"  - Quota Skips           : {self.quota_skipped}",

            f"Parse Failures            : {self.parse_failures}",
            f"Validation Failures       : {self.validation_failures}",

            "-" * 60,

            f"Average LLM Latency       : {avg_latency:.2f}s",
            f"Fastest LLM Call          : {fastest:.2f}s",
            f"Slowest LLM Call          : {slowest:.2f}s",

            f"Average Requests / Min    : {rpm_avg:.2f}",
            f"Peak Requests / Min       : {peak_rpm}",

            f"Total LLM Time            : {sum(self.latencies):.2f}s",
            f"Total Stagger Wait Time   : {self.total_stagger_wait_seconds:.2f}s",

            "-" * 60,

            f"Input Tokens              : {self.total_input_tokens}",
            f"Output Tokens             : {self.total_output_tokens}",
            f"Total Tokens              : {self.total_tokens}",

            "-" * 60,

            f"Pipeline Runtime          : {elapsed:.2f}s",

            "=" * 60,
        ]

        logger.info("\n".join(lines))

    # ─────────────────────────────
    # PEAK RPM
    # ─────────────────────────────
    def calculate_peak_rpm(self):

        if not self.request_timestamps:
            return 0

        timestamps = sorted(self.request_timestamps)

        peak = 0

        for ts in timestamps:

            count = sum(
                1 for t in timestamps
                if ts <= t <= ts + 60
            )

            peak = max(peak, count)

        return peak

    # ─────────────────────────────
    # GENERATE METADATA JSON
    # ─────────────────────────────
    def generate_metadata(self):

        elapsed = time.time() - self.start_time

        avg_latency = (
            sum(self.latencies) / len(self.latencies)
            if self.latencies else 0
        )

        fastest = min(self.latencies) if self.latencies else 0
        slowest = max(self.latencies) if self.latencies else 0

        rpm_avg = (
            (self.api_calls_made / elapsed) * 60
            if elapsed > 0 else 0
        )

        retention_percent = (
            (self.total_articles_out / self.total_articles_in) * 100
            if self.total_articles_in > 0 else 0
        )

        return {

            "pipeline_runtime_seconds":
                round(elapsed, 2),

            "config": {
                "batch_size": 10,
                "concurrency": 1,
                "stagger_delay_seconds": 6.0,
            },

            "api_summary": {
                "total_calls_attempted": self.api_calls_made,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "quota_skipped_count": self.quota_skipped,
                
                "requests_per_minute_average": round(rpm_avg, 2),
                "peak_requests_per_minute": self.calculate_peak_rpm(),
                
                "average_llm_latency_seconds": round(avg_latency, 2),
                "fastest_llm_call_seconds": round(fastest, 2),
                "slowest_llm_call_seconds": round(slowest, 2),
                "total_llm_processing_seconds": round(sum(self.latencies), 2),
                
                "total_stagger_wait_seconds": round(self.total_stagger_wait_seconds, 2),
                
                "parse_failures": self.parse_failures,
                "validation_failures": self.validation_failures,
            },

            "token_usage": {

                "input_tokens":
                    self.total_input_tokens,

                "output_tokens":
                    self.total_output_tokens,

                "total_tokens":
                    self.total_tokens,
            },

            "data_summary": {

                "companies_input":
                    self.total_companies,

                "companies_with_signal":
                    self.companies_with_signal,

                "companies_removed":
                    self.companies_removed,

                "articles_input":
                    self.total_articles_in,

                "articles_output":
                    self.total_articles_out,

                "signal_retention_percent":
                    round(retention_percent, 2),
            },

            "batches":
                self.batch_details,

            "generated_at":
                time.strftime("%Y-%m-%d %H:%M:%S")
        }
