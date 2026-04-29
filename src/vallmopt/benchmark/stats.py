"""Benchmark statistics."""

from __future__ import annotations

from statistics import median


def compute_median(values: list[float]) -> float:
    """Compute the median of a non-empty timing list."""

    if not values:
        raise ValueError("Cannot compute median of an empty list")
    return float(median(values))


def percentile(values: list[float], p: float) -> float:
    """Compute a linear-interpolated percentile for ``0 <= p <= 1``."""

    if not values:
        raise ValueError("Cannot compute percentile of an empty list")
    if not 0 <= p <= 1:
        raise ValueError("Percentile p must be in [0, 1]")
    sorted_values = sorted(float(value) for value in values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def compute_iqr(values: list[float]) -> float:
    """Compute Q3 - Q1 using linear-interpolated quartiles."""

    return percentile(values, 0.75) - percentile(values, 0.25)


def compute_speedup(baseline_median: float, candidate_median: float) -> float:
    """Compute speedup as baseline median divided by candidate median."""

    if candidate_median <= 0:
        raise ValueError("Candidate median must be positive")
    return baseline_median / candidate_median


def summarize_timings(baseline: list[float], candidate: list[float]) -> dict[str, float]:
    """Summarize repeated baseline and candidate timings."""

    baseline_median = compute_median(baseline)
    candidate_median = compute_median(candidate)
    return {
        "baseline_median_sec": baseline_median,
        "candidate_median_sec": candidate_median,
        "baseline_iqr_sec": compute_iqr(baseline),
        "candidate_iqr_sec": compute_iqr(candidate),
        "speedup": compute_speedup(baseline_median, candidate_median),
    }
