from __future__ import annotations

from etcm.ir import (
    AssertionDef,
    Assignment,
    ComparisonConstraint,
    Document,
    Expression,
    FieldDef,
    ImplDef,
    LiteralValue,
    ParameterReference,
    RefAssignment,
    Selector,
    SpecDef,
    SpecRef,
    TypeExpr,
)
from etcm.syntax.ast import (
    SyntaxAssertion,
    SyntaxAssignment,
    SyntaxComparisonConstraint,
    SyntaxDocument,
    SyntaxExpression,
    SyntaxField,
    SyntaxImpl,
    SyntaxLiteral,
    SyntaxRefAssignment,
    SyntaxSpec,
    SyntaxSpecRef,
    SyntaxTypeExpr,
)


def syntax_to_ir(document: SyntaxDocument) -> Document:
    spec_ref = next((item for item in document.items if isinstance(item, SyntaxSpecRef)), None)
    implementations = tuple(
        _impl_to_ir(item) for item in document.items if isinstance(item, SyntaxImpl)
    )
    return Document(
        source_path=document.source_path,
        specs=tuple(_spec_to_ir(item) for item in document.items if isinstance(item, SyntaxSpec)),
        spec_ref=_spec_ref_to_ir(spec_ref) if spec_ref is not None else None,
        implementations=implementations,
    )


def _spec_to_ir(spec: SyntaxSpec) -> SpecDef:
    return SpecDef(
        name=spec.name,
        parent=Selector.parse(spec.parent) if spec.parent is not None else None,
        fields=tuple(_field_to_ir(field, spec.name) for field in spec.fields),
        assertions=tuple(_assertion_to_ir(item) for item in spec.assertions),
        implementations=tuple(_impl_to_ir(impl) for impl in spec.implementations),
        span=spec.span,
    )


def _spec_ref_to_ir(spec_ref: SyntaxSpecRef) -> SpecRef:
    return SpecRef(selector=Selector.parse(spec_ref.selector), span=spec_ref.span)


def _field_to_ir(field: SyntaxField, owner_name: str) -> FieldDef:
    type_expr = (
        TypeExpr(kind="named", name=_nested_type_name(owner_name, field.name))
        if field.fields
        else TypeExpr(kind="named", name="__ref__")
        if field.ref_selector is not None
        else _type_to_ir(_required_type_expr(field))
    )
    return FieldDef(
        name=field.name,
        type_expr=type_expr,
        default=_literal_to_ir(field.default) if field.default is not None else None,
        derived=_expression_to_ir(field.derived) if field.derived is not None else None,
        constraints=tuple(_constraint_to_ir(item) for item in field.constraints),
        metadata={key: _literal_to_ir(value) for key, value in field.metadata.items()},
        override=field.override,
        ref_selector=Selector.parse(field.ref_selector) if field.ref_selector is not None else None,
        fields=tuple(_field_to_ir(child, str(type_expr.name)) for child in field.fields),
        assertions=tuple(_assertion_to_ir(item) for item in field.assertions),
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
            field_path=assignment.field_path,
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


def _required_type_expr(field: SyntaxField) -> SyntaxTypeExpr:
    if field.type_expr is None:
        raise AssertionError(f"field '{field.name}' is missing type expression")
    return field.type_expr


def _nested_type_name(owner_name: str, field_name: str) -> str:
    return f"{owner_name}_{field_name}"


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


def _expression_to_ir(expression: SyntaxExpression) -> Expression:
    return Expression(
        kind=expression.kind,
        operator=expression.operator,
        literal=_literal_to_ir(expression.literal) if expression.literal is not None else None,
        reference=(
            ParameterReference(
                parts=expression.reference.parts,
                raw=expression.reference.raw,
                span=expression.reference.span,
            )
            if expression.reference is not None
            else None
        ),
        operands=tuple(_expression_to_ir(operand) for operand in expression.operands),
        raw=expression.raw,
        span=expression.span,
    )


def _constraint_to_ir(constraint: SyntaxComparisonConstraint) -> ComparisonConstraint:
    return ComparisonConstraint(
        left=_expression_to_ir(constraint.left),
        operator=constraint.operator,
        right=_expression_to_ir(constraint.right),
        raw=constraint.raw,
        span=constraint.span,
    )


def _assertion_to_ir(assertion: SyntaxAssertion) -> AssertionDef:
    return AssertionDef(
        name=assertion.name,
        predicates=tuple(_expression_to_ir(predicate) for predicate in assertion.predicates),
        span=assertion.span,
    )
