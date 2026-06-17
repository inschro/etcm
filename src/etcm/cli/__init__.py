from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, cast

from etcm import Resolver
from etcm.codegen import ViewTarget
from etcm.errors import Diagnostic, ETCMError
from etcm.resolve import PathExistsPolicy


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
        if args.command == "load":
            return _cmd_load(args)
    except ETCMError as exc:
        sys.stderr.write(f"{_format_diagnostic(exc.diagnostic)}\n")
        return 1

    parser.error(f"unknown command: {args.command}")


def _add_selector_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("selector", help="ETCM selector, such as configs/train.etcm#smoke")


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
