from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn, cast

from etcm.ir import AssertionDef, ComparisonConstraint, ParameterReference
from etcm.resolve._diagnostics import raise_error
from etcm.resolve._parameters import resolved_parameter_value
from etcm.resolve._types import (
    is_number,
    ref_assignable,
    spec_assignable,
    type_text,
    value_matches_type,
)
from etcm.resolve.graph import (
    PathResolution,
    ResolvedField,
    ResolvedGraph,
    ResolvedNode,
    ResolvedValue,
)
from etcm.resolve.relations import (
    RelationEvaluationError,
    evaluate_assertion_expression,
    evaluate_comparison,
    evaluate_expression,
    format_value,
    render_assertion_expression,
    render_expression,
)

_PATH_METADATA = {"path_exists", "path_kind"}


def validate_graph(graph: ResolvedGraph) -> ResolvedGraph:
    node_by_id = {node.id: node for node in graph.nodes}
    for edge in graph.edges:
        if edge.kind == "impl_parent":
            source = node_by_id[edge.source]
            target = node_by_id[edge.target]
            if not spec_assignable(target, source.spec_name):
                raise_error(
                    "E_TYPE_MISMATCH",
                    f"Implementation parent is not assignable to spec '{source.spec_name}'.",
                    source_path=source.source_path,
                    selector=target.selector,
                    graph_path=source.graph_path,
                    details={"actual": target.spec_name, "expected": source.spec_name},
                )

    for node in sorted(graph.nodes, key=lambda item: item.id):
        _validate_node_values(node, node_by_id)

    for path in graph.path_resolution:
        _validate_path(path)

    for node in sorted(graph.nodes, key=lambda item: item.id):
        _validate_node_constraints(node, node_by_id)

    for node in sorted(graph.nodes, key=lambda item: item.id):
        _validate_node_assertions(node, node_by_id)

    return graph.with_validated(True)


def _validate_node_values(
    node: ResolvedNode,
    node_by_id: Mapping[str, ResolvedNode],
) -> None:
    for field_name, field in node.fields.items():
        value = node.field_values.get(field_name)
        graph_path = f"{node.graph_path}.{field_name}"
        if value is None:
            raise_error(
                "E_MISSING_FIELD",
                f"Missing required field '{field_name}'.",
                source_path=field.source_path,
                span=field.span,
                graph_path=graph_path,
                details={"field": field_name},
            )
        if value.applied_override:
            _validate_override(field, value, graph_path)
        if value.ref_target is not None:
            _validate_ref(field, value, node_by_id, graph_path)
            continue
        _validate_value_type(field, value, graph_path)


def _validate_node_constraints(
    node: ResolvedNode,
    node_by_id: Mapping[str, ResolvedNode],
) -> None:
    for field_name, field in node.fields.items():
        value = node.field_values[field_name]
        if value.ref_target is not None:
            continue
        _validate_constraints(field, value, f"{node.graph_path}.{field_name}")
        for constraint in field.constraints:
            _validate_relational_constraint(
                node=node,
                field=field,
                value=value,
                constraint=constraint,
                node_by_id=node_by_id,
            )


def _validate_ref(
    field: ResolvedField,
    value: ResolvedValue,
    node_by_id: Mapping[str, ResolvedNode],
    graph_path: str,
) -> None:
    assert value.ref_target is not None
    target = node_by_id[value.ref_target]
    if not ref_assignable(target, field.type_expr):
        raise_error(
            "E_TYPE_MISMATCH",
            f"Reference for field '{field.name}' is not assignable.",
            source_path=value.source_path,
            span=value.span,
            selector=target.selector,
            graph_path=graph_path,
            details={"actual": target.spec_name, "expected": type_text(field.type_expr)},
        )


def _validate_value_type(
    field: ResolvedField,
    value: ResolvedValue,
    graph_path: str,
) -> None:
    if value_matches_type(value.value, field.type_expr):
        return
    actual = value.literal.kind if value.literal is not None else type(value.value).__name__
    raise_error(
        "E_TYPE_MISMATCH",
        f"Value of type '{actual}' is not assignable to '{type_text(field.type_expr)}'.",
        source_path=value.source_path,
        span=value.span,
        graph_path=graph_path,
        details={"actual": actual, "expected": type_text(field.type_expr)},
    )


def _validate_override(
    field: ResolvedField,
    value: ResolvedValue,
    graph_path: str,
) -> None:
    if field.override == "deny":
        _invalid_override(field, value, graph_path)
    if field.override == "force_only" and not value.override_forced:
        _invalid_override(field, value, graph_path)
    if field.override == "append" and not (
        isinstance(value.previous_value, list) and isinstance(value.local_value, list)
    ):
        _invalid_override(field, value, graph_path)
    if field.override == "merge" and not (
        isinstance(value.previous_value, dict) and isinstance(value.local_value, dict)
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


def _validate_constraints(
    field: ResolvedField,
    value: ResolvedValue,
    graph_path: str,
) -> None:
    for name, constraint in field.metadata.items():
        if name in _PATH_METADATA:
            continue
        if name == "choices":
            _validate_choices(field, value, constraint, graph_path)
        elif name in {"gt", "ge", "lt", "le"}:
            _validate_numeric_bound(field, value, name, constraint, graph_path)
        elif name == "ne":
            _validate_not_equal(field, value, constraint, graph_path)
        elif name in {"min_length", "max_length"}:
            _validate_length_bound(field, value, name, constraint, graph_path)
        elif name == "regex":
            _validate_regex(field, value, constraint, graph_path)


def _validate_relational_constraint(
    *,
    node: ResolvedNode,
    field: ResolvedField,
    value: ResolvedValue,
    constraint: ComparisonConstraint,
    node_by_id: Mapping[str, ResolvedNode],
) -> None:
    graph_path = f"{node.graph_path}.{field.name}"
    resolved_values: dict[str, Any] = {
        field.name: _relation_detail_value(value.value),
    }

    def reference_value(reference: ParameterReference) -> Any:
        resolved = resolved_parameter_value(
            node=node,
            node_by_id=node_by_id,
            reference=reference,
            required_by=graph_path,
            source_path=field.source_path,
            span=constraint.span,
        )
        resolved_values[".".join(reference.parts)] = _relation_detail_value(resolved)
        return resolved

    try:
        left = evaluate_expression(
            constraint.left,
            current_value=value.value,
            reference_value=reference_value,
        )
        right = evaluate_expression(
            constraint.right,
            current_value=value.value,
            reference_value=reference_value,
        )
        substituted_left = render_expression(
            constraint.left,
            current_value=value.value,
            reference_value=reference_value,
            substitute_values=True,
        )
        substituted_right = render_expression(
            constraint.right,
            current_value=value.value,
            reference_value=reference_value,
            substitute_values=True,
        )
        substituted = f"{substituted_left} {constraint.operator} {substituted_right}"
        simplified = (
            f"{format_value(left)} {constraint.operator} {format_value(right)}"
        )
        valid = evaluate_comparison(constraint.operator, left, right)
    except RelationEvaluationError as exc:
        raise_error(
            "E_EXPRESSION_EVALUATION",
            f"Could not evaluate constraint for '{field.name}': {exc}",
            source_path=value.source_path,
            span=value.span,
            graph_path=graph_path,
            details={
                "field": field.name,
                "constraint": constraint.raw,
                "resolved_values": resolved_values,
                **exc.details,
            },
        )

    if valid:
        return
    raise_error(
        "E_CONSTRAINT",
        f"Validation failed for {node.spec_name}.{field.name}.",
        source_path=value.source_path,
        span=value.span,
        graph_path=graph_path,
        details={
            "field": field.name,
            "constraint": constraint.raw,
            "resolved_values": resolved_values,
            "evaluation": [substituted, simplified],
            "operator": constraint.operator,
        },
    )


def _validate_node_assertions(
    node: ResolvedNode,
    node_by_id: Mapping[str, ResolvedNode],
) -> None:
    for assertion in node.assertions:
        for index in range(len(assertion.predicates)):
            _validate_assertion_predicate(
                node=node,
                assertion=assertion,
                predicate_index=index,
                node_by_id=node_by_id,
            )


def _validate_assertion_predicate(
    *,
    node: ResolvedNode,
    assertion: AssertionDef,
    predicate_index: int,
    node_by_id: Mapping[str, ResolvedNode],
) -> None:
    predicate = assertion.predicates[predicate_index]
    resolved_values: dict[str, Any] = {}
    source_path = (
        assertion.span.source_path if assertion.span is not None else node.source_path
    )

    def reference_value(reference: ParameterReference) -> Any:
        resolved = resolved_parameter_value(
            node=node,
            node_by_id=node_by_id,
            reference=reference,
            required_by=node.graph_path,
            source_path=source_path,
            span=predicate.span,
        )
        resolved_values[".".join(reference.parts)] = _relation_detail_value(resolved)
        return resolved

    try:
        valid = evaluate_assertion_expression(
            predicate,
            reference_value=reference_value,
        )
        substituted = render_assertion_expression(
            predicate,
            reference_value=reference_value,
            substitute_values=True,
        )
    except RelationEvaluationError as exc:
        raise_error(
            "E_EXPRESSION_EVALUATION",
            f"Could not evaluate assertion '{assertion.name}': {exc}",
            source_path=source_path,
            span=predicate.span,
            graph_path=node.graph_path,
            details={
                "assertion": assertion.name,
                "predicate_index": predicate_index,
                "expression": predicate.raw,
                "resolved_values": resolved_values,
                **exc.details,
            },
        )

    if valid:
        return
    raise_error(
        "E_ASSERTION",
        f"Assertion '{assertion.name}' failed.",
        source_path=source_path,
        span=predicate.span,
        graph_path=node.graph_path,
        details={
            "assertion": assertion.name,
            "predicate_index": predicate_index,
            "expression": predicate.raw,
            "resolved_values": resolved_values,
            "evaluation": [substituted, "false"],
        },
    )


def _relation_detail_value(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _relation_detail_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_relation_detail_value(item) for item in value]
    return value


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
    if not is_number(bound) or not is_number(value.value):
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


def _validate_not_equal(
    field: ResolvedField,
    value: ResolvedValue,
    forbidden: object,
    graph_path: str,
) -> None:
    if value.value == forbidden:
        _constraint_failed(field, value, "ne", forbidden, graph_path)


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


def _invalid_override(
    field: ResolvedField,
    value: ResolvedValue,
    graph_path: str,
) -> NoReturn:
    details: dict[str, Any] = {
        "field": field.name,
        "override": field.override,
        "previous_origin": value.previous_origin,
    }
    if field.override == "force_only":
        details["force_authorized"] = value.override_forced
    raise_error(
        "E_INVALID_OVERRIDE",
        f"Field '{field.name}' cannot be overridden with policy '{field.override}'.",
        source_path=value.source_path,
        span=value.span,
        graph_path=graph_path,
        details=details,
    )


def _invalid_path(path: PathResolution) -> NoReturn:
    field_name = path.field_path.rsplit(".", 1)[-1]
    raise_error(
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
    raise_error(
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
    raise_error(
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
