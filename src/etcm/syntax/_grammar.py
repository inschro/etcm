from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

from lark import Lark
from lark.indenter import Indenter


class ETCMIndenter(Indenter):
    @property
    def NL_type(self) -> str:
        return "_NL"

    @property
    def OPEN_PAREN_types(self) -> list[str]:
        return ["LPAR", "LSQB", "META_LSQB", "LBRACE"]

    @property
    def CLOSE_PAREN_types(self) -> list[str]:
        return ["RPAR", "RSQB", "RBRACE"]

    @property
    def INDENT_type(self) -> str:
        return "_INDENT"

    @property
    def DEDENT_type(self) -> str:
        return "_DEDENT"

    @property
    def tab_len(self) -> int:
        return 8


@lru_cache(maxsize=1)
def build_parser() -> Lark:
    grammar = files("etcm.syntax").joinpath("grammar.lark").read_text(encoding="utf-8")
    return Lark(
        grammar,
        parser="lalr",
        start=["start", "expression_start", "assertion_expression_start", "literal_start"],
        propagate_positions=True,
        maybe_placeholders=False,
        postlex=ETCMIndenter(),
    )
