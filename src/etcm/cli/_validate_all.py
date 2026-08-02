from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from etcm.errors import Diagnostic, ETCMError
from etcm.ir import Document, ImplDef
from etcm.resolve import Resolver
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

    for source_path in _discover_etcm_files(tuple(existing_paths)):
        try:
            document = parse_file(source_path)
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
                resolver.validate(resolver.resolve(selector))
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


def _discover_etcm_files(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    files: dict[Path, None] = {}
    for path in paths:
        resolved = path.resolve()
        if resolved.is_dir():
            for file_path in sorted(resolved.rglob("*.etcm")):
                if file_path.is_file():
                    files[file_path.resolve()] = None
        elif resolved.is_file() and resolved.suffix == ".etcm":
            files[resolved] = None
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
