from __future__ import annotations

from pathlib import Path
from typing import Any

from etcm.syntax._source import raise_syntax_error
from etcm.syntax.ast import (
    SyntaxAssignment,
    SyntaxDocument,
    SyntaxField,
    SyntaxImpl,
    SyntaxItem,
    SyntaxRefAssignment,
    SyntaxSpec,
    SyntaxSpecRef,
)


def validate_document(document: SyntaxDocument) -> None:
    specs = [item for item in document.items if isinstance(item, SyntaxSpec)]
    spec_refs = [item for item in document.items if isinstance(item, SyntaxSpecRef)]

    seen_specs: dict[str, SyntaxSpec] = {}
    for spec in specs:
        previous = seen_specs.get(spec.name)
        if previous is not None:
            raise_syntax_error(
                "E_DUPLICATE_SPEC",
                f"Duplicate spec definition '{spec.name}'.",
                document.source_path,
                spec.span,
                details={"previous": previous.name},
            )
        seen_specs[spec.name] = spec

    if specs and any(isinstance(item, SyntaxImpl) for item in document.items):
        raise_syntax_error(
            "E_DUPLICATE_IMPL",
            "Top-level implementations require top-level $spec.",
            document.source_path,
            next(item.span for item in document.items if isinstance(item, SyntaxImpl)),
        )

    if specs and spec_refs:
        second = _second_of(document.items, SyntaxSpec, SyntaxSpecRef)
        raise_syntax_error(
            "E_SPEC_AND_SPEC_REF",
            "Document may define either inline spec or top-level $spec, not both.",
            document.source_path,
            second.span,
        )

    for spec in specs:
        _validate_fields(document.source_path, spec)
        _validate_impl_group(document.source_path, spec.implementations)

    _validate_implementations(document)


def _validate_fields(source_path: Path, spec: SyntaxSpec) -> None:
    _validate_field_group(source_path, spec.name, spec.fields)


def _validate_field_group(
    source_path: Path,
    owner_name: str,
    fields: tuple[SyntaxField, ...],
) -> None:
    seen: dict[str, SyntaxField] = {}
    for field in fields:
        previous = seen.get(field.name)
        if previous is not None:
            raise_syntax_error(
                "E_DUPLICATE_FIELD",
                f"Duplicate field '{field.name}' in spec '{owner_name}'.",
                source_path,
                field.span,
                details={
                    "previous_line": previous.span.line if previous.span is not None else None
                },
            )
        seen[field.name] = field
        if field.fields:
            _validate_field_group(source_path, f"{owner_name}.{field.name}", field.fields)


def _validate_implementations(document: SyntaxDocument) -> None:
    if any(isinstance(item, SyntaxSpecRef) for item in document.items):
        _validate_impl_group(
            document.source_path,
            tuple(item for item in document.items if isinstance(item, SyntaxImpl)),
        )


def _validate_impl_group(
    source_path: Path,
    implementations: tuple[SyntaxImpl, ...],
) -> None:
    seen: dict[str, SyntaxImpl] = {}
    for impl in implementations:
        previous = seen.get(impl.name)
        if previous is not None:
            raise_syntax_error(
                "E_DUPLICATE_IMPL",
                f"Duplicate implementation '{impl.name}'.",
                source_path,
                impl.span,
                details={
                    "previous_line": previous.span.line if previous.span is not None else None
                },
            )
        seen[impl.name] = impl

    for impl in implementations:
        _validate_assignment_group(source_path, impl)


def _validate_assignment_group(source_path: Path, impl: SyntaxImpl) -> None:
    seen: dict[tuple[str, ...], SyntaxAssignment | SyntaxRefAssignment] = {}
    for assignment in impl.assignments:
        path = assignment.field_path
        previous = seen.get(path)
        canonical_path = ".".join(path)
        if previous is not None:
            raise_syntax_error(
                "E_DUPLICATE_ASSIGNMENT",
                f"Duplicate assignment to '{canonical_path}' in implementation "
                f"'{impl.name}'.",
                source_path,
                assignment.span,
                details={
                    "field_path": canonical_path,
                    "previous_line": previous.span.line
                    if previous.span is not None
                    else None,
                },
            )

        for previous_path, previous_assignment in seen.items():
            if _path_is_prefix(previous_path, path) or _path_is_prefix(path, previous_path):
                previous_text = ".".join(previous_path)
                raise_syntax_error(
                    "E_ASSIGNMENT_PATH_CONFLICT",
                    f"Assignments to '{previous_text}' and '{canonical_path}' conflict "
                    f"in implementation '{impl.name}'.",
                    source_path,
                    assignment.span,
                    details={
                        "field_path": canonical_path,
                        "conflicting_path": previous_text,
                        "previous_line": previous_assignment.span.line
                        if previous_assignment.span is not None
                        else None,
                    },
                )
        seen[path] = assignment


def _path_is_prefix(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return len(left) < len(right) and right[: len(left)] == left


def _second_of(items: tuple[SyntaxItem, ...], left: type[Any], right: type[Any]) -> Any:
    seen = False
    for item in items:
        if isinstance(item, left | right):
            if seen:
                return item
            seen = True
    raise AssertionError("expected two matching items")
