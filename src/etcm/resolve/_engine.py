from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from etcm.ir import (
    Assignment,
    FieldDef,
    LiteralValue,
    RefAssignment,
    Selector,
    SourceSpan,
    TypeExpr,
)
from etcm.resolve._derivations import finalize_derivations
from etcm.resolve._diagnostics import field_source_path as _field_source_path
from etcm.resolve._diagnostics import raise_error as _raise
from etcm.resolve._overrides import apply_value as _apply_value
from etcm.resolve._selectors import canonical_selector as _canonical_selector
from etcm.resolve._selectors import resolve_path as _resolve_path
from etcm.resolve._selectors import selector_from_ir as _selector_from_ir
from etcm.resolve._selectors import selector_from_raw as _selector_from_raw
from etcm.resolve._selectors import selector_text as _selector_text
from etcm.resolve._specs import ResolvedSpec as _ResolvedSpec
from etcm.resolve._specs import SpecResolver
from etcm.resolve._types import literal_plain_value as _literal_plain_value
from etcm.resolve._types import type_accepts_path as _type_accepts_path
from etcm.resolve.graph import (
    PathResolution,
    ResolvedEdge,
    ResolvedField,
    ResolvedGraph,
    ResolvedNode,
    ResolvedValue,
)
from etcm.resolve.relations import render_expression

if TYPE_CHECKING:
    from etcm.resolve._api import Resolver

_PATH_METADATA = {"path_exists", "path_kind"}


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


def _add_edge(builder: _GraphBuilder, edge: ResolvedEdge) -> None:
    if edge not in builder.edges:
        builder.edges.append(edge)


class _ResolverState:
    def __init__(self, resolver: Resolver) -> None:
        self._resolver = resolver
        self._spec_resolver = SpecResolver()

    def resolve(self, raw_selector: str) -> ResolvedGraph:
        selector = _selector_from_raw(raw_selector)
        builder = _GraphBuilder(root_selector=_canonical_selector(selector))
        self._resolve_node(
            selector=selector,
            graph_path="root",
            builder=builder,
            impl_stack=(),
            ref_stack=(),
            cycle_code="E_IMPL_CYCLE",
        )
        self._finalize_derivations(builder)
        builder.sources.update(self._spec_resolver.documents)
        return builder.to_graph()

    def _resolve_node(
        self,
        *,
        selector: Selector,
        graph_path: str,
        builder: _GraphBuilder,
        impl_stack: tuple[tuple[Path, str, str], ...],
        ref_stack: tuple[tuple[Path, str, str], ...],
        cycle_code: str,
    ) -> _NodeResult:
        target = self._spec_resolver.resolve_implementation_selector(selector)
        source_path = target.source_path
        spec = target.spec
        impl = target.implementation
        key = target.key
        if key in impl_stack:
            _raise(
                cycle_code,
                f"Cycle while resolving implementation '{impl.name}'.",
                source_path=source_path,
                selector=target.selector,
                graph_path=graph_path,
                details={
                    "chain": [
                        _selector_text(path, spec_name, impl_name)
                        for path, spec_name, impl_name in impl_stack
                    ]
                },
            )
        if key in ref_stack:
            _raise(
                "E_REF_CYCLE",
                f"Reference cycle at implementation '{impl.name}'.",
                source_path=source_path,
                selector=target.selector,
                graph_path=graph_path,
                details={
                    "chain": [
                        _selector_text(path, spec_name, impl_name)
                        for path, spec_name, impl_name in ref_stack
                    ]
                },
            )

        builder.sources.add(source_path)
        next_impl_stack = (*impl_stack, key)

        values = self._default_values(spec, builder, graph_path)
        parent_result: _NodeResult | None = None
        if impl.parent is not None:
            parent_selector = _selector_from_ir(
                impl.parent,
                source_path,
                active_spec=spec.name,
            )
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
            previous = values.get(field_name)
            new_value = self._assignment_value(
                assignment=assignment,
                field=field,
                source_path=source_path,
                graph_path=f"{graph_path}.{field_name}",
                builder=builder,
                impl_stack=next_impl_stack,
                ref_stack=ref_stack,
                previous_value=previous,
                active_spec=spec.name,
            )
            values = _apply_value(
                values=values,
                field=field,
                field_name=field_name,
                new_value=new_value,
            )

        node_id = graph_path
        builder.nodes[node_id] = ResolvedNode(
            id=node_id,
            selector=target.selector,
            spec_name=spec.name,
            spec_ancestors=spec.ancestors,
            implementation=impl.name,
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
        impl_stack: tuple[tuple[Path, str, str], ...],
        ref_stack: tuple[tuple[Path, str, str], ...],
        previous_value: ResolvedValue | None,
        active_spec: str,
    ) -> ResolvedValue:
        if field.derived is not None:
            _raise(
                "E_DERIVED_ASSIGNMENT",
                f"Cannot assign derived parameter '{field.name}'.",
                source_path=source_path,
                span=assignment.span,
                graph_path=graph_path,
                details={
                    "field": field.name,
                    "expression": field.derived.raw
                    or render_expression(field.derived),
                },
            )
        if len(assignment.field_path) != 1:
            if not field.fields:
                if field.ref_selector is not None:
                    requested_path = ".".join(
                        (graph_path, *assignment.field_path[1:])
                    )
                    _raise(
                        "E_INVALID_PATH",
                        f"Cannot assign beneath referenced field '${field.name}'; "
                        "references must be selected as a whole.",
                        source_path=source_path,
                        span=assignment.span,
                        graph_path=graph_path,
                        details={
                            "field": field.name,
                            "field_path": requested_path,
                            "boundary": graph_path,
                        },
                    )
                _raise(
                    "E_TYPE_MISMATCH",
                    "Nested assignment paths are only valid for inline nested spec fields.",
                    source_path=source_path,
                    span=assignment.span,
                    graph_path=graph_path,
                )
            child = self._resolve_inline_node(
                field=field,
                source_path=source_path,
                graph_path=graph_path,
                builder=builder,
                assignments=(
                    replace(assignment, field_path=assignment.field_path[1:]),
                ),
                base_node=self._node_from_value(previous_value, builder),
                base_as_parent=previous_value.origin == "parent"
                if previous_value is not None
                else False,
                impl_stack=impl_stack,
                ref_stack=ref_stack,
            )
            source_node_id = graph_path.rsplit(".", 1)[0] if "." in graph_path else "root"
            _add_edge(
                builder,
                ResolvedEdge("ref", source_node_id, child.node_id, (field.name,)),
            )
            return ResolvedValue(
                value={"$ref": child.node_id},
                source_path=source_path,
                span=assignment.span,
                origin="local",
                ref_target=child.node_id,
            )

        if isinstance(assignment, RefAssignment):
            if field.fields:
                _raise(
                    "E_TYPE_MISMATCH",
                    f"Nested field '{field.name}' cannot be assigned with a reference.",
                    source_path=source_path,
                    span=assignment.span,
                    graph_path=graph_path,
                    details={"field": field.name},
                )
            child_selector = _selector_from_ir(
                assignment.selector,
                source_path,
                active_spec=active_spec,
            )
            child = self._resolve_node(
                selector=child_selector,
                graph_path=graph_path,
                builder=builder,
                impl_stack=impl_stack,
                ref_stack=(*ref_stack, impl_stack[-1]),
                cycle_code="E_REF_CYCLE",
            )
            source_node_id = graph_path.rsplit(".", 1)[0] if "." in graph_path else "root"
            _add_edge(
                builder,
                ResolvedEdge("ref", source_node_id, child.node_id, (field.name,)),
            )
            return ResolvedValue(
                value={"$ref": child.node_id},
                source_path=source_path,
                span=assignment.span,
                origin="local",
                ref_target=child.node_id,
            )

        if field.fields:
            _raise(
                "E_TYPE_MISMATCH",
                f"Nested field '{field.name}' requires a child assignment path.",
                source_path=source_path,
                span=assignment.span,
                graph_path=graph_path,
                details={"field": field.name},
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

    def _resolve_inline_node(
        self,
        *,
        field: FieldDef,
        source_path: Path,
        graph_path: str,
        builder: _GraphBuilder,
        assignments: tuple[Assignment | RefAssignment, ...],
        base_node: ResolvedNode | None,
        base_as_parent: bool,
        impl_stack: tuple[tuple[Path, str, str], ...],
        ref_stack: tuple[tuple[Path, str, str], ...],
    ) -> _NodeResult:
        spec = _ResolvedSpec(
            name=str(field.type_expr.name),
            source_path=_field_source_path(field, source_path),
            fields={child.name: child for child in field.fields},
        )
        if base_node is None:
            values = self._default_values(spec, builder, graph_path)
        elif base_as_parent:
            values = {name: value.as_parent() for name, value in base_node.field_values.items()}
        else:
            values = dict(base_node.field_values)

        for assignment in assignments:
            field_name = self._assignment_field_name(assignment)
            child_field = self._field(spec, field_name, assignment.span)
            previous = values.get(field_name)
            new_value = self._assignment_value(
                assignment=assignment,
                field=child_field,
                source_path=source_path,
                graph_path=f"{graph_path}.{field_name}",
                builder=builder,
                impl_stack=impl_stack,
                ref_stack=ref_stack,
                previous_value=previous,
                active_spec=spec.name,
            )
            values = _apply_value(
                values=values,
                field=child_field,
                field_name=field_name,
                new_value=new_value,
            )

        builder.nodes[graph_path] = ResolvedNode(
            id=graph_path,
            selector=graph_path,
            spec_name=spec.name,
            spec_ancestors=spec.ancestors,
            implementation="inline",
            source_path=spec.source_path,
            graph_path=graph_path,
            fields={name: self._field_schema(child) for name, child in spec.fields.items()},
            field_values=values,
            values={name: value.value for name, value in values.items()},
        )
        return _NodeResult(node_id=graph_path, spec=spec, values=values)

    def _node_from_value(
        self,
        value: ResolvedValue | None,
        builder: _GraphBuilder,
    ) -> ResolvedNode | None:
        if value is None or value.ref_target is None:
            return None
        return builder.nodes.get(value.ref_target)

    def _default_values(
        self,
        spec: _ResolvedSpec,
        builder: _GraphBuilder,
        graph_path: str,
    ) -> dict[str, ResolvedValue]:
        values: dict[str, ResolvedValue] = {}
        for name, field_def in spec.fields.items():
            if field_def.fields:
                child = self._resolve_inline_node(
                    field=field_def,
                    source_path=spec.source_path,
                    graph_path=f"{graph_path}.{name}",
                    builder=builder,
                    assignments=(),
                    base_node=None,
                    base_as_parent=False,
                    impl_stack=(),
                    ref_stack=(),
                )
                _add_edge(builder, ResolvedEdge("ref", graph_path, child.node_id, (name,)))
                values[name] = ResolvedValue(
                    value={"$ref": child.node_id},
                    source_path=_field_source_path(field_def, spec.source_path),
                    origin="default",
                    span=field_def.span,
                    ref_target=child.node_id,
                )
                continue
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
        resolved = _resolve_path(Path(original), source_path.parent)
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
            required=field.default is None and field.derived is None,
            source_path=source_path,
            metadata={key: _literal_plain_value(value) for key, value in field.metadata.items()},
            override=field.override,
            has_default=field.default is not None,
            default=_literal_plain_value(field.default) if field.default is not None else None,
            derived=field.derived,
            constraints=field.constraints,
            span=field.span,
        )

    def _finalize_derivations(self, builder: _GraphBuilder) -> None:
        finalize_derivations(
            nodes=builder.nodes,
            paths=builder.paths,
            path_exists=self._resolver.path_exists,
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
        return assignment.field_path[0]

    def _metadata_string(
        self,
        field: FieldDef | ResolvedField,
        name: str,
        default: str,
    ) -> str:
        value = field.metadata.get(name)
        if value is None:
            return default
        return str(value.value) if isinstance(value, LiteralValue) else str(value)
