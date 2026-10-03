import json
import math
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
from typing import Mapping


EdgeId = tuple[int, int, int]
Coordinate = tuple[float, float]  # WGS84: longitude, latitude.


class NoRoute(Exception):
    pass


@dataclass(frozen=True)
class Edge:
    u: int
    v: int
    key: int
    length_m: float
    time_s: float
    coordinates: tuple[Coordinate, ...]

    @property
    def id(self) -> EdgeId:
        return self.u, self.v, self.key


class Graph:
    def __init__(
        self, nodes: Mapping[int, Coordinate], edges: list[Edge]
    ) -> None:
        if not nodes:
            raise ValueError("Graph must contain nodes")
        self.nodes = dict(nodes)
        for lon, lat in self.nodes.values():
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("Invalid WGS84 node coordinates")
        self.edges: dict[EdgeId, Edge] = {}
        self.adjacency: dict[int, list[EdgeId]] = {
            node: [] for node in self.nodes
        }
        for edge in edges:
            if edge.u not in nodes or edge.v not in nodes:
                raise ValueError("Edge references an unknown node")
            if edge.id in self.edges:
                raise ValueError("Duplicate (u, v, key)")
            if not all(
                math.isfinite(value) and value > 0
                for value in (edge.length_m, edge.time_s)
            ):
                raise ValueError("Edge length and time must be positive")
            if (
                len(edge.coordinates) < 2
                or edge.coordinates[0] != nodes[edge.u]
                or edge.coordinates[-1] != nodes[edge.v]
            ):
                raise ValueError("Geometry must follow the edge direction")
            for lon, lat in edge.coordinates:
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError("Invalid WGS84 edge coordinates")
            self.edges[edge.id] = edge
            self.adjacency[edge.u].append(edge.id)

    @classmethod
    def load(cls, path: str | Path) -> "Graph":
        with Path(path).open(encoding="utf-8") as file:
            data = json.load(file)
        nodes = {
            int(node): tuple(coords)
            for node, coords in data["nodes"].items()
        }
        edges = [
            Edge(
                u=item["u"], v=item["v"], key=item["key"],
                length_m=item["length_m"], time_s=item["time_s"],
                coordinates=tuple(tuple(p) for p in item["coordinates"]),
            )
            for item in data["edges"]
        ]
        return cls(nodes, edges)

    def snap(self, lon: float, lat: float) -> int:
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("Invalid WGS84 coordinates")
        lon_scale = math.cos(math.radians(lat))
        # ponytail: linear scan; use a spatial index for the city graph.
        return min(
            self.nodes,
            key=lambda node: (
                ((self.nodes[node][0] - lon) * lon_scale) ** 2
                + (self.nodes[node][1] - lat) ** 2
            ),
        )

    def shortest(
        self, start: int, end: int, weights: Mapping[EdgeId, float]
    ) -> tuple[EdgeId, ...]:
        if start not in self.nodes or end not in self.nodes:
            raise ValueError("Unknown start or end node")
        if not self.edges.keys() <= weights.keys():
            raise ValueError("Missing edge weights")
        for edge_id in self.edges:
            cost = weights[edge_id]
            if not math.isfinite(cost) or cost < 0:
                raise ValueError("Weights must be finite and nonnegative")
        distances = {start: 0.0}
        predecessors: dict[int, EdgeId] = {}
        queue = [(0.0, start)]
        while queue:
            distance, node = heappop(queue)
            if distance != distances[node]:
                continue
            if node == end:
                path = []
                while node != start:
                    edge_id = predecessors[node]
                    path.append(edge_id)
                    node = edge_id[0]
                return tuple(reversed(path))
            for edge_id in self.adjacency[node]:
                target = edge_id[1]
                candidate = distance + weights[edge_id]
                if candidate < distances.get(target, math.inf):
                    distances[target] = candidate
                    predecessors[target] = edge_id
                    heappush(queue, (candidate, target))
        raise NoRoute(f"No directed route from {start} to {end}")
