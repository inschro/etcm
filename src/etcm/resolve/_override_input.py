from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from etcm._contracts import OverrideInput
from etcm.errors import ETCMError
from etcm.ir import Assignment, LiteralValue, RefAssignment, Selector, SourceSpan
from etcm.syntax._literals import parse_literal

OverrideOrigin = Literal["local", "external"]

_FIELD_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_NUMERIC_PREFIX = re.compile(r"^[+-]?(?:\d|\.\d)")


@dataclass(frozen=True)
class OverrideOperation:
    path: tuple[str, ...]
    value: LiteralValue | None
    selector: Selector | None
    source_path: Path | None
    span: SourceSpan | None
    origin: OverrideOrigin
    value_base: Path
    force_authorized: bool = False
    raw: str | None = None


def operations_from_assignments(
    assignments: tuple[Assignment | RefAssignment, ...],
    *,
    source_path: Path,
) -> tuple[OverrideOperation, ...]:
    operations = [
        OverrideOperation(
            path=assignment.field_path,
            value=assignment.value if isinstance(assignment, Assignment) else None,
            selector=assignment.selector if isinstance(assignment, RefAssignment) else None,
            source_path=source_path,
            span=assignment.span,
            origin="local",
            value_base=source_path.parent,
        )
        for assignment in assignments
    ]
    return _ordered_operations(operations)


def normalize_external_overrides(
    overrides: OverrideInput | None,
    *,
    force_authorized: bool,
    override_base: str | Path | None,
) -> tuple[OverrideOperation, ...]:
    if overrides is None:
        return ()

    base = Path.cwd() if override_base is None else Path(override_base)
    base = base.resolve()
    if isinstance(overrides, Mapping):
        entries = [
            (path, _literal_from_native(value, path=path), None)
            for path, value in overrides.items()
        ]
    elif isinstance(overrides, str):
        raise ValueError("overrides must be a mapping or a sequence of 'PATH=VALUE' strings")
    elif isinstance(overrides, Sequence):
        entries = [_parse_entry(entry) for entry in overrides]
    else:
        raise TypeError("overrides must be a mapping or a sequence of strings")

    operations: list[OverrideOperation] = []
    seen: set[tuple[str, ...]] = set()
    for raw_path, value, raw in entries:
        path = _parse_path(raw_path)
        if path in seen:
            canonical = ".".join(path)
            raise ValueError(f"duplicate override path '{canonical}'")
        seen.add(path)
        operations.append(
            OverrideOperation(
                path=path,
                value=value,
                selector=None,
                source_path=None,
                span=None,
                origin="external",
                value_base=base,
                force_authorized=force_authorized,
                raw=raw,
            )
        )
    return _ordered_operations(operations)


def _ordered_operations(
    operations: list[OverrideOperation],
) -> tuple[OverrideOperation, ...]:
    return tuple(
        operation
        for _, operation in sorted(
            enumerate(operations),
            key=lambda item: (len(item[1].path), item[0]),
        )
    )


def _parse_entry(entry: object) -> tuple[str, LiteralValue, str]:
    if not isinstance(entry, str):
        raise TypeError("override sequences may contain only strings")
    path, separator, raw_value = entry.partition("=")
    if not separator:
        raise ValueError(f"override '{entry}' must use PATH=VALUE")
    if not raw_value.strip():
        raise ValueError(f"override '{entry}' is missing a value")
    return path, _literal_from_text(raw_value.strip(), entry=entry), entry


def _parse_path(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, str):
        raise TypeError("override paths must be strings")
    path = raw.strip()
    if _FIELD_PATH.fullmatch(path) is None:
        raise ValueError(
            f"invalid override path '{raw}'; expected dot-separated field names"
        )
    return tuple(path.split("."))


def _literal_from_text(raw: str, *, entry: str) -> LiteralValue:
    try:
        return parse_literal(raw)
    except ETCMError as exc:
        if _requires_literal_syntax(raw):
            raise ValueError(f"invalid ETCM literal in override '{entry}'") from exc
        return LiteralValue(kind="string", value=raw)


def _requires_literal_syntax(raw: str) -> bool:
    return (
        raw.startswith(('"', "[", "{"))
        or raw in {"true", "false", "null"}
        or _NUMERIC_PREFIX.match(raw) is not None
    )


def _literal_from_native(value: object, *, path: object) -> LiteralValue:
    if value is None:
        return LiteralValue(kind="null", value=None)
    if isinstance(value, bool):
        return LiteralValue(kind="bool", value=value)
    if isinstance(value, int):
        return LiteralValue(kind="int", value=value)
    if isinstance(value, float):
        return LiteralValue(kind="float", value=value)
    if isinstance(value, Path):
        return LiteralValue(kind="string", value=value.as_posix())
    if isinstance(value, str):
        return LiteralValue(kind="string", value=value)
    if isinstance(value, list):
        return LiteralValue(
            kind="list",
            value=tuple(_literal_from_native(item, path=path) for item in value),
        )
    if isinstance(value, Mapping):
        items: list[tuple[str, LiteralValue]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"override '{path}' contains a mapping key that is not a string"
                )
            items.append((key, _literal_from_native(item, path=path)))
        return LiteralValue(kind="map", value=tuple(items))
    raise TypeError(
        f"override '{path}' uses unsupported Python value type "
        f"'{type(value).__name__}'"
    )
