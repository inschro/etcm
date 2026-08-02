from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from etcm import convert, load, resolve, validate
from etcm.errors import ETCMError
from etcm.resolve.relations import render_expression
from etcm.syntax import SyntaxSpec, parse_document, parse_syntax

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def _write_config(tmp_path: Path, text: str, name: str = "config.etcm") -> Path:
    path = tmp_path / name
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def test_dotted_relations_traverse_inline_and_referenced_objects() -> None:
    selector = str(
        FIXTURES
        / "valid/parameter_relations/training.etcm#TrainingConfig:distributed"
    )

    graph = resolve(selector)
    root = next(node for node in graph.nodes if node.id == "root")

    assert graph.validated is False
    assert root.values["global_batch_size"] == 32
    assert root.values["copied_seed"] == 42
    assert root.values["copied_child_total"] == 12
    assert root.values["copied_inline_total"] == 32
    assert root.field_values["global_batch_size"].origin == "derived"
    assert validate(graph).validated is True
    assert load(selector, target="dict")["global_batch_size"] == 32


def test_relation_syntax_and_ir_preserve_structured_references() -> None:
    source = FIXTURES / "valid/parameter_relations/training.etcm"
    text = source.read_text(encoding="utf-8")

    syntax = parse_syntax(text, source)
    syntax_spec = next(item for item in syntax.items if isinstance(item, SyntaxSpec))
    syntax_fields = {field.name: field for field in syntax_spec.fields}
    syntax_expression = syntax_fields["copied_seed"].derived
    assert syntax_expression is not None
    assert syntax_expression.reference is not None
    assert syntax_expression.reference.parts == ("dataloader", "sampler", "seed")
    assert syntax_expression.reference.span is not None

    document = parse_document(text, source)
    fields = {field.name: field for field in document.specs[0].fields}
    expression = fields["global_batch_size"].derived
    assert expression is not None
    assert expression.kind == "binary"
    assert expression.operator == "*"
    assert expression.span is not None
    assert expression.span.line == 11
    left_product = expression.operands[0]
    assert left_product.span is not None
    assert (left_product.span.line, left_product.span.end_line) == (11, 12)
    assert left_product.raw == (
        "@dataloader.local_batch_size\n    * @gradient_accumulation_steps"
    )
    assert fields["aligned_batch"].constraints[0].raw == (
        "% @dataloader.sampler.alignment == 0"
    )
    with pytest.raises(FrozenInstanceError):
        expression.operator = "+"  # type: ignore[misc]


def test_generated_views_include_derived_values() -> None:
    selector = str(
        FIXTURES
        / "valid/parameter_relations/training.etcm#TrainingConfig:distributed"
    )
    graph = validate(resolve(selector))

    dataclass_value: Any = convert(graph, target="dataclass")
    pydantic_value: Any = convert(graph, target="pydantic")

    assert dataclass_value.global_batch_size == 32
    assert pydantic_value.copied_seed == 42


def test_expression_precedence_matches_python(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Math:
  base: int = 2
  negative_power: int := -2 ** 2
  grouped_power: int := (-2) ** 2
  right_associative: int := 2 ** 3 ** 2
  floor_value: int := 7 // 2
  ratio: float := 7 / 2

  impl values:
    base: 2
""",
    )

    root = next(node for node in resolve(f"{source}#Math:values").nodes if node.id == "root")

    assert root.values["negative_power"] == -4
    assert root.values["grouped_power"] == 4
    assert root.values["right_associative"] == 512
    assert root.values["floor_value"] == 3
    assert root.values["ratio"] == 3.5
    grouped = root.fields["grouped_power"].derived
    assert grouped is not None
    assert render_expression(grouped) == "(-2) ** 2"


def test_all_arithmetic_and_comparison_operators(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Operators:
  other: int = 4
  value: int = 9 [
    ==9;
    !=8;
    > @other;
    >=9;
    <10;
    <=9;
    + @other == 13;
    - @other == 5;
    * @other == 36;
    / @other == 2.25;
    // @other == 2;
    % @other == 1;
    ** 2 == 81
  ]
  unary_plus: int := +@other

  impl valid:
    value: 9
""",
    )

    graph = validate(resolve(f"{source}#Operators:valid"))
    root = next(node for node in graph.nodes if node.id == "root")

    assert root.values["unary_plus"] == 4
    assert [item.operator for item in root.fields["value"].constraints] == [
        "==",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "==",
        "==",
        "==",
        "==",
        "==",
        "==",
        "==",
    ]


def test_forward_parameter_reference_is_resolved(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Forward:
  result: int := @later + 1
  later: int = 4

  impl default:
    later: 4
""",
    )

    assert load(f"{source}#Forward:default", target="dict")["result"] == 5


def test_scalar_copy_null_and_path_equality(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Scalars:
  name: str = "stable"
  copied_name: str := @name [== @name]
  enabled: bool = true
  confirmed: bool [== @enabled]
  maybe: int | null = null [== null]
  source_path: Path = "artifact.bin"
  copied_path: Path := @source_path [== @source_path]

  impl default:
    confirmed: true
""",
    )

    loaded = load(f"{source}#Scalars:default", target="dict")

    assert loaded["copied_name"] == "stable"
    assert loaded["maybe"] is None
    assert loaded["copied_path"] == loaded["source_path"]


def test_multiline_string_derivation_preserves_hash_characters(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Text:
  marker: int = 0
  message: str :=
    "stable # value"

  impl default:
    marker: 0
""",
    )

    loaded = load(f"{source}#Text:default", target="dict")

    assert loaded["message"] == "stable # value"


@pytest.mark.parametrize(
    ("field_text", "code"),
    [
        ("total: int := @missing + 1", "E_PARAMETER_REFERENCE"),
        ("total: int := @value.missing", "E_PARAMETER_REFERENCE"),
        ("total: int := @total + 1", "E_PARAMETER_REFERENCE"),
        ("total: int := @label + 1", "E_EXPRESSION_TYPE"),
        ("total: int := @values", "E_EXPRESSION_TYPE"),
        ("total: int := @used / @available", "E_EXPRESSION_TYPE"),
        ("total: float := @used % 2.0", "E_EXPRESSION_TYPE"),
        ("total: int = 1 [== @label]", "E_EXPRESSION_TYPE"),
    ],
)
def test_invalid_reference_and_expression_types_fail_during_resolve(
    tmp_path: Path,
    field_text: str,
    code: str,
) -> None:
    source = _write_config(
        tmp_path,
        f"""
spec Invalid:
  value: int = 1
  label: str = "one"
  values: list[int] = [1]
  used: int = 4
  available: int = 2
  {field_text}

  impl default:
    value: 1
""",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Invalid:default")

    assert raised.value.diagnostic.code == code


def test_reference_must_end_at_scalar_leaf(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Invalid:
  child:
    value: int = 1
  copied: int := @child

  impl default:
    child.value: 1
""",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Invalid:default")

    assert raised.value.diagnostic.code == "E_PARAMETER_REFERENCE"


def test_derived_cycle_is_a_spec_error(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Cycle:
  marker: int = 0
  first: int := @second + 1
  second: int := @first + 1

  impl default:
    marker: 0
""",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Cycle:default")

    assert raised.value.diagnostic.code == "E_DERIVED_CYCLE"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["chain"] == ("first", "second", "first")


def test_assigning_derived_parameter_is_rejected(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Derived:
  source: int = 2
  total: int := @source * 2

  impl invalid:
    total: 3
""",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Derived:invalid")

    assert raised.value.diagnostic.code == "E_DERIVED_ASSIGNMENT"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["expression"] == "@source * 2"


def test_inherited_derived_values_are_recomputed(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Derived:
  source: int
  total: int := @source * 2

  impl base:
    source: 2

  impl child <- :base:
    source: 3
""",
    )

    graph = resolve(f"{source}#Derived:child")
    nodes = {node.id: node for node in graph.nodes}

    assert nodes["root.__parent"].values["total"] == 4
    assert nodes["root"].values["total"] == 6


def test_relational_failure_reports_operands_and_evaluation(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Model:
  attention_heads: int [>0]
  hidden_size: int [% @attention_heads == 0]

  impl invalid:
    attention_heads: 12
    hidden_size: 512
""",
    )
    graph = resolve(f"{source}#Model:invalid")

    with pytest.raises(ETCMError) as raised:
        validate(graph)

    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "E_CONSTRAINT"
    assert diagnostic.details is not None
    assert diagnostic.details["constraint"] == "% @attention_heads == 0"
    assert diagnostic.details["resolved_values"] == {
        "hidden_size": 512,
        "attention_heads": 12,
    }
    assert diagnostic.details["evaluation"] == ["512 % 12 == 0", "8 == 0"]


def test_derived_constraint_runs_after_derivation(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec DerivedConstraint:
  left: int = 2
  right: int = 3
  total: int := @left + @right [>10]

  impl invalid:
    left: 2
""",
    )

    graph = resolve(f"{source}#DerivedConstraint:invalid")
    assert next(node for node in graph.nodes if node.id == "root").values["total"] == 5
    with pytest.raises(ETCMError) as raised:
        validate(graph)
    assert raised.value.diagnostic.code == "E_CONSTRAINT"


def test_arithmetic_runtime_errors_are_wrapped(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Division:
  numerator: int = 1
  denominator: int = 0
  ratio: float := @numerator / @denominator

  impl invalid:
    numerator: 1
""",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Division:invalid")

    assert raised.value.diagnostic.code == "E_EXPRESSION_EVALUATION"


@pytest.mark.parametrize(
    ("field_type", "expression"),
    [
        ("float", "1e309"),
        ("float", "(-1) ** 0.5"),
        ("int", "2 ** 10001"),
    ],
)
def test_unsafe_numeric_results_are_rejected(
    tmp_path: Path,
    field_type: str,
    expression: str,
) -> None:
    source = _write_config(
        tmp_path,
        f"""
spec Unsafe:
  marker: int = 0
  result: {field_type} := {expression}

  impl invalid:
    marker: 0
""",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Unsafe:invalid")

    assert raised.value.diagnostic.code == "E_EXPRESSION_EVALUATION"


def test_missing_derived_dependency_fails_resolve(tmp_path: Path) -> None:
    source = _write_config(
        tmp_path,
        """
spec Missing:
  source: int
  marker: int = 0
  total: int := @source * 2

  impl invalid:
    marker: 0
""",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Missing:invalid")

    assert raised.value.diagnostic.code == "E_MISSING_FIELD"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["required_by"] == "root.total"


@pytest.mark.parametrize(
    "expression",
    ["@values[0]", "max(@left, @right)", "@left > 0 and @right > 0"],
)
def test_out_of_scope_expression_syntax_is_rejected(
    tmp_path: Path,
    expression: str,
) -> None:
    source = _write_config(
        tmp_path,
        f"""
spec InvalidSyntax:
  left: int = 1
  right: int = 2
  values: list[int] = [1]
  total: int := {expression}
""",
    )

    with pytest.raises(ETCMError) as raised:
        parse_document(source.read_text(encoding="utf-8"), source)

    assert raised.value.diagnostic.code == "E_PARSE_UNEXPECTED_TOKEN"


def test_dotted_assignments_still_cannot_write_through_references(tmp_path: Path) -> None:
    child = _write_config(
        tmp_path,
        """
spec Child:
  value: int = 1

  impl default:
    value: 1
""",
        "child.etcm",
    )
    assert child.is_file()
    parent = _write_config(
        tmp_path,
        """
spec Parent:
  $child: child.etcm#Child

  impl invalid:
    child.value: 2
""",
        "parent.etcm",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{parent}#Parent:invalid")

    assert raised.value.diagnostic.code == "E_INVALID_PATH"
