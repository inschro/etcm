from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, NoReturn, cast

from ruamel.yaml import YAML

from etcm.ir import SourceSpan, TypeExpr
from etcm.resolve._diagnostics import raise_error

FileCodec = Literal["bytes", "json", "str", "yaml"]

_FILE_CODECS = frozenset({"bytes", "json", "str", "yaml"})
_WRAPPED_ONLY_CODECS = frozenset({"bytes", "json", "yaml"})
_FILE_TYPE = "File"


@dataclass(frozen=True)
class StagedFile:
    raw_value: Any
    literal_kind: str
    original: str | None
    resolved_path: Path | None
    codec: FileCodec
    source_path: Path
    span: SourceSpan | None


class FileTypeError(ValueError):
    def __init__(self, message: str, *, reason: str, details: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = dict(details)


def contains_file_type(type_expr: TypeExpr) -> bool:
    if type_expr.name == _FILE_TYPE and type_expr.kind in {"named", "generic"}:
        return True
    return any(contains_file_type(arg) for arg in type_expr.args)


def file_leaf_codec(type_expr: TypeExpr) -> FileCodec | None:
    if type_expr.kind == "generic" and type_expr.name == _FILE_TYPE:
        if len(type_expr.args) != 1:
            return None
        return _codec_name(type_expr.args[0])
    if type_expr.kind == "union" and type_allows_null(type_expr):
        non_null = non_null_union_options(type_expr)
        if len(non_null) == 1:
            return file_leaf_codec(non_null[0])
    return None


def type_allows_null(type_expr: TypeExpr) -> bool:
    return type_expr.kind == "union" and any(
        option.kind == "named" and option.name == "null" for option in type_expr.args
    )


def non_null_union_options(type_expr: TypeExpr) -> tuple[TypeExpr, ...]:
    if type_expr.kind != "union":
        return ()
    return tuple(
        option
        for option in type_expr.args
        if not (option.kind == "named" and option.name == "null")
    )


def validate_file_type(type_expr: TypeExpr) -> None:
    standalone = _standalone_codecs(type_expr)
    if standalone:
        replacement = _file_migration_type(type_expr)
        if replacement is not None:
            hint = f"Use {replacement}."
        elif len(standalone) == 1:
            codec = standalone[0]
            hint = f"Use File[{codec}] for a file-backed {codec.upper()} value."
        else:
            choices = " or ".join(f"File[{codec}]" for codec in standalone)
            hint = f"Choose one explicit file codec, such as {choices}."
        raise FileTypeError(
            f"Codec '{standalone[0]}' must be wrapped in File[...].",
            reason="codec_requires_file",
            details={
                "type": type_text(type_expr),
                "codec": standalone[0],
                "codecs": list(standalone),
                "hint": hint,
            },
        )
    _validate_file_type(type_expr, position="value")


def _validate_file_type(type_expr: TypeExpr, *, position: str) -> None:
    if type_expr.kind == "named" and type_expr.name == _FILE_TYPE:
        raise FileTypeError(
            "File must declare exactly one codec argument.",
            reason="invalid_file_type",
            details={
                "type": type_text(type_expr),
                "hint": "Use File[str], File[bytes], File[json], or File[yaml].",
            },
        )

    if type_expr.kind == "generic" and type_expr.name == _FILE_TYPE:
        if position == "key":
            raise FileTypeError(
                "File types cannot be dictionary key types.",
                reason="file_dictionary_key",
                details={"type": type_text(type_expr)},
            )
        if len(type_expr.args) != 1:
            raise FileTypeError(
                "File must declare exactly one codec argument.",
                reason="invalid_file_type",
                details={
                    "type": type_text(type_expr),
                    "hint": (
                        "Use one exact codec argument, such as File[str], File[bytes], "
                        "File[json], or File[yaml]."
                    ),
                },
            )
        codec_type = type_expr.args[0]
        if codec_type.kind == "union":
            hint = _file_codec_union_hint(codec_type)
            raise FileTypeError(
                "File codec unions are not supported; declare one exact codec.",
                reason="file_codec_union",
                details={
                    "type": type_text(type_expr),
                    "codec_type": type_text(codec_type),
                    "alternatives": [type_text(option) for option in codec_type.args],
                    "supported_codecs": sorted(_FILE_CODECS),
                    "hint": hint,
                },
            )
        if _codec_name(codec_type) is None:
            hint = "Supported exact codecs are str, bytes, json, and yaml."
            raise FileTypeError(
                f"Unsupported File codec type '{type_text(codec_type)}'.",
                reason="unsupported_file_codec",
                details={
                    "type": type_text(type_expr),
                    "codec_type": type_text(codec_type),
                    "supported_codecs": sorted(_FILE_CODECS),
                    "hint": hint,
                },
            )
        return

    if not contains_file_type(type_expr):
        return

    if type_expr.kind == "union":
        non_null = non_null_union_options(type_expr)
        if type_allows_null(type_expr) and len(non_null) == 1:
            _validate_file_type(non_null[0], position=position)
            return
        raise FileTypeError(
            "File value unions are not supported; a file type may only share a union "
            "with null.",
            reason="file_value_union",
            details={
                "type": type_text(type_expr),
                "hint": (
                    "Choose one exact File[...] type. Only null may be added outside it, "
                    "such as File[json] | null."
                ),
            },
        )

    if type_expr.kind == "generic" and type_expr.name == "list" and len(type_expr.args) == 1:
        _validate_file_type(type_expr.args[0], position=position)
        return

    if type_expr.kind == "generic" and type_expr.name == "dict" and len(type_expr.args) == 2:
        _validate_file_type(type_expr.args[0], position="key")
        _validate_file_type(type_expr.args[1], position=position)
        return

    raise FileTypeError(
        "File types are supported only as fields, list items, or dictionary values.",
        reason="unsupported_file_container",
        details={"type": type_text(type_expr)},
    )


def _codec_name(type_expr: TypeExpr) -> FileCodec | None:
    if type_expr.kind == "named" and type_expr.name in _FILE_CODECS:
        return cast(FileCodec, type_expr.name)
    return None


def _standalone_codecs(type_expr: TypeExpr) -> tuple[str, ...]:
    if type_expr.kind == "named" and type_expr.name in _WRAPPED_ONLY_CODECS:
        return (str(type_expr.name),)
    if type_expr.kind == "generic" and type_expr.name == _FILE_TYPE:
        return ()
    codecs: list[str] = []
    for arg in type_expr.args:
        for codec in _standalone_codecs(arg):
            if codec not in codecs:
                codecs.append(codec)
    return tuple(codecs)


def _file_migration_type(type_expr: TypeExpr) -> str | None:
    if type_expr.kind == "named" and type_expr.name in _WRAPPED_ONLY_CODECS:
        return f"File[{type_expr.name}]"

    if type_expr.kind == "union":
        non_null = non_null_union_options(type_expr)
        has_null = len(non_null) != len(type_expr.args)
        if has_null and len(non_null) == 1:
            migrated = _file_migration_type(non_null[0])
            return f"{migrated} | null" if migrated is not None else None
        return None

    if type_expr.kind == "generic" and type_expr.name == "list" and len(type_expr.args) == 1:
        item = _file_migration_type(type_expr.args[0])
        return f"list[{item}]" if item is not None else None

    if type_expr.kind == "generic" and type_expr.name == "dict" and len(type_expr.args) == 2:
        key_type, value_type = type_expr.args
        if _standalone_codecs(key_type):
            return None
        value = _file_migration_type(value_type)
        return f"dict[{type_text(key_type)}, {value}]" if value is not None else None

    return None


def _file_codec_union_hint(codec_type: TypeExpr) -> str:
    non_null = non_null_union_options(codec_type)
    if type_allows_null(codec_type) and len(non_null) == 1:
        codec = _codec_name(non_null[0])
        if codec is not None:
            return f"Move null outside the file type: File[{codec}] | null."

    codecs = tuple(
        codec
        for option in codec_type.args
        if (codec := _codec_name(option)) is not None
    )
    if len(codecs) >= 2:
        choices = " or ".join(f"File[{codec}]" for codec in codecs)
        return f"Choose one explicit codec: {choices}."
    return "Choose exactly one of File[str], File[bytes], File[json], or File[yaml]."


def type_text(type_expr: TypeExpr) -> str:
    if type_expr.kind == "named":
        return str(type_expr.name)
    if type_expr.kind == "generic":
        return f"{type_expr.name}[{', '.join(type_text(arg) for arg in type_expr.args)}]"
    if type_expr.kind == "union":
        return " | ".join(type_text(arg) for arg in type_expr.args)
    return type_expr.kind


def stage_file(
    *,
    raw_value: Any,
    literal_kind: str,
    codec: FileCodec,
    source_path: Path,
    span: SourceSpan | None,
    value_base: Path | None,
) -> StagedFile:
    original = raw_value if isinstance(raw_value, str) else None
    resolved_path = None
    if original is not None:
        raw_path = Path(original)
        base = source_path.parent if value_base is None else value_base
        resolved_path = (
            raw_path.resolve() if raw_path.is_absolute() else (base / raw_path).resolve()
        )
    return StagedFile(
        raw_value=raw_value,
        literal_kind=literal_kind,
        original=original,
        resolved_path=resolved_path,
        codec=codec,
        source_path=source_path,
        span=span,
    )


def unstage_files(value: Any) -> Any:
    if isinstance(value, StagedFile):
        return value.raw_value
    if isinstance(value, Mapping):
        return {key: unstage_files(item) for key, item in value.items()}
    if isinstance(value, list):
        return [unstage_files(item) for item in value]
    if isinstance(value, tuple):
        return tuple(unstage_files(item) for item in value)
    return value


class FileLoader:
    def __init__(self) -> None:
        self._bytes: dict[Path, bytes] = {}
        self._decoded: dict[tuple[Path, FileCodec], Any] = {}

    def materialize(self, value: Any, type_expr: TypeExpr, *, graph_path: str) -> Any:
        codec = file_leaf_codec(type_expr)
        if codec is not None:
            if value is None and type_allows_null(type_expr):
                return None
            if not isinstance(value, StagedFile):
                self._raise_input_type(value, type_expr, graph_path)
            return self._load(value, graph_path)

        if type_expr.kind == "union" and contains_file_type(type_expr):
            if value is None and type_allows_null(type_expr):
                return None
            non_null = non_null_union_options(type_expr)
            if len(non_null) != 1:
                raise AssertionError("file union was not validated")
            return self.materialize(value, non_null[0], graph_path=graph_path)

        if (
            type_expr.kind == "generic"
            and type_expr.name == "list"
            and len(type_expr.args) == 1
            and contains_file_type(type_expr)
        ):
            if not isinstance(value, list):
                return value
            return [
                self.materialize(
                    item,
                    type_expr.args[0],
                    graph_path=f"{graph_path}[{index}]",
                )
                for index, item in enumerate(value)
            ]

        if (
            type_expr.kind == "generic"
            and type_expr.name == "dict"
            and len(type_expr.args) == 2
            and contains_file_type(type_expr)
        ):
            if not isinstance(value, Mapping):
                return value
            return {
                key: self.materialize(
                    item,
                    type_expr.args[1],
                    graph_path=f"{graph_path}.{key}",
                )
                for key, item in value.items()
            }

        return value

    def _load(self, staged: StagedFile, graph_path: str) -> Any:
        if staged.original is None or staged.resolved_path is None:
            self._raise_input_type(staged.raw_value, None, graph_path, staged=staged)
        path = staged.resolved_path
        file_codec = staged.codec
        key = (path, file_codec)
        if key not in self._decoded:
            raw = self._read(staged, graph_path, file_codec)
            if file_codec == "bytes":
                decoded: Any = raw
            elif file_codec == "str":
                try:
                    decoded = raw.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise_error(
                        "E_FILE_LOAD",
                        f"Could not decode file '{staged.original}' as UTF-8 text.",
                        source_path=staged.source_path,
                        span=staged.span,
                        graph_path=graph_path,
                        details={
                            **self._details(staged, graph_path),
                            "codec": file_codec,
                            "reason": "decode_error",
                            "encoding": "utf-8",
                            "decoder_error": str(exc),
                            "byte_start": exc.start,
                            "byte_end": exc.end,
                        },
                    )
            else:
                try:
                    if file_codec == "json":
                        decoded = json.loads(raw)
                    else:
                        parser = YAML(typ="safe", pure=True)
                        parser.version = (1, 2)
                        decoded = parser.load(BytesIO(raw))
                except Exception as exc:
                    line, column = _parser_location(exc)
                    details: dict[str, Any] = {
                        **self._details(staged, graph_path),
                        "codec": file_codec,
                        "reason": "parse_error",
                        "parser_error": _parser_message(exc),
                    }
                    if line is not None:
                        details["file_line"] = line
                    if column is not None:
                        details["file_column"] = column
                    raise_error(
                        "E_FILE_LOAD",
                        f"Could not decode file '{staged.original}' as {file_codec}.",
                        source_path=staged.source_path,
                        span=staged.span,
                        graph_path=graph_path,
                        details=details,
                    )
            self._decoded[key] = decoded
        return copy.deepcopy(self._decoded[key])

    def _read(
        self,
        staged: StagedFile,
        graph_path: str,
        file_codec: FileCodec,
    ) -> bytes:
        if staged.resolved_path is None:
            raise AssertionError("staged file path is missing")
        path = staged.resolved_path
        cached = self._bytes.get(path)
        if cached is not None:
            return cached
        if not path.exists():
            self._raise_load(
                staged,
                graph_path,
                file_codec,
                "missing",
                "does not exist",
            )
        if not path.is_file():
            self._raise_load(
                staged,
                graph_path,
                file_codec,
                "not_file",
                "is not a regular file",
            )
        try:
            raw = path.read_bytes()
        except OSError as exc:
            self._raise_load(
                staged,
                graph_path,
                file_codec,
                "read_error",
                str(exc),
            )
        self._bytes[path] = raw
        return raw

    def _raise_input_type(
        self,
        value: Any,
        type_expr: TypeExpr | None,
        graph_path: str,
        *,
        staged: StagedFile | None = None,
    ) -> NoReturn:
        details: dict[str, Any] = {
            "reason": "file_path_required",
            "actual": staged.literal_kind if staged is not None else type(value).__name__,
            "expected": "file path string",
        }
        source_path = staged.source_path if staged is not None else None
        span = staged.span if staged is not None else None
        if staged is not None:
            details.update(self._details(staged, graph_path))
        if type_expr is not None:
            details["type"] = type_text(type_expr)
        raise_error(
            "E_TYPE_MISMATCH",
            "File fields require file path strings.",
            source_path=source_path,
            span=span,
            graph_path=graph_path,
            details=details,
        )

    def _raise_load(
        self,
        staged: StagedFile,
        graph_path: str,
        file_codec: FileCodec,
        reason: str,
        problem: str,
    ) -> NoReturn:
        raise_error(
            "E_FILE_LOAD",
            f"Could not load file '{staged.original}': {problem}.",
            source_path=staged.source_path,
            span=staged.span,
            graph_path=graph_path,
            details={
                **self._details(staged, graph_path),
                "codec": file_codec,
                "reason": reason,
                "problem": problem,
            },
        )

    @staticmethod
    def _details(staged: StagedFile, graph_path: str) -> dict[str, Any]:
        return {
            "original": staged.original,
            "resolved_path": (
                staged.resolved_path.as_posix() if staged.resolved_path is not None else None
            ),
            "declaring_source_path": staged.source_path.as_posix(),
            "graph_path": graph_path,
        }


def _parser_location(exc: Exception) -> tuple[int | None, int | None]:
    line = getattr(exc, "lineno", None)
    column = getattr(exc, "colno", None)
    mark = getattr(exc, "problem_mark", None)
    if mark is not None:
        line = getattr(mark, "line", -1) + 1
        column = getattr(mark, "column", -1) + 1
    return (
        line if isinstance(line, int) and line > 0 else None,
        column if isinstance(column, int) and column > 0 else None,
    )


def _parser_message(exc: Exception) -> str:
    problem = getattr(exc, "problem", None)
    if isinstance(problem, str) and problem:
        return problem
    return str(exc)


__all__ = [
    "FileLoader",
    "FileTypeError",
    "StagedFile",
    "contains_file_type",
    "file_leaf_codec",
    "non_null_union_options",
    "stage_file",
    "type_allows_null",
    "unstage_files",
    "validate_file_type",
]
