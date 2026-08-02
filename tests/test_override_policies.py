from __future__ import annotations

from pathlib import Path
from textwrap import dedent, indent

import pytest

from etcm import resolve, validate
from etcm.errors import ETCMError
from etcm.resolve import ResolvedGraph, ResolvedNode, ResolvedValue


def _write_config(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "config.etcm"
    path.write_text(dedent(source).lstrip(), encoding="utf-8")
    return path


def _root(graph: ResolvedGraph) -> ResolvedNode:
    return next(node for node in graph.nodes if node.id == "root")


def _value(graph: ResolvedGraph, field_name: str) -> ResolvedValue:
    return _root(graph).field_values[field_name]


@pytest.mark.parametrize(
    ("declarations", "reason"),
    [
        ('value: int [override="unknown"]', "unknown_policy"),
        ('value: int [override="deny"]', "missing_inline_default"),
        ('value: int [override="append"]', "incompatible_type"),
        (
            'value: list[int] | null = null [override="append"]',
            "incompatible_type",
        ),
        ('value: dict[int, str] [override="merge"]', "incompatible_type"),
        (
            'value: dict[str, int] | null = null [override="merge"]',
            "incompatible_type",
        ),
        (
            'source: int = 1\nvalue: int := @source [override="deny"]',
            "derived_parameter",
        ),
    ],
)
def test_invalid_override_declarations_fail_during_resolution(
    tmp_path: Path,
    declarations: str,
    reason: str,
) -> None:
    source = (
        "spec Config:\n"
        f"{indent(declarations, '  ')}\n"
        "  marker: int = 0\n\n"
        "  impl default:\n"
        "    marker: 1\n"
    )
    path = _write_config(tmp_path, source)

    with pytest.raises(ETCMError) as raised:
        resolve(f"{path}#Config:default")

    assert raised.value.diagnostic.code == "E_INVALID_OVERRIDE"
    details = raised.value.diagnostic.details
    assert details is not None
    assert details["reason"] == reason


@pytest.mark.parametrize(
    "source",
    [
        """
        spec Child:
          value: int = 0

          impl default:
            value: 0

        spec Config:
          $child: #Child [override="deny"]

          impl default:
            $child: #Child:default
        """,
        """
        spec Config:
          nested: [override="deny"]
            value: int = 0

          impl default:
            nested:
              value: 0
        """,
    ],
)
def test_deny_requires_inline_default_for_object_fields(tmp_path: Path, source: str) -> None:
    path = _write_config(tmp_path, source)

    with pytest.raises(ETCMError) as raised:
        resolve(f"{path}#Config:default")

    assert raised.value.diagnostic.code == "E_INVALID_OVERRIDE"
    details = raised.value.diagnostic.details
    assert details is not None
    assert details["reason"] == "missing_inline_default"


@pytest.mark.parametrize("implementation", ["base", "default"])
def test_deny_rejects_every_implementation_assignment(
    tmp_path: Path,
    implementation: str,
) -> None:
    path = _write_config(
        tmp_path,
        """
        spec Runtime:
          seed: int = 0 [override="deny"]

          impl base:
            seed: 0

          impl default:
            seed: 0
        """,
    )
    graph = resolve(f"{path}#Runtime:{implementation}")

    with pytest.raises(ETCMError) as raised:
        validate(graph)

    assert raised.value.diagnostic.code == "E_INVALID_OVERRIDE"
    assert raised.value.diagnostic.details == {
        "field": "seed",
        "override": "deny",
        "previous_origin": "default",
    }


def test_deny_allows_its_inline_default_when_unassigned(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
        spec Runtime:
          seed: int = 0 [override="deny"]
          optional_seed: int | null = null [override="deny"]
          label: str = "base"

          impl configured:
            label: "configured"
        """,
    )

    graph = validate(resolve(f"{path}#Runtime:configured"))

    assert _root(graph).values["seed"] == 0
    assert _root(graph).values["optional_seed"] is None
    assert _value(graph, "seed").applied_override is False


def test_allow_assignment_over_default_is_audited(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
        spec Config:
          value: int = 1

          impl configured:
            value: 2
        """,
    )

    graph = validate(resolve(f"{path}#Config:configured"))
    value = _value(graph, "value")

    assert value.value == 2
    assert value.applied_override is True
    assert value.previous_origin == "default"
    assert value.previous_value == 1
    assert value.local_value == 2


def test_append_composes_with_defaults_and_inherited_values(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
        spec Config:
          items: list[int] = [1] [override="append"]
          untouched: list[int] = [10] [override="append"]

          impl base:
            items: [2]
            untouched: [20]

          impl child <- :base:
            items: [3]
        """,
    )

    base_graph = validate(resolve(f"{path}#Config:base"))
    base_items = _value(base_graph, "items")
    assert base_items.value == [1, 2]
    assert base_items.previous_origin == "default"
    assert base_items.previous_value == [1]
    assert base_items.local_value == [2]

    child_graph = validate(resolve(f"{path}#Config:child"))
    child_items = _value(child_graph, "items")
    assert child_items.value == [1, 2, 3]
    assert child_items.previous_origin == "parent"
    assert child_items.previous_value == [1, 2]
    assert child_items.local_value == [3]

    untouched = _value(child_graph, "untouched")
    assert untouched.value == [10, 20]
    assert untouched.origin == "parent"
    assert untouched.applied_override is False
    assert untouched.previous_origin is None
    assert untouched.previous_value is None
    assert untouched.local_value is None


def test_append_first_assignment_establishes_required_value(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
        spec Config:
          items: list[int] [override="append"]

          impl configured:
            items: [1]
        """,
    )

    graph = validate(resolve(f"{path}#Config:configured"))
    value = _value(graph, "items")

    assert value.value == [1]
    assert value.applied_override is False


def test_merge_first_assignment_establishes_required_value(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
        spec Config:
          settings: dict[str, int] [override="merge"]

          impl configured:
            settings: {"value": 1}
        """,
    )

    graph = validate(resolve(f"{path}#Config:configured"))
    value = _value(graph, "settings")

    assert value.value == {"value": 1}
    assert value.applied_override is False


def test_merge_recursively_composes_with_defaults_and_inherited_values(tmp_path: Path) -> None:
    source = (
        "spec Config:\n"
        '  settings: dict[str, dict[str, int]] = {"nested": '
        '{"left": 1, "replace": 1}, "spec_only": {"value": 1}} '
        '[override="merge"]\n\n'
        "  impl base:\n"
        '    settings: {"nested": {"right": 2, "replace": 2}, '
        '"local_only": {"value": 2}}\n\n'
        "  impl child <- :base:\n"
        '    settings: {"nested": {"child": 3, "replace": 3}, '
        '"child_only": {"value": 3}}\n'
    )
    path = _write_config(
        tmp_path,
        source,
    )

    base_graph = validate(resolve(f"{path}#Config:base"))
    base_value = _value(base_graph, "settings")

    assert base_value.value == {
        "nested": {"left": 1, "replace": 2, "right": 2},
        "spec_only": {"value": 1},
        "local_only": {"value": 2},
    }
    assert base_value.previous_origin == "default"

    child_graph = validate(resolve(f"{path}#Config:child"))
    child_value = _value(child_graph, "settings")

    assert child_value.value == {
        "nested": {"left": 1, "replace": 3, "right": 2, "child": 3},
        "spec_only": {"value": 1},
        "local_only": {"value": 2},
        "child_only": {"value": 3},
    }
    assert list(child_value.value) == [
        "nested",
        "spec_only",
        "local_only",
        "child_only",
    ]
    assert list(child_value.value["nested"]) == ["left", "replace", "right", "child"]
    assert child_value.previous_origin == "parent"
    assert child_value.previous_value == base_value.value


def test_force_only_allows_initial_value_but_rejects_default_override(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        """
        spec Config:
          initial: int [override="force_only"]
          fixed: int = 1 [override="force_only"]

          impl configured:
            initial: 2
            fixed: 2
        """,
    )
    graph = resolve(f"{path}#Config:configured")

    assert _value(graph, "initial").applied_override is False
    with pytest.raises(ETCMError) as raised:
        validate(graph)

    assert raised.value.diagnostic.code == "E_INVALID_OVERRIDE"
    details = raised.value.diagnostic.details
    assert details is not None
    assert details["field"] == "fixed"
