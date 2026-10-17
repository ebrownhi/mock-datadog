"""Request counts over the half-open interval (now - window_seconds, now]."""


def summarize(events, window_seconds, now):
    """Scan all events, counting 5xx responses in the event-time window.

    Return None for an empty window's fraction, and zero for healthy traffic.
    Input order does not matter; events after now are excluded.
    """
    total = 0
    errors = 0
    for event in events:
        if now - window_seconds < event.timestamp <= now:
            total += 1
            errors += int(500 <= event.status <= 599)
    return {
        "total": total,
        "errors": errors,
        "error_fraction": errors / total if total else None,
    }


def legacy_bucket_rates(events, bucket_seconds=60):
    """Deprecated: use summarize's sliding window for current monitor evaluation.

    This historical-chart helper groups all services into epoch-aligned buckets
    [start, start + bucket_seconds). A boundary event enters the next bucket.
    Unlike a rolling window ending at now, these intervals never move and this
    helper has no now cutoff. It expects validated Event records.

    bucket_seconds must be a positive integer (not bool). Return occupied buckets
    in ascending order, with start/end timestamps, total, errors, and error_fraction.
    Empty buckets are omitted; empty input returns []. Healthy occupied buckets
    have a zero fraction, so absent data is distinct from healthy traffic.
    """
    if (isinstance(bucket_seconds, bool)
            or not isinstance(bucket_seconds, int) or bucket_seconds <= 0):
        raise ValueError("bucket_seconds must be a positive integer")

    buckets = {}
    for event in events:
        start = int(event.timestamp // bucket_seconds) * bucket_seconds
        bucket = buckets.setdefault(start, {
            "start": start,
            "end": start + bucket_seconds,
            "total": 0,
            "errors": 0,
        })
        bucket["total"] += 1
        bucket["errors"] += int(500 <= event.status <= 599)

    result = []
    for start in sorted(buckets):
        bucket = buckets[start]
        bucket["error_fraction"] = bucket["errors"] / bucket["total"]
        result.append(bucket)
    return result
