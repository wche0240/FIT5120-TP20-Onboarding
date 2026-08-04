def classify_crowd_level(total_count: int, low_max: int, medium_max: int) -> str:
    """Return a user-facing crowd level from a non-negative minute count."""
    if total_count < 0:
        raise ValueError("total_count cannot be negative")
    if low_max < 0 or medium_max < low_max:
        raise ValueError("crowd thresholds are invalid")
    if total_count <= low_max:
        return "low"
    if total_count <= medium_max:
        return "medium"
    return "high"
