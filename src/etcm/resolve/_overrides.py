from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from etcm.ir import FieldDef
from etcm.resolve._diagnostics import field_source_path, raise_error
from etcm.resolve._types import is_list_type, is_string_keyed_dict_type, type_text
from etcm.resolve.graph import ResolvedValue

OVERRIDE_POLICIES = {"allow", "deny", "force_only", "append", "merge"}


def validate_override_policy(field: FieldDef, source_path: Path) -> None:
    policy = field.override
    field_source = field_source_path(field, source_path)
    details = {"field": field.name, "override": policy}

    if policy not in OVERRIDE_POLICIES:
        raise_error(
            "E_INVALID_OVERRIDE",
            f"Unknown override policy '{policy}' for field '{field.name}'.",
            source_path=field_source,
            span=field.span,
            details={**details, "reason": "unknown_policy"},
        )
    if field.derived is not None and policy != "allow":
        raise_error(
            "E_INVALID_OVERRIDE",
            f"Derived parameter '{field.name}' cannot declare override policy '{policy}'.",
            source_path=field_source,
            span=field.span,
            details={**details, "reason": "derived_parameter"},
        )
    if policy == "deny" and field.default is None:
        raise_error(
            "E_INVALID_OVERRIDE",
            f"Field '{field.name}' with override policy 'deny' requires an inline default.",
            source_path=field_source,
            span=field.span,
            details={**details, "reason": "missing_inline_default"},
        )
    if policy == "append" and not is_list_type(field.type_expr):
        raise_error(
            "E_INVALID_OVERRIDE",
            f"Field '{field.name}' with override policy 'append' must use list[T], "
            f"got '{type_text(field.type_expr)}'.",
            source_path=field_source,
            span=field.span,
            details={
                **details,
                "reason": "incompatible_type",
                "expected": "list[T]",
                "actual": type_text(field.type_expr),
            },
        )
    if policy == "merge" and not is_string_keyed_dict_type(field.type_expr):
        raise_error(
            "E_INVALID_OVERRIDE",
            f"Field '{field.name}' with override policy 'merge' must use "
            f"dict[str, T], got '{type_text(field.type_expr)}'.",
            source_path=field_source,
            span=field.span,
            details={
                **details,
                "reason": "incompatible_type",
                "expected": "dict[str, T]",
                "actual": type_text(field.type_expr),
            },
        )


def merge_mappings(
    previous: Mapping[str, Any],
    local: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(previous)
    for key, local_value in local.items():
        previous_value = result.get(key)
        if isinstance(previous_value, Mapping) and isinstance(local_value, Mapping):
            result[key] = merge_mappings(previous_value, local_value)
        else:
            result[key] = local_value
    return result


def apply_value(
    *,
    values: Mapping[str, ResolvedValue],
    field: FieldDef,
    field_name: str,
    new_value: ResolvedValue,
    force_authorized: bool = False,
) -> dict[str, ResolvedValue]:
    result = dict(values)
    previous = result.get(field_name)
    if previous is None:
        result[field_name] = new_value
        return result

    applied_value = new_value.value
    if (
        field.override == "append"
        and isinstance(previous.value, list)
        and isinstance(new_value.value, list)
    ):
        applied_value = [*previous.value, *new_value.value]
    elif (
        field.override == "merge"
        and isinstance(previous.value, dict)
        and isinstance(new_value.value, dict)
    ):
        applied_value = merge_mappings(previous.value, new_value.value)
    result[field_name] = new_value.with_override(
        value=applied_value,
        previous_origin=previous.origin,
        previous_value=previous.value,
        local_value=new_value.value,
        override_forced=force_authorized and field.override == "force_only",
    )
    return result
