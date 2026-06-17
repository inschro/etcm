from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

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


def test_source_span_is_frozen() -> None:
    span = SourceSpan(
        source_path=Path("configs/data.etcm"),
        line=1,
        column=1,
        end_line=1,
        end_column=10,
    )

    with pytest.raises(FrozenInstanceError):
        span.line = 2  # type: ignore[misc]


def test_selector_parse_with_implementation() -> None:
    selector = Selector.parse("configs/train.etcm#smoke")

    assert selector.path == Path("configs/train.etcm")
    assert selector.implementation == "smoke"
    assert selector.raw == "configs/train.etcm#smoke"


def test_selector_parse_without_implementation() -> None:
    selector = Selector.parse("configs/train.etcm")

    assert selector.path == Path("configs/train.etcm")
    assert selector.implementation is None
    assert selector.raw == "configs/train.etcm"


@pytest.mark.parametrize("raw", ["", "configs/train.etcm#"])
def test_selector_parse_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        Selector.parse(raw)


def test_ir_contracts_can_be_instantiated() -> None:
    int_type = TypeExpr(kind="named", name="int")
    literal = LiteralValue(kind="int", value=2)
    field = FieldDef(name="retries", type_expr=int_type, default=literal)
    spec = SpecDef(name="DataConfig", fields=(field,))
    assignment = Assignment(field_path=("retries",), value=literal)
    ref = RefAssignment(field_name="model", selector=Selector.parse("models/lm.etcm#tiny"))
    impl = ImplDef(name="smoke", assignments=(assignment, ref))
    document = Document(source_path=Path("configs/data.etcm"), spec=spec, implementations=(impl,))

    assert document.spec == spec
    assert document.implementations == (impl,)
    assert field.metadata == {}


def test_field_metadata_is_immutable_mapping() -> None:
    field = FieldDef(
        name="train_file",
        type_expr=TypeExpr(kind="named", name="Path"),
        metadata={"path_exists": LiteralValue(kind="str", value="must_exist")},
    )

    with pytest.raises(TypeError):
        field.metadata["path_exists"] = LiteralValue(kind="str", value="allow_missing")  # type: ignore[index]


def test_document_rejects_inline_spec_and_spec_ref_together() -> None:
    with pytest.raises(ValueError, match="either spec or spec_ref"):
        Document(
            source_path=Path("configs/data.etcm"),
            spec=SpecDef(name="DataConfig"),
            spec_ref=SpecRef(path=Path("specs/data.etcm")),
        )
