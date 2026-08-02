from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn

from etcm.errors import Diagnostic, ETCMError
from etcm.ir import FieldDef, SourceSpan


def field_source_path(field: FieldDef, fallback: Path) -> Path:
    if field.span is not None:
        return field.span.source_path.resolve()
    return fallback


def raise_error(
    code: str,
    message: str,
    *,
    source_path: Path | None = None,
    span: SourceSpan | None = None,
    selector: str | None = None,
    graph_path: str | None = None,
    details: dict[str, Any] | None = None,
) -> NoReturn:
    raise ETCMError(
        Diagnostic(
            code=code,
            message=message,
            source_path=source_path,
            line=span.line if span is not None else None,
            column=span.column if span is not None else None,
            end_line=span.end_line if span is not None else None,
            end_column=span.end_column if span is not None else None,
            selector=selector,
            graph_path=graph_path,
            details=details,
        )
    )
