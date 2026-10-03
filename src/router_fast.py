import math
from collections.abc import Mapping
from dataclasses import dataclass

from src.graph import Coordinate, EdgeId, Graph
from src.pareto import knee, nondominated

LAMBDAS = (0.0, .1, .2, .35, .5, .65, .8, .9, 1.0)


@dataclass(frozen=True)
class RouteResult:
    edge_ids: tuple[EdgeId, ...]
    coordinates: tuple[Coordinate, ...]
    distance_m: float
    time_s: float
    exposure: float  # Seconds multiplied by discomfort on the 0–10 scale.

    @property
    def discomfort_avg(self) -> float:
        return self.exposure / self.time_s if self.time_s else 0.0

    @property
    def geometry(self) -> dict:
        return {
            "type": "LineString",
            "coordinates": [list(point) for point in self.coordinates],
        }


@dataclass(frozen=True)
class SweepResult:
    front: tuple[RouteResult, ...]
    routes: Mapping[str, RouteResult]


def route(
    graph: Graph,
    start: Coordinate,
    end: Coordinate,
    discomfort: Mapping[EdgeId, float],
    lam: float = 0.0,
) -> RouteResult:
    """Internal result; lambda 0 selects FASTEST, lambda 1 selects ECO."""
    if not math.isfinite(lam) or not 0 <= lam <= 1:
        raise ValueError("Lambda must be between 0 and 1")
    if not graph.edges.keys() <= discomfort.keys():
        raise ValueError("Missing edge discomfort values")
    values = [discomfort[edge_id] for edge_id in graph.edges]
    if any(not math.isfinite(d) or not 0 <= d <= 10 for d in values):
        raise ValueError("Discomfort must be finite and between 0 and 10")
    mean = sum(values) / len(values) if values else 0.0
    kappa = 1.0 / max(mean, 1e-6)
    weights = {
        edge_id: edge.time_s * (
            (1 - lam) + lam * kappa * discomfort[edge_id]
        )
        for edge_id, edge in graph.edges.items()
    }
    source = graph.snap(*start)
    target = graph.snap(*end)
    edge_ids = graph.shortest(source, target, weights)
    coordinates = [graph.nodes[source]]
    for edge_id in edge_ids:
        coordinates.extend(graph.edges[edge_id].coordinates[1:])
    if not edge_ids:
        coordinates.append(coordinates[0])
    return RouteResult(
        edge_ids=edge_ids,
        coordinates=tuple(coordinates),
        distance_m=sum(graph.edges[e].length_m for e in edge_ids),
        time_s=sum(graph.edges[e].time_s for e in edge_ids),
        exposure=sum(
            graph.edges[e].time_s * discomfort[e] for e in edge_ids
        ),
    )


def sweep(
    graph: Graph,
    start: Coordinate,
    end: Coordinate,
    discomfort: Mapping[EdgeId, float],
) -> SweepResult:
    candidates = {}
    for lam in LAMBDAS:
        candidate = route(graph, start, end, discomfort, lam)
        candidates.setdefault(candidate.edge_ids, candidate)
    unique = list(candidates.values())
    objectives = [(r.time_s, r.exposure) for r in unique]
    front = tuple(unique[i] for i in nondominated(objectives))
    selected = {"fastest": front[0]}
    choices = [("cleanest", front[-1])]
    if len(front) >= 3:
        index = knee([(r.time_s, r.exposure) for r in front])
        choices.append(("balanced", front[index]))
    for name, candidate in choices:
        edges = set(candidate.edge_ids)
        for existing in selected.values():
            other = set(existing.edge_ids)
            union = edges | other
            similarity = len(edges & other) / len(union) if union else 1.0
            if similarity > .9:
                break
        else:
            selected[name] = candidate
    routes = {
        name: selected[name]
        for name in ("fastest", "balanced", "cleanest")
        if name in selected
    }
    return SweepResult(front=front, routes=routes)
