from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class SourceSpan:
    source_path: Path
    line: int
    column: int
    end_line: int
    end_column: int
    start_pos: int | None = None
    end_pos: int | None = None


@dataclass(frozen=True)
class Selector:
    path: Path
    implementation: str | None = None
    raw: str | None = None

    @classmethod
    def parse(cls, raw: str) -> Selector:
        path_text, separator, implementation = raw.partition("#")
        if not path_text:
            raise ValueError("selector path must be non-empty")
        if separator and not implementation:
            raise ValueError("selector implementation must be non-empty when '#' is used")
        return cls(
            path=Path(path_text),
            implementation=implementation if separator else None,
            raw=raw,
        )


@dataclass(frozen=True)
class TypeExpr:
    kind: str
    name: str | None = None
    args: tuple[TypeExpr, ...] = ()


@dataclass(frozen=True)
class LiteralValue:
    kind: str
    value: Any


@dataclass(frozen=True)
class Assignment:
    field_path: tuple[str, ...]
    value: LiteralValue
    span: SourceSpan | None = None


@dataclass(frozen=True)
class RefAssignment:
    field_name: str
    selector: Selector
    span: SourceSpan | None = None


@dataclass(frozen=True)
class FieldDef:
    name: str
    type_expr: TypeExpr
    default: LiteralValue | None = None
    metadata: Mapping[str, LiteralValue] = field(default_factory=dict)
    override: str = "allow"
    span: SourceSpan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SpecDef:
    name: str
    parent: Path | None = None
    fields: tuple[FieldDef, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SpecRef:
    path: Path
    span: SourceSpan | None = None


@dataclass(frozen=True)
class ImplDef:
    name: str
    parent: Selector | None = None
    assignments: tuple[Assignment | RefAssignment, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True)
class Document:
    source_path: Path
    spec: SpecDef | None = None
    spec_ref: SpecRef | None = None
    implementations: tuple[ImplDef, ...] = ()

    def __post_init__(self) -> None:
        if self.spec is not None and self.spec_ref is not None:
            raise ValueError("document may define either spec or spec_ref, not both")
