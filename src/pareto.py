from collections.abc import Sequence


def nondominated(objectives: Sequence[tuple[float, float]]) -> list[int]:
    """Return indices ordered by time, retaining one copy of equal metrics."""
    ordered = sorted(range(len(objectives)), key=objectives.__getitem__)
    keep = []
    best_exposure = float("inf")
    for index in ordered:
        exposure = objectives[index][1]
        if exposure < best_exposure:
            keep.append(index)
            best_exposure = exposure
    return keep


def knee(front: Sequence[tuple[float, float]]) -> int:
    """Select an interior compromise on a nondominated front sorted by time."""
    if not front:
        raise ValueError("Pareto front is empty")
    if len(front) < 3:
        return 0
    first, last = front[0], front[-1]
    time_span = max(last[0] - first[0], 1e-9)
    exposure_span = max(first[1] - last[1], 1e-9)
    return max(
        range(1, len(front) - 1),
        key=lambda i: abs(
            (front[i][0] - first[0]) / time_span
            + (front[i][1] - last[1]) / exposure_span - 1
        ),
    )
