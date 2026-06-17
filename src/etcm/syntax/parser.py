from __future__ import annotations

import ast as py_ast
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from lark import Lark, Token, Tree, UnexpectedInput
from lark.indenter import Indenter

from etcm.errors import Diagnostic, ETCMError
from etcm.ir import (
    Assignment,
    Document,
    FieldDef,
    ImplDef,
    LiteralValue,
    RefAssignment,
    Selector,
    SourceSpan,
    SpecDef,
    SpecRef,
    TypeExpr,
)
from etcm.syntax.ast import (
    SyntaxAssignment,
    SyntaxDocument,
    SyntaxField,
    SyntaxImpl,
    SyntaxItem,
    SyntaxLiteral,
    SyntaxRefAssignment,
    SyntaxSpec,
    SyntaxSpecRef,
    SyntaxTypeExpr,
)

SyntaxDiagnostic = Diagnostic


class ETCMIndenter(Indenter):
    @property
    def NL_type(self) -> str:
        return "_NL"

    @property
    def OPEN_PAREN_types(self) -> list[str]:
        return ["LPAR", "LSQB", "LBRACE"]

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
        propagate_positions=True,
        maybe_placeholders=False,
        postlex=ETCMIndenter(),
    )


def parse_syntax(text: str, source_path: str | Path = "<string>") -> SyntaxDocument:
    source = Path(source_path)
    _reject_tab_indentation(text, source)
    stripped_text = _strip_yaml_style_comments(text)
    try:
        tree = build_parser().parse(stripped_text)
    except UnexpectedInput as exc:
        raise ETCMError(_diagnostic_from_unexpected(exc, source)) from exc

    document = _SyntaxBuilder(source).document(tree)
    _validate_document(document)
    return document


def parse_document(text: str, source_path: str | Path = "<string>") -> Document:
    return _syntax_to_ir(parse_syntax(text, source_path))


def parse_file(path: str | Path) -> Document:
    source = Path(path)
    return parse_document(source.read_text(encoding="utf-8"), source)


class _SyntaxBuilder:
    def __init__(self, source_path: Path) -> None:
        self._source_path = source_path

    def document(self, tree: Tree[Token]) -> SyntaxDocument:
        items: list[SyntaxItem] = []
        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "spec":
                items.append(self.spec(child))
            elif child.data == "spec_ref":
                items.append(self.spec_ref(child))
            elif child.data == "impl":
                items.append(self.impl(child))
        return SyntaxDocument(source_path=self._source_path, items=tuple(items))

    def spec(self, tree: Tree[Token]) -> SyntaxSpec:
        name = _required_token(tree, "NAME")
        parent: Path | None = None
        fields: list[SyntaxField] = []

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "spec_parent":
                parent = Path(str(_required_token(child, "PATH")))
            elif child.data == "field":
                fields.append(self.field(child))

        return SyntaxSpec(
            name=str(name),
            parent=parent,
            fields=tuple(fields),
            span=_span(tree, self._source_path),
        )

    def spec_ref(self, tree: Tree[Token]) -> SyntaxSpecRef:
        return SyntaxSpecRef(
            path=Path(str(_required_token(tree, "PATH"))),
            span=_span(tree, self._source_path),
        )

    def impl(self, tree: Tree[Token]) -> SyntaxImpl:
        name = _required_token(tree, "NAME")
        parent: str | None = None
        assignments: list[SyntaxAssignment | SyntaxRefAssignment] = []

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "impl_parent":
                parent = self._selector(str(_required_token(child, "SELECTOR")), child)
            elif child.data == "value_assignment":
                assignments.append(self.value_assignment(child))
            elif child.data == "ref_assignment":
                assignments.append(self.ref_assignment(child))

        return SyntaxImpl(
            name=str(name),
            parent=parent,
            assignments=tuple(assignments),
            span=_span(tree, self._source_path),
        )

    def field(self, tree: Tree[Token]) -> SyntaxField:
        name = _required_token(tree, "NAME")
        type_expr: SyntaxTypeExpr | None = None
        default: SyntaxLiteral | None = None
        metadata: dict[str, SyntaxLiteral] = {}
        override = "allow"

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data in {"union_type", "generic_type", "named_type"}:
                type_expr = self.type_expr(child)
            elif child.data == "field_meta":
                meta = self.field_meta(child)
                default = meta.pop("default", None)
                override_literal = meta.pop("override", None)
                if override_literal is not None:
                    override = str(override_literal.value)
                metadata = meta

        if type_expr is None:
            raise AssertionError("field is missing type expression")

        return SyntaxField(
            name=str(name),
            type_expr=type_expr,
            default=default,
            metadata=metadata,
            override=override,
            span=_span(tree, self._source_path),
        )

    def field_meta(self, tree: Tree[Token]) -> dict[str, SyntaxLiteral]:
        metadata: dict[str, SyntaxLiteral] = {}
        for child in tree.children:
            if isinstance(child, Tree) and child.data == "meta_pair":
                key = str(_required_token(child, "NAME"))
                value_tree = _required_tree(child)
                metadata[key] = self.literal(value_tree)
        return metadata

    def value_assignment(self, tree: Tree[Token]) -> SyntaxAssignment:
        field_path: tuple[str, ...] | None = None
        value: SyntaxLiteral | None = None

        for child in tree.children:
            if isinstance(child, Tree) and child.data == "field_path":
                field_path = tuple(str(token) for token in _tokens(child, "NAME"))
            elif isinstance(child, Tree):
                value = self.literal(child)

        if field_path is None or value is None:
            raise AssertionError("value assignment is incomplete")

        return SyntaxAssignment(
            field_path=field_path,
            value=value,
            span=_span(tree, self._source_path),
        )

    def ref_assignment(self, tree: Tree[Token]) -> SyntaxRefAssignment:
        field_name = str(_required_token(tree, "NAME"))
        selector = self._selector(str(_required_token(tree, "SELECTOR")), tree)
        return SyntaxRefAssignment(
            field_name=field_name,
            selector=selector,
            span=_span(tree, self._source_path),
        )

    def type_expr(self, tree: Tree[Token]) -> SyntaxTypeExpr:
        if tree.data == "union_type":
            parts = [self.type_expr(child) for child in tree.children if isinstance(child, Tree)]
            if len(parts) == 1:
                return parts[0]
            return SyntaxTypeExpr(kind="union", args=tuple(parts))

        if tree.data == "generic_type":
            name = str(_required_token(tree, "NAME"))
            args = tuple(
                self.type_expr(child) for child in tree.children if isinstance(child, Tree)
            )
            return SyntaxTypeExpr(kind="generic", name=name, args=args)

        if tree.data == "named_type":
            return SyntaxTypeExpr(kind="named", name=str(_required_token(tree, "NAME")))

        raise AssertionError(f"unsupported type expression: {tree.data}")

    def literal(self, tree: Tree[Token]) -> SyntaxLiteral:
        span = _span(tree, self._source_path)

        if tree.data == "string":
            return SyntaxLiteral(
                kind="string",
                value=py_ast.literal_eval(str(tree.children[0])),
                span=span,
            )

        if tree.data == "number":
            raw = str(tree.children[0])
            if "." in raw or "e" in raw.lower():
                return SyntaxLiteral(kind="float", value=float(raw), span=span)
            return SyntaxLiteral(kind="int", value=int(raw), span=span)

        if tree.data == "true":
            return SyntaxLiteral(kind="bool", value=True, span=span)

        if tree.data == "false":
            return SyntaxLiteral(kind="bool", value=False, span=span)

        if tree.data == "null":
            return SyntaxLiteral(kind="null", value=None, span=span)

        if tree.data == "list_lit":
            values = tuple(
                self.literal(child) for child in tree.children if isinstance(child, Tree)
            )
            return SyntaxLiteral(kind="list", value=values, span=span)

        if tree.data == "map_lit":
            values = tuple(
                self.map_pair(child) for child in tree.children if isinstance(child, Tree)
            )
            return SyntaxLiteral(kind="map", value=values, span=span)

        raise AssertionError(f"unsupported literal: {tree.data}")

    def map_pair(self, tree: Tree[Token]) -> tuple[str, SyntaxLiteral]:
        key: str | None = None
        value: SyntaxLiteral | None = None

        for child in tree.children:
            if isinstance(child, Tree) and child.data in {"bare_key", "string_key"}:
                key = self.map_key(child)
            elif isinstance(child, Tree):
                value = self.literal(child)

        if key is None or value is None:
            raise AssertionError("map pair is incomplete")

        return (key, value)

    def map_key(self, tree: Tree[Token]) -> str:
        if tree.data == "bare_key":
            return str(_required_token(tree, "NAME"))
        if tree.data == "string_key":
            return str(py_ast.literal_eval(str(tree.children[0])))
        raise AssertionError(f"unsupported map key: {tree.data}")

    def _selector(self, raw: str, node: Tree[Token]) -> str:
        try:
            Selector.parse(raw)
        except ValueError as exc:
            _raise(
                "E_PARSE_SELECTOR",
                f"Invalid selector '{raw}'.",
                self._source_path,
                _span(node, self._source_path),
                selector=raw,
            )
            raise AssertionError("unreachable") from exc
        return raw


def _syntax_to_ir(document: SyntaxDocument) -> Document:
    spec = next((item for item in document.items if isinstance(item, SyntaxSpec)), None)
    spec_ref = next((item for item in document.items if isinstance(item, SyntaxSpecRef)), None)
    implementations = tuple(
        _impl_to_ir(item) for item in document.items if isinstance(item, SyntaxImpl)
    )
    return Document(
        source_path=document.source_path,
        spec=_spec_to_ir(spec) if spec is not None else None,
        spec_ref=_spec_ref_to_ir(spec_ref) if spec_ref is not None else None,
        implementations=implementations,
    )


def _spec_to_ir(spec: SyntaxSpec) -> SpecDef:
    return SpecDef(
        name=spec.name,
        parent=spec.parent,
        fields=tuple(_field_to_ir(field) for field in spec.fields),
        span=spec.span,
    )


def _spec_ref_to_ir(spec_ref: SyntaxSpecRef) -> SpecRef:
    return SpecRef(path=spec_ref.path, span=spec_ref.span)


def _field_to_ir(field: SyntaxField) -> FieldDef:
    return FieldDef(
        name=field.name,
        type_expr=_type_to_ir(field.type_expr),
        default=_literal_to_ir(field.default) if field.default is not None else None,
        metadata={key: _literal_to_ir(value) for key, value in field.metadata.items()},
        override=field.override,
        span=field.span,
    )


def _impl_to_ir(impl: SyntaxImpl) -> ImplDef:
    return ImplDef(
        name=impl.name,
        parent=Selector.parse(impl.parent) if impl.parent is not None else None,
        assignments=tuple(_assignment_to_ir(assignment) for assignment in impl.assignments),
        span=impl.span,
    )


def _assignment_to_ir(
    assignment: SyntaxAssignment | SyntaxRefAssignment,
) -> Assignment | RefAssignment:
    if isinstance(assignment, SyntaxRefAssignment):
        return RefAssignment(
            field_name=assignment.field_name,
            selector=Selector.parse(assignment.selector),
            span=assignment.span,
        )
    return Assignment(
        field_path=assignment.field_path,
        value=_literal_to_ir(assignment.value),
        span=assignment.span,
    )


def _type_to_ir(type_expr: SyntaxTypeExpr) -> TypeExpr:
    return TypeExpr(
        kind=type_expr.kind,
        name=type_expr.name,
        args=tuple(_type_to_ir(arg) for arg in type_expr.args),
    )


def _literal_to_ir(literal: SyntaxLiteral) -> LiteralValue:
    if literal.kind == "list":
        return LiteralValue(
            kind=literal.kind,
            value=tuple(_literal_to_ir(value) for value in literal.value),
        )
    if literal.kind == "map":
        return LiteralValue(
            kind=literal.kind,
            value=tuple((key, _literal_to_ir(value)) for key, value in literal.value),
        )
    return LiteralValue(kind=literal.kind, value=literal.value)


def _validate_document(document: SyntaxDocument) -> None:
    specs = [item for item in document.items if isinstance(item, SyntaxSpec)]
    spec_refs = [item for item in document.items if isinstance(item, SyntaxSpecRef)]

    if len(specs) > 1:
        _raise(
            "E_DUPLICATE_SPEC",
            f"Duplicate spec definition '{specs[1].name}'.",
            document.source_path,
            specs[1].span,
            details={"previous": specs[0].name},
        )

    if specs and spec_refs:
        second = _second_of(document.items, SyntaxSpec, SyntaxSpecRef)
        _raise(
            "E_SPEC_AND_SPEC_REF",
            "Document may define either inline spec or top-level $spec, not both.",
            document.source_path,
            second.span,
        )

    for spec in specs:
        _validate_fields(document.source_path, spec)

    _validate_implementations(document)


def _validate_fields(source_path: Path, spec: SyntaxSpec) -> None:
    seen: dict[str, SyntaxField] = {}
    for field in spec.fields:
        previous = seen.get(field.name)
        if previous is not None:
            _raise(
                "E_DUPLICATE_FIELD",
                f"Duplicate field '{field.name}' in spec '{spec.name}'.",
                source_path,
                field.span,
                details={
                    "previous_line": previous.span.line if previous.span is not None else None
                },
            )
        seen[field.name] = field


def _validate_implementations(document: SyntaxDocument) -> None:
    seen: dict[str, SyntaxImpl] = {}
    for impl in (item for item in document.items if isinstance(item, SyntaxImpl)):
        previous = seen.get(impl.name)
        if previous is not None:
            _raise(
                "E_DUPLICATE_IMPL",
                f"Duplicate implementation '{impl.name}'.",
                document.source_path,
                impl.span,
                details={
                    "previous_line": previous.span.line if previous.span is not None else None
                },
            )
        seen[impl.name] = impl


def _second_of(items: tuple[SyntaxItem, ...], left: type[Any], right: type[Any]) -> Any:
    seen = False
    for item in items:
        if isinstance(item, left | right):
            if seen:
                return item
            seen = True
    raise AssertionError("expected two matching items")


def _reject_tab_indentation(text: str, source_path: Path) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        for column, char in enumerate(line, start=1):
            if char == "\t":
                _raise(
                    "E_PARSE_TAB_INDENT",
                    "Tabs cannot be used for indentation in ETCM.",
                    source_path,
                    SourceSpan(
                        source_path=source_path,
                        line=line_number,
                        column=column,
                        end_line=line_number,
                        end_column=column + 1,
                    ),
                )
            if char != " ":
                break


def _strip_yaml_style_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        lines.append(_strip_yaml_style_comment_from_line(line))
    return "".join(lines)


def _strip_yaml_style_comment_from_line(line: str) -> str:
    in_string = False
    escaped = False
    chars = list(line)

    for index, char in enumerate(chars):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "#" and (index == 0 or chars[index - 1] in {" ", "\t"}):
            for comment_index in range(index, len(chars)):
                if chars[comment_index] not in {"\n", "\r"}:
                    chars[comment_index] = " "
            break

    return "".join(chars)


def _diagnostic_from_unexpected(exc: UnexpectedInput, source_path: Path) -> Diagnostic:
    expected = set(getattr(exc, "expected", []) or [])
    token = getattr(exc, "token", None)
    token_type = getattr(token, "type", None)
    code = "E_PARSE_UNEXPECTED_TOKEN"
    message = "Unexpected token while parsing ETCM."

    if token_type in {"_INDENT", "_DEDENT"} or expected.intersection({"_INDENT", "_DEDENT"}):
        code = "E_PARSE_BAD_INDENT"
        message = "Invalid indentation in ETCM document."

    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)

    return Diagnostic(
        code=code,
        message=message,
        source_path=source_path,
        line=line,
        column=column,
        end_line=line,
        end_column=column + 1 if column is not None else None,
        details={"expected": sorted(str(value) for value in expected)},
    )


def _raise(
    code: str,
    message: str,
    source_path: Path,
    span: SourceSpan | None,
    *,
    selector: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    raise ETCMError(
        Diagnostic(
            code=code,
            message=message,
            source_path=source_path,
            line=span.line if span is not None else None,
            column=span.column if span is not None else None,
            end_line=span.end_line if span is not None else None,
            end_column=span.end_column if span is not None else None,
            selector=selector,
            details=details,
        )
    )


def _span(node: Tree[Token] | Token, source_path: Path) -> SourceSpan:
    meta = node.meta if isinstance(node, Tree) else node
    line = int(getattr(meta, "line", 1) or 1)
    column = int(getattr(meta, "column", 1) or 1)
    end_line = int(getattr(meta, "end_line", line) or line)
    end_column = int(getattr(meta, "end_column", column) or column)
    return SourceSpan(
        source_path=source_path,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
        start_pos=getattr(meta, "start_pos", None),
        end_pos=getattr(meta, "end_pos", None),
    )


def _required_token(tree: Tree[Token], token_type: str) -> Token:
    for child in tree.children:
        if isinstance(child, Token) and child.type == token_type:
            return child
    raise AssertionError(f"missing token {token_type}")


def _tokens(tree: Tree[Token], token_type: str) -> tuple[Token, ...]:
    return tuple(
        child for child in tree.children if isinstance(child, Token) and child.type == token_type
    )


def _required_tree(tree: Tree[Token]) -> Tree[Token]:
    for child in tree.children:
        if isinstance(child, Tree):
            return child
    raise AssertionError("missing child tree")
