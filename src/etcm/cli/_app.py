from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from etcm._contracts import PathExistsPolicy, ViewTarget
from etcm.cli._output import (
    format_diagnostic,
    loaded_json_payload,
    validate_all_json_payload,
    write_json,
    write_validate_all_text,
)
from etcm.cli._validate_all import validate_all_results
from etcm.errors import ETCMError
from etcm.resolve import Resolver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="etcm",
        description="Resolve, validate, and load ETCM configuration graphs.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subcommands.add_parser("resolve", help="print resolved graph JSON")
    _add_selector_argument(resolve_parser)
    _add_path_exists_argument(resolve_parser)
    _add_override_arguments(resolve_parser)
    resolve_parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        help="output format",
    )

    validate_parser = subcommands.add_parser("validate", help="print validated graph JSON")
    _add_selector_argument(validate_parser)
    _add_path_exists_argument(validate_parser)
    _add_override_arguments(validate_parser)
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
    _add_override_arguments(load_parser)
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
        sys.stderr.write(f"{format_diagnostic(exc.diagnostic)}\n")
        return 1
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

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


def _add_override_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help="override a field using a dot-separated path; may be repeated",
    )
    parser.add_argument(
        "--force-overrides",
        action="store_true",
        help="authorize external overrides of fields marked force_only",
    )
    parser.add_argument(
        "--override-base",
        type=Path,
        help=(
            "base directory for relative Path/File values and explicit "
            "selector paths"
        ),
    )


def _cmd_validate(args: argparse.Namespace) -> int:
    resolver = _resolver_from_args(args)
    graph = resolver.validate(
        resolver.resolve(
            str(args.selector),
            overrides=args.overrides,
            force_overrides=bool(args.force_overrides),
            override_base=args.override_base,
        )
    )
    if args.short:
        sys.stdout.write(f"OK: {graph.root_selector}\n")
    else:
        write_json(graph.to_dict())
    return 0


def _cmd_validate_all(args: argparse.Namespace) -> int:
    resolver = _resolver_from_args(args)
    results = validate_all_results(
        paths=tuple(Path(path) for path in args.paths) or (Path.cwd(),),
        resolver=resolver,
    )
    if args.format == "json":
        write_json(validate_all_json_payload(results))
    else:
        write_validate_all_text(
            results,
            verbose=bool(args.verbose),
            quiet=bool(args.quiet),
        )
    return 1 if any(not result.ok for result in results) else 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    graph = _resolver_from_args(args).resolve(
        str(args.selector),
        overrides=args.overrides,
        force_overrides=bool(args.force_overrides),
        override_base=args.override_base,
    )
    write_json(graph.to_dict())
    return 0


def _cmd_load(args: argparse.Namespace) -> int:
    target = cast(ViewTarget, args.target)
    resolver = _resolver_from_args(args)
    graph = resolver.validate(
        resolver.resolve(
            str(args.selector),
            overrides=args.overrides,
            force_overrides=bool(args.force_overrides),
            override_base=args.override_base,
        )
    )
    loaded = resolver.convert(graph, target=target)
    write_json(loaded_json_payload(loaded, graph=graph))
    return 0


def _resolver_from_args(args: argparse.Namespace) -> Resolver:
    path_exists = cast(PathExistsPolicy, args.path_exists)
    return Resolver(path_exists=path_exists)


__all__ = ["build_parser", "main"]
