from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from etcm.ir import FieldDef, LiteralValue, Selector, SourceSpan, TypeExpr
from etcm.resolve._diagnostics import field_source_path, raise_error
from etcm.resolve._graph_builder import GraphBuilder, add_edge
from etcm.resolve._override_input import OverrideOperation
from etcm.resolve._overrides import apply_value
from etcm.resolve._selectors import normalize_selector, selector_from_ir
from etcm.resolve._specs import ResolvedSpec
from etcm.resolve._types import PRIMITIVE_TYPES
from etcm.resolve.graph import PathResolution, ResolvedEdge, ResolvedNode, ResolvedValue
from etcm.resolve.relations import render_expression

_ImplKey = tuple[Path, str, str]


class PatchHost(Protocol):
    def resolve_patch_reference(
        self,
        *,
        selector: Selector,
        graph_path: str,
        builder: GraphBuilder,
        impl_stack: tuple[_ImplKey, ...],
        ref_stack: tuple[_ImplKey, ...],
    ) -> str: ...

    def materialize_patch_literal(
        self,
        *,
        literal: LiteralValue,
        expected: TypeExpr,
        field: FieldDef,
        source_path: Path,
        span: SourceSpan | None,
        graph_path: str,
        builder: GraphBuilder,
        value_base: Path,
    ) -> Any: ...


class PatchApplier:
    def __init__(self, host: PatchHost) -> None:
        self._host = host

    def apply_operations(
        self,
        *,
        node_id: str,
        operations: tuple[OverrideOperation, ...],
        builder: GraphBuilder,
        impl_stack: tuple[_ImplKey, ...],
        ref_stack: tuple[_ImplKey, ...],
    ) -> None:
        for index, operation in enumerate(operations):
            has_descendant = any(
                _path_is_prefix(operation.path, later.path)
                for later in operations[index + 1 :]
            )
            if has_descendant and not self._operation_targets_reference(
                node_id, operation, builder
            ):
                self._raise_path_conflict(operation)
            self._apply_operation(
                node_id=node_id,
                operation=operation,
                builder=builder,
                impl_stack=impl_stack,
                ref_stack=ref_stack,
            )

    def _apply_operation(
        self,
        *,
        node_id: str,
        operation: OverrideOperation,
        builder: GraphBuilder,
        impl_stack: tuple[_ImplKey, ...],
        ref_stack: tuple[_ImplKey, ...],
    ) -> None:
        active_node_id = node_id
        for index, field_name in enumerate(operation.path):
            node = builder.nodes[active_node_id]
            spec = builder.specs[active_node_id]
            field = self._field(spec, field_name, operation.span)
            graph_path = f"{active_node_id}.{field_name}"
            is_leaf = index == len(operation.path) - 1

            if not is_leaf:
                if not field.fields and field.ref_selector is None:
                    self._raise_invalid_traversal(
                        operation=operation,
                        field=field,
                        graph_path=graph_path,
                    )
                previous = node.field_values.get(field_name)
                if previous is None or previous.ref_target is None:
                    self._raise_invalid_traversal(
                        operation=operation,
                        field=field,
                        graph_path=graph_path,
                        reason="unset_reference",
                    )
                assert previous is not None
                active_node_id = self._writable_child(
                    parent_id=active_node_id,
                    field=field,
                    previous=previous,
                    operation=operation,
                    builder=builder,
                )
                continue

            if field.derived is not None:
                raise_error(
                    "E_DERIVED_ASSIGNMENT",
                    f"Cannot assign derived parameter '{field.name}'.",
                    source_path=self._operation_source(operation, node),
                    span=operation.span,
                    graph_path=graph_path,
                    details={
                        "field": field.name,
                        "expression": field.derived.raw
                        or render_expression(field.derived),
                    },
                )

            previous = node.field_values.get(field_name)
            if self._operation_assigns_reference(field, previous, operation):
                new_value = self._reference_value(
                    node_id=active_node_id,
                    spec=spec,
                    field=field,
                    previous=previous,
                    operation=operation,
                    graph_path=graph_path,
                    builder=builder,
                    impl_stack=impl_stack,
                    ref_stack=ref_stack,
                )
            else:
                new_value = self._literal_value(
                    node=node,
                    field=field,
                    operation=operation,
                    graph_path=graph_path,
                    builder=builder,
                )

            values = apply_value(
                values=node.field_values,
                field=field,
                field_name=field_name,
                new_value=new_value,
                force_authorized=operation.force_authorized,
            )
            self._replace_node_values(active_node_id, values, builder)

    def _literal_value(
        self,
        *,
        node: ResolvedNode,
        field: FieldDef,
        operation: OverrideOperation,
        graph_path: str,
        builder: GraphBuilder,
    ) -> ResolvedValue:
        if operation.value is None:
            raise_error(
                "E_TYPE_MISMATCH",
                f"Field '{field.name}' requires a literal value.",
                source_path=self._operation_source(operation, node),
                span=operation.span,
                graph_path=graph_path,
                details={"field": field.name},
            )
        if field.fields:
            raise_error(
                "E_TYPE_MISMATCH",
                f"Nested field '{field.name}' requires a child assignment path.",
                source_path=self._operation_source(operation, node),
                span=operation.span,
                graph_path=graph_path,
                details={"field": field.name},
            )

        self._remove_value_paths(builder, graph_path)
        value = self._host.materialize_patch_literal(
            literal=operation.value,
            expected=field.type_expr,
            field=field,
            source_path=self._operation_source(operation, node),
            span=operation.span,
            graph_path=graph_path,
            builder=builder,
            value_base=operation.value_base,
        )
        return ResolvedValue(
            value=value,
            source_path=self._operation_source(operation, node),
            span=operation.span,
            origin=operation.origin,
            literal=operation.value,
            override_base=operation.value_base if operation.origin == "external" else None,
        )

    def _reference_value(
        self,
        *,
        node_id: str,
        spec: ResolvedSpec,
        field: FieldDef,
        previous: ResolvedValue | None,
        operation: OverrideOperation,
        graph_path: str,
        builder: GraphBuilder,
        impl_stack: tuple[_ImplKey, ...],
        ref_stack: tuple[_ImplKey, ...],
    ) -> ResolvedValue:
        node = builder.nodes[node_id]
        if field.fields:
            raise_error(
                "E_TYPE_MISMATCH",
                f"Field '{field.name}' cannot be assigned with a reference.",
                source_path=self._operation_source(operation, node),
                span=operation.span,
                graph_path=graph_path,
                details={"field": field.name},
            )

        selector = self._reference_selector(
            operation=operation,
            field=field,
            previous=previous,
            node=node,
            spec=spec,
            builder=builder,
        )
        self._remove_subtree(builder, graph_path)
        next_ref_stack = ref_stack
        if impl_stack:
            next_ref_stack = (*ref_stack, impl_stack[-1])
        else:
            context_key = self._reference_context_key(node_id, builder)
            if context_key is not None:
                next_ref_stack = (*ref_stack, context_key)
        child_id = self._host.resolve_patch_reference(
            selector=selector,
            graph_path=graph_path,
            builder=builder,
            impl_stack=impl_stack,
            ref_stack=next_ref_stack,
        )
        self._set_ref_edge(builder, node_id, field.name, child_id)
        return ResolvedValue(
            value={"$ref": child_id},
            source_path=self._operation_source(operation, node),
            span=operation.span,
            origin=operation.origin,
            ref_target=child_id,
            override_base=operation.value_base if operation.origin == "external" else None,
        )

    def _reference_context_key(
        self,
        node_id: str,
        builder: GraphBuilder,
    ) -> _ImplKey | None:
        candidate = node_id
        while True:
            node = builder.nodes.get(candidate)
            if node is not None and node.implementation != "inline":
                return (node.source_path, node.spec_name, node.implementation)
            if "." not in candidate:
                return None
            candidate = candidate.rsplit(".", 1)[0]

    def _reference_selector(
        self,
        *,
        operation: OverrideOperation,
        field: FieldDef,
        previous: ResolvedValue | None,
        node: ResolvedNode,
        spec: ResolvedSpec,
        builder: GraphBuilder,
    ) -> Selector:
        if operation.selector is not None:
            source_path = operation.source_path or node.source_path
            return selector_from_ir(
                operation.selector,
                source_path,
                active_spec=spec.name,
            )

        literal = operation.value
        if literal is None or literal.kind != "string":
            raise_error(
                "E_TYPE_MISMATCH",
                f"Reference override for '{field.name}' must be an implementation selector.",
                source_path=self._operation_source(operation, node),
                span=operation.span,
                graph_path=f"{node.graph_path}.{field.name}",
                details={"field": field.name, "expected": "implementation selector"},
            )
        raw = str(literal.value)
        try:
            selector = Selector.parse(raw)
        except ValueError as exc:
            raise_error(
                "E_MISSING_SELECTOR",
                f"Invalid reference override for '{field.name}': {exc}.",
                source_path=self._operation_source(operation, node),
                span=operation.span,
                selector=raw,
                graph_path=f"{node.graph_path}.{field.name}",
            )
        if selector.target != "implementation":
            raise_error(
                "E_MISSING_SELECTOR",
                f"Reference override for '{field.name}' must select an implementation.",
                source_path=self._operation_source(operation, node),
                span=operation.span,
                selector=raw,
                graph_path=f"{node.graph_path}.{field.name}",
            )

        if selector.path is not None:
            return normalize_selector(
                selector,
                declaring_source=operation.value_base / "__override__.etcm",
                active_spec=None,
            )

        anchor_path: Path | None = None
        anchor_spec: str | None = None
        if previous is not None and previous.ref_target is not None:
            target = builder.nodes.get(previous.ref_target)
            if target is not None:
                anchor_path = target.source_path
                anchor_spec = target.spec_name
        if anchor_path is None:
            if field.ref_selector is None:
                raise_error(
                    "E_MISSING_SELECTOR",
                    f"Pathless reference override for '{field.name}' has no anchor.",
                    source_path=self._operation_source(operation, node),
                    span=operation.span,
                    selector=raw,
                    graph_path=f"{node.graph_path}.{field.name}",
                    details={
                        "field": field.name,
                        "reason": "missing_reference_anchor",
                    },
                )
            declared = normalize_selector(
                field.ref_selector,
                declaring_source=field_source_path(field, spec.source_path),
                active_spec=None,
            )
            anchor_path = declared.path
            anchor_spec = declared.spec
        if anchor_path is None:
            raise AssertionError("normalized reference selector has no path")
        return normalize_selector(
            selector,
            declaring_source=anchor_path,
            active_spec=anchor_spec,
        )

    def _writable_child(
        self,
        *,
        parent_id: str,
        field: FieldDef,
        previous: ResolvedValue,
        operation: OverrideOperation,
        builder: GraphBuilder,
    ) -> str:
        if previous.ref_target is None:
            raise AssertionError("object value has no reference target")
        desired_id = f"{parent_id}.{field.name}"
        if previous.ref_target == desired_id:
            return desired_id

        base_id = previous.ref_target
        base = builder.nodes.get(base_id)
        if base is None:
            raise AssertionError(f"missing referenced node '{base_id}'")
        self._remove_subtree(builder, desired_id)

        mark_parent = operation.origin == "local" and previous.origin == "parent"
        values = {
            name: value.as_parent() if mark_parent else value
            for name, value in base.field_values.items()
        }
        builder.nodes[desired_id] = replace(
            base,
            id=desired_id,
            graph_path=desired_id,
            field_values=values,
            values={name: value.value for name, value in values.items()},
        )
        builder.specs[desired_id] = builder.specs[base_id]

        for edge in tuple(builder.edges):
            if edge.source == base_id:
                add_edge(builder, replace(edge, source=desired_id))
        self._clone_node_paths(builder, base_id, desired_id, values)
        self._set_ref_edge(builder, parent_id, field.name, desired_id)

        parent = builder.nodes[parent_id]
        parent_values = dict(parent.field_values)
        parent_values[field.name] = replace(
            previous,
            value={"$ref": desired_id},
            ref_target=desired_id,
        )
        self._replace_node_values(parent_id, parent_values, builder)
        return desired_id

    def _clone_node_paths(
        self,
        builder: GraphBuilder,
        base_id: str,
        desired_id: str,
        values: Mapping[str, ResolvedValue],
    ) -> None:
        scalar_prefixes = tuple(
            f"{base_id}.{name}"
            for name, value in values.items()
            if value.ref_target is None
        )
        additions: list[PathResolution] = []
        for path in builder.paths:
            for prefix in scalar_prefixes:
                if path.field_path == prefix or path.field_path.startswith(
                    (f"{prefix}.", f"{prefix}[")
                ):
                    additions.append(
                        replace(
                            path,
                            field_path=f"{desired_id}{path.field_path[len(base_id):]}",
                        )
                    )
                    break
        builder.paths.extend(additions)

    def _operation_targets_reference(
        self,
        node_id: str,
        operation: OverrideOperation,
        builder: GraphBuilder,
    ) -> bool:
        active_node_id = node_id
        for index, field_name in enumerate(operation.path):
            spec = builder.specs.get(active_node_id)
            node = builder.nodes.get(active_node_id)
            if spec is None or node is None:
                return False
            field = spec.fields.get(field_name)
            if field is None:
                return False
            if index == len(operation.path) - 1:
                previous = node.field_values.get(field_name)
                return self._operation_assigns_reference(
                    field, previous, operation
                )
            value = node.field_values.get(field_name)
            if value is None or value.ref_target is None:
                return False
            active_node_id = value.ref_target
        return False

    def _operation_assigns_reference(
        self,
        field: FieldDef,
        previous: ResolvedValue | None,
        operation: OverrideOperation,
    ) -> bool:
        if operation.selector is not None:
            return True
        if (
            operation.origin != "external"
            or operation.value is None
            or operation.value.kind != "string"
        ):
            return False
        if field.ref_selector is not None:
            return True
        if previous is not None and previous.ref_target is not None:
            return True
        if not _type_accepts_reference(field.type_expr):
            return False
        try:
            Selector.parse(str(operation.value.value))
        except ValueError:
            return False
        return True

    def _replace_node_values(
        self,
        node_id: str,
        values: Mapping[str, ResolvedValue],
        builder: GraphBuilder,
    ) -> None:
        node = builder.nodes[node_id]
        builder.nodes[node_id] = replace(
            node,
            field_values=values,
            values={name: value.value for name, value in values.items()},
        )

    def _set_ref_edge(
        self,
        builder: GraphBuilder,
        source: str,
        field_name: str,
        target: str,
    ) -> None:
        builder.edges = [
            edge
            for edge in builder.edges
            if not (
                edge.kind == "ref"
                and edge.source == source
                and edge.field_path == (field_name,)
            )
        ]
        add_edge(builder, ResolvedEdge("ref", source, target, (field_name,)))

    def _remove_subtree(self, builder: GraphBuilder, root: str) -> None:
        removed = {
            node_id
            for node_id in builder.nodes
            if node_id == root or node_id.startswith(f"{root}.")
        }
        if not removed:
            return
        for node_id in removed:
            builder.nodes.pop(node_id, None)
            builder.specs.pop(node_id, None)
        builder.edges = [
            edge
            for edge in builder.edges
            if edge.source not in removed and edge.target not in removed
        ]
        builder.paths = [
            path
            for path in builder.paths
            if not (
                path.field_path == root
                or path.field_path.startswith((f"{root}.", f"{root}["))
            )
        ]

    def _remove_value_paths(self, builder: GraphBuilder, graph_path: str) -> None:
        builder.paths = [
            path
            for path in builder.paths
            if not (
                path.field_path == graph_path
                or path.field_path.startswith(
                    (f"{graph_path}.", f"{graph_path}[")
                )
            )
        ]

    def _raise_path_conflict(self, operation: OverrideOperation) -> None:
        canonical = ".".join(operation.path)
        raise_error(
            "E_OVERRIDE_PATH_CONFLICT",
            f"Override '{canonical}' conflicts with a descendant override.",
            source_path=operation.source_path or operation.value_base,
            span=operation.span,
            graph_path=f"root.{canonical}",
            details={"field_path": canonical},
        )

    def _raise_invalid_traversal(
        self,
        *,
        operation: OverrideOperation,
        field: FieldDef,
        graph_path: str,
        reason: str = "scalar_boundary",
    ) -> None:
        canonical = ".".join(operation.path)
        raise_error(
            "E_INVALID_PATH",
            f"Cannot traverse field '{field.name}' while applying '{canonical}'.",
            source_path=operation.source_path or operation.value_base,
            span=operation.span,
            graph_path=graph_path,
            details={
                "field": field.name,
                "field_path": canonical,
                "boundary": graph_path,
                "reason": reason,
            },
        )

    def _field(
        self,
        spec: ResolvedSpec,
        field_name: str,
        span: SourceSpan | None,
    ) -> FieldDef:
        field = spec.fields.get(field_name)
        if field is None:
            raise_error(
                "E_TYPE_MISMATCH",
                f"Unknown field '{field_name}' for spec '{spec.name}'.",
                source_path=span.source_path if span is not None else spec.source_path,
                span=span,
                details={"field": field_name, "spec": spec.name},
            )
        return field

    def _operation_source(
        self,
        operation: OverrideOperation,
        node: ResolvedNode,
    ) -> Path:
        return operation.source_path or operation.value_base or node.source_path


def _path_is_prefix(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return len(left) < len(right) and right[: len(left)] == left


def _type_accepts_reference(type_expr: TypeExpr) -> bool:
    if type_expr.kind == "union":
        return any(_type_accepts_reference(option) for option in type_expr.args)
    return (
        type_expr.kind == "named"
        and type_expr.name is not None
        and type_expr.name not in PRIMITIVE_TYPES
    )
