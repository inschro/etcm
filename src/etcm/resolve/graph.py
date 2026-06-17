from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from etcm.ir import LiteralValue, SourceSpan, TypeExpr


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
class ResolvedField:
    name: str
    type_expr: TypeExpr
    required: bool
    source_path: Path
    metadata: Mapping[str, Any] = field(default_factory=dict)
    override: str = "allow"
    has_default: bool = False
    default: Any = None
    span: SourceSpan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self, path_base: Path | None = None) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": _type_expr_to_dict(self.type_expr),
            "required": self.required,
            "has_default": self.has_default,
            "default": _json_value(self.default, path_base) if self.has_default else None,
            "metadata": _json_value(self.metadata, path_base),
            "override": self.override,
            "source_path": _path_to_string(self.source_path, path_base),
            "span": _span_to_dict(self.span),
        }


@dataclass(frozen=True)
class ResolvedValue:
    value: Any
    source_path: Path
    origin: str
    span: SourceSpan | None = None
    literal: LiteralValue | None = None
    ref_target: str | None = None
    overrode_parent: bool = False
    parent_value: Any = None
    local_value: Any = None

    def with_override(self, *, value: Any, parent_value: Any, local_value: Any) -> ResolvedValue:
        return replace(
            self,
            value=value,
            overrode_parent=True,
            parent_value=parent_value,
            local_value=local_value,
        )

    def as_parent(self) -> ResolvedValue:
        return replace(self, origin="parent", overrode_parent=False)

    def to_dict(self, path_base: Path | None = None) -> dict[str, Any]:
        return {
            "value": _json_value(self.value, path_base),
            "origin": self.origin,
            "source_path": _path_to_string(self.source_path, path_base),
            "span": _span_to_dict(self.span),
            "literal": _literal_to_dict(self.literal, path_base),
            "ref_target": self.ref_target,
            "overrode_parent": self.overrode_parent,
            "parent_value": _json_value(self.parent_value, path_base)
            if self.overrode_parent
            else None,
            "local_value": _json_value(self.local_value, path_base)
            if self.overrode_parent
            else None,
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
    span: SourceSpan | None = None

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
            "span": _span_to_dict(self.span),
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
    fields: Mapping[str, ResolvedField] = field(default_factory=dict)
    field_values: Mapping[str, ResolvedValue] = field(default_factory=dict)
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "field_values", MappingProxyType(dict(self.field_values)))
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
            "fields": {
                name: field_def.to_dict(path_base)
                for name, field_def in sorted(self.fields.items())
            },
            "field_values": {
                name: value.to_dict(path_base)
                for name, value in sorted(self.field_values.items())
            },
            "values": _json_value(self.values, path_base),
        }


@dataclass(frozen=True)
class ResolvedGraph:
    root_selector: str
    nodes: tuple[ResolvedNode, ...]
    edges: tuple[ResolvedEdge, ...]
    sources: tuple[Path, ...]
    path_resolution: tuple[PathResolution, ...] = ()
    validated: bool = False

    def with_validated(self, validated: bool) -> ResolvedGraph:
        return replace(self, validated=validated)

    def to_dict(self, path_base: str | Path | None = None) -> dict[str, Any]:
        base = Path(path_base).resolve() if path_base is not None else None
        return {
            "root_selector": self.root_selector,
            "validated": self.validated,
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
    if isinstance(value, LiteralValue):
        return _literal_to_dict(value, path_base)
    if isinstance(value, Path):
        return _path_to_string(value, path_base)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item, path_base) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item, path_base) for item in value]
    return value


def _type_expr_to_dict(type_expr: TypeExpr) -> dict[str, Any]:
    return {
        "kind": type_expr.kind,
        "name": type_expr.name,
        "args": [_type_expr_to_dict(arg) for arg in type_expr.args],
    }


def _literal_to_dict(literal: LiteralValue | None, path_base: Path | None) -> dict[str, Any] | None:
    if literal is None:
        return None
    return {
        "kind": literal.kind,
        "value": _json_value(literal.value, path_base),
    }


def _span_to_dict(span: SourceSpan | None) -> dict[str, int] | None:
    if span is None:
        return None
    return {
        "line": span.line,
        "column": span.column,
        "end_line": span.end_line,
        "end_column": span.end_column,
    }
