from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from etcm.ir import ParameterReference, SourceSpan
from etcm.resolve._diagnostics import raise_error
from etcm.resolve._types import type_text, value_matches_type
from etcm.resolve.graph import ResolvedNode, ResolvedValue


def resolved_parameter_value(
    *,
    node: ResolvedNode,
    node_by_id: Mapping[str, ResolvedNode],
    reference: ParameterReference,
    initial_values: Mapping[str, ResolvedValue] | None = None,
    required_by: str,
    source_path: Path,
    span: SourceSpan | None,
) -> Any:
    active_node = node
    for index, part in enumerate(reference.parts):
        field = active_node.fields.get(part)
        if field is None:
            raise_error(
                "E_PARAMETER_REFERENCE",
                f"Unknown parameter reference '{reference.raw}' in resolved graph.",
                source_path=source_path,
                span=reference.span or span,
                graph_path=required_by,
                details={
                    "reference": reference.raw,
                    "missing_segment": part,
                    "available_parameters": list(active_node.fields),
                },
            )
        active_values = (
            initial_values
            if index == 0 and active_node.id == node.id and initial_values is not None
            else active_node.field_values
        )
        value = active_values.get(part)
        field_graph_path = f"{active_node.graph_path}.{part}"
        if value is None:
            raise_error(
                "E_MISSING_FIELD",
                f"Missing required field '{part}' needed by parameter expression.",
                source_path=field.source_path,
                span=field.span,
                graph_path=field_graph_path,
                details={
                    "field": part,
                    "reference": reference.raw,
                    "required_by": required_by,
                },
            )
        is_final = index == len(reference.parts) - 1
        if is_final:
            if value.ref_target is not None:
                raise_error(
                    "E_PARAMETER_REFERENCE",
                    f"Parameter reference '{reference.raw}' ends at an object.",
                    source_path=source_path,
                    span=reference.span or span,
                    graph_path=required_by,
                    details={"reference": reference.raw, "required_by": required_by},
                )
            if not value_matches_type(value.value, field.type_expr):
                raise_error(
                    "E_TYPE_MISMATCH",
                    f"Value used by '{reference.raw}' is not assignable to "
                    f"'{type_text(field.type_expr)}'.",
                    source_path=value.source_path,
                    span=value.span,
                    graph_path=field_graph_path,
                    details={
                        "reference": reference.raw,
                        "required_by": required_by,
                        "actual": type(value.value).__name__,
                        "expected": type_text(field.type_expr),
                    },
                )
            return value.value
        if value.ref_target is None:
            raise_error(
                "E_PARAMETER_REFERENCE",
                f"Parameter reference '{reference.raw}' cannot traverse scalar field '{part}'.",
                source_path=source_path,
                span=reference.span or span,
                graph_path=required_by,
                details={"reference": reference.raw, "scalar_segment": part},
            )
        target = node_by_id.get(value.ref_target)
        if target is None:
            raise_error(
                "E_PARAMETER_REFERENCE",
                f"Parameter reference '{reference.raw}' has no resolved object at '{part}'.",
                source_path=source_path,
                span=reference.span or span,
                graph_path=required_by,
                details={"reference": reference.raw, "object_segment": part},
            )
        active_node = target
    raise AssertionError("parameter reference path is empty")
