from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

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
class SyntaxParameterReference:
    parts: tuple[str, ...]
    raw: str
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxExpression:
    kind: Literal["literal", "reference", "current", "unary", "binary"]
    operator: str | None = None
    literal: SyntaxLiteral | None = None
    reference: SyntaxParameterReference | None = None
    operands: tuple[SyntaxExpression, ...] = ()
    raw: str | None = None
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxComparisonConstraint:
    left: SyntaxExpression
    operator: str
    right: SyntaxExpression
    raw: str
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxAssertion:
    name: str
    predicates: tuple[SyntaxExpression, ...]
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxField:
    name: str
    type_expr: SyntaxTypeExpr | None = None
    default: SyntaxLiteral | None = None
    derived: SyntaxExpression | None = None
    constraints: tuple[SyntaxComparisonConstraint, ...] = ()
    metadata: Mapping[str, SyntaxLiteral] = field(default_factory=dict)
    override: str = "allow"
    ref_selector: str | None = None
    fields: tuple[SyntaxField, ...] = ()
    assertions: tuple[SyntaxAssertion, ...] = ()
    span: SourceSpan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SyntaxSpec:
    name: str
    parent: str | None = None
    fields: tuple[SyntaxField, ...] = ()
    assertions: tuple[SyntaxAssertion, ...] = ()
    implementations: tuple[SyntaxImpl, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxSpecRef:
    selector: str
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxAssignment:
    field_path: tuple[str, ...]
    value: SyntaxLiteral
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SyntaxRefAssignment:
    field_path: tuple[str, ...]
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
