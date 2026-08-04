from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from etcm._contracts import OverrideInput
from etcm.ir import FieldDef, LiteralValue, Selector, SourceSpan, TypeExpr
from etcm.resolve._derivations import finalize_derivations
from etcm.resolve._diagnostics import field_source_path as _field_source_path
from etcm.resolve._diagnostics import raise_error as _raise
from etcm.resolve._graph_builder import GraphBuilder as _GraphBuilder
from etcm.resolve._graph_builder import NodeResult as _NodeResult
from etcm.resolve._graph_builder import add_edge as _add_edge
from etcm.resolve._override_input import (
    normalize_external_overrides,
    operations_from_assignments,
)
from etcm.resolve._patches import PatchApplier
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

if TYPE_CHECKING:
    from etcm.resolve._api import Resolver

_PATH_METADATA = {"path_exists", "path_kind"}


class _ResolverState:
    def __init__(self, resolver: Resolver) -> None:
        self._resolver = resolver
        self._spec_resolver = SpecResolver()
        self._patch_applier = PatchApplier(self)

    def resolve(
        self,
        raw_selector: str,
        *,
        overrides: OverrideInput | None = None,
        force_overrides: bool = False,
        override_base: str | Path | None = None,
    ) -> ResolvedGraph:
        selector = _selector_from_raw(raw_selector)
        builder = _GraphBuilder(root_selector=_canonical_selector(selector))
        root = self._resolve_node(
            selector=selector,
            graph_path="root",
            builder=builder,
            impl_stack=(),
            ref_stack=(),
            cycle_code="E_IMPL_CYCLE",
        )
        operations = normalize_external_overrides(
            overrides,
            force_authorized=force_overrides,
            override_base=override_base,
        )
        self._patch_applier.apply_operations(
            node_id=root.node_id,
            operations=operations,
            builder=builder,
            impl_stack=(),
            ref_stack=(),
        )
        self._finalize_derivations(builder)
        builder.sources.update(self._spec_resolver.documents)
        return builder.to_graph()

    def resolve_patch_reference(
        self,
        *,
        selector: Selector,
        graph_path: str,
        builder: _GraphBuilder,
        impl_stack: tuple[tuple[Path, str, str], ...],
        ref_stack: tuple[tuple[Path, str, str], ...],
    ) -> str:
        return self._resolve_node(
            selector=selector,
            graph_path=graph_path,
            builder=builder,
            impl_stack=impl_stack,
            ref_stack=ref_stack,
            cycle_code="E_REF_CYCLE",
        ).node_id

    def materialize_patch_literal(
        self,
        *,
        literal: LiteralValue,
        expected: TypeExpr,
        field: FieldDef,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
        builder: _GraphBuilder,
        value_base: Path,
    ) -> Any:
        return self._materialize_literal(
            literal=literal,
            expected=expected,
            field=field,
            source_path=source_path,
            span=span,
            graph_path=graph_path,
            builder=builder,
            value_base=value_base,
        )

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
        builder.specs[node_id] = spec
        if spec.ancestors:
            builder.edges.append(ResolvedEdge("spec_parent", node_id, f"spec:{spec.ancestors[0]}"))
        if parent_result is not None:
            builder.edges.append(ResolvedEdge("impl_parent", node_id, parent_result.node_id))
        self._patch_applier.apply_operations(
            node_id=node_id,
            operations=operations_from_assignments(
                impl.assignments,
                source_path=source_path,
            ),
            builder=builder,
            impl_stack=next_impl_stack,
            ref_stack=ref_stack,
        )
        resolved_values = builder.nodes[node_id].field_values
        return _NodeResult(node_id=node_id, spec=spec, values=resolved_values)

    def _resolve_inline_node(
        self,
        *,
        field: FieldDef,
        source_path: Path,
        graph_path: str,
        builder: _GraphBuilder,
    ) -> _NodeResult:
        spec = _ResolvedSpec(
            name=str(field.type_expr.name),
            source_path=_field_source_path(field, source_path),
            fields={child.name: child for child in field.fields},
        )
        values = self._default_values(spec, builder, graph_path)
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
        builder.specs[graph_path] = spec
        return _NodeResult(node_id=graph_path, spec=spec, values=values)

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
        value_base: Path | None = None,
    ) -> Any:
        if _type_accepts_path(expected) and literal.kind == "string":
            return self._materialize_path(
                literal,
                field,
                source_path,
                span,
                graph_path,
                builder,
                value_base,
            )
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
                    value_base=value_base,
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
                    value_base=value_base,
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
        value_base: Path | None,
    ) -> Path:
        original = str(literal.value)
        resolved = _resolve_path(
            Path(original),
            source_path.parent if value_base is None else value_base,
        )
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
