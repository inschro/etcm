from __future__ import annotations

from pathlib import Path
from typing import Any

from etcm.ir import LiteralValue, TypeExpr
from etcm.resolve.graph import ResolvedNode

PRIMITIVE_TYPES = {"str", "int", "float", "bool", "null", "Path"}


def value_matches_type(value: Any, type_expr: TypeExpr) -> bool:
    if type_expr.kind == "union":
        return any(value_matches_type(value, option) for option in type_expr.args)
    if type_expr.kind == "generic":
        if type_expr.name == "File" and len(type_expr.args) == 1:
            codec_type = type_expr.args[0]
            if codec_type.kind == "named" and codec_type.name == "str":
                return isinstance(value, str)
            if codec_type.kind == "named" and codec_type.name == "bytes":
                return isinstance(value, bytes)
            return True
        if type_expr.name == "list" and isinstance(value, list) and len(type_expr.args) == 1:
            return all(value_matches_type(item, type_expr.args[0]) for item in value)
        if type_expr.name == "dict" and isinstance(value, dict) and len(type_expr.args) == 2:
            key_type, value_type = type_expr.args
            return key_type.name == "str" and all(
                isinstance(key, str) and value_matches_type(item, value_type)
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


def ref_assignable(actual: ResolvedNode, expected: TypeExpr) -> bool:
    if expected.kind == "union":
        return any(ref_assignable(actual, option) for option in expected.args)
    if expected.kind != "named" or expected.name is None:
        return False
    if expected.name in PRIMITIVE_TYPES:
        return False
    return spec_assignable(actual, expected.name)


def spec_assignable(actual: ResolvedNode, expected_name: str) -> bool:
    return actual.spec_name == expected_name or expected_name in actual.spec_ancestors


def type_accepts_path(type_expr: TypeExpr) -> bool:
    if type_expr.kind == "named":
        return type_expr.name == "Path"
    if type_expr.kind == "union":
        return any(type_accepts_path(option) for option in type_expr.args)
    return False


def literal_plain_value(literal: LiteralValue) -> Any:
    if literal.kind == "list":
        return [literal_plain_value(value) for value in literal.value]
    if literal.kind == "map":
        return {key: literal_plain_value(value) for key, value in literal.value}
    return literal.value


def is_number(value: object) -> bool:
    return type(value) in {int, float}


def type_text(type_expr: TypeExpr) -> str:
    if type_expr.kind == "named":
        return str(type_expr.name)
    if type_expr.kind == "generic":
        return f"{type_expr.name}[{', '.join(type_text(arg) for arg in type_expr.args)}]"
    if type_expr.kind == "union":
        return " | ".join(type_text(arg) for arg in type_expr.args)
    return type_expr.kind


def is_list_type(type_expr: TypeExpr) -> bool:
    return type_expr.kind == "generic" and type_expr.name == "list" and len(type_expr.args) == 1


def is_string_keyed_dict_type(type_expr: TypeExpr) -> bool:
    if type_expr.kind != "generic" or type_expr.name != "dict" or len(type_expr.args) != 2:
        return False
    key_type = type_expr.args[0]
    return key_type.kind == "named" and key_type.name == "str"
