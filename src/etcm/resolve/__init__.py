from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, NoReturn

from etcm.errors import Diagnostic, ETCMError, ETCMNotImplementedError
from etcm.ir import (
    Assignment,
    Document,
    FieldDef,
    ImplDef,
    LiteralValue,
    RefAssignment,
    Selector,
    SourceSpan,
    TypeExpr,
)
from etcm.resolve.graph import PathResolution, ResolvedEdge, ResolvedGraph, ResolvedNode
from etcm.syntax import parse_file

PathExistsPolicy = Literal["allow_missing", "must_exist"]

_STAGE6_MESSAGE = "ETCM generated views are not implemented until Stage 6."
_PRIMITIVE_TYPES = {"str", "int", "float", "bool", "null", "Path"}


@dataclass(frozen=True)
class _ResolvedSpec:
    name: str
    source_path: Path
    fields: Mapping[str, FieldDef]
    ancestors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True)
class _ResolvedValue:
    value: Any
    source_path: Path
    span: SourceSpan | None
    origin: str


@dataclass(frozen=True)
class _NodeResult:
    node_id: str
    spec: _ResolvedSpec
    values: Mapping[str, _ResolvedValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass
class _GraphBuilder:
    root_selector: str
    sources: set[Path] = dataclass_field(default_factory=set)
    nodes: dict[str, ResolvedNode] = dataclass_field(default_factory=dict)
    edges: list[ResolvedEdge] = dataclass_field(default_factory=list)
    paths: list[PathResolution] = dataclass_field(default_factory=list)

    def to_graph(self) -> ResolvedGraph:
        return ResolvedGraph(
            root_selector=self.root_selector,
            nodes=tuple(self.nodes.values()),
            edges=tuple(self.edges),
            sources=tuple(sorted(self.sources)),
            path_resolution=tuple(self.paths),
        )


@dataclass(frozen=True)
class Resolver:
    path_exists: PathExistsPolicy = "allow_missing"

    def __post_init__(self) -> None:
        if self.path_exists not in ("allow_missing", "must_exist"):
            raise ValueError("path_exists must be 'allow_missing' or 'must_exist'")

    def load(self, selector: str, *, as_: str = "pydantic") -> object:
        raise ETCMNotImplementedError(_STAGE6_MESSAGE)

    def resolve(self, selector: str) -> ResolvedGraph:
        state = _ResolverState(self)
        return state.resolve(selector)

    def validate(self, selector: str) -> None:
        self.resolve(selector)


class _ResolverState:
    def __init__(self, resolver: Resolver) -> None:
        self._resolver = resolver
        self._documents: dict[Path, Document] = {}
        self._specs: dict[Path, _ResolvedSpec] = {}

    def resolve(self, raw_selector: str) -> ResolvedGraph:
        selector = self._selector_from_raw(raw_selector, Path.cwd() / "__root__.etcm")
        builder = _GraphBuilder(root_selector=raw_selector)
        self._resolve_node(
            selector=selector,
            graph_path="root",
            builder=builder,
            impl_stack=(),
            ref_stack=(),
            cycle_code="E_IMPL_CYCLE",
        )
        builder.sources.update(self._documents)
        return builder.to_graph()

    def _resolve_node(
        self,
        *,
        selector: Selector,
        graph_path: str,
        builder: _GraphBuilder,
        impl_stack: tuple[tuple[Path, str], ...],
        ref_stack: tuple[tuple[Path, str], ...],
        cycle_code: str,
    ) -> _NodeResult:
        source_path = selector.path.resolve()
        implementation = selector.implementation or "default"
        key = (source_path, implementation)
        if key in impl_stack:
            self._raise(
                cycle_code,
                f"Cycle while resolving implementation '{implementation}'.",
                source_path=source_path,
                selector=self._selector_text(source_path, implementation),
                graph_path=graph_path,
                details={"chain": [self._selector_text(path, impl) for path, impl in impl_stack]},
            )
        if key in ref_stack:
            self._raise(
                "E_REF_CYCLE",
                f"Reference cycle at implementation '{implementation}'.",
                source_path=source_path,
                selector=self._selector_text(source_path, implementation),
                graph_path=graph_path,
                details={"chain": [self._selector_text(path, impl) for path, impl in ref_stack]},
            )

        document = self._load_document(source_path)
        builder.sources.add(source_path)
        spec = self._resolve_spec(source_path, ())
        impl = self._implementation(document, implementation)
        next_impl_stack = (*impl_stack, key)

        values = self._default_values(spec, builder, graph_path)
        parent_result: _NodeResult | None = None
        if impl.parent is not None:
            parent_selector = self._selector_from_ir(impl.parent, source_path)
            parent_result = self._resolve_node(
                selector=parent_selector,
                graph_path=f"{graph_path}.__parent",
                builder=builder,
                impl_stack=next_impl_stack,
                ref_stack=ref_stack,
                cycle_code="E_IMPL_CYCLE",
            )
            if not self._is_assignable(parent_result.spec, spec.name):
                self._raise(
                    "E_TYPE_MISMATCH",
                    f"Implementation parent is not assignable to spec '{spec.name}'.",
                    source_path=source_path,
                    span=impl.span,
                    selector=self._selector_text(
                        parent_selector.path,
                        parent_selector.implementation,
                    ),
                    graph_path=graph_path,
                    details={"actual": parent_result.spec.name, "expected": spec.name},
                )
            values = {
                name: _ResolvedValue(
                    value=value.value,
                    source_path=value.source_path,
                    span=value.span,
                    origin="parent",
                )
                for name, value in parent_result.values.items()
            }

        local_fields: set[str] = set()
        for assignment in impl.assignments:
            field_name = self._assignment_field_name(assignment)
            field = self._field(spec, field_name, assignment.span)
            new_value = self._assignment_value(
                assignment=assignment,
                field=field,
                spec=spec,
                source_path=source_path,
                graph_path=f"{graph_path}.{field_name}",
                builder=builder,
                impl_stack=next_impl_stack,
                ref_stack=ref_stack,
            )
            values = self._apply_value(
                values=values,
                field=field,
                field_name=field_name,
                new_value=new_value,
                source_path=source_path,
                span=assignment.span,
                graph_path=f"{graph_path}.{field_name}",
            )
            local_fields.add(field_name)

        for field_name in spec.fields:
            if field_name not in values:
                self._raise(
                    "E_MISSING_FIELD",
                    f"Missing required field '{field_name}'.",
                    source_path=source_path,
                    span=impl.span,
                    graph_path=f"{graph_path}.{field_name}",
                    details={"field": field_name},
                )

        node_id = graph_path
        builder.nodes[node_id] = ResolvedNode(
            id=node_id,
            selector=self._selector_text(source_path, implementation),
            spec_name=spec.name,
            spec_ancestors=spec.ancestors,
            implementation=implementation,
            source_path=source_path,
            graph_path=graph_path,
            values={name: value.value for name, value in values.items()},
        )
        if spec.ancestors:
            builder.edges.append(ResolvedEdge("spec_parent", node_id, f"spec:{spec.ancestors[0]}"))
        if parent_result is not None:
            builder.edges.append(ResolvedEdge("impl_parent", node_id, parent_result.node_id))
        return _NodeResult(node_id=node_id, spec=spec, values=values)

    def _assignment_value(
        self,
        *,
        assignment: Assignment | RefAssignment,
        field: FieldDef,
        spec: _ResolvedSpec,
        source_path: Path,
        graph_path: str,
        builder: _GraphBuilder,
        impl_stack: tuple[tuple[Path, str], ...],
        ref_stack: tuple[tuple[Path, str], ...],
    ) -> _ResolvedValue:
        if isinstance(assignment, RefAssignment):
            child_selector = self._selector_from_ir(assignment.selector, source_path)
            child = self._resolve_node(
                selector=child_selector,
                graph_path=graph_path,
                builder=builder,
                impl_stack=impl_stack,
                ref_stack=(*ref_stack, (impl_stack[-1][0], impl_stack[-1][1])),
                cycle_code="E_REF_CYCLE",
            )
            if not self._ref_assignable(child.spec, field.type_expr):
                self._raise(
                    "E_TYPE_MISMATCH",
                    f"Reference for field '{field.name}' is not assignable.",
                    source_path=source_path,
                    span=assignment.span,
                    selector=self._selector_text(
                        child_selector.path,
                        child_selector.implementation,
                    ),
                    graph_path=graph_path,
                    details={
                        "actual": child.spec.name,
                        "expected": self._type_text(field.type_expr),
                    },
                )
            source_node_id = graph_path.rsplit(".", 1)[0] if "." in graph_path else "root"
            builder.edges.append(ResolvedEdge("ref", source_node_id, child.node_id, (field.name,)))
            return _ResolvedValue(
                value={"$ref": child.node_id},
                source_path=source_path,
                span=assignment.span,
                origin="local",
            )

        if len(assignment.field_path) != 1:
            self._raise(
                "E_TYPE_MISMATCH",
                "Nested assignment paths are not supported in Stage 5.",
                source_path=source_path,
                span=assignment.span,
                graph_path=graph_path,
            )
        value = self._materialize_literal(
            literal=assignment.value,
            expected=field.type_expr,
            field=field,
            source_path=source_path,
            span=assignment.span,
            graph_path=graph_path,
            builder=builder,
        )
        return _ResolvedValue(
            value=value,
            source_path=source_path,
            span=assignment.span,
            origin="local",
        )

    def _apply_value(
        self,
        *,
        values: Mapping[str, _ResolvedValue],
        field: FieldDef,
        field_name: str,
        new_value: _ResolvedValue,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
    ) -> dict[str, _ResolvedValue]:
        result = dict(values)
        previous = result.get(field_name)
        if previous is None or previous.origin == "default":
            result[field_name] = new_value
            return result

        policy = field.override
        if previous.origin == "parent":
            if policy == "deny":
                self._invalid_override(field, source_path, span, graph_path)
            if policy == "force_only":
                self._invalid_override(field, source_path, span, graph_path)
            if policy == "append":
                if not isinstance(previous.value, list) or not isinstance(new_value.value, list):
                    self._invalid_override(field, source_path, span, graph_path)
                result[field_name] = _ResolvedValue(
                    value=[*previous.value, *new_value.value],
                    source_path=new_value.source_path,
                    span=new_value.span,
                    origin="local",
                )
                return result
            if policy == "merge":
                if not isinstance(previous.value, dict) or not isinstance(new_value.value, dict):
                    self._invalid_override(field, source_path, span, graph_path)
                result[field_name] = _ResolvedValue(
                    value={**previous.value, **new_value.value},
                    source_path=new_value.source_path,
                    span=new_value.span,
                    origin="local",
                )
                return result
        result[field_name] = new_value
        return result

    def _resolve_spec(self, source_path: Path, stack: tuple[Path, ...]) -> _ResolvedSpec:
        source_path = source_path.resolve()
        cached = self._specs.get(source_path)
        if cached is not None:
            return cached
        if source_path in stack:
            self._raise(
                "E_SPEC_CYCLE",
                "Cycle while resolving spec inheritance.",
                source_path=source_path,
                details={"chain": [path.as_posix() for path in stack]},
            )

        document = self._load_document(source_path)
        if document.spec_ref is not None:
            ref_path = self._resolve_path(document.spec_ref.path, source_path.parent)
            spec = self._resolve_spec(ref_path, (*stack, source_path))
            self._specs[source_path] = spec
            return spec
        if document.spec is None:
            self._raise("E_MISSING_SELECTOR", "Document has no spec.", source_path=source_path)

        assert document.spec is not None
        fields: dict[str, FieldDef] = {}
        ancestors: tuple[str, ...] = ()
        if document.spec.parent is not None:
            parent_path = self._resolve_path(document.spec.parent, source_path.parent)
            parent = self._resolve_spec(parent_path, (*stack, source_path))
            fields.update(parent.fields)
            ancestors = (parent.name, *parent.ancestors)

        for field_def in document.spec.fields:
            if field_def.name in fields:
                self._raise(
                    "E_TYPE_MISMATCH",
                    f"Spec '{document.spec.name}' redefines inherited field '{field_def.name}'.",
                    source_path=source_path,
                    span=field_def.span,
                    details={"field": field_def.name},
                )
            fields[field_def.name] = field_def

        spec = _ResolvedSpec(
            name=document.spec.name,
            source_path=source_path,
            fields=fields,
            ancestors=ancestors,
        )
        self._specs[source_path] = spec
        return spec

    def _default_values(
        self,
        spec: _ResolvedSpec,
        builder: _GraphBuilder,
        graph_path: str,
    ) -> dict[str, _ResolvedValue]:
        values: dict[str, _ResolvedValue] = {}
        for name, field_def in spec.fields.items():
            if field_def.default is None:
                continue
            source_path = (
                field_def.span.source_path.resolve()
                if field_def.span is not None
                else spec.source_path
            )
            values[name] = _ResolvedValue(
                value=self._materialize_literal(
                    literal=field_def.default,
                    expected=field_def.type_expr,
                    field=field_def,
                    source_path=source_path,
                    span=field_def.span,
                    graph_path=f"{graph_path}.{name}",
                    builder=builder,
                ),
                source_path=source_path,
                span=field_def.span,
                origin="default",
            )
        return values

    def _materialize_literal(
        self,
        *,
        literal: LiteralValue,
        expected: TypeExpr,
        field: FieldDef,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
        builder: _GraphBuilder | None,
    ) -> Any:
        if expected.kind == "union":
            for option in expected.args:
                try:
                    return self._materialize_literal(
                        literal=literal,
                        expected=option,
                        field=field,
                        source_path=source_path,
                        span=span,
                        graph_path=graph_path,
                        builder=builder,
                    )
                except ETCMError as exc:
                    if exc.diagnostic.code != "E_TYPE_MISMATCH":
                        raise
            self._type_mismatch(literal, expected, source_path, span, graph_path)

        if expected.kind == "generic":
            return self._materialize_generic(
                literal,
                expected,
                field,
                source_path,
                span,
                graph_path,
            )

        if expected.kind != "named" or expected.name is None:
            self._type_mismatch(literal, expected, source_path, span, graph_path)

        name = expected.name
        if name == "str" and literal.kind == "string":
            return literal.value
        if name == "int" and literal.kind == "int":
            return literal.value
        if name == "float" and literal.kind in {"int", "float"}:
            return float(literal.value)
        if name == "bool" and literal.kind == "bool":
            return literal.value
        if name == "null" and literal.kind == "null":
            return None
        if name == "Path" and literal.kind == "string":
            return self._materialize_path(literal, field, source_path, span, graph_path, builder)

        self._type_mismatch(literal, expected, source_path, span, graph_path)

    def _materialize_generic(
        self,
        literal: LiteralValue,
        expected: TypeExpr,
        field: FieldDef,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
    ) -> Any:
        if expected.name == "list" and literal.kind == "list" and len(expected.args) == 1:
            return [
                self._materialize_literal(
                    literal=value,
                    expected=expected.args[0],
                    field=field,
                    source_path=source_path,
                    span=span,
                    graph_path=graph_path,
                    builder=None,
                )
                for value in literal.value
            ]
        if expected.name == "dict" and literal.kind == "map" and len(expected.args) == 2:
            key_type, value_type = expected.args
            if key_type.name != "str":
                self._type_mismatch(literal, expected, source_path, span, graph_path)
            return {
                key: self._materialize_literal(
                    literal=value,
                    expected=value_type,
                    field=field,
                    source_path=source_path,
                    span=span,
                    graph_path=f"{graph_path}.{key}",
                    builder=None,
                )
                for key, value in literal.value
            }
        self._type_mismatch(literal, expected, source_path, span, graph_path)

    def _materialize_path(
        self,
        literal: LiteralValue,
        field: FieldDef,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
        builder: _GraphBuilder | None,
    ) -> Path:
        original = str(literal.value)
        resolved = self._resolve_path(Path(original), source_path.parent)
        field_policy = self._metadata_string(field, "path_exists", "resolver")
        expected_kind = self._metadata_string(field, "path_kind", "any")
        effective_policy = (
            self._resolver.path_exists if field_policy == "resolver" else field_policy
        )
        exists = resolved.exists()
        kind_ok = (
            expected_kind == "any"
            or (expected_kind == "file" and resolved.is_file())
            or (expected_kind == "dir" and resolved.is_dir())
        )
        if effective_policy == "must_exist" and not exists:
            self._invalid_path(
                field,
                original,
                resolved,
                field_policy,
                expected_kind,
                exists,
                source_path,
                span,
                graph_path,
            )
        if exists and not kind_ok:
            self._invalid_path(
                field,
                original,
                resolved,
                field_policy,
                expected_kind,
                exists,
                source_path,
                span,
                graph_path,
            )
        if builder is not None:
            builder.paths.append(
                PathResolution(
                    field_path=graph_path,
                    source_path=source_path,
                    original=original,
                    resolved_path=resolved,
                    field_policy=field_policy,
                    resolver_policy=self._resolver.path_exists,
                    expected_kind=expected_kind,
                    exists=exists,
                )
            )
        return resolved

    def _ref_assignable(self, actual: _ResolvedSpec, expected: TypeExpr) -> bool:
        if expected.kind == "union":
            return any(self._ref_assignable(actual, option) for option in expected.args)
        if expected.kind != "named" or expected.name is None:
            return False
        if expected.name in _PRIMITIVE_TYPES:
            return False
        return self._is_assignable(actual, expected.name)

    def _is_assignable(self, actual: _ResolvedSpec, expected_name: str) -> bool:
        return actual.name == expected_name or expected_name in actual.ancestors

    def _load_document(self, source_path: Path) -> Document:
        source_path = source_path.resolve()
        cached = self._documents.get(source_path)
        if cached is not None:
            return cached
        if not source_path.is_file():
            self._raise(
                "E_MISSING_SELECTOR",
                f"Selector source file does not exist: {source_path}",
                source_path=source_path,
            )
        document = parse_file(source_path)
        self._documents[source_path] = document
        return document

    def _implementation(self, document: Document, name: str) -> ImplDef:
        for implementation in document.implementations:
            if implementation.name == name:
                return implementation
        self._raise(
            "E_MISSING_SELECTOR",
            f"Implementation '{name}' not found.",
            source_path=document.source_path.resolve(),
            selector=self._selector_text(document.source_path.resolve(), name),
        )

    def _field(self, spec: _ResolvedSpec, field_name: str, span: SourceSpan | None) -> FieldDef:
        field = spec.fields.get(field_name)
        if field is None:
            self._raise(
                "E_TYPE_MISMATCH",
                f"Unknown field '{field_name}' for spec '{spec.name}'.",
                source_path=span.source_path if span is not None else spec.source_path,
                span=span,
                details={"field": field_name, "spec": spec.name},
            )
        return field

    def _assignment_field_name(self, assignment: Assignment | RefAssignment) -> str:
        if isinstance(assignment, RefAssignment):
            return assignment.field_name
        return assignment.field_path[0]

    def _selector_from_ir(self, selector: Selector, declaring_source: Path) -> Selector:
        raw = selector.raw or str(selector.path)
        return self._selector_from_raw(raw, declaring_source)

    def _selector_from_raw(self, raw: str, declaring_source: Path) -> Selector:
        try:
            selector = Selector.parse(raw)
        except ValueError as exc:
            self._raise(
                "E_MISSING_SELECTOR",
                str(exc),
                source_path=declaring_source.resolve(),
                selector=raw,
            )
        raw_path = str(selector.path)
        if selector.implementation is None and not self._looks_like_file_path(raw_path):
            return Selector(
                path=declaring_source.resolve(),
                implementation=raw_path,
                raw=raw,
            )
        return Selector(
            path=self._resolve_path(selector.path, declaring_source.parent),
            implementation=selector.implementation or "default",
            raw=raw,
        )

    def _looks_like_file_path(self, raw_path: str) -> bool:
        return "/" in raw_path or "\\" in raw_path or raw_path.endswith(".etcm") or "." in raw_path

    def _resolve_path(self, path: Path, base: Path) -> Path:
        if path.is_absolute():
            return path.resolve()
        return (base / path).resolve()

    def _metadata_string(self, field: FieldDef, name: str, default: str) -> str:
        value = field.metadata.get(name)
        if value is None:
            return default
        return str(value.value)

    def _type_text(self, type_expr: TypeExpr) -> str:
        if type_expr.kind == "named":
            return str(type_expr.name)
        if type_expr.kind == "generic":
            return f"{type_expr.name}[{', '.join(self._type_text(arg) for arg in type_expr.args)}]"
        if type_expr.kind == "union":
            return " | ".join(self._type_text(arg) for arg in type_expr.args)
        return type_expr.kind

    def _selector_text(self, source_path: Path, implementation: str | None) -> str:
        if implementation is None:
            return source_path.as_posix()
        return f"{source_path.as_posix()}#{implementation}"

    def _type_mismatch(
        self,
        literal: LiteralValue,
        expected: TypeExpr,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
    ) -> None:
        self._raise(
            "E_TYPE_MISMATCH",
            f"Value of type '{literal.kind}' is not assignable to '{self._type_text(expected)}'.",
            source_path=source_path,
            span=span,
            graph_path=graph_path,
            details={"actual": literal.kind, "expected": self._type_text(expected)},
        )

    def _invalid_override(
        self,
        field: FieldDef,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
    ) -> None:
        self._raise(
            "E_INVALID_OVERRIDE",
            f"Field '{field.name}' cannot be overridden with policy '{field.override}'.",
            source_path=source_path,
            span=span,
            graph_path=graph_path,
            details={"field": field.name, "override": field.override},
        )

    def _invalid_path(
        self,
        field: FieldDef,
        original: str,
        resolved: Path,
        field_policy: str,
        expected_kind: str,
        exists: bool,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
    ) -> None:
        self._raise(
            "E_INVALID_PATH",
            f"Invalid path for field '{field.name}'.",
            source_path=source_path,
            span=span,
            graph_path=graph_path,
            details={
                "field": field.name,
                "original": original,
                "resolved_path": resolved.as_posix(),
                "declaring_source_path": source_path.as_posix(),
                "field_policy": field_policy,
                "resolver_policy": self._resolver.path_exists,
                "expected_kind": expected_kind,
                "exists": exists,
            },
        )

    def _raise(
        self,
        code: str,
        message: str,
        *,
        source_path: Path,
        span: SourceSpan | None = None,
        selector: str | None = None,
        graph_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> NoReturn:
        raise ETCMError(
            Diagnostic(
                code=code,
                message=message,
                source_path=source_path,
                line=span.line if span is not None else None,
                column=span.column if span is not None else None,
                end_line=span.end_line if span is not None else None,
                end_column=span.end_column if span is not None else None,
                selector=selector,
                graph_path=graph_path,
                details=details,
            )
        )


def load(selector: str, *, as_: str = "pydantic") -> object:
    return Resolver().load(selector, as_=as_)


def resolve(selector: str) -> ResolvedGraph:
    return Resolver().resolve(selector)


def validate(selector: str) -> None:
    return Resolver().validate(selector)


__all__ = [
    "PathExistsPolicy",
    "PathResolution",
    "ResolvedEdge",
    "ResolvedGraph",
    "ResolvedNode",
    "Resolver",
    "load",
    "resolve",
    "validate",
]
