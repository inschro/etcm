from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from etcm.cli._validate_all import ValidationResult
from etcm.errors import Diagnostic


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


def loaded_json_payload(value: object) -> Any:
    if isinstance(value, Mapping):
        return _json_compatible(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_compatible(asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_compatible(model_dump(mode="json"))
    return _json_compatible(value)


def write_json(payload: Any) -> None:
    sys.stdout.write(f"{json.dumps(payload, indent=2)}\n")


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
    constraint = details.get("constraint")
    resolved_values = details.get("resolved_values")
    evaluation = details.get("evaluation")
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
