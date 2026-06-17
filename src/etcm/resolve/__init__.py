from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, NoReturn, cast

from etcm.errors import Diagnostic, ETCMError
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
from etcm.resolve.graph import (
    PathResolution,
    ResolvedEdge,
    ResolvedField,
    ResolvedGraph,
    ResolvedNode,
    ResolvedValue,
)
from etcm.syntax import parse_file

PathExistsPolicy = Literal["allow_missing", "must_exist"]
ViewTarget = Literal["pydantic", "dataclass", "dict"]

_PRIMITIVE_TYPES = {"str", "int", "float", "bool", "null", "Path"}
_PATH_METADATA = {"path_exists", "path_kind"}


@dataclass(frozen=True)
class _ResolvedSpec:
    name: str
    source_path: Path
    fields: Mapping[str, FieldDef]
    ancestors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True)
class _NodeResult:
    node_id: str
    spec: _ResolvedSpec
    values: Mapping[str, ResolvedValue]

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
            validated=False,
        )


@dataclass(frozen=True)
class Resolver:
    path_exists: PathExistsPolicy = "allow_missing"

    def __post_init__(self) -> None:
        if self.path_exists not in ("allow_missing", "must_exist"):
            raise ValueError("path_exists must be 'allow_missing' or 'must_exist'")

    def load(self, selector: str, *, target: ViewTarget = "pydantic") -> object:
        return self.convert(self.validate(self.resolve(selector)), target=target)

    def resolve(self, selector: str) -> ResolvedGraph:
        state = _ResolverState(self)
        return state.resolve(selector)

    def validate(self, graph: ResolvedGraph) -> ResolvedGraph:
        return _validate_graph(graph)

    def convert(
        self,
        graph: ResolvedGraph,
        *,
        target: ViewTarget = "pydantic",
        force: bool = False,
    ) -> object:
        from etcm.codegen import convert

        return convert(graph, target=target, force=force)


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
            _raise(
                cycle_code,
                f"Cycle while resolving implementation '{implementation}'.",
                source_path=source_path,
                selector=_selector_text(source_path, implementation),
                graph_path=graph_path,
                details={"chain": [_selector_text(path, impl) for path, impl in impl_stack]},
            )
        if key in ref_stack:
            _raise(
                "E_REF_CYCLE",
                f"Reference cycle at implementation '{implementation}'.",
                source_path=source_path,
                selector=_selector_text(source_path, implementation),
                graph_path=graph_path,
                details={"chain": [_selector_text(path, impl) for path, impl in ref_stack]},
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
            values = {name: value.as_parent() for name, value in parent_result.values.items()}

        for assignment in impl.assignments:
            field_name = self._assignment_field_name(assignment)
            field = self._field(spec, field_name, assignment.span)
            new_value = self._assignment_value(
                assignment=assignment,
                field=field,
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
            )

        node_id = graph_path
        builder.nodes[node_id] = ResolvedNode(
            id=node_id,
            selector=_selector_text(source_path, implementation),
            spec_name=spec.name,
            spec_ancestors=spec.ancestors,
            implementation=implementation,
            source_path=source_path,
            graph_path=graph_path,
            fields={name: self._field_schema(field) for name, field in spec.fields.items()},
            field_values=values,
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
        source_path: Path,
        graph_path: str,
        builder: _GraphBuilder,
        impl_stack: tuple[tuple[Path, str], ...],
        ref_stack: tuple[tuple[Path, str], ...],
    ) -> ResolvedValue:
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
            source_node_id = graph_path.rsplit(".", 1)[0] if "." in graph_path else "root"
            builder.edges.append(ResolvedEdge("ref", source_node_id, child.node_id, (field.name,)))
            return ResolvedValue(
                value={"$ref": child.node_id},
                source_path=source_path,
                span=assignment.span,
                origin="local",
                ref_target=child.node_id,
            )

        if len(assignment.field_path) != 1:
            _raise(
                "E_TYPE_MISMATCH",
                "Nested assignment paths are not supported in Stage 6.",
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
        return ResolvedValue(
            value=value,
            source_path=source_path,
            span=assignment.span,
            origin="local",
            literal=assignment.value,
        )

    def _apply_value(
        self,
        *,
        values: Mapping[str, ResolvedValue],
        field: FieldDef,
        field_name: str,
        new_value: ResolvedValue,
    ) -> dict[str, ResolvedValue]:
        result = dict(values)
        previous = result.get(field_name)
        if previous is None or previous.origin == "default":
            result[field_name] = new_value
            return result

        if previous.origin == "parent":
            if (
                field.override == "append"
                and isinstance(previous.value, list)
                and isinstance(new_value.value, list)
            ):
                result[field_name] = new_value.with_override(
                    value=[*previous.value, *new_value.value],
                    parent_value=previous.value,
                    local_value=new_value.value,
                )
                return result
            if (
                field.override == "merge"
                and isinstance(previous.value, dict)
                and isinstance(new_value.value, dict)
            ):
                result[field_name] = new_value.with_override(
                    value={**previous.value, **new_value.value},
                    parent_value=previous.value,
                    local_value=new_value.value,
                )
                return result
            result[field_name] = new_value.with_override(
                value=new_value.value,
                parent_value=previous.value,
                local_value=new_value.value,
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
            _raise(
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
            _raise("E_MISSING_SELECTOR", "Document has no spec.", source_path=source_path)

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
                _raise(
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
    ) -> dict[str, ResolvedValue]:
        values: dict[str, ResolvedValue] = {}
        for name, field_def in spec.fields.items():
            if field_def.default is None:
                continue
            source_path = (
                field_def.span.source_path.resolve()
                if field_def.span is not None
                else spec.source_path
            )
            values[name] = ResolvedValue(
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
                literal=field_def.default,
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
        if _type_accepts_path(expected) and literal.kind == "string":
            return self._materialize_path(literal, field, source_path, span, graph_path, builder)
        if expected.kind == "generic" and expected.name == "list" and literal.kind == "list":
            item_type = expected.args[0] if expected.args else TypeExpr(kind="named", name="Any")
            return [
                self._materialize_literal(
                    literal=value,
                    expected=item_type,
                    field=field,
                    source_path=source_path,
                    span=span,
                    graph_path=f"{graph_path}[{index}]",
                    builder=builder,
                )
                for index, value in enumerate(literal.value)
            ]
        if expected.kind == "generic" and expected.name == "dict" and literal.kind == "map":
            value_type = (
                expected.args[1]
                if len(expected.args) == 2
                else TypeExpr(kind="named", name="Any")
            )
            return {
                key: self._materialize_literal(
                    literal=value,
                    expected=value_type,
                    field=field,
                    source_path=source_path,
                    span=span,
                    graph_path=f"{graph_path}.{key}",
                    builder=builder,
                )
                for key, value in literal.value
            }
        return _literal_plain_value(literal)

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
        exists = resolved.exists()
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
                    span=span,
                )
            )
        return resolved

    def _field_schema(self, field: FieldDef) -> ResolvedField:
        source_path = field.span.source_path.resolve() if field.span is not None else Path()
        return ResolvedField(
            name=field.name,
            type_expr=field.type_expr,
            required=field.default is None,
            source_path=source_path,
            metadata={key: _literal_plain_value(value) for key, value in field.metadata.items()},
            override=field.override,
            has_default=field.default is not None,
            default=_literal_plain_value(field.default) if field.default is not None else None,
            span=field.span,
        )

    def _load_document(self, source_path: Path) -> Document:
        source_path = source_path.resolve()
        cached = self._documents.get(source_path)
        if cached is not None:
            return cached
        if not source_path.is_file():
            _raise(
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
        _raise(
            "E_MISSING_SELECTOR",
            f"Implementation '{name}' not found.",
            source_path=document.source_path.resolve(),
            selector=_selector_text(document.source_path.resolve(), name),
        )

    def _field(self, spec: _ResolvedSpec, field_name: str, span: SourceSpan | None) -> FieldDef:
        field = spec.fields.get(field_name)
        if field is None:
            _raise(
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
            _raise(
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


def _validate_graph(graph: ResolvedGraph) -> ResolvedGraph:
    node_by_id = {node.id: node for node in graph.nodes}
    for edge in graph.edges:
        if edge.kind == "impl_parent":
            source = node_by_id[edge.source]
            target = node_by_id[edge.target]
            if not _spec_assignable(target, source.spec_name):
                _raise(
                    "E_TYPE_MISMATCH",
                    f"Implementation parent is not assignable to spec '{source.spec_name}'.",
                    source_path=source.source_path,
                    selector=target.selector,
                    graph_path=source.graph_path,
                    details={"actual": target.spec_name, "expected": source.spec_name},
                )

    for node in sorted(graph.nodes, key=lambda item: item.id):
        _validate_node(node, node_by_id)

    for path in graph.path_resolution:
        _validate_path(path)

    return graph.with_validated(True)


def _validate_node(node: ResolvedNode, node_by_id: Mapping[str, ResolvedNode]) -> None:
    for field_name, field in node.fields.items():
        value = node.field_values.get(field_name)
        graph_path = f"{node.graph_path}.{field_name}"
        if value is None:
            _raise(
                "E_MISSING_FIELD",
                f"Missing required field '{field_name}'.",
                source_path=field.source_path,
                span=field.span,
                graph_path=graph_path,
                details={"field": field_name},
            )
        if value.overrode_parent:
            _validate_override(field, value, graph_path)
        if value.ref_target is not None:
            _validate_ref(field, value, node_by_id, graph_path)
            continue
        _validate_value_type(field, value, graph_path)
        _validate_constraints(field, value, graph_path)


def _validate_ref(
    field: ResolvedField,
    value: ResolvedValue,
    node_by_id: Mapping[str, ResolvedNode],
    graph_path: str,
) -> None:
    assert value.ref_target is not None
    target = node_by_id[value.ref_target]
    if not _ref_assignable(target, field.type_expr):
        _raise(
            "E_TYPE_MISMATCH",
            f"Reference for field '{field.name}' is not assignable.",
            source_path=value.source_path,
            span=value.span,
            selector=target.selector,
            graph_path=graph_path,
            details={"actual": target.spec_name, "expected": _type_text(field.type_expr)},
        )


def _validate_value_type(field: ResolvedField, value: ResolvedValue, graph_path: str) -> None:
    if _value_matches_type(value.value, field.type_expr):
        return
    actual = value.literal.kind if value.literal is not None else type(value.value).__name__
    _raise(
        "E_TYPE_MISMATCH",
        f"Value of type '{actual}' is not assignable to '{_type_text(field.type_expr)}'.",
        source_path=value.source_path,
        span=value.span,
        graph_path=graph_path,
        details={"actual": actual, "expected": _type_text(field.type_expr)},
    )


def _validate_override(field: ResolvedField, value: ResolvedValue, graph_path: str) -> None:
    if field.override in {"deny", "force_only"}:
        _invalid_override(field, value, graph_path)
    if field.override == "append" and not (
        isinstance(value.parent_value, list) and isinstance(value.local_value, list)
    ):
        _invalid_override(field, value, graph_path)
    if field.override == "merge" and not (
        isinstance(value.parent_value, dict) and isinstance(value.local_value, dict)
    ):
        _invalid_override(field, value, graph_path)


def _validate_path(path: PathResolution) -> None:
    effective_policy = (
        path.resolver_policy if path.field_policy == "resolver" else path.field_policy
    )
    kind_ok = (
        path.expected_kind == "any"
        or (path.expected_kind == "file" and path.resolved_path.is_file())
        or (path.expected_kind == "dir" and path.resolved_path.is_dir())
    )
    if effective_policy == "must_exist" and not path.exists:
        _invalid_path(path)
    if path.exists and not kind_ok:
        _invalid_path(path)


def _validate_constraints(field: ResolvedField, value: ResolvedValue, graph_path: str) -> None:
    for name, constraint in field.metadata.items():
        if name in _PATH_METADATA:
            continue
        if name == "choices":
            _validate_choices(field, value, constraint, graph_path)
        elif name in {"gt", "ge", "lt", "le"}:
            _validate_numeric_bound(field, value, name, constraint, graph_path)
        elif name in {"min_length", "max_length"}:
            _validate_length_bound(field, value, name, constraint, graph_path)
        elif name == "regex":
            _validate_regex(field, value, constraint, graph_path)


def _validate_choices(
    field: ResolvedField,
    value: ResolvedValue,
    choices: object,
    graph_path: str,
) -> None:
    if not isinstance(choices, list):
        _invalid_constraint(field, value, "choices", choices, graph_path)
    if value.value not in choices:
        _constraint_failed(field, value, "choices", choices, graph_path)


def _validate_numeric_bound(
    field: ResolvedField,
    value: ResolvedValue,
    name: str,
    bound: object,
    graph_path: str,
) -> None:
    if not _is_number(bound) or not _is_number(value.value):
        _invalid_constraint(field, value, name, bound, graph_path)
    actual = float(cast(int | float, value.value))
    expected = float(cast(int | float, bound))
    ok = (
        (name == "gt" and actual > expected)
        or (name == "ge" and actual >= expected)
        or (name == "lt" and actual < expected)
        or (name == "le" and actual <= expected)
    )
    if not ok:
        _constraint_failed(field, value, name, bound, graph_path)


def _validate_length_bound(
    field: ResolvedField,
    value: ResolvedValue,
    name: str,
    bound: object,
    graph_path: str,
) -> None:
    if not isinstance(bound, int) or isinstance(bound, bool) or not hasattr(value.value, "__len__"):
        _invalid_constraint(field, value, name, bound, graph_path)
    actual = len(value.value)
    ok = (name == "min_length" and actual >= bound) or (
        name == "max_length" and actual <= bound
    )
    if not ok:
        _constraint_failed(field, value, name, bound, graph_path)


def _validate_regex(
    field: ResolvedField,
    value: ResolvedValue,
    pattern: object,
    graph_path: str,
) -> None:
    if not isinstance(pattern, str) or not isinstance(value.value, str):
        _invalid_constraint(field, value, "regex", pattern, graph_path)
    try:
        matched = re.fullmatch(pattern, value.value) is not None
    except re.error:
        _invalid_constraint(field, value, "regex", pattern, graph_path)
    if not matched:
        _constraint_failed(field, value, "regex", pattern, graph_path)


def _value_matches_type(value: Any, type_expr: TypeExpr) -> bool:
    if type_expr.kind == "union":
        return any(_value_matches_type(value, option) for option in type_expr.args)
    if type_expr.kind == "generic":
        if type_expr.name == "list" and isinstance(value, list) and len(type_expr.args) == 1:
            return all(_value_matches_type(item, type_expr.args[0]) for item in value)
        if type_expr.name == "dict" and isinstance(value, dict) and len(type_expr.args) == 2:
            key_type, value_type = type_expr.args
            return key_type.name == "str" and all(
                isinstance(key, str) and _value_matches_type(item, value_type)
                for key, item in value.items()
            )
        return False
    if type_expr.kind != "named" or type_expr.name is None:
        return False
    if type_expr.name == "str":
        return isinstance(value, str)
    if type_expr.name == "int":
        return type(value) is int
    if type_expr.name == "float":
        return type(value) in {int, float}
    if type_expr.name == "bool":
        return isinstance(value, bool)
    if type_expr.name == "null":
        return value is None
    if type_expr.name == "Path":
        return isinstance(value, Path)
    return False


def _ref_assignable(actual: ResolvedNode, expected: TypeExpr) -> bool:
    if expected.kind == "union":
        return any(_ref_assignable(actual, option) for option in expected.args)
    if expected.kind != "named" or expected.name is None:
        return False
    if expected.name in _PRIMITIVE_TYPES:
        return False
    return _spec_assignable(actual, expected.name)


def _spec_assignable(actual: ResolvedNode, expected_name: str) -> bool:
    return actual.spec_name == expected_name or expected_name in actual.spec_ancestors


def _type_accepts_path(type_expr: TypeExpr) -> bool:
    if type_expr.kind == "named":
        return type_expr.name == "Path"
    if type_expr.kind == "union":
        return any(_type_accepts_path(option) for option in type_expr.args)
    return False


def _literal_plain_value(literal: LiteralValue) -> Any:
    if literal.kind == "list":
        return [_literal_plain_value(value) for value in literal.value]
    if literal.kind == "map":
        return {key: _literal_plain_value(value) for key, value in literal.value}
    return literal.value


def _is_number(value: object) -> bool:
    return type(value) in {int, float}


def _type_text(type_expr: TypeExpr) -> str:
    if type_expr.kind == "named":
        return str(type_expr.name)
    if type_expr.kind == "generic":
        return f"{type_expr.name}[{', '.join(_type_text(arg) for arg in type_expr.args)}]"
    if type_expr.kind == "union":
        return " | ".join(_type_text(arg) for arg in type_expr.args)
    return type_expr.kind


def _selector_text(source_path: Path, implementation: str | None) -> str:
    if implementation is None:
        return source_path.as_posix()
    return f"{source_path.as_posix()}#{implementation}"


def _invalid_override(field: ResolvedField, value: ResolvedValue, graph_path: str) -> NoReturn:
    _raise(
        "E_INVALID_OVERRIDE",
        f"Field '{field.name}' cannot be overridden with policy '{field.override}'.",
        source_path=value.source_path,
        span=value.span,
        graph_path=graph_path,
        details={"field": field.name, "override": field.override},
    )


def _invalid_path(path: PathResolution) -> NoReturn:
    field_name = path.field_path.rsplit(".", 1)[-1]
    _raise(
        "E_INVALID_PATH",
        f"Invalid path for field '{field_name}'.",
        source_path=path.source_path,
        span=path.span,
        graph_path=path.field_path,
        details={
            "field": field_name,
            "original": path.original,
            "resolved_path": path.resolved_path.as_posix(),
            "declaring_source_path": path.source_path.as_posix(),
            "field_policy": path.field_policy,
            "resolver_policy": path.resolver_policy,
            "expected_kind": path.expected_kind,
            "exists": path.exists,
        },
    )


def _constraint_failed(
    field: ResolvedField,
    value: ResolvedValue,
    constraint: str,
    expected: object,
    graph_path: str,
) -> NoReturn:
    _raise(
        "E_CONSTRAINT",
        f"Field '{field.name}' violates constraint '{constraint}'.",
        source_path=value.source_path,
        span=value.span,
        graph_path=graph_path,
        details={
            "field": field.name,
            "constraint": constraint,
            "expected": expected,
            "actual": value.value,
        },
    )


def _invalid_constraint(
    field: ResolvedField,
    value: ResolvedValue,
    constraint: str,
    expected: object,
    graph_path: str,
) -> NoReturn:
    _raise(
        "E_CONSTRAINT",
        f"Field '{field.name}' has invalid constraint '{constraint}'.",
        source_path=value.source_path,
        span=value.span,
        graph_path=graph_path,
        details={
            "field": field.name,
            "constraint": constraint,
            "expected": expected,
            "actual": value.value,
        },
    )


def _raise(
    code: str,
    message: str,
    *,
    source_path: Path | None = None,
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


def load(
    selector: str,
    *,
    target: ViewTarget = "pydantic",
    path_exists: PathExistsPolicy = "allow_missing",
) -> object:
    return Resolver(path_exists=path_exists).load(selector, target=target)


def resolve(
    selector: str,
    *,
    path_exists: PathExistsPolicy = "allow_missing",
) -> ResolvedGraph:
    return Resolver(path_exists=path_exists).resolve(selector)


def validate(graph: ResolvedGraph) -> ResolvedGraph:
    return Resolver().validate(graph)


def convert(
    graph: ResolvedGraph,
    *,
    target: ViewTarget = "pydantic",
    force: bool = False,
) -> object:
    return Resolver().convert(graph, target=target, force=force)


__all__ = [
    "PathExistsPolicy",
    "PathResolution",
    "ResolvedEdge",
    "ResolvedField",
    "ResolvedGraph",
    "ResolvedNode",
    "ResolvedValue",
    "Resolver",
    "ViewTarget",
    "convert",
    "load",
    "resolve",
    "validate",
]
