from __future__ import annotations

from vallmopt.benchmark.stats import compute_iqr, compute_median, compute_speedup, summarize_timings


def test_stats_compute_median_iqr_and_speedup() -> None:
    assert compute_median([5.0, 1.0, 3.0]) == 3.0
    assert compute_iqr([1.0, 2.0, 3.0, 4.0, 5.0]) == 2.0
    assert compute_speedup(10.0, 5.0) == 2.0


def test_summarize_timings() -> None:
    summary = summarize_timings(
        baseline=[10.0, 12.0, 14.0],
        candidate=[5.0, 6.0, 7.0],
    )

    assert summary["baseline_median_sec"] == 12.0
    assert summary["candidate_median_sec"] == 6.0
    assert summary["speedup"] == 2.0
