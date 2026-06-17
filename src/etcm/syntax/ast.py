from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from etcm.ir import SourceSpan


@dataclass(frozen=True)
class SyntaxTypeExpr:
    kind: str
    name: str | None = None
    args: tuple[SyntaxTypeExpr, ...] = ()


@dataclass(frozen=True)
class SyntaxLiteral:
    kind: str
    value: Any
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxField:
    name: str
    type_expr: SyntaxTypeExpr
    default: SyntaxLiteral | None = None
    metadata: Mapping[str, SyntaxLiteral] = field(default_factory=dict)
    override: str = "allow"
    span: SourceSpan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SyntaxSpec:
    name: str
    parent: Path | None = None
    fields: tuple[SyntaxField, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxSpecRef:
    path: Path
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxAssignment:
    field_path: tuple[str, ...]
    value: SyntaxLiteral
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxRefAssignment:
    field_name: str
    selector: str
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxImpl:
    name: str
    parent: str | None = None
    assignments: tuple[SyntaxAssignment | SyntaxRefAssignment, ...] = ()
    span: SourceSpan | None = None


SyntaxItem = SyntaxSpec | SyntaxSpecRef | SyntaxImpl


@dataclass(frozen=True)
class SyntaxDocument:
    source_path: Path
    items: tuple[SyntaxItem, ...] = ()
