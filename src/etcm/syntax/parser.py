from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from lark import Lark


@dataclass(frozen=True)
class SyntaxDiagnostic:
    message: str
    source_path: Path | None = None
    line: int | None = None
    column: int | None = None


def build_parser() -> Lark:
    grammar = files("etcm.syntax").joinpath("grammar.lark").read_text(encoding="utf-8")
    return Lark(grammar, parser="lalr", propagate_positions=True, maybe_placeholders=False)
