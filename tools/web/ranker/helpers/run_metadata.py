import json
import time
from pathlib import Path
from datetime import datetime
import pytz


class RunTelemetry:

    def __init__(self):
        self.start_time = time.time()

        self.request_timestamps = []

        self.latencies = []

        self.total_calls = 0

        self.success_calls = 0

        self.failed_calls = 0

        self.quota_hits = 0

    # ─────────────────────────────
    # RECORD API CALL
    # ─────────────────────────────
    def record_call(self, latency: float, success=True):

        now = time.time()

        self.request_timestamps.append(now)

        self.latencies.append(latency)

        self.total_calls += 1

        if success:
            self.success_calls += 1
        else:
            self.failed_calls += 1

    # ─────────────────────────────
    # RECORD QUOTA HIT
    # ─────────────────────────────
    def record_quota_hit(self):
        self.quota_hits += 1

    # ─────────────────────────────
    # REQUESTS PER MINUTE
    # ─────────────────────────────
    def calculate_rpm(self):

        if not self.request_timestamps:
            return 0

        elapsed_minutes = (
            max(self.request_timestamps) -
            min(self.request_timestamps)
        ) / 60

        if elapsed_minutes <= 0:
            return self.total_calls

        return round(self.total_calls / elapsed_minutes, 2)

    # ─────────────────────────────
    # PEAK RPM
    # ─────────────────────────────
    def peak_rpm(self):

        timestamps = self.request_timestamps

        if not timestamps:
            return 0

        peak = 0

        for i in range(len(timestamps)):

            window_start = timestamps[i]

            count = 0

            for ts in timestamps:

                if ts >= window_start and ts <= window_start + 60:
                    count += 1

            peak = max(peak, count)

        return peak

    # ─────────────────────────────
    # SAVE METADATA FILE
    # ─────────────────────────────
    def save(self, output_dir="outputs/run_metadata"):

        total_runtime = round(
            time.time() - self.start_time,
            2
        )

        avg_latency = round(
            sum(self.latencies) / len(self.latencies),
            2
        ) if self.latencies else 0

        metadata = {

            "runtime": {

                "total_runtime_seconds": total_runtime,

                "requests_per_minute_avg": self.calculate_rpm(),

                "peak_requests_per_minute": self.peak_rpm(),

                "total_llm_calls": self.total_calls,

                "successful_calls": self.success_calls,

                "failed_calls": self.failed_calls,

                "quota_hits": self.quota_hits,
            },

            "latency": {

                "average_latency_seconds": avg_latency,

                "max_latency_seconds": round(max(self.latencies), 2) if self.latencies else 0,

                "min_latency_seconds": round(min(self.latencies), 2) if self.latencies else 0,
            },

            "generated_at": datetime.now(
                pytz.timezone("Asia/Kolkata")
            ).isoformat()
        }

        output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(
            pytz.timezone("Asia/Kolkata")
        ).strftime("%Y%m%d_%H%M%S")

        output_file = output_dir / f"run_metadata_{ts}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return output_file
