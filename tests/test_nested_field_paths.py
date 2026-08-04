from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from etcm import load, resolve, validate
from etcm.errors import ETCMError
from etcm.ir import Assignment, RefAssignment
from etcm.syntax import SyntaxField, SyntaxSpec, parse_document, parse_syntax

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def test_dotted_and_indented_declarations_have_the_same_shape() -> None:
    dotted = parse_syntax(
        """spec Config:
  optimizer.lr: float = 0.001
  $optimizer.schedule: schedule.etcm#Schedule
"""
    )
    indented = parse_syntax(
        """spec Config:
  optimizer:
    lr: float = 0.001
    $schedule: schedule.etcm#Schedule
"""
    )

    dotted_spec = next(item for item in dotted.items if isinstance(item, SyntaxSpec))
    indented_spec = next(item for item in indented.items if isinstance(item, SyntaxSpec))

    assert _syntax_field_shapes(dotted_spec.fields) == _syntax_field_shapes(
        indented_spec.fields
    )


def test_mixed_implementation_forms_flatten_to_canonical_paths() -> None:
    source = FIXTURES / "valid/dotted_indented_paths.etcm"
    document = parse_document(source.read_text(encoding="utf-8"), source)
    training = next(spec for spec in document.specs if spec.name == "Training")
    optimizer = training.fields[0]

    assert [field.name for field in training.fields] == ["optimizer"]
    assert [field.name for field in optimizer.fields] == [
        "lr",
        "weight_decay",
        "schedule",
        "total",
        "options",
    ]
    assignments = training.implementations[0].assignments
    assert [assignment.field_path for assignment in assignments] == [
        ("optimizer", "lr"),
        ("optimizer", "weight_decay"),
        ("optimizer", "schedule"),
        ("optimizer", "options", "momentum"),
    ]
    assert isinstance(assignments[0], Assignment)
    assert isinstance(assignments[1], Assignment)
    assert isinstance(assignments[2], RefAssignment)
    assert isinstance(assignments[3], Assignment)


def test_top_level_spec_reuse_impl_accepts_indented_assignments() -> None:
    document = parse_document(
        """$spec: config.etcm#Config

impl nested:
  optimizer:
    learning_rate: 0.001
"""
    )

    assert document.implementations[0].assignments[0].field_path == (
        "optimizer",
        "learning_rate",
    )


def test_mixed_paths_resolve_relations_and_nested_references() -> None:
    source = FIXTURES / "valid/dotted_indented_paths.etcm"
    selector = f"{source}#Training:mixed"

    graph = validate(resolve(selector))
    root = next(node for node in graph.nodes if node.id == "root")
    optimizer = next(node for node in graph.nodes if node.id == "root.optimizer")
    schedule = next(node for node in graph.nodes if node.id == "root.optimizer.schedule")
    options = next(node for node in graph.nodes if node.id == "root.optimizer.options")

    assert root.values == {"optimizer": {"$ref": "root.optimizer"}}
    assert optimizer.values == {
        "lr": 3,
        "weight_decay": 4,
        "schedule": {"$ref": "root.optimizer.schedule"},
        "total": 7,
        "options": {"$ref": "root.optimizer.options"},
    }
    assert schedule.values == {"kind": "cosine"}
    assert options.values == {"momentum": 9}
    assert load(selector, target="dict") == {
        "optimizer": {
            "lr": 3,
            "weight_decay": 4,
            "schedule": {"kind": "cosine"},
            "total": 7,
            "options": {"momentum": 9},
        }
    }


@pytest.mark.parametrize(
    ("declarations", "code"),
    [
        ("  value.child: int\n  value.child: int\n", "E_DUPLICATE_FIELD"),
        ("  value:\n    child: int\n  value:\n    other: int\n", "E_DUPLICATE_FIELD"),
        ("  value: int\n  value.child: int\n", "E_FIELD_PATH_CONFLICT"),
        ("  value.child: int\n  value: int\n", "E_FIELD_PATH_CONFLICT"),
        ("  $value: child.etcm#Child\n  value.child: int\n", "E_FIELD_PATH_CONFLICT"),
    ],
)
def test_declaration_path_conflicts_are_rejected(declarations: str, code: str) -> None:
    with pytest.raises(ETCMError) as raised:
        parse_document(f"spec Invalid:\n{declarations}")

    assert raised.value.diagnostic.code == code


@pytest.mark.parametrize(
    "assignment",
    [
        "    child.value: 2\n",
        "    child:\n      value: 2\n",
        "    $child.grandchild: child.etcm#Child:default\n",
        "    child:\n      $grandchild: child.etcm#Child:default\n",
    ],
)
def test_implementation_paths_require_a_selected_reference(
    tmp_path: Path,
    assignment: str,
) -> None:
    child = tmp_path / "child.etcm"
    child.write_text(
        """spec Child:
  value: int = 1

  impl default:
    value: 1
""",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.etcm"
    parent.write_text(
        """spec Parent:
  $child: child.etcm#Child

  impl invalid:
"""
        + assignment,
        encoding="utf-8",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(f"{parent}#Parent:invalid")

    assert raised.value.diagnostic.code == "E_INVALID_PATH"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["reason"] == "unset_reference"


def _syntax_field_shapes(fields: tuple[SyntaxField, ...]) -> list[dict[str, Any]]:
    return [
        {
            "name": field.name,
            "type": field.type_expr.name if field.type_expr is not None else None,
            "default": field.default.value if field.default is not None else None,
            "ref": field.ref_selector,
            "fields": _syntax_field_shapes(field.fields),
        }
        for field in fields
    ]
