from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn

from etcm.ir import (
    AssertionDef,
    Document,
    FieldDef,
    ImplDef,
    ParameterReference,
    Selector,
    SourceSpan,
    SpecDef,
    TypeExpr,
)
from etcm.resolve._derivations import derived_cycle, expression_contains_current
from etcm.resolve._diagnostics import field_source_path, raise_error
from etcm.resolve._overrides import validate_override_policy
from etcm.resolve._selectors import normalize_selector, selector_text
from etcm.resolve._types import type_text
from etcm.resolve.relations import (
    RelationTypeError,
    infer_expression_type,
    type_assignable,
    validate_assertion_expression,
    validate_comparison_types,
)
from etcm.syntax import parse_file


@dataclass(frozen=True)
class ResolvedSpec:
    name: str
    source_path: Path
    fields: Mapping[str, FieldDef]
    assertions: tuple[AssertionDef, ...] = ()
    ancestors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True)
class ImplTarget:
    source_path: Path
    spec: ResolvedSpec
    implementation: ImplDef
    selector: str

    @property
    def key(self) -> tuple[Path, str, str]:
        return (self.source_path, self.spec.name, self.implementation.name)


class SpecResolver:
    def __init__(self) -> None:
        self._documents: dict[Path, Document] = {}
        self._specs: dict[tuple[Path, str], ResolvedSpec] = {}
        self._relations_validating: set[tuple[Path, str]] = set()
        self._relations_validated: set[tuple[Path, str]] = set()

    @property
    def documents(self) -> Mapping[Path, Document]:
        return MappingProxyType(self._documents)

    def resolve_implementation_selector(self, selector: Selector) -> ImplTarget:
        if selector.target != "implementation":
            raise_error(
                "E_MISSING_SELECTOR",
                "This position requires an implementation selector ending in ':implementation'.",
                selector=selector.raw,
            )
        if selector.path is None or selector.spec is None or selector.implementation is None:
            raise AssertionError("normalized implementation selector is incomplete")
        source_path = selector.path.resolve()
        document = self.load_document(source_path)
        spec = self._resolve_spec(source_path, selector.spec, ())
        implementation = self._implementation_for_spec(
            document,
            source_path,
            spec.name,
            selector.implementation,
        )
        return ImplTarget(
            source_path=source_path,
            spec=spec,
            implementation=implementation,
            selector=selector_text(source_path, spec.name, implementation.name),
        )

    def load_document(self, source_path: Path) -> Document:
        source_path = source_path.resolve()
        cached = self._documents.get(source_path)
        if cached is not None:
            return cached
        if not source_path.is_file():
            raise_error(
                "E_MISSING_SELECTOR",
                f"Selector source file does not exist: {source_path}",
                source_path=source_path,
            )
        document = parse_file(source_path)
        self._documents[source_path] = document
        return document

    def _resolve_spec(
        self,
        source_path: Path,
        spec_name: str,
        stack: tuple[tuple[Path, str], ...],
    ) -> ResolvedSpec:
        source_path = source_path.resolve()
        key = (source_path, spec_name)
        cached = self._specs.get(key)
        if cached is not None:
            return cached
        if key in stack:
            raise_error(
                "E_SPEC_CYCLE",
                "Cycle while resolving spec inheritance.",
                source_path=source_path,
                details={"chain": [selector_text(path, name) for path, name in stack]},
            )

        document = self.load_document(source_path)

        if document.spec_ref is not None:
            spec = self._resolve_spec_selector(
                document.spec_ref.selector,
                source_path,
                (*stack, key),
                require_path=True,
            )
            if spec.name != spec_name:
                raise_error(
                    "E_MISSING_SELECTOR",
                    f"Spec '{spec_name}' not found.",
                    source_path=source_path,
                    selector=selector_text(source_path, spec_name, None),
                    details={"available": [spec.name]},
                )
            self._specs[key] = spec
            self._relations_validated.add(key)
            return spec

        if not document.specs:
            raise_error("E_MISSING_SELECTOR", "Document has no spec.", source_path=source_path)

        spec_def = self._select_spec(document, source_path, spec_name)

        fields: dict[str, FieldDef] = {}
        assertions: list[AssertionDef] = []
        ancestors: tuple[str, ...] = ()
        if spec_def.parent is not None:
            parent = self._resolve_spec_selector(spec_def.parent, source_path, (*stack, key))
            fields.update(parent.fields)
            assertions.extend(parent.assertions)
            ancestors = (parent.name, *parent.ancestors)

        for raw_field_def in spec_def.fields:
            field_def = self._resolve_field_def(
                raw_field_def,
                source_path=source_path,
                stack=(*stack, key),
            )
            if field_def.name in fields:
                raise_error(
                    "E_TYPE_MISMATCH",
                    f"Spec '{spec_def.name}' redefines inherited field '{field_def.name}'.",
                    source_path=source_path,
                    span=field_def.span,
                    details={"field": field_def.name},
                )
            fields[field_def.name] = field_def

        inherited_assertions = {assertion.name: assertion for assertion in assertions}
        for assertion in spec_def.assertions:
            previous = inherited_assertions.get(assertion.name)
            if previous is not None:
                raise_error(
                    "E_DUPLICATE_ASSERTION",
                    f"Assertion '{assertion.name}' is already inherited by "
                    f"spec '{spec_def.name}'.",
                    source_path=source_path,
                    span=assertion.span,
                    details={
                        "assertion": assertion.name,
                        "owner": spec_def.name,
                        "previous_source_path": (
                            previous.span.source_path.as_posix()
                            if previous.span is not None
                            else None
                        ),
                        "previous_line": (
                            previous.span.line if previous.span is not None else None
                        ),
                    },
                )
            inherited_assertions[assertion.name] = assertion
            assertions.append(assertion)

        spec = ResolvedSpec(
            name=spec_def.name,
            source_path=source_path,
            fields=fields,
            assertions=tuple(assertions),
            ancestors=ancestors,
        )
        self._specs[key] = spec
        self._validate_spec_relations(key, spec)
        return spec

    def _resolve_spec_selector(
        self,
        selector: Selector,
        declaring_source: Path,
        stack: tuple[tuple[Path, str], ...],
        *,
        require_path: bool = False,
    ) -> ResolvedSpec:
        if selector.target != "spec":
            raise_error(
                "E_MISSING_SELECTOR",
                "This position requires a spec selector such as 'path.etcm#Spec' or '#Spec'.",
                source_path=declaring_source.resolve(),
                selector=selector.raw,
            )
        resolved = normalize_selector(
            selector,
            declaring_source=declaring_source,
            active_spec=None,
            require_path=require_path,
        )
        if resolved.path is None or resolved.spec is None:
            raise AssertionError("normalized spec selector is incomplete")
        return self._resolve_spec(resolved.path, resolved.spec, stack)

    def _implementation_for_spec(
        self,
        document: Document,
        source_path: Path,
        spec_name: str,
        implementation_name: str,
    ) -> ImplDef:
        if document.spec_ref is not None:
            spec = self._resolve_spec(source_path, spec_name, ())
            implementations = document.implementations
            available_specs = [spec.name]
        else:
            spec_def = self._select_spec(document, source_path, spec_name)
            implementations = spec_def.implementations
            available_specs = [spec.name for spec in document.specs]

        for implementation in implementations:
            if implementation.name == implementation_name:
                return implementation

        raise_error(
            "E_MISSING_SELECTOR",
            f"Implementation '{implementation_name}' not found for spec '{spec_name}'.",
            source_path=source_path,
            selector=selector_text(source_path, spec_name, implementation_name),
            details={
                "spec": spec_name,
                "available_specs": available_specs,
                "available_implementations": [
                    implementation.name for implementation in implementations
                ],
            },
        )

    def _select_spec(
        self,
        document: Document,
        source_path: Path,
        spec_name: str,
    ) -> SpecDef:
        for spec in document.specs:
            if spec.name == spec_name:
                return spec
        raise_error(
            "E_MISSING_SELECTOR",
            f"Spec '{spec_name}' not found.",
            source_path=source_path,
            selector=selector_text(source_path, spec_name, None),
            details={"candidates": [spec.name for spec in document.specs]},
        )

    def _resolve_field_def(
        self,
        field: FieldDef,
        *,
        source_path: Path,
        stack: tuple[tuple[Path, str], ...],
    ) -> FieldDef:
        if field.ref_selector is not None:
            target = self._resolve_spec_selector(field.ref_selector, source_path, stack)
            return replace(field, type_expr=TypeExpr(kind="named", name=target.name))

        if field.fields:
            return replace(
                field,
                fields=tuple(
                    self._resolve_field_def(child, source_path=source_path, stack=stack)
                    for child in field.fields
                ),
            )

        return field

    def _validate_spec_relations(
        self,
        key: tuple[Path, str],
        spec: ResolvedSpec,
    ) -> None:
        if key in self._relations_validated or key in self._relations_validating:
            return
        self._relations_validating.add(key)
        try:
            self._validate_relation_group(
                owner_name=spec.name,
                source_path=spec.source_path,
                fields=spec.fields,
                assertions=spec.assertions,
            )
        finally:
            self._relations_validating.discard(key)
        self._relations_validated.add(key)

    def _validate_relation_group(
        self,
        *,
        owner_name: str,
        source_path: Path,
        fields: Mapping[str, FieldDef],
        assertions: tuple[AssertionDef, ...],
    ) -> None:
        for field in fields.values():
            validate_override_policy(field, source_path)

            def reference_type(
                reference: ParameterReference,
                current: FieldDef = field,
            ) -> TypeExpr:
                return self._relation_reference_type(
                    owner_name=owner_name,
                    source_path=source_path,
                    fields=fields,
                    current_field=current,
                    reference=reference,
                )
            if field.derived is not None:
                if field.default is not None:
                    raise_error(
                        "E_EXPRESSION_TYPE",
                        f"Derived parameter '{field.name}' cannot also have a default.",
                        source_path=field_source_path(field, source_path),
                        span=field.span,
                        details={"field": field.name},
                    )
                if expression_contains_current(field.derived):
                    raise_error(
                        "E_PARAMETER_REFERENCE",
                        f"Derived parameter '{field.name}' cannot reference its current value.",
                        source_path=field_source_path(field, source_path),
                        span=field.derived.span,
                        details={"field": field.name},
                    )
                try:
                    actual_type = infer_expression_type(
                        field.derived,
                        current_type=field.type_expr,
                        reference_type=reference_type,
                    )
                except RelationTypeError as exc:
                    self._raise_relation_type_error(
                        exc,
                        field=field,
                        source_path=source_path,
                        raw=field.derived.raw,
                        span=field.derived.span,
                    )
                if not type_assignable(actual_type, field.type_expr):
                    raise_error(
                        "E_EXPRESSION_TYPE",
                        f"Derived expression for '{field.name}' produces "
                        f"'{type_text(actual_type)}', which is not assignable to "
                        f"'{type_text(field.type_expr)}'.",
                        source_path=field_source_path(field, source_path),
                        span=field.derived.span,
                        details={
                            "field": field.name,
                            "expression": field.derived.raw,
                            "actual": type_text(actual_type),
                            "expected": type_text(field.type_expr),
                        },
                    )

            for constraint in field.constraints:
                try:
                    validate_comparison_types(
                        constraint,
                        current_type=field.type_expr,
                        reference_type=reference_type,
                    )
                except RelationTypeError as exc:
                    self._raise_relation_type_error(
                        exc,
                        field=field,
                        source_path=source_path,
                        raw=constraint.raw,
                        span=constraint.span,
                    )

            if field.fields:
                self._validate_relation_group(
                    owner_name=str(field.type_expr.name),
                    source_path=field_source_path(field, source_path),
                    fields={child.name: child for child in field.fields},
                    assertions=field.assertions,
                )

        for assertion in assertions:
            for predicate in assertion.predicates:
                try:
                    validate_assertion_expression(
                        predicate,
                        reference_type=lambda reference, current=assertion: (
                            self._assertion_reference_type(
                                owner_name=owner_name,
                                source_path=source_path,
                                fields=fields,
                                assertion=current,
                                reference=reference,
                            )
                        ),
                    )
                except RelationTypeError as exc:
                    raise_error(
                        "E_EXPRESSION_TYPE",
                        f"Invalid expression in assertion '{assertion.name}': {exc}",
                        source_path=(
                            assertion.span.source_path
                            if assertion.span is not None
                            else source_path
                        ),
                        span=predicate.span,
                        details={
                            "assertion": assertion.name,
                            "expression": predicate.raw,
                            **exc.details,
                        },
                    )

        cycle = derived_cycle(fields)
        if cycle is not None:
            first = fields[cycle[0]]
            raise_error(
                "E_DERIVED_CYCLE",
                "Derived parameter cycle detected.",
                source_path=field_source_path(first, source_path),
                span=first.derived.span if first.derived is not None else first.span,
                details={"owner": owner_name, "chain": cycle},
            )

    def _relation_reference_type(
        self,
        *,
        owner_name: str,
        source_path: Path,
        fields: Mapping[str, FieldDef],
        current_field: FieldDef,
        reference: ParameterReference,
    ) -> TypeExpr:
        if reference.parts == (current_field.name,):
            raise_error(
                "E_PARAMETER_REFERENCE",
                f"Parameter '{current_field.name}' cannot reference itself.",
                source_path=field_source_path(current_field, source_path),
                span=reference.span,
                details={"field": current_field.name, "reference": reference.raw},
            )

        active_fields = fields
        active_source = source_path
        for index, part in enumerate(reference.parts):
            target = active_fields.get(part)
            if target is None:
                raise_error(
                    "E_PARAMETER_REFERENCE",
                    f"Unknown parameter reference '{reference.raw}'.",
                    source_path=field_source_path(current_field, source_path),
                    span=reference.span,
                    details={
                        "field": current_field.name,
                        "reference": reference.raw,
                        "resolved_prefix": ".".join(reference.parts[:index]),
                        "missing_segment": part,
                        "available_parameters": list(active_fields),
                        "owner": owner_name,
                    },
                )

            is_final = index == len(reference.parts) - 1
            is_object = bool(target.fields) or target.ref_selector is not None
            if is_final:
                if is_object:
                    raise_error(
                        "E_PARAMETER_REFERENCE",
                        f"Parameter reference '{reference.raw}' must end at a scalar field.",
                        source_path=field_source_path(current_field, source_path),
                        span=reference.span,
                        details={"field": current_field.name, "reference": reference.raw},
                    )
                return target.type_expr

            if target.fields:
                active_fields = {child.name: child for child in target.fields}
                active_source = field_source_path(target, active_source)
                continue
            if target.ref_selector is not None:
                declaring_source = field_source_path(target, active_source)
                target_spec = self._resolve_spec_selector(
                    target.ref_selector,
                    declaring_source,
                    (),
                )
                active_fields = target_spec.fields
                active_source = target_spec.source_path
                continue
            raise_error(
                "E_PARAMETER_REFERENCE",
                f"Parameter reference '{reference.raw}' cannot traverse scalar field "
                f"'{part}'.",
                source_path=field_source_path(current_field, source_path),
                span=reference.span,
                details={
                    "field": current_field.name,
                    "reference": reference.raw,
                    "scalar_segment": part,
                    "scalar_type": type_text(target.type_expr),
                },
            )
        raise AssertionError("parameter reference path is empty")

    def _assertion_reference_type(
        self,
        *,
        owner_name: str,
        source_path: Path,
        fields: Mapping[str, FieldDef],
        assertion: AssertionDef,
        reference: ParameterReference,
    ) -> TypeExpr:
        assertion_source = (
            assertion.span.source_path if assertion.span is not None else source_path
        )
        active_fields = fields
        active_source = source_path
        for index, part in enumerate(reference.parts):
            target = active_fields.get(part)
            if target is None:
                raise_error(
                    "E_PARAMETER_REFERENCE",
                    f"Unknown parameter reference '{reference.raw}' in assertion "
                    f"'{assertion.name}'.",
                    source_path=assertion_source,
                    span=reference.span,
                    details={
                        "assertion": assertion.name,
                        "reference": reference.raw,
                        "resolved_prefix": ".".join(reference.parts[:index]),
                        "missing_segment": part,
                        "available_parameters": list(active_fields),
                        "owner": owner_name,
                    },
                )

            is_final = index == len(reference.parts) - 1
            is_object = bool(target.fields) or target.ref_selector is not None
            if is_final:
                if is_object:
                    raise_error(
                        "E_PARAMETER_REFERENCE",
                        f"Parameter reference '{reference.raw}' in assertion "
                        "must end at a scalar field.",
                        source_path=assertion_source,
                        span=reference.span,
                        details={
                            "assertion": assertion.name,
                            "reference": reference.raw,
                        },
                    )
                return target.type_expr

            if target.fields:
                active_fields = {child.name: child for child in target.fields}
                active_source = field_source_path(target, active_source)
                continue
            if target.ref_selector is not None:
                declaring_source = field_source_path(target, active_source)
                target_spec = self._resolve_spec_selector(
                    target.ref_selector,
                    declaring_source,
                    (),
                )
                active_fields = target_spec.fields
                active_source = target_spec.source_path
                continue
            raise_error(
                "E_PARAMETER_REFERENCE",
                f"Parameter reference '{reference.raw}' in assertion cannot traverse "
                f"scalar field '{part}'.",
                source_path=assertion_source,
                span=reference.span,
                details={
                    "assertion": assertion.name,
                    "reference": reference.raw,
                    "scalar_segment": part,
                    "scalar_type": type_text(target.type_expr),
                },
            )
        raise AssertionError("parameter reference path is empty")

    def _raise_relation_type_error(
        self,
        error: RelationTypeError,
        *,
        field: FieldDef,
        source_path: Path,
        raw: str | None,
        span: SourceSpan | None,
    ) -> NoReturn:
        raise_error(
            "E_EXPRESSION_TYPE",
            f"Invalid parameter expression for '{field.name}': {error}",
            source_path=field_source_path(field, source_path),
            span=span,
            details={"field": field.name, "expression": raw, **error.details},
        )
