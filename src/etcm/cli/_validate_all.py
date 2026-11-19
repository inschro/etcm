from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from itertools import batched, repeat
from pathlib import Path
from typing import Any

from etcm._contracts import PathExistsPolicy
from etcm.errors import Diagnostic, ETCMError
from etcm.ir import Document, ImplDef
from etcm.resolve import Resolver
from etcm.resolve._engine import _ResolverState
from etcm.syntax import parse_file


@dataclass(frozen=True)
class ValidationResult:
    artifact: str
    ok: bool
    diagnostic: Diagnostic | None = None


def validate_all_results(
    *,
    paths: tuple[Path, ...],
    resolver: Resolver,
    jobs: int = 1,
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    existing_paths: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved.exists():
            existing_paths.append(resolved)
            continue
        results.append(
            ValidationResult(
                artifact=path.as_posix(),
                ok=False,
                diagnostic=Diagnostic(
                    code="E_MISSING_SELECTOR",
                    message=f"Validation path does not exist: {path}",
                    source_path=resolved,
                ),
            )
        )

    files = _discover_etcm_files(tuple(existing_paths))
    workers = min(jobs, len(files))
    if sys.platform == "win32":
        workers = min(workers, 61)  # ProcessPoolExecutor's Windows limit.
    if workers <= 1:
        results.extend(_validate_files(files, resolver))
        return results

    from concurrent.futures import ProcessPoolExecutor

    group_size = (len(files) + workers - 1) // workers
    groups = tuple(batched(files, group_size))
    with ProcessPoolExecutor(max_workers=len(groups)) as pool:
        for rows in pool.map(_validate_group, groups, repeat(resolver.path_exists)):
            results.extend(
                ValidationResult(
                    artifact, ok, Diagnostic(**payload) if payload is not None else None
                )
                for artifact, ok, payload in rows
            )
    return results


def _validate_files(files: tuple[Path, ...], resolver: Resolver) -> list[ValidationResult]:
    document_loader = cache(parse_file)
    results: list[ValidationResult] = []
    for source_path in files:
        try:
            document = document_loader(source_path)
            selectors = tuple(_document_selectors(document))
        except ETCMError as exc:
            results.append(
                ValidationResult(
                    artifact=source_path.as_posix(),
                    ok=False,
                    diagnostic=exc.diagnostic,
                )
            )
            continue

        for selector in selectors:
            try:
                state = _ResolverState(resolver, document_loader=document_loader)
                resolver.validate(state.resolve(selector))
            except ETCMError as exc:
                results.append(
                    ValidationResult(
                        artifact=selector,
                        ok=False,
                        diagnostic=exc.diagnostic,
                    )
                )
            else:
                results.append(ValidationResult(artifact=selector, ok=True))
    return results


def _validate_group(
    files: tuple[Path, ...], path_exists: PathExistsPolicy
) -> list[tuple[str, bool, dict[str, Any] | None]]:
    return [
        (result.artifact, result.ok, diagnostic_payload(result.diagnostic))
        for result in _validate_files(files, Resolver(path_exists=path_exists))
    ]


def diagnostic_payload(diagnostic: Diagnostic | None) -> dict[str, Any] | None:
    if diagnostic is None:
        return None
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
        "details": dict(diagnostic.details) if diagnostic.details is not None else None,
    }


def _discover_etcm_files(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            for file_path in path.rglob("*.etcm"):
                if file_path.is_file():
                    files.add(file_path.resolve())
        elif path.is_file() and path.suffix == ".etcm":
            files.add(path)
    return tuple(sorted(files))


def _document_selectors(document: Document) -> Iterable[str]:
    source = document.source_path.resolve()
    if document.spec_ref is not None:
        spec_name = document.spec_ref.selector.spec
        if spec_name is None:
            raise AssertionError("$spec selector is missing its spec name")
        return (
            _selector_text(source, spec_name, implementation)
            for implementation in document.implementations
        )
    return (
        _selector_text(source, spec.name, implementation)
        for spec in document.specs
        for implementation in spec.implementations
    )


def _selector_text(source_path: Path, spec_name: str, implementation: ImplDef) -> str:
    return f"{source_path.as_posix()}#{spec_name}:{implementation.name}"
