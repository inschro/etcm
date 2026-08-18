from __future__ import annotations

import ast as py_ast
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from pathlib import Path

from lark import Token, Tree

from etcm.ir import Selector, SelectorTarget, SourceSpan
from etcm.syntax._expressions import ExpressionBuilder
from etcm.syntax._source import (
    raise_syntax_error,
    required_token,
    required_tree,
    source_span,
    tokens,
)
from etcm.syntax.ast import (
    SyntaxAssertion,
    SyntaxAssignment,
    SyntaxComparisonConstraint,
    SyntaxDocument,
    SyntaxExpression,
    SyntaxField,
    SyntaxImpl,
    SyntaxItem,
    SyntaxLiteral,
    SyntaxRefAssignment,
    SyntaxSpec,
    SyntaxSpecRef,
    SyntaxTypeExpr,
)


@dataclass(frozen=True)
class _FieldDeclaration:
    path: tuple[str, ...]
    field: SyntaxField
    is_container: bool = False


@dataclass
class _FieldNode:
    name: str
    first_span: SourceSpan | None
    children: dict[str, _FieldNode] = dataclass_field(default_factory=dict)
    leaf: SyntaxField | None = None
    container: SyntaxField | None = None


class SyntaxBuilder:
    def __init__(self, source_path: Path, source_text: str) -> None:
        self._source_path = source_path
        self._expressions = ExpressionBuilder(source_path, source_text)

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
        name = required_token(tree, "NAME")
        parent: str | None = None
        declarations: list[_FieldDeclaration] = []
        assertions: list[SyntaxAssertion] = []
        implementations: list[SyntaxImpl] = []

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "spec_parent":
                parent = self._selector(
                    str(required_token(child, "SELECTOR")),
                    child,
                    expected="spec",
                )
            elif child.data in {"field", "spec_ref_field", "nested_field"}:
                declarations.extend(self._field_declarations(child))
            elif child.data == "assertion":
                assertions.append(self.assertion(child))
            elif child.data == "impl":
                implementations.append(self.impl(child))

        return SyntaxSpec(
            name=str(name),
            parent=parent,
            fields=self._normalize_fields(str(name), declarations),
            assertions=tuple(assertions),
            implementations=tuple(implementations),
            span=source_span(tree, self._source_path),
        )

    def spec_ref(self, tree: Tree[Token]) -> SyntaxSpecRef:
        return SyntaxSpecRef(
            selector=self._selector(
                str(required_token(tree, "SELECTOR")),
                tree,
                expected="spec",
                require_path=True,
            ),
            span=source_span(tree, self._source_path),
        )

    def impl(self, tree: Tree[Token]) -> SyntaxImpl:
        name = required_token(tree, "NAME")
        parent: str | None = None
        assignments: list[SyntaxAssignment | SyntaxRefAssignment] = []

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "impl_parent":
                parent = self._selector(
                    str(required_token(child, "SELECTOR")),
                    child,
                    expected="implementation",
                )
            elif child.data == "value_assignment":
                assignments.append(self.value_assignment(child))
            elif child.data == "ref_assignment":
                assignments.append(self.ref_assignment(child))
            elif child.data == "assignment_block":
                assignments.extend(self.assignment_block(child))

        return SyntaxImpl(
            name=str(name),
            parent=parent,
            assignments=tuple(assignments),
            span=source_span(tree, self._source_path),
        )

    def _field_declarations(
        self,
        tree: Tree[Token],
        prefix: tuple[str, ...] = (),
    ) -> tuple[_FieldDeclaration, ...]:
        if tree.data == "field":
            return (self.field(tree, prefix),)
        if tree.data == "spec_ref_field":
            return (self.spec_ref_field(tree, prefix),)
        if tree.data == "nested_field":
            return self.nested_field(tree, prefix)
        raise AssertionError(f"unsupported field declaration: {tree.data}")

    def field(
        self,
        tree: Tree[Token],
        prefix: tuple[str, ...] = (),
    ) -> _FieldDeclaration:
        path = (*prefix, *self.field_path(tree))
        type_expr: SyntaxTypeExpr | None = None
        default: SyntaxLiteral | None = None
        derived: SyntaxExpression | None = None
        constraints: tuple[SyntaxComparisonConstraint, ...] = ()
        metadata: dict[str, SyntaxLiteral] = {}
        override = "allow"

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data in {"union_type", "generic_type", "named_type"}:
                type_expr = self.type_expr(child)
            elif child.data == "field_default":
                default = self.literal(required_tree(child))
            elif child.data == "field_derived":
                derived = self._expressions.expression(required_tree(child))
            elif child.data == "derived_block":
                derived = self._expressions.derived_block(child)
            elif child.data == "field_meta":
                meta, constraints = self.field_meta(child)
                override_literal = meta.pop("override", None)
                if override_literal is not None:
                    override = str(override_literal.value)
                metadata = meta

        if type_expr is None:
            raise AssertionError("field is missing type expression")

        return _FieldDeclaration(
            path=path,
            field=SyntaxField(
                name=path[-1],
                type_expr=type_expr,
                default=default,
                derived=derived,
                constraints=constraints,
                metadata=metadata,
                override=override,
                span=source_span(tree, self._source_path),
            ),
        )

    def spec_ref_field(
        self,
        tree: Tree[Token],
        prefix: tuple[str, ...] = (),
    ) -> _FieldDeclaration:
        path = (*prefix, *self.field_path(tree))
        ref_selector = self._selector(
            str(required_token(tree, "SELECTOR")),
            tree,
            expected="spec",
        )
        metadata: dict[str, SyntaxLiteral] = {}
        constraints: tuple[SyntaxComparisonConstraint, ...] = ()
        override = "allow"

        for child in tree.children:
            if isinstance(child, Tree) and child.data == "field_meta":
                metadata, constraints = self.field_meta(child)
                override_literal = metadata.pop("override", None)
                if override_literal is not None:
                    override = str(override_literal.value)

        return _FieldDeclaration(
            path=path,
            field=SyntaxField(
                name=path[-1],
                constraints=constraints,
                metadata=metadata,
                override=override,
                ref_selector=ref_selector,
                span=source_span(tree, self._source_path),
            ),
        )

    def nested_field(
        self,
        tree: Tree[Token],
        prefix: tuple[str, ...] = (),
    ) -> tuple[_FieldDeclaration, ...]:
        path = (*prefix, *self.field_path(tree))
        metadata: dict[str, SyntaxLiteral] = {}
        constraints: tuple[SyntaxComparisonConstraint, ...] = ()
        override = "allow"
        declarations: list[_FieldDeclaration] = []
        assertions: list[SyntaxAssertion] = []

        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "field_meta":
                metadata, constraints = self.field_meta(child)
                override_literal = metadata.pop("override", None)
                if override_literal is not None:
                    override = str(override_literal.value)
            elif child.data in {"field", "spec_ref_field", "nested_field"}:
                declarations.extend(self._field_declarations(child, path))
            elif child.data == "assertion":
                assertions.append(self.assertion(child))
            elif child.data == "nested_impl":
                raise_syntax_error(
                    "E_NESTED_IMPL",
                    "Implementation blocks must be declared directly under a spec.",
                    self._source_path,
                    source_span(child, self._source_path),
                    details={"field_path": ".".join(path)},
                )

        container = _FieldDeclaration(
            path=path,
            field=SyntaxField(
                name=path[-1],
                constraints=constraints,
                metadata=metadata,
                override=override,
                assertions=tuple(assertions),
                span=source_span(tree, self._source_path),
            ),
            is_container=True,
        )
        return (container, *declarations)

    def assertion(self, tree: Tree[Token]) -> SyntaxAssertion:
        predicates: list[SyntaxExpression] = []
        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "assertion_statement":
                predicates.append(
                    self._expressions.assertion_expression(required_tree(child))
                )
            else:
                predicates.append(self._expressions.assertion_expression(child))
        if not predicates:
            raise AssertionError("assertion must contain at least one predicate")
        return SyntaxAssertion(
            name=str(required_token(tree, "NAME")),
            predicates=tuple(predicates),
            span=source_span(tree, self._source_path),
        )

    def field_path(self, tree: Tree[Token]) -> tuple[str, ...]:
        for child in tree.children:
            if isinstance(child, Tree) and child.data == "field_path":
                return tuple(str(token) for token in tokens(child, "NAME"))
        raise AssertionError(f"{tree.data} is missing a field path")

    def _normalize_fields(
        self,
        owner_name: str,
        declarations: list[_FieldDeclaration],
    ) -> tuple[SyntaxField, ...]:
        root = _FieldNode(name="", first_span=None)
        for declaration in declarations:
            node = root
            for index, segment in enumerate(declaration.path):
                child = node.children.get(segment)
                if child is None:
                    child = _FieldNode(name=segment, first_span=declaration.field.span)
                    node.children[segment] = child
                node = child
                if index < len(declaration.path) - 1 and node.leaf is not None:
                    self._raise_field_path_conflict(
                        owner_name,
                        declaration.path,
                        declaration.field.span,
                        node.leaf.span,
                    )

            if declaration.is_container:
                if node.leaf is not None:
                    self._raise_field_path_conflict(
                        owner_name,
                        declaration.path,
                        declaration.field.span,
                        node.leaf.span,
                    )
                if node.container is not None:
                    self._raise_duplicate_field(
                        owner_name,
                        declaration.path,
                        declaration.field.span,
                        node.container.span,
                    )
                node.container = declaration.field
                continue

            if node.leaf is not None:
                self._raise_duplicate_field(
                    owner_name,
                    declaration.path,
                    declaration.field.span,
                    node.leaf.span,
                )
            if node.container is not None or node.children:
                previous_span = (
                    node.container.span
                    if node.container is not None
                    else next(iter(node.children.values())).first_span
                )
                self._raise_field_path_conflict(
                    owner_name,
                    declaration.path,
                    declaration.field.span,
                    previous_span,
                )
            node.leaf = declaration.field

        return tuple(self._materialize_field(node) for node in root.children.values())

    def _materialize_field(self, node: _FieldNode) -> SyntaxField:
        if node.leaf is not None:
            return node.leaf
        children = tuple(self._materialize_field(child) for child in node.children.values())
        if node.container is not None:
            return replace(node.container, fields=children)
        return SyntaxField(name=node.name, fields=children, span=node.first_span)

    def _raise_duplicate_field(
        self,
        owner_name: str,
        path: tuple[str, ...],
        span: SourceSpan | None,
        previous_span: SourceSpan | None,
    ) -> None:
        canonical_path = ".".join(path)
        raise_syntax_error(
            "E_DUPLICATE_FIELD",
            f"Duplicate field '{canonical_path}' in spec '{owner_name}'.",
            self._source_path,
            span,
            details={
                "field_path": canonical_path,
                "previous_line": previous_span.line if previous_span is not None else None,
            },
        )

    def _raise_field_path_conflict(
        self,
        owner_name: str,
        path: tuple[str, ...],
        span: SourceSpan | None,
        previous_span: SourceSpan | None,
    ) -> None:
        canonical_path = ".".join(path)
        raise_syntax_error(
            "E_FIELD_PATH_CONFLICT",
            f"Field path '{canonical_path}' conflicts with an anonymous container "
            f"in spec '{owner_name}'.",
            self._source_path,
            span,
            details={
                "field_path": canonical_path,
                "previous_line": previous_span.line if previous_span is not None else None,
            },
        )

    def field_meta(
        self,
        tree: Tree[Token],
    ) -> tuple[dict[str, SyntaxLiteral], tuple[SyntaxComparisonConstraint, ...]]:
        metadata: dict[str, SyntaxLiteral] = {}
        constraints: list[SyntaxComparisonConstraint] = []
        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "meta_pair":
                metadata[str(required_token(child, "NAME"))] = self.literal(
                    required_tree(child)
                )
            elif child.data in {
                "implicit_comparison_constraint",
                "transformed_comparison_constraint",
            }:
                constraints.append(self._expressions.comparison_constraint(child))
            elif child.data == "in_constraint":
                metadata["choices"] = self.literal(required_tree(child))
        return metadata, tuple(constraints)

    def value_assignment(
        self,
        tree: Tree[Token],
        prefix: tuple[str, ...] = (),
    ) -> SyntaxAssignment:
        field_path: tuple[str, ...] | None = None
        value: SyntaxLiteral | None = None

        for child in tree.children:
            if isinstance(child, Tree) and child.data == "field_path":
                field_path = (*prefix, *tuple(str(token) for token in tokens(child, "NAME")))
            elif isinstance(child, Tree):
                value = self.literal(child)

        if field_path is None or value is None:
            raise AssertionError("value assignment is incomplete")

        return SyntaxAssignment(
            field_path=field_path,
            value=value,
            span=source_span(tree, self._source_path),
        )

    def ref_assignment(
        self,
        tree: Tree[Token],
        prefix: tuple[str, ...] = (),
    ) -> SyntaxRefAssignment:
        field_path = (*prefix, *self.field_path(tree))
        selector = self._selector(
            str(required_token(tree, "SELECTOR")),
            tree,
            expected="implementation",
        )
        return SyntaxRefAssignment(
            field_path=field_path,
            selector=selector,
            span=source_span(tree, self._source_path),
        )

    def assignment_block(
        self,
        tree: Tree[Token],
        prefix: tuple[str, ...] = (),
    ) -> tuple[SyntaxAssignment | SyntaxRefAssignment, ...]:
        block_path = (*prefix, *self.field_path(tree))
        assignments: list[SyntaxAssignment | SyntaxRefAssignment] = []
        for child in tree.children:
            if not isinstance(child, Tree):
                continue
            if child.data == "value_assignment":
                assignments.append(self.value_assignment(child, block_path))
            elif child.data == "ref_assignment":
                assignments.append(self.ref_assignment(child, block_path))
            elif child.data == "assignment_block":
                assignments.extend(self.assignment_block(child, block_path))
        return tuple(assignments)

    def type_expr(self, tree: Tree[Token]) -> SyntaxTypeExpr:
        if tree.data == "union_type":
            parts = [self.type_expr(child) for child in tree.children if isinstance(child, Tree)]
            if len(parts) == 1:
                return parts[0]
            return SyntaxTypeExpr(kind="union", args=tuple(parts))

        if tree.data == "generic_type":
            name = str(required_token(tree, "NAME"))
            args = tuple(
                self.type_expr(child) for child in tree.children if isinstance(child, Tree)
            )
            return SyntaxTypeExpr(kind="generic", name=name, args=args)

        if tree.data == "named_type":
            return SyntaxTypeExpr(kind="named", name=str(required_token(tree, "NAME")))

        raise AssertionError(f"unsupported type expression: {tree.data}")

    def literal(self, tree: Tree[Token]) -> SyntaxLiteral:
        span = source_span(tree, self._source_path)

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
            return str(required_token(tree, "NAME"))
        if tree.data == "string_key":
            return str(py_ast.literal_eval(str(tree.children[0])))
        raise AssertionError(f"unsupported map key: {tree.data}")

    def _selector(
        self,
        raw: str,
        node: Tree[Token],
        *,
        expected: SelectorTarget,
        require_path: bool = False,
    ) -> str:
        try:
            selector = Selector.parse(raw)
            if selector.target != expected:
                required_form = (
                    "path.etcm#Spec or #Spec"
                    if expected == "spec"
                    else (
                        "path.etcm#Spec:implementation, "
                        "#Spec:implementation, or :implementation"
                    )
                )
                raise ValueError(f"expected {expected} selector ({required_form})")
            if require_path and selector.path is None:
                raise ValueError("this selector position requires a file path")
        except ValueError as exc:
            raise_syntax_error(
                "E_PARSE_SELECTOR",
                f"Invalid {expected} selector '{raw}': {exc}.",
                self._source_path,
                source_span(node, self._source_path),
                selector=raw,
            )
            raise AssertionError("unreachable") from exc
        return raw
