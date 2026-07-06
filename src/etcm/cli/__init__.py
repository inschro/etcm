from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, cast

from etcm import Resolver
from etcm.codegen import ViewTarget
from etcm.errors import Diagnostic, ETCMError
from etcm.ir import Document, ImplDef
from etcm.resolve import PathExistsPolicy
from etcm.syntax import parse_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="etcm",
        description="Resolve, validate, and load ETCM configuration graphs.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subcommands.add_parser("resolve", help="print resolved graph JSON")
    _add_selector_argument(resolve_parser)
    _add_path_exists_argument(resolve_parser)
    resolve_parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        help="output format",
    )

    validate_parser = subcommands.add_parser("validate", help="print validated graph JSON")
    _add_selector_argument(validate_parser)
    _add_path_exists_argument(validate_parser)
    validate_parser.add_argument(
        "--short",
        action="store_true",
        help="print only a short success message",
    )
    validate_parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        help="output format",
    )

    validate_all_parser = subcommands.add_parser(
        "validate-all",
        help="validate all ETCM implementations under paths",
    )
    validate_all_parser.add_argument(
        "paths",
        nargs="*",
        help="ETCM files or directories to scan; defaults to the current directory",
    )
    _add_path_exists_argument(validate_all_parser)
    validate_all_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print one status line per discovered implementation",
    )
    validate_all_parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only the final summary",
    )
    validate_all_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format",
    )

    load_parser = subcommands.add_parser("load", help="print built config object JSON")
    _add_selector_argument(load_parser)
    _add_path_exists_argument(load_parser)
    load_parser.add_argument(
        "--target",
        choices=("dict", "dataclass", "pydantic"),
        default="dict",
        help="generated view target to build before serializing to JSON",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "resolve":
            return _cmd_resolve(args)
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "validate-all":
            return _cmd_validate_all(args)
        if args.command == "load":
            return _cmd_load(args)
    except ETCMError as exc:
        sys.stderr.write(f"{_format_diagnostic(exc.diagnostic)}\n")
        return 1

    parser.error(f"unknown command: {args.command}")


def _add_selector_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "selector",
        help="ETCM selector, such as configs/train.etcm#TrainRun:smoke",
    )


def _add_path_exists_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path-exists",
        choices=("allow_missing", "must_exist"),
        default="allow_missing",
        help="default Path existence policy for fields that delegate to the resolver",
    )


def _cmd_validate(args: argparse.Namespace) -> int:
    resolver = _resolver_from_args(args)
    graph = resolver.validate(resolver.resolve(str(args.selector)))
    if args.short:
        sys.stdout.write(f"OK: {graph.root_selector}\n")
    else:
        _write_json(graph.to_dict())
    return 0


def _cmd_validate_all(args: argparse.Namespace) -> int:
    resolver = _resolver_from_args(args)
    results = _validate_all_results(
        paths=tuple(Path(path) for path in args.paths) or (Path.cwd(),),
        resolver=resolver,
    )
    if args.format == "json":
        _write_json(_validate_all_json_payload(results))
    else:
        _write_validate_all_text(
            results,
            verbose=bool(args.verbose),
            quiet=bool(args.quiet),
        )
    return 1 if any(not result.ok for result in results) else 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    graph = _resolver_from_args(args).resolve(str(args.selector))
    _write_json(graph.to_dict())
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    target = cast(ViewTarget, args.target)
    loaded = _resolver_from_args(args).load(str(args.selector), target=target)
    _write_json(_loaded_json_payload(loaded))
    return 0


def _resolver_from_args(args: argparse.Namespace) -> Resolver:
    path_exists = cast(PathExistsPolicy, args.path_exists)
    return Resolver(path_exists=path_exists)


@dataclass(frozen=True)
class _ValidationResult:
    artifact: str
    ok: bool
    diagnostic: Diagnostic | None = None


def _validate_all_results(
    *,
    paths: tuple[Path, ...],
    resolver: Resolver,
) -> list[_ValidationResult]:
    results: list[_ValidationResult] = []
    existing_paths: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved.exists():
            existing_paths.append(resolved)
            continue
        results.append(
            _ValidationResult(
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
                _ValidationResult(
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
                    _ValidationResult(
                        artifact=selector,
                        ok=False,
                        diagnostic=exc.diagnostic,
                    )
                )
            else:
                results.append(_ValidationResult(artifact=selector, ok=True))
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
            return (
                f"{source.as_posix()}#{implementation.name}"
                for implementation in document.implementations
            )
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


def _write_validate_all_text(
    results: Sequence[_ValidationResult],
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
                    sys.stdout.write(f"{_format_diagnostic(result.diagnostic)}\n")
        elif failures:
            for result in failures:
                sys.stdout.write(f"FAIL: {result.artifact}\n")
                if result.diagnostic is not None:
                    sys.stdout.write(f"{_format_diagnostic(result.diagnostic)}\n")
    sys.stdout.write(f"{_validate_all_summary(results)}\n")


def _validate_all_summary(results: Sequence[_ValidationResult]) -> str:
    total = len(results)
    failures = sum(1 for result in results if not result.ok)
    return f"{total} total, {total - failures} OK, {failures} fail"


def _validate_all_json_payload(results: Sequence[_ValidationResult]) -> dict[str, Any]:
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


def _loaded_json_payload(value: object) -> Any:
    if isinstance(value, Mapping):
        return _json_compatible(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_compatible(asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_compatible(model_dump(mode="json"))
    return _json_compatible(value)


def _write_json(payload: Any) -> None:
    sys.stdout.write(f"{json.dumps(payload, indent=2)}\n")


def _format_diagnostic(diagnostic: Diagnostic) -> str:
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
    if diagnostic.details:
        lines.append(f"details: {json.dumps(_json_compatible(diagnostic.details), sort_keys=True)}")
    return "\n".join(lines)


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_compatible(item) for item in value]
    return value


__all__ = ["build_parser", "main"]
