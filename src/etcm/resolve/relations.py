from __future__ import annotations

import json
import math
import operator
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from etcm.ir import ComparisonConstraint, Expression, ParameterReference, TypeExpr

_SCALAR_TYPES = {"int", "float", "str", "bool", "null", "Path"}
_NUMERIC_TYPES = {"int", "float"}
_MAX_ABS_EXPONENT = 10_000


class RelationTypeError(ValueError):
    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class RelationEvaluationError(ValueError):
    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


def expression_references(expression: Expression) -> tuple[ParameterReference, ...]:
    references: list[ParameterReference] = []

    def visit(node: Expression) -> None:
        if node.kind == "reference":
            if node.reference is None:
                raise AssertionError("reference expression is missing its reference")
            references.append(node.reference)
        for operand in node.operands:
            visit(operand)

    visit(expression)
    return tuple(references)


def constraint_references(
    constraint: ComparisonConstraint,
) -> tuple[ParameterReference, ...]:
    return (*expression_references(constraint.left), *expression_references(constraint.right))


def infer_expression_type(
    expression: Expression,
    *,
    current_type: TypeExpr,
    reference_type: Callable[[ParameterReference], TypeExpr],
) -> TypeExpr:
    if expression.kind == "current":
        _scalar_names(current_type)
        return current_type
    if expression.kind == "reference":
        if expression.reference is None:
            raise AssertionError("reference expression is missing its reference")
        resolved = reference_type(expression.reference)
        _scalar_names(resolved)
        return resolved
    if expression.kind == "literal":
        if expression.literal is None:
            raise AssertionError("literal expression is missing its literal")
        name = {
            "int": "int",
            "float": "float",
            "string": "str",
            "bool": "bool",
            "null": "null",
        }.get(expression.literal.kind)
        if name is None:
            raise RelationTypeError(
                "Collection and object literals are not supported in parameter expressions.",
                details={"literal_kind": expression.literal.kind},
            )
        return TypeExpr(kind="named", name=name)
    if expression.kind == "unary":
        if expression.operator not in {"+", "-"} or len(expression.operands) != 1:
            raise AssertionError("invalid unary expression")
        operand_type = infer_expression_type(
            expression.operands[0],
            current_type=current_type,
            reference_type=reference_type,
        )
        names = _scalar_names(operand_type)
        _require_numeric(names, expression.operator)
        return _type_from_names(names)
    if expression.kind == "binary":
        if expression.operator is None or len(expression.operands) != 2:
            raise AssertionError("invalid binary expression")
        left_type = infer_expression_type(
            expression.operands[0],
            current_type=current_type,
            reference_type=reference_type,
        )
        right_type = infer_expression_type(
            expression.operands[1],
            current_type=current_type,
            reference_type=reference_type,
        )
        return _infer_binary_type(expression.operator, left_type, right_type)
    raise AssertionError(f"unsupported expression kind: {expression.kind}")


def validate_comparison_types(
    constraint: ComparisonConstraint,
    *,
    current_type: TypeExpr,
    reference_type: Callable[[ParameterReference], TypeExpr],
) -> None:
    left = infer_expression_type(
        constraint.left,
        current_type=current_type,
        reference_type=reference_type,
    )
    right = infer_expression_type(
        constraint.right,
        current_type=current_type,
        reference_type=reference_type,
    )
    left_names = _scalar_names(left)
    right_names = _scalar_names(right)
    if constraint.operator in {"<", "<=", ">", ">="}:
        _require_numeric(left_names, constraint.operator)
        _require_numeric(right_names, constraint.operator)
        return
    if constraint.operator not in {"==", "!="}:
        raise AssertionError(f"unsupported comparison operator: {constraint.operator}")
    if not _equality_compatible(left_names, right_names):
        raise RelationTypeError(
            f"Operator '{constraint.operator}' requires compatible scalar operands.",
            details={
                "operator": constraint.operator,
                "left_type": _type_text(left),
                "right_type": _type_text(right),
            },
        )


def type_assignable(actual: TypeExpr, expected: TypeExpr) -> bool:
    try:
        actual_names = _scalar_names(actual)
        expected_names = _scalar_names(expected)
    except RelationTypeError:
        return False
    for actual_name in actual_names:
        if not any(
            _name_assignable(actual_name, expected_name) for expected_name in expected_names
        ):
            return False
    return True


def evaluate_expression(
    expression: Expression,
    *,
    current_value: Any,
    reference_value: Callable[[ParameterReference], Any],
) -> Any:
    if expression.kind == "current":
        return _checked_expression_leaf(current_value)
    if expression.kind == "reference":
        if expression.reference is None:
            raise AssertionError("reference expression is missing its reference")
        return _checked_expression_leaf(reference_value(expression.reference))
    if expression.kind == "literal":
        if expression.literal is None:
            raise AssertionError("literal expression is missing its literal")
        return _checked_expression_leaf(expression.literal.value)
    if expression.kind == "unary":
        if expression.operator is None or len(expression.operands) != 1:
            raise AssertionError("invalid unary expression")
        value = evaluate_expression(
            expression.operands[0],
            current_value=current_value,
            reference_value=reference_value,
        )
        _runtime_number(value, expression.operator)
        result = +value if expression.operator == "+" else -value
        return _checked_numeric_result(result, expression.operator)
    if expression.kind == "binary":
        if expression.operator is None or len(expression.operands) != 2:
            raise AssertionError("invalid binary expression")
        left = evaluate_expression(
            expression.operands[0],
            current_value=current_value,
            reference_value=reference_value,
        )
        right = evaluate_expression(
            expression.operands[1],
            current_value=current_value,
            reference_value=reference_value,
        )
        return _evaluate_binary(expression.operator, left, right)
    raise AssertionError(f"unsupported expression kind: {expression.kind}")


def evaluate_comparison(operator_text: str, left: Any, right: Any) -> bool:
    operation = {
        "==": operator.eq,
        "!=": operator.ne,
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
    }.get(operator_text)
    if operation is None:
        raise AssertionError(f"unsupported comparison operator: {operator_text}")
    try:
        return bool(operation(left, right))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise RelationEvaluationError(
            f"Could not evaluate comparison operator '{operator_text}': {exc}",
            details={"operator": operator_text},
        ) from exc


def render_expression(
    expression: Expression,
    *,
    current_value: Any = None,
    reference_value: Callable[[ParameterReference], Any] | None = None,
    substitute_values: bool = False,
) -> str:
    return _render_expression(
        expression,
        current_value=current_value,
        reference_value=reference_value,
        substitute_values=substitute_values,
        parent_precedence=-1,
        side="root",
    )


def format_value(value: Any) -> str:
    if isinstance(value, Path):
        return value.as_posix()
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value)
    return str(value)


def _infer_binary_type(operator_text: str, left: TypeExpr, right: TypeExpr) -> TypeExpr:
    left_names = _scalar_names(left)
    right_names = _scalar_names(right)
    _require_numeric(left_names, operator_text)
    _require_numeric(right_names, operator_text)

    if operator_text == "%":
        if left_names != ("int",) or right_names != ("int",):
            raise RelationTypeError(
                "Operator '%' requires integer operands.",
                details={
                    "operator": operator_text,
                    "left_type": _type_text(left),
                    "right_type": _type_text(right),
                },
            )
        return TypeExpr(kind="named", name="int")
    if operator_text == "/":
        return TypeExpr(kind="named", name="float")
    if operator_text not in {"+", "-", "*", "//", "**"}:
        raise AssertionError(f"unsupported arithmetic operator: {operator_text}")

    results: list[str] = []
    for left_name in left_names:
        for right_name in right_names:
            result = "int"
            if left_name == "float" or right_name == "float":
                result = "float"
            if result not in results:
                results.append(result)
    return _type_from_names(tuple(results))


def _evaluate_binary(operator_text: str, left: Any, right: Any) -> Any:
    _runtime_number(left, operator_text)
    _runtime_number(right, operator_text)
    if operator_text == "%" and (type(left) is not int or type(right) is not int):
        raise RelationEvaluationError(
            "Operator '%' requires integer operands.",
            details={"operator": operator_text},
        )
    if operator_text == "**" and isinstance(right, int) and abs(right) > _MAX_ABS_EXPONENT:
        raise RelationEvaluationError(
            f"Exponent magnitude exceeds the ETCM limit of {_MAX_ABS_EXPONENT}.",
            details={"operator": operator_text, "exponent": right},
        )
    operation = {
        "+": operator.add,
        "-": operator.sub,
        "*": operator.mul,
        "/": operator.truediv,
        "//": operator.floordiv,
        "%": operator.mod,
        "**": operator.pow,
    }.get(operator_text)
    if operation is None:
        raise AssertionError(f"unsupported arithmetic operator: {operator_text}")
    try:
        result = operation(left, right)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise RelationEvaluationError(
            f"Could not evaluate arithmetic operator '{operator_text}': {exc}",
            details={"operator": operator_text, "left": left, "right": right},
        ) from exc
    return _checked_numeric_result(result, operator_text)


def _checked_numeric_result(value: Any, operator_text: str) -> int | float:
    if type(value) not in {int, float}:
        raise RelationEvaluationError(
            f"Operator '{operator_text}' produced unsupported value type "
            f"'{type(value).__name__}'.",
            details={"operator": operator_text, "result_type": type(value).__name__},
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise RelationEvaluationError(
            f"Operator '{operator_text}' produced a non-finite value.",
            details={"operator": operator_text, "result": str(value)},
        )
    return value


def _checked_expression_leaf(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise RelationEvaluationError(
            "Parameter expression contains a non-finite value.",
            details={"value": str(value)},
        )
    if value is None or type(value) in {int, float, str, bool} or isinstance(value, Path):
        return value
    raise RelationEvaluationError(
        f"Parameter expression contains unsupported value type '{type(value).__name__}'.",
        details={"actual_type": type(value).__name__},
    )


def _runtime_number(value: Any, operator_text: str) -> None:
    if type(value) not in {int, float}:
        raise RelationEvaluationError(
            f"Operator '{operator_text}' requires numeric operands, got "
            f"'{type(value).__name__}'.",
            details={"operator": operator_text, "actual_type": type(value).__name__},
        )


def _scalar_names(type_expr: TypeExpr) -> tuple[str, ...]:
    if type_expr.kind == "union":
        names: list[str] = []
        for option in type_expr.args:
            for name in _scalar_names(option):
                if name not in names:
                    names.append(name)
        return tuple(names)
    if type_expr.kind != "named" or type_expr.name not in _SCALAR_TYPES:
        raise RelationTypeError(
            "Parameter expressions require scalar leaf values.",
            details={"type": _type_text(type_expr)},
        )
    return (str(type_expr.name),)


def _require_numeric(names: Iterable[str], operator_text: str) -> None:
    names_tuple = tuple(names)
    if not names_tuple or any(name not in _NUMERIC_TYPES for name in names_tuple):
        raise RelationTypeError(
            f"Operator '{operator_text}' requires numeric operands.",
            details={"operator": operator_text, "actual_types": list(names_tuple)},
        )


def _equality_compatible(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    left_set = set(left)
    right_set = set(right)
    if left_set == {"null"}:
        return "null" in right_set
    if right_set == {"null"}:
        return "null" in left_set
    left_non_null = left_set - {"null"}
    right_non_null = right_set - {"null"}
    if not left_non_null or not right_non_null:
        return "null" in left_set and "null" in right_set
    if left_non_null <= _NUMERIC_TYPES and right_non_null <= _NUMERIC_TYPES:
        return True
    return left_non_null == right_non_null and len(left_non_null) == 1


def _name_assignable(actual: str, expected: str) -> bool:
    return actual == expected or (actual == "int" and expected == "float")


def _type_from_names(names: tuple[str, ...]) -> TypeExpr:
    if len(names) == 1:
        return TypeExpr(kind="named", name=names[0])
    return TypeExpr(
        kind="union",
        args=tuple(TypeExpr(kind="named", name=name) for name in names),
    )


def _type_text(type_expr: TypeExpr) -> str:
    if type_expr.kind == "named":
        return str(type_expr.name)
    if type_expr.kind == "union":
        return " | ".join(_type_text(option) for option in type_expr.args)
    if type_expr.kind == "generic":
        return f"{type_expr.name}[{', '.join(_type_text(arg) for arg in type_expr.args)}]"
    return type_expr.kind


def _render_expression(
    expression: Expression,
    *,
    current_value: Any,
    reference_value: Callable[[ParameterReference], Any] | None,
    substitute_values: bool,
    parent_precedence: int,
    side: str,
) -> str:
    if expression.kind == "current":
        return format_value(current_value) if substitute_values else "<current>"
    if expression.kind == "reference":
        if expression.reference is None:
            raise AssertionError("reference expression is missing its reference")
        if substitute_values:
            if reference_value is None:
                raise AssertionError("substituted rendering requires a reference resolver")
            return format_value(reference_value(expression.reference))
        return expression.reference.raw
    if expression.kind == "literal":
        if expression.literal is None:
            raise AssertionError("literal expression is missing its literal")
        return format_value(expression.literal.value)
    if expression.kind == "unary":
        if expression.operator is None or len(expression.operands) != 1:
            raise AssertionError("invalid unary expression")
        precedence = 3
        rendered = expression.operator + _render_expression(
            expression.operands[0],
            current_value=current_value,
            reference_value=reference_value,
            substitute_values=substitute_values,
            parent_precedence=precedence,
            side="right",
        )
        needs_parentheses = precedence < parent_precedence
        # Python gives exponentiation asymmetric precedence around unary
        # operators: ``-2 ** 2`` is unary-over-power, while ``(-2) ** 2``
        # requires grouping when the unary expression is the left operand.
        if side == "left" and parent_precedence == 2:
            needs_parentheses = True
        return f"({rendered})" if needs_parentheses else rendered
    if expression.kind != "binary" or expression.operator is None:
        raise AssertionError(f"unsupported expression kind: {expression.kind}")

    precedence = {"+": 0, "-": 0, "*": 1, "/": 1, "//": 1, "%": 1, "**": 2}[
        expression.operator
    ]
    left = _render_expression(
        expression.operands[0],
        current_value=current_value,
        reference_value=reference_value,
        substitute_values=substitute_values,
        parent_precedence=precedence,
        side="left",
    )
    right_parent = precedence if expression.operator == "**" else precedence + 1
    right = _render_expression(
        expression.operands[1],
        current_value=current_value,
        reference_value=reference_value,
        substitute_values=substitute_values,
        parent_precedence=right_parent,
        side="right",
    )
    rendered = f"{left} {expression.operator} {right}"
    needs_parentheses = precedence < parent_precedence
    if expression.operator == "**" and side == "left" and precedence == parent_precedence:
        needs_parentheses = True
    return f"({rendered})" if needs_parentheses else rendered


__all__ = [
    "RelationEvaluationError",
    "RelationTypeError",
    "constraint_references",
    "evaluate_comparison",
    "evaluate_expression",
    "expression_references",
    "format_value",
    "infer_expression_type",
    "render_expression",
    "type_assignable",
    "validate_comparison_types",
]
