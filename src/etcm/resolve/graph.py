from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from etcm.ir import (
    AssertionDef,
    ComparisonConstraint,
    Expression,
    LiteralValue,
    SourceSpan,
    TypeExpr,
)
from etcm.resolve._files import (
    contains_file_type,
    file_leaf_codec,
    non_null_union_options,
    type_allows_null,
)


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
    derived: Expression | None = None
    constraints: tuple[ComparisonConstraint, ...] = ()
    span: SourceSpan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self, path_base: Path | None = None) -> dict[str, Any]:
        result = {
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
        if self.derived is not None:
            result["derived"] = _expression_to_dict(self.derived)
        if self.constraints:
            result["constraints"] = [
                _constraint_to_dict(constraint) for constraint in self.constraints
            ]
        return result


@dataclass(frozen=True)
class ResolvedValue:
    value: Any
    source_path: Path
    origin: str
    span: SourceSpan | None = None
    literal: LiteralValue | None = None
    ref_target: str | None = None
    applied_override: bool = False
    previous_origin: str | None = None
    previous_value: Any = None
    local_value: Any = None
    derived_expression: Expression | None = None
    override_forced: bool = False
    override_base: Path | None = None

    def with_override(
        self,
        *,
        value: Any,
        previous_origin: str,
        previous_value: Any,
        local_value: Any,
        override_forced: bool = False,
    ) -> ResolvedValue:
        return replace(
            self,
            value=value,
            applied_override=True,
            previous_origin=previous_origin,
            previous_value=previous_value,
            local_value=local_value,
            override_forced=override_forced,
        )

    def as_parent(self) -> ResolvedValue:
        return replace(
            self,
            origin="parent",
            applied_override=False,
            previous_origin=None,
            previous_value=None,
            local_value=None,
            override_forced=False,
            override_base=None,
        )

    def to_dict(
        self,
        path_base: Path | None = None,
        type_expr: TypeExpr | None = None,
    ) -> dict[str, Any]:
        result = {
            "value": _resolved_value(self.value, type_expr, path_base),
            "origin": self.origin,
            "source_path": _path_to_string(self.source_path, path_base),
            "span": _span_to_dict(self.span),
            "literal": _literal_to_dict(self.literal, path_base),
            "ref_target": self.ref_target,
            "applied_override": self.applied_override,
            "previous_origin": self.previous_origin if self.applied_override else None,
            "previous_value": _json_value(self.previous_value, path_base)
            if self.applied_override
            else None,
            "local_value": _json_value(self.local_value, path_base)
            if self.applied_override
            else None,
        }
        if self.derived_expression is not None:
            result["derived_expression"] = _expression_to_dict(self.derived_expression)
        if self.origin == "external" and self.override_base is not None:
            result["override_base"] = _path_to_string(self.override_base, path_base)
        if self.override_forced:
            result["override_forced"] = True
        return result


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
    assertions: tuple[AssertionDef, ...] = ()
    fields: Mapping[str, ResolvedField] = field(default_factory=dict)
    field_values: Mapping[str, ResolvedValue] = field(default_factory=dict)
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "field_values", MappingProxyType(dict(self.field_values)))
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def to_dict(self, path_base: Path | None = None) -> dict[str, Any]:
        result = {
            "id": self.id,
            "selector": _selector_to_string(self.selector, path_base),
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
                name: value.to_dict(path_base, self.fields[name].type_expr)
                for name, value in sorted(self.field_values.items())
            },
            "values": {
                name: _resolved_value(value, self.fields[name].type_expr, path_base)
                for name, value in sorted(self.values.items())
            },
        }
        if self.assertions:
            result["assertions"] = [
                _assertion_to_dict(assertion, path_base) for assertion in self.assertions
            ]
        return result


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
            "root_selector": _selector_to_string(self.root_selector, base),
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


def _selector_to_string(selector: str, path_base: Path | None) -> str:
    if path_base is None:
        return selector
    path_text, separator, fragment = selector.partition("#")
    if not separator or not path_text:
        return selector
    return f"{_path_to_string(Path(path_text), path_base)}#{fragment}"


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


def _resolved_value(
    value: Any,
    type_expr: TypeExpr | None,
    path_base: Path | None,
) -> Any:
    if type_expr is None or not contains_file_type(type_expr):
        return _json_value(value, path_base)
    codec = file_leaf_codec(type_expr)
    if codec is not None:
        if codec == "bytes":
            return None
        return value
    if type_expr.kind == "union":
        if value is None and type_allows_null(type_expr):
            return None
        non_null = non_null_union_options(type_expr)
        if len(non_null) == 1:
            return _resolved_value(value, non_null[0], path_base)
        return value
    if (
        type_expr.kind == "generic"
        and type_expr.name == "list"
        and len(type_expr.args) == 1
        and isinstance(value, list)
    ):
        return [
            _resolved_value(item, type_expr.args[0], path_base) for item in value
        ]
    if (
        type_expr.kind == "generic"
        and type_expr.name == "dict"
        and len(type_expr.args) == 2
        and isinstance(value, Mapping)
    ):
        return {
            str(key): _resolved_value(item, type_expr.args[1], path_base)
            for key, item in value.items()
        }
    return _json_value(value, path_base)


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


def _constraint_to_dict(constraint: ComparisonConstraint) -> dict[str, Any]:
    return {
        "kind": "comparison",
        "operator": constraint.operator,
        "left": _expression_to_dict(constraint.left),
        "right": _expression_to_dict(constraint.right),
        "raw": constraint.raw,
        "span": _span_to_dict(constraint.span),
    }


def _expression_to_dict(expression: Expression) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": expression.kind,
        "span": _span_to_dict(expression.span),
    }
    if expression.raw is not None:
        result["raw"] = expression.raw
    if expression.operator is not None:
        result["operator"] = expression.operator
    if expression.literal is not None:
        result["literal"] = _literal_to_dict(expression.literal, None)
    if expression.reference is not None:
        result["reference"] = {
            "parts": list(expression.reference.parts),
            "raw": expression.reference.raw,
            "span": _span_to_dict(expression.reference.span),
        }
    if expression.operands:
        result["operands"] = [_expression_to_dict(operand) for operand in expression.operands]
    return result


def _assertion_to_dict(
    assertion: AssertionDef,
    path_base: Path | None,
) -> dict[str, Any]:
    return {
        "name": assertion.name,
        "source_path": (
            _path_to_string(assertion.span.source_path, path_base)
            if assertion.span is not None
            else None
        ),
        "predicates": [
            _expression_to_dict(predicate) for predicate in assertion.predicates
        ],
        "span": _span_to_dict(assertion.span),
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
