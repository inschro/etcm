from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from etcm.ir import Expression, FieldDef, ParameterReference
from etcm.resolve._diagnostics import raise_error
from etcm.resolve._parameters import resolved_parameter_value
from etcm.resolve._types import type_text, value_matches_type
from etcm.resolve.graph import PathResolution, ResolvedField, ResolvedNode, ResolvedValue
from etcm.resolve.relations import (
    RelationEvaluationError,
    evaluate_expression,
    expression_references,
    render_expression,
)


def expression_contains_current(expression: Expression) -> bool:
    return expression.kind == "current" or any(
        expression_contains_current(operand) for operand in expression.operands
    )


def derived_dependencies(
    fields: Mapping[str, FieldDef | ResolvedField],
    field_name: str,
) -> tuple[str, ...]:
    derived = fields[field_name].derived
    if derived is None:
        return ()
    dependencies: list[str] = []
    for reference in expression_references(derived):
        if len(reference.parts) != 1:
            continue
        dependency_name = reference.parts[0]
        dependency = fields.get(dependency_name)
        if (
            dependency is not None
            and dependency.derived is not None
            and dependency_name not in dependencies
        ):
            dependencies.append(dependency_name)
    return tuple(dependencies)


def derived_cycle(
    fields: Mapping[str, FieldDef | ResolvedField],
) -> tuple[str, ...] | None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(name: str) -> tuple[str, ...] | None:
        if name in visiting:
            start = visiting.index(name)
            return (*visiting[start:], name)
        if name in visited:
            return None
        visiting.append(name)
        for dependency in derived_dependencies(fields, name):
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        visiting.pop()
        visited.add(name)
        return None

    for name, field in fields.items():
        if field.derived is None:
            continue
        cycle = visit(name)
        if cycle is not None:
            return cycle
    return None


def derived_order(fields: Mapping[str, FieldDef | ResolvedField]) -> tuple[str, ...]:
    order: list[str] = []
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        for dependency in derived_dependencies(fields, name):
            visit(dependency)
        visited.add(name)
        order.append(name)

    for name, field in fields.items():
        if field.derived is not None:
            visit(name)
    return tuple(order)


def finalize_derivations(
    *,
    nodes: dict[str, ResolvedNode],
    paths: list[PathResolution],
    path_exists: str,
) -> None:
    finalized: set[str] = set()
    active: set[str] = set()

    def finalize_node(node_id: str) -> None:
        if node_id in finalized:
            return
        if node_id in active:
            raise_error(
                "E_REF_CYCLE",
                "Reference cycle encountered while computing derived parameters.",
                graph_path=node_id,
            )
        active.add(node_id)
        node = nodes[node_id]
        for resolved_value in node.field_values.values():
            if resolved_value.ref_target is not None:
                finalize_node(resolved_value.ref_target)

        values = dict(node.field_values)
        for field_name in derived_order(node.fields):
            field = node.fields[field_name]
            expression = field.derived
            if expression is None:
                raise AssertionError("derived field order contains a non-derived field")
            resolved_operands: dict[str, Any] = {}

            def reference_value(
                reference: ParameterReference,
                current_node: ResolvedNode = node,
                current_values: Mapping[str, ResolvedValue] = values,
                current_field_name: str = field_name,
                current_field: ResolvedField = field,
                current_expression: Expression = expression,
                operands: dict[str, Any] = resolved_operands,
            ) -> Any:
                resolved = resolved_parameter_value(
                    node=current_node,
                    node_by_id=nodes,
                    reference=reference,
                    initial_values=current_values,
                    required_by=f"{current_node.graph_path}.{current_field_name}",
                    source_path=current_field.source_path,
                    span=current_expression.span,
                )
                operands[reference.raw[1:]] = resolved
                return resolved

            try:
                result = evaluate_expression(
                    expression,
                    current_value=None,
                    reference_value=reference_value,
                )
            except RelationEvaluationError as exc:
                raise_error(
                    "E_EXPRESSION_EVALUATION",
                    f"Could not derive parameter '{field_name}': {exc}",
                    source_path=field.source_path,
                    span=expression.span,
                    graph_path=f"{node.graph_path}.{field_name}",
                    details={
                        "field": field_name,
                        "expression": expression.raw or render_expression(expression),
                        "resolved_values": resolved_operands,
                        **exc.details,
                    },
                )
            if not value_matches_type(result, field.type_expr):
                raise_error(
                    "E_TYPE_MISMATCH",
                    f"Derived value of type '{type(result).__name__}' is not assignable "
                    f"to '{type_text(field.type_expr)}'.",
                    source_path=field.source_path,
                    span=expression.span,
                    graph_path=f"{node.graph_path}.{field_name}",
                    details={
                        "field": field_name,
                        "expression": expression.raw,
                        "actual": type(result).__name__,
                        "expected": type_text(field.type_expr),
                        "resolved_values": resolved_operands,
                    },
                )
            values[field_name] = ResolvedValue(
                value=result,
                source_path=field.source_path,
                origin="derived",
                span=expression.span,
                derived_expression=expression,
            )
            if isinstance(result, Path):
                paths.append(
                    PathResolution(
                        field_path=f"{node.graph_path}.{field_name}",
                        source_path=field.source_path,
                        original=expression.raw or render_expression(expression),
                        resolved_path=result,
                        field_policy=_metadata_string(field, "path_exists", "resolver"),
                        resolver_policy=path_exists,
                        expected_kind=_metadata_string(field, "path_kind", "any"),
                        exists=result.exists(),
                        span=expression.span,
                    )
                )

        nodes[node_id] = replace(
            node,
            field_values=values,
            values={name: value.value for name, value in values.items()},
        )
        active.remove(node_id)
        finalized.add(node_id)

    for node_id in tuple(nodes):
        finalize_node(node_id)


def _metadata_string(field: ResolvedField, name: str, default: str) -> str:
    value = field.metadata.get(name)
    if value is None:
        return default
    return str(value)
