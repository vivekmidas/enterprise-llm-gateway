# backend/app/utils/time_utils.py
# ==============================================================================
# BLOCK COMMENT: EXECUTION TIMING METADATA
# Description:
#   Single source for node/workflow timing metadata. Emits both epoch timestamps
#   (client can format in customer locale) and ISO-8601 UTC strings.
#   Keys stay flat (start_time, end_time, latency_ms, ...) because the frontend
#   RunVisualizerModal reads context.nodes[id].metadata.latency_ms directly.
# ==============================================================================
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def to_iso_utc(ts: Optional[float]) -> Optional[str]:
    """Converts an epoch timestamp (seconds) to ISO-8601 UTC with millisecond precision."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_timing_metadata(start_ts: float, end_ts: Optional[float] = None, perf_start: Optional[float] = None) -> Dict[str, Any]:
    """
    Builds timing metadata.
    - start_ts / end_ts: wall-clock epoch seconds (time.time()).
    - perf_start: optional time.perf_counter() mark; when given, latency uses the
      monotonic clock (immune to system clock jumps), else end_ts - start_ts.
    """
    end_ts = end_ts if end_ts is not None else time.time()
    if perf_start is not None:
        latency_ms = (time.perf_counter() - perf_start) * 1000
    else:
        latency_ms = (end_ts - start_ts) * 1000
    return {
        "start_time": start_ts,
        "start_time_iso": to_iso_utc(start_ts),
        "end_time": end_ts,
        "end_time_iso": to_iso_utc(end_ts),
        "latency_ms": round(latency_ms, 2),
    }

