from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from etcm import load, resolve, validate
from etcm.cli import main
from etcm.codegen import pydantic_schema_summary
from etcm.errors import ETCMError
from etcm.syntax import SyntaxAssertion, SyntaxSpec, parse_document, parse_syntax


def _write(tmp_path: Path, source: str, name: str = "config.etcm") -> Path:
    path = tmp_path / name
    path.write_text(dedent(source).lstrip(), encoding="utf-8")
    return path


def test_assertion_syntax_and_ir_preserve_named_predicates(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        """
        spec Config:
          model:
            hidden_size: int = 128
            attention_heads: int = 8

            assert local_shape:
              @hidden_size % @attention_heads == 0
              @hidden_size == 128

          timeout: int | null = null
          assert timeout_valid: @timeout == null or @timeout > 0

          impl default:
            model.hidden_size: 128
        """,
    )

    syntax = parse_syntax(source.read_text(encoding="utf-8"), source)
    syntax_spec = syntax.items[0]
    assert isinstance(syntax_spec, SyntaxSpec)
    root_assertion = syntax_spec.assertions[0]
    nested_assertion = syntax_spec.fields[0].assertions[0]

    assert isinstance(root_assertion, SyntaxAssertion)
    assert root_assertion.name == "timeout_valid"
    assert root_assertion.predicates[0].operator == "or"
    assert nested_assertion.name == "local_shape"
    assert len(nested_assertion.predicates) == 2
    assert nested_assertion.predicates[0].span is not None

    document = parse_document(source.read_text(encoding="utf-8"), source)
    assert document.specs[0].assertions[0].name == "timeout_valid"
    assert document.specs[0].fields[0].assertions[0].name == "local_shape"


def test_assertions_reach_downward_across_inline_branches_and_recompute(
    tmp_path: Path,
) -> None:
    source = _write(
        tmp_path,
        """
        spec Training:
          model:
            hidden_size: int = 128
            attention_heads: int = 8
            head_size: int := @hidden_size // @attention_heads

            assert local_shape:
              @hidden_size % @attention_heads == 0

          runtime:
            partition_size: int = 64
            devices: int = 2

          assert distributed_shape:
            @model.hidden_size == @runtime.partition_size * @runtime.devices
            @model.head_size == @model.hidden_size // @model.attention_heads

          impl default:
            model.hidden_size: 128
            runtime.partition_size: 64
        """,
    )

    loaded = load(
        f"{source}#Training:default",
        target="dict",
        overrides={"model.hidden_size": 256, "runtime.partition_size": 128},
    )

    assert loaded["model"]["hidden_size"] == 256
    assert loaded["model"]["head_size"] == 32


def test_assertions_reach_through_typed_cross_file_children(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
        spec Model:
          shape:
            hidden_size: int
            attention_heads: int

            assert divisible:
              @hidden_size % @attention_heads == 0

          impl base:
            shape.hidden_size: 128
            shape.attention_heads: 8
        """,
        "model.etcm",
    )
    parent = _write(
        tmp_path,
        """
        spec Training:
          $model: model.etcm#Model
          partition_size: int = 64
          devices: int = 2

          assert distributed_shape:
            @model.shape.hidden_size == @partition_size * @devices

          impl default:
            $model: model.etcm#Model:base
        """,
        "training.etcm",
    )

    graph = validate(resolve(f"{parent}#Training:default"))

    assert graph.validated is True
    assert {node.id for node in graph.nodes} == {
        "root",
        "root.model",
        "root.model.shape",
    }


def test_assertion_block_stops_at_first_failed_predicate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write(
        tmp_path,
        """
        spec Config:
          value: int = 4

          assert expected_value:
            @value > 0
            @value == 8
            1 / 0 == 0

          impl default:
            value: 4
        """,
    )

    exit_code = main(["validate", f"{source}#Config:default", "--short"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "E_ASSERTION: Assertion 'expected_value' failed." in captured.err
    assert "assertion:\n  expected_value" in captured.err
    assert "failed expression:\n  @value == 8" in captured.err
    assert "1 / 0" not in captured.err


def test_assertion_evaluation_errors_report_the_assertion_name(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        """
        spec Config:
          numerator: int = 1
          denominator: int = 0
          assert ratio_is_positive: @numerator / @denominator > 0

          impl default:
            numerator: 1
        """,
    )

    with pytest.raises(ETCMError) as raised:
        validate(resolve(f"{source}#Config:default"))

    assert raised.value.diagnostic.code == "E_EXPRESSION_EVALUATION"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["assertion"] == "ratio_is_positive"


@pytest.mark.parametrize(
    ("value", "valid"),
    [("null", True), ("4", True), ("-1", False)],
)
def test_nullable_assertions_narrow_after_short_circuit_guards(
    tmp_path: Path,
    value: str,
    valid: bool,
) -> None:
    source = _write(
        tmp_path,
        f"""
        spec Config:
          timeout: int | null = null

          assert timeout_valid:
            @timeout == null or @timeout > 0
            not (@timeout != null and @timeout < 0)

          impl default:
            timeout: {value}
        """,
    )

    if valid:
        assert load(f"{source}#Config:default", target="dict")["timeout"] in {None, 4}
    else:
        with pytest.raises(ETCMError) as raised:
            load(f"{source}#Config:default", target="dict")
        assert raised.value.diagnostic.code == "E_ASSERTION"
        assert raised.value.diagnostic.details is not None
        assert raised.value.diagnostic.details["assertion"] == "timeout_valid"


def test_boolean_precedence_and_parenthesized_multiline_predicates(
    tmp_path: Path,
) -> None:
    source = _write(
        tmp_path,
        """
        spec Config:
          enabled: bool = true
          count: int = 2

          assert boolean_rules:
            true or false and false
            not false and @enabled
            (
              @count > 0
              and @count < 4
            )

          impl default:
            enabled: true
        """,
    )

    assert validate(resolve(f"{source}#Config:default")).validated is True


@pytest.mark.parametrize(
    ("assertion", "code"),
    [
        ("@missing == 1", "E_PARAMETER_REFERENCE"),
        ("@model == 1", "E_PARAMETER_REFERENCE"),
        ("@values.item == 1", "E_PARAMETER_REFERENCE"),
        ("@value", "E_EXPRESSION_TYPE"),
        ("@timeout > 0", "E_EXPRESSION_TYPE"),
    ],
)
def test_invalid_assertion_references_and_types_fail_during_resolve(
    tmp_path: Path,
    assertion: str,
    code: str,
) -> None:
    source = _write(
        tmp_path,
        f"""
        spec Config:
          value: int = 1
          timeout: int | null = null
          values: list[int] = [1]
          model:
            size: int = 1

          assert invalid: {assertion}

          impl default:
            value: 1
        """,
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Config:default")

    assert raised.value.diagnostic.code == code


@pytest.mark.parametrize("reference", ["@parent.value", "@root.value"])
def test_nested_assertions_cannot_discover_parent_or_root(
    tmp_path: Path,
    reference: str,
) -> None:
    source = _write(
        tmp_path,
        f"""
        spec Config:
          value: int = 1
          nested:
            local: int = 1
            assert invalid: {reference} == @local

          impl default:
            value: 1
        """,
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Config:default")

    assert raised.value.diagnostic.code == "E_PARAMETER_REFERENCE"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["missing_segment"] in {"parent", "root"}


def test_assertions_accumulate_under_spec_inheritance(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        """
        spec Base:
          value: int
          assert positive: @value > 0

          impl base:
            value: 5

        spec Child <- #Base:
          assert bounded: @value < 10

          impl default:
            value: 5
        """,
    )

    graph = validate(resolve(f"{source}#Child:default"))
    root = next(node for node in graph.nodes if node.id == "root")

    assert [assertion.name for assertion in root.assertions] == ["positive", "bounded"]


def test_inherited_assertion_names_cannot_be_replaced(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        """
        spec Base:
          value: int
          assert stable: @value > 0

        spec Child <- #Base:
          assert stable: @value < 10

          impl default:
            value: 5
        """,
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{source}#Child:default")

    assert raised.value.diagnostic.code == "E_DUPLICATE_ASSERTION"


def test_local_duplicate_assertions_are_rejected(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        """
        spec Config:
          value: int = 1
          assert stable: @value > 0
          assert stable: @value < 10
        """,
    )

    with pytest.raises(ETCMError) as raised:
        parse_document(source.read_text(encoding="utf-8"), source)

    assert raised.value.diagnostic.code == "E_DUPLICATE_ASSERTION"


def test_assertions_cannot_be_declared_in_implementations(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        """
        spec Config:
          value: int = 1

          impl default:
            assert invalid: @value > 0
        """,
    )

    with pytest.raises(ETCMError) as raised:
        parse_document(source.read_text(encoding="utf-8"), source)

    assert raised.value.diagnostic.code == "E_PARSE_UNEXPECTED_TOKEN"


@pytest.mark.parametrize(
    "predicate",
    ["@value < 2 < 3", "max(@value, 2) == 2", "@values[0] == 1"],
)
def test_out_of_scope_assertion_syntax_is_rejected(
    tmp_path: Path,
    predicate: str,
) -> None:
    source = _write(
        tmp_path,
        f"""
        spec Config:
          value: int = 1
          values: list[int] = [1]
          assert invalid: {predicate}
        """,
    )

    with pytest.raises(ETCMError) as raised:
        parse_document(source.read_text(encoding="utf-8"), source)

    assert raised.value.diagnostic.code == "E_PARSE_UNEXPECTED_TOKEN"


def test_assertions_serialize_and_appear_in_schema_summaries(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        """
        spec Config:
          value: int = 4
          assert positive: @value > 0

          impl default:
            value: 4
        """,
    )
    graph = validate(resolve(f"{source}#Config:default"))
    root_payload = next(node for node in graph.to_dict()["nodes"] if node["id"] == "root")
    summary: dict[str, Any] = pydantic_schema_summary(graph)

    assert root_payload["assertions"][0]["name"] == "positive"
    assert root_payload["assertions"][0]["predicates"][0]["operator"] == ">"
    assert summary["classes"][0]["assertions"] == [
        {"name": "positive", "predicates": ["@value > 0"]}
    ]
