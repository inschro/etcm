from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class ResolvedEdge:
    kind: str
    source: str
    target: str
    field_path: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "target": self.target,
            "field_path": list(self.field_path),
        }


@dataclass(frozen=True)
class PathResolution:
    field_path: str
    source_path: Path
    original: str
    resolved_path: Path
    field_policy: str
    resolver_policy: str
    expected_kind: str
    exists: bool

    def to_dict(self, path_base: Path | None = None) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "source_path": _path_to_string(self.source_path, path_base),
            "original": self.original,
            "resolved_path": _path_to_string(self.resolved_path, path_base),
            "field_policy": self.field_policy,
            "resolver_policy": self.resolver_policy,
            "expected_kind": self.expected_kind,
            "exists": self.exists,
        }


@dataclass(frozen=True)
class ResolvedNode:
    id: str
    selector: str
    spec_name: str
    spec_ancestors: tuple[str, ...]
    implementation: str
    source_path: Path
    graph_path: str
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def to_dict(self, path_base: Path | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "selector": self.selector,
            "spec_name": self.spec_name,
            "spec_ancestors": list(self.spec_ancestors),
            "implementation": self.implementation,
            "source_path": _path_to_string(self.source_path, path_base),
            "graph_path": self.graph_path,
            "values": _json_value(self.values, path_base),
        }


@dataclass(frozen=True)
class ResolvedGraph:
    root_selector: str
    nodes: tuple[ResolvedNode, ...]
    edges: tuple[ResolvedEdge, ...]
    sources: tuple[Path, ...]
    path_resolution: tuple[PathResolution, ...] = ()

    def to_dict(self, path_base: str | Path | None = None) -> dict[str, Any]:
        base = Path(path_base).resolve() if path_base is not None else None
        return {
            "root_selector": self.root_selector,
            "sources": [_path_to_string(path, base) for path in self.sources],
            "nodes": [node.to_dict(base) for node in sorted(self.nodes, key=lambda node: node.id)],
            "edges": [edge.to_dict() for edge in sorted(self.edges, key=_edge_sort_key)],
            "path_resolution": [
                path.to_dict(base)
                for path in sorted(
                    self.path_resolution,
                    key=lambda path: (path.field_path, str(path.source_path), path.original),
                )
            ],
        }


def _edge_sort_key(edge: ResolvedEdge) -> tuple[str, str, str, tuple[str, ...]]:
    return (edge.source, edge.kind, edge.target, edge.field_path)


def _path_to_string(path: Path, path_base: Path | None) -> str:
    resolved = path.resolve()
    if path_base is not None:
        try:
            return resolved.relative_to(path_base).as_posix()
        except ValueError:
            pass
    return resolved.as_posix()


def _json_value(value: Any, path_base: Path | None) -> Any:
    if isinstance(value, Path):
        return _path_to_string(value, path_base)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item, path_base) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item, path_base) for item in value]
    return value
