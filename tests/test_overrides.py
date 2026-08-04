from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from etcm import OverrideInput, load, resolve, validate
from etcm.cli import main
from etcm.errors import ETCMError
from etcm.resolve import ResolvedGraph, ResolvedNode


def _write_config(tmp_path: Path) -> Path:
    source = tmp_path / "config.etcm"
    source.write_text(
        dedent(
            """
            spec Child:
              seed: int = 1
              scale: int = 2
              total: int := @seed * @scale

              impl base:
                seed: 1

              impl alternate:
                seed: 10

            spec Config:
              $child: #Child

              nested:
                value: int = 1

              source: int = 2
              doubled: int := @source * 2
              label: str = "base"
              items: list[int] = [1] [override="append"]
              settings: dict[str, int] = {a: 1} [override="merge"]
              asset: Path = "declared.txt"

              impl base:
                $child: #Child:base

              impl empty:
                label: "empty"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return source


def _node(graph: ResolvedGraph, node_id: str) -> ResolvedNode:
    return next(node for node in graph.nodes if node.id == node_id)


def test_impl_can_replace_then_patch_reference_in_either_source_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "local.etcm"
    source.write_text(
        dedent(
            """
            spec Child:
              seed: int = 1

              impl base:
                seed: 1

            spec Config:
              $child: #Child

              impl configured:
                child.seed: 4
                $child: #Child:base

              impl inherited <- :configured:
                child.seed: 8
            """
        ).lstrip(),
        encoding="utf-8",
    )

    configured = validate(resolve(f"{source}#Config:configured"))
    assert _node(configured, "root.child").values["seed"] == 4

    inherited = validate(resolve(f"{source}#Config:inherited"))
    assert _node(inherited, "root.child").values["seed"] == 8
    assert _node(inherited, "root.__parent.child").values["seed"] == 4
    root_child = _node(inherited, "root").field_values["child"]
    leaf = _node(inherited, "root.child").field_values["seed"]
    assert root_child.origin == "parent"
    assert root_child.applied_override is False
    assert leaf.previous_origin == "parent"


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "child.seed": 7,
            "nested.value": 3,
            "source": 4,
            "label": "plain text",
            "items": [2, 3],
            "settings": {"b": 2},
            "asset": Path("asset.bin"),
        },
        [
            "child.seed=7",
            "nested.value=3",
            "source=4",
            "label=plain text",
            "items=[2, 3]",
            "settings={b: 2}",
            "asset=asset.bin",
        ],
    ],
)
def test_python_overrides_share_literal_and_deep_patch_pipeline(
    tmp_path: Path,
    overrides: OverrideInput,
) -> None:
    source = _write_config(tmp_path)
    override_base = tmp_path / "runtime"

    graph = validate(
        resolve(
            f"{source}#Config:base",
            overrides=overrides,
            override_base=override_base,
        )
    )

    root = _node(graph, "root")
    child = _node(graph, "root.child")
    nested = _node(graph, "root.nested")
    assert child.values == {"seed": 7, "scale": 2, "total": 14}
    assert nested.values["value"] == 3
    assert root.values["doubled"] == 8
    assert root.values["label"] == "plain text"
    assert root.values["items"] == [1, 2, 3]
    assert root.values["settings"] == {"a": 1, "b": 2}
    assert root.values["asset"] == (override_base / "asset.bin").resolve()

    seed = child.field_values["seed"]
    assert seed.origin == "external"
    assert seed.applied_override is True
    assert seed.override_base == override_base.resolve()


def test_external_reference_replacement_precedes_descendant_patches(
    tmp_path: Path,
) -> None:
    source = _write_config(tmp_path)

    graph = validate(
        resolve(
            f"{source}#Config:base",
            overrides=["child.seed=11", "child=:alternate"],
        )
    )

    child = _node(graph, "root.child")
    assert child.implementation == "alternate"
    assert child.values == {"seed": 11, "scale": 2, "total": 22}


def test_explicit_reference_and_path_values_use_override_base(tmp_path: Path) -> None:
    source = _write_config(tmp_path)
    override_base = tmp_path / "external"
    override_base.mkdir()
    external = override_base / "other.etcm"
    external.write_text(
        dedent(
            """
            spec Child:
              seed: int
              scale: int = 3
              total: int := @seed * @scale

              impl alternate:
                seed: 21
            """
        ).lstrip(),
        encoding="utf-8",
    )

    loaded = load(
        f"{source}#Config:base",
        target="dict",
        overrides=[
            "child=other.etcm#Child:alternate",
            "asset=data.bin",
        ],
        override_base=override_base,
    )

    assert loaded["child"] == {"seed": 21, "scale": 3, "total": 63}
    assert loaded["asset"] == (override_base / "data.bin").resolve().as_posix()


def test_force_only_requires_explicit_external_authorization(tmp_path: Path) -> None:
    source = tmp_path / "policies.etcm"
    source.write_text(
        dedent(
            """
            spec Config:
              guarded: int = 1 [override="force_only"]
              locked: int = 1 [override="deny"]
              required: int [override="force_only"]
              marker: int = 0

              impl base:
                required: 2

              impl empty:
                marker: 1
            """
        ).lstrip(),
        encoding="utf-8",
    )
    selector = f"{source}#Config:base"

    with pytest.raises(ETCMError) as raised:
        validate(resolve(selector, overrides={"guarded": 3}))
    assert raised.value.diagnostic.code == "E_INVALID_OVERRIDE"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["force_authorized"] is False

    graph = validate(
        resolve(selector, overrides={"guarded": 3}, force_overrides=True)
    )
    guarded = _node(graph, "root").field_values["guarded"]
    assert guarded.value == 3
    assert guarded.override_forced is True

    with pytest.raises(ETCMError) as raised:
        validate(
            resolve(
                selector,
                overrides={"locked": 2},
                force_overrides=True,
            )
        )
    assert raised.value.diagnostic.code == "E_INVALID_OVERRIDE"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["override"] == "deny"

    first_value = validate(
        resolve(f"{source}#Config:empty", overrides={"required": 5})
    )
    required = _node(first_value, "root").field_values["required"]
    assert required.value == 5
    assert required.applied_override is False


def test_external_override_conflicts_and_duplicates_are_rejected(
    tmp_path: Path,
) -> None:
    source = _write_config(tmp_path)
    selector = f"{source}#Config:base"

    with pytest.raises(ValueError, match="duplicate override path 'source'"):
        resolve(selector, overrides=["source=3", "source=4"])

    with pytest.raises(ETCMError) as raised:
        resolve(
            selector,
            overrides=["nested={value: 2}", "nested.value=3"],
        )
    assert raised.value.diagnostic.code == "E_OVERRIDE_PATH_CONFLICT"


def test_cli_set_uses_the_public_override_pipeline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_config(tmp_path)
    selector = f"{source}#Config:base"

    exit_code = main(
        [
            "load",
            selector,
            "--set",
            "child.seed=6",
            "--set",
            "source=5",
            "--target",
            "dict",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["child"]["seed"] == 6
    assert payload["child"]["total"] == 12
    assert payload["doubled"] == 10


def test_cli_reports_malformed_set_as_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_config(tmp_path)

    with pytest.raises(SystemExit) as raised:
        main(["resolve", f"{source}#Config:base", "--set", "source"])

    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert "must use PATH=VALUE" in captured.err
