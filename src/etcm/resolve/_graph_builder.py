from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from etcm.resolve._specs import ResolvedSpec
from etcm.resolve.graph import (
    PathResolution,
    ResolvedEdge,
    ResolvedGraph,
    ResolvedNode,
    ResolvedValue,
)


@dataclass(frozen=True)
class NodeResult:
    node_id: str
    spec: ResolvedSpec
    values: Mapping[str, ResolvedValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass
class GraphBuilder:
    root_selector: str
    sources: set[Path] = field(default_factory=set)
    nodes: dict[str, ResolvedNode] = field(default_factory=dict)
    edges: list[ResolvedEdge] = field(default_factory=list)
    paths: list[PathResolution] = field(default_factory=list)
    specs: dict[str, ResolvedSpec] = field(default_factory=dict)

    def to_graph(self) -> ResolvedGraph:
        return ResolvedGraph(
            root_selector=self.root_selector,
            nodes=tuple(self.nodes.values()),
            edges=tuple(self.edges),
            sources=tuple(sorted(self.sources)),
            path_resolution=tuple(self.paths),
            validated=False,
        )


def add_edge(builder: GraphBuilder, edge: ResolvedEdge) -> None:
    if edge not in builder.edges:
        builder.edges.append(edge)
