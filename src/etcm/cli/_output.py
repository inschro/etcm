from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, NoReturn

from etcm.cli._validate_all import ValidationResult
from etcm.errors import Diagnostic, ETCMError
from etcm.ir import TypeExpr
from etcm.resolve._files import (
    contains_file_type,
    file_leaf_codec,
    non_null_union_options,
    type_allows_null,
)
from etcm.resolve.graph import ResolvedGraph, ResolvedNode


def write_validate_all_text(
    results: Sequence[ValidationResult],
    *,
    verbose: bool,
    quiet: bool,
) -> None:
    failures = [result for result in results if not result.ok]
    if not quiet:
        if verbose:
            for result in results:
                status = "OK" if result.ok else "FAIL"
                sys.stdout.write(f"{status}: {result.artifact}\n")
                if result.diagnostic is not None:
                    sys.stdout.write(f"{format_diagnostic(result.diagnostic)}\n")
        elif failures:
            for result in failures:
                sys.stdout.write(f"FAIL: {result.artifact}\n")
                if result.diagnostic is not None:
                    sys.stdout.write(f"{format_diagnostic(result.diagnostic)}\n")
    sys.stdout.write(f"{_validate_all_summary(results)}\n")


def _validate_all_summary(results: Sequence[ValidationResult]) -> str:
    total = len(results)
    failures = sum(1 for result in results if not result.ok)
    return f"{total} total, {total - failures} OK, {failures} fail"


def validate_all_json_payload(results: Sequence[ValidationResult]) -> dict[str, Any]:
    total = len(results)
    failures = sum(1 for result in results if not result.ok)
    return {
        "total": total,
        "ok": total - failures,
        "fail": failures,
        "results": [
            {
                "artifact": result.artifact,
                "ok": result.ok,
                "diagnostic": _diagnostic_payload(result.diagnostic)
                if result.diagnostic is not None
                else None,
            }
            for result in results
        ],
    }


def _diagnostic_payload(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "source_path": diagnostic.source_path,
        "line": diagnostic.line,
        "column": diagnostic.column,
        "end_line": diagnostic.end_line,
        "end_column": diagnostic.end_column,
        "selector": diagnostic.selector,
        "graph_path": diagnostic.graph_path,
        "details": diagnostic.details,
    }


def loaded_json_payload(value: object, *, graph: ResolvedGraph | None = None) -> Any:
    try:
        if isinstance(value, Mapping):
            plain = value
        elif is_dataclass(value) and not isinstance(value, type):
            plain = asdict(value)
        else:
            model_dump = getattr(value, "model_dump", None)
            plain = model_dump(mode="python") if callable(model_dump) else value
        if graph is not None:
            return _graph_json_payload(plain, graph)
        return _json_compatible(plain)
    except (RecursionError, TypeError, ValueError) as exc:
        _raise_serialization("$", type(value).__name__, str(exc))


def write_json(payload: Any) -> None:
    problem = _json_problem(payload)
    if problem is not None:
        path, type_name, reason = problem
        _raise_serialization(path, type_name, reason)
    try:
        rendered = json.dumps(payload, indent=2, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        _raise_serialization("$", type(payload).__name__, str(exc))
    sys.stdout.write(f"{rendered}\n")


def format_diagnostic(diagnostic: Diagnostic) -> str:
    lines = [f"{diagnostic.code}: {diagnostic.message}"]
    if diagnostic.source_path is not None:
        location = diagnostic.source_path.as_posix()
        if diagnostic.line is not None:
            location = f"{location}:{diagnostic.line}"
            if diagnostic.column is not None:
                location = f"{location}:{diagnostic.column}"
        lines.append(f"source: {location}")
    if diagnostic.selector is not None:
        lines.append(f"selector: {diagnostic.selector}")
    if diagnostic.graph_path is not None:
        lines.append(f"graph_path: {diagnostic.graph_path}")
    details = dict(diagnostic.details or {})
    expression = details.get("expression")
    if diagnostic.code == "E_DERIVED_ASSIGNMENT" and isinstance(expression, str):
        lines.extend(["", "defined as:", f"  {expression}"])
        return "\n".join(lines)
    assertion = details.get("assertion")
    resolved_values = details.get("resolved_values")
    evaluation = details.get("evaluation")
    if (
        isinstance(assertion, str)
        and isinstance(expression, str)
        and isinstance(resolved_values, Mapping)
    ):
        lines.extend(
            [
                "",
                "assertion:",
                f"  {assertion}",
                "",
                "failed expression:",
                f"  {expression}",
                "",
                "resolved values:",
            ]
        )
        for name, value in resolved_values.items():
            rendered = json.dumps(_json_compatible(value), sort_keys=True)
            lines.append(f"  {name}: {rendered}")
        if isinstance(evaluation, Sequence) and not isinstance(evaluation, str):
            lines.extend(["", "evaluation:"])
            lines.extend(f"  {item}" for item in evaluation)
        return "\n".join(lines)
    constraint = details.get("constraint")
    if isinstance(constraint, str) and isinstance(resolved_values, Mapping):
        lines.extend(["", "constraint:", f"  {constraint}", "", "resolved values:"])
        for name, value in resolved_values.items():
            rendered = json.dumps(_json_compatible(value), sort_keys=True)
            lines.append(f"  {name}: {rendered}")
        if isinstance(evaluation, Sequence) and not isinstance(evaluation, str):
            lines.extend(["", "evaluation:"])
            lines.extend(f"  {item}" for item in evaluation)
        return "\n".join(lines)
    if details:
        lines.append(f"details: {json.dumps(_json_compatible(details), sort_keys=True)}")
    return "\n".join(lines)


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_compatible(item) for item in value]
    return value


def _graph_json_payload(value: Any, graph: ResolvedGraph) -> Any:
    nodes = {node.id: node for node in graph.nodes}
    ref_targets: dict[tuple[str, str], str] = {}
    for edge in graph.edges:
        if edge.kind == "ref" and len(edge.field_path) == 1:
            ref_targets[(edge.source, edge.field_path[0])] = edge.target
    for node in graph.nodes:
        for field_name, field_value in node.field_values.items():
            if field_value.ref_target is not None:
                ref_targets[(node.id, field_name)] = field_value.ref_target

    def node_payload(node_value: Any, node: ResolvedNode) -> Any:
        if not isinstance(node_value, Mapping):
            return _json_compatible(node_value)
        result: dict[str, Any] = {}
        for field_name, item in node_value.items():
            field = node.fields.get(field_name)
            if field is None:
                result[str(field_name)] = _json_compatible(item)
                continue
            target = ref_targets.get((node.id, field_name))
            if target is not None:
                result[field_name] = node_payload(item, nodes[target])
            else:
                result[field_name] = _typed_json_value(item, field.type_expr)
        return result

    root = nodes.get("root")
    return node_payload(value, root) if root is not None else _json_compatible(value)


def _typed_json_value(value: Any, type_expr: TypeExpr) -> Any:
    codec = file_leaf_codec(type_expr)
    if codec is not None:
        if codec == "bytes":
            return None
        return value
    if type_expr.kind == "union" and contains_file_type(type_expr):
        if value is None and type_allows_null(type_expr):
            return None
        non_null = non_null_union_options(type_expr)
        if len(non_null) == 1:
            return _typed_json_value(value, non_null[0])
        return value
    if (
        type_expr.kind == "generic"
        and type_expr.name == "list"
        and len(type_expr.args) == 1
        and isinstance(value, list)
        and contains_file_type(type_expr)
    ):
        return [_typed_json_value(item, type_expr.args[0]) for item in value]
    if (
        type_expr.kind == "generic"
        and type_expr.name == "dict"
        and len(type_expr.args) == 2
        and isinstance(value, Mapping)
        and contains_file_type(type_expr)
    ):
        return {
            str(key): _typed_json_value(item, type_expr.args[1])
            for key, item in value.items()
        }
    return _json_compatible(value)


def _json_problem(
    value: Any,
    path: str = "$",
    active: set[int] | None = None,
) -> tuple[str, str, str] | None:
    if value is None or isinstance(value, str | bool | int):
        return None
    if isinstance(value, float):
        if math.isfinite(value):
            return None
        return (path, "float", "non-finite numbers are not valid JSON")

    if active is None:
        active = set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            return (path, type(value).__name__, "cyclic values are not valid JSON")
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    return (
                        path,
                        type(key).__name__,
                        "JSON object keys must be strings",
                    )
                problem = _json_problem(item, f"{path}.{key}", active)
                if problem is not None:
                    return problem
        finally:
            active.remove(identity)
        return None
    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            return (path, "list", "cyclic values are not valid JSON")
        active.add(identity)
        try:
            for index, item in enumerate(value):
                problem = _json_problem(item, f"{path}[{index}]", active)
                if problem is not None:
                    return problem
        finally:
            active.remove(identity)
        return None
    return (path, type(value).__name__, "value is not JSON-serializable")


def _raise_serialization(path: str, type_name: str, reason: str) -> NoReturn:
    raise ETCMError(
        Diagnostic(
            code="E_SERIALIZATION",
            message=f"Could not serialize value at '{path}' as JSON.",
            details={"path": path, "type": type_name, "reason": reason},
        )
    )
