from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

SelectorTarget = Literal["spec", "implementation"]
ExpressionKind = Literal["literal", "reference", "current", "unary", "binary"]

_SELECTOR_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    path: Path | None
    spec: str | None = None
    implementation: str | None = None
    raw: str | None = None

    def __post_init__(self) -> None:
        if self.spec is None and self.implementation is None:
            raise ValueError("selector must identify a spec or implementation")
        if self.path is not None and self.spec is None:
            raise ValueError("a selector path must be followed by '#Spec'")
        if self.path is not None and self.path.suffix != ".etcm":
            raise ValueError("selector paths must end in '.etcm'")
        if self.spec is not None and _SELECTOR_NAME.fullmatch(self.spec) is None:
            raise ValueError(f"invalid selector spec name '{self.spec}'")
        if (
            self.implementation is not None
            and _SELECTOR_NAME.fullmatch(self.implementation) is None
        ):
            raise ValueError(
                f"invalid selector implementation name '{self.implementation}'"
            )

    @property
    def target(self) -> SelectorTarget:
        if self.implementation is None:
            return "spec"
        return "implementation"

    @classmethod
    def parse(cls, raw: str) -> Selector:
        if not raw:
            raise ValueError("selector must not be empty")

        if raw.startswith(":"):
            implementation = raw[1:]
            if not implementation or ":" in implementation or "#" in implementation:
                raise ValueError(
                    "local implementation selectors must use ':implementation'"
                )
            return cls(path=None, implementation=implementation, raw=raw)

        path_text, separator, fragment = raw.partition("#")
        if not separator:
            raise ValueError(
                "selectors must use 'path.etcm#Spec', '#Spec', "
                "'path.etcm#Spec:implementation', '#Spec:implementation', "
                "or ':implementation'"
            )
        if not fragment:
            raise ValueError("selector fragment must name a spec")

        spec, impl_separator, implementation = fragment.partition(":")
        if not spec:
            raise ValueError("selector fragment must name a spec")
        if impl_separator and not implementation:
            raise ValueError("selector implementation must not be empty")
        if implementation and ":" in implementation:
            raise ValueError("selector may contain only one implementation fragment")

        return cls(
            path=Path(path_text) if path_text else None,
            spec=spec,
            implementation=implementation if impl_separator else None,
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
class ParameterReference:
    parts: tuple[str, ...]
    raw: str
    span: SourceSpan | None = None

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("parameter reference must contain at least one path segment")


@dataclass(frozen=True)
class Expression:
    kind: ExpressionKind
    operator: str | None = None
    literal: LiteralValue | None = None
    reference: ParameterReference | None = None
    operands: tuple[Expression, ...] = ()
    raw: str | None = None
    span: SourceSpan | None = None


@dataclass(frozen=True)
class ComparisonConstraint:
    left: Expression
    operator: str
    right: Expression
    raw: str
    span: SourceSpan | None = None


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
    derived: Expression | None = None
    constraints: tuple[ComparisonConstraint, ...] = ()
    metadata: Mapping[str, LiteralValue] = field(default_factory=dict)
    override: str = "allow"
    ref_selector: Selector | None = None
    fields: tuple[FieldDef, ...] = ()
    span: SourceSpan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SpecDef:
    name: str
    parent: Selector | None = None
    fields: tuple[FieldDef, ...] = ()
    implementations: tuple[ImplDef, ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True)
class SpecRef:
    selector: Selector
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
    specs: tuple[SpecDef, ...] = ()
    spec_ref: SpecRef | None = None
    implementations: tuple[ImplDef, ...] = ()

    def __post_init__(self) -> None:
        if self.specs and self.spec_ref is not None:
            raise ValueError("document may define either spec or spec_ref, not both")
