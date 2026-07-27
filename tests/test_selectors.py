from __future__ import annotations

from pathlib import Path

import pytest

from etcm import resolve, validate
from etcm.errors import ETCMError
from etcm.syntax import parse_document


def test_local_spec_and_implementation_selectors_resolve_with_comments(
    tmp_path: Path,
) -> None:
    source = tmp_path / "config.etcm"
    source.write_text(
        "\n".join(
            [
                "#compact-comment",
                "spec Model:",
                "  name: str = \"small#model\"",
                "  impl small:",
                "    name: \"small\"",
                "",
                "spec Train:",
                "  $model: #Model # local spec",
                "  impl default:",
                "    $model: #Model:small # local implementation",
                "",
            ]
        ),
        encoding="utf-8",
    )

    graph = validate(resolve(f"{source}#Train:default"))

    model = next(node for node in graph.nodes if node.id == "root.model")
    assert model.spec_name == "Model"
    assert model.implementation == "small"
    assert model.values["name"] == "small"


def test_comment_marker_still_requires_leading_whitespace() -> None:
    with pytest.raises(ETCMError):
        parse_document(
            "spec Config:\n  value: int\n  impl default:\n    value: 1#comment\n",
            "config.etcm",
        )


def test_local_spec_inheritance_uses_hash_fragment(tmp_path: Path) -> None:
    source = tmp_path / "config.etcm"
    source.write_text(
        "\n".join(
            [
                "spec Base:",
                "  value: int = 1",
                "",
                "spec Child <- #Base:",
                "  extra: int = 2",
                "  impl default:",
                "    value: 3",
                "",
            ]
        ),
        encoding="utf-8",
    )

    graph = validate(resolve(f"{source}#Child:default"))

    root = next(node for node in graph.nodes if node.id == "root")
    assert root.spec_ancestors == ("Base",)
    assert root.values == {"value": 3, "extra": 2}


def test_active_spec_implementation_shortcut_works_in_spec_reuse(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "spec.etcm"
    spec.write_text("spec Config:\n  value: int\n", encoding="utf-8")
    variants = tmp_path / "variants.etcm"
    variants.write_text(
        "\n".join(
            [
                "$spec: spec.etcm#Config",
                "",
                "impl base:",
                "  value: 1",
                "",
                "impl child <- :base:",
                "  value: 2",
                "",
            ]
        ),
        encoding="utf-8",
    )

    graph = resolve(f"{variants}#Config:child")

    parent = next(node for node in graph.nodes if node.id == "root.__parent")
    assert parent.selector == f"{variants.resolve().as_posix()}#Config:base"


def test_absolute_selectors_are_allowed_inside_documents(tmp_path: Path) -> None:
    model = tmp_path / "model.etcm"
    model.write_text(
        "spec Model:\n  value: int\n  impl small:\n    value: 1\n",
        encoding="utf-8",
    )
    train = tmp_path / "train.etcm"
    model_path = model.resolve().as_posix()
    train.write_text(
        "\n".join(
            [
                "spec Train:",
                f"  $model: {model_path}#Model",
                "  impl default:",
                f"    $model: {model_path}#Model:small",
                "",
            ]
        ),
        encoding="utf-8",
    )

    graph = resolve(f"{train}#Train:default")

    assert any(node.selector == f"{model_path}#Model:small" for node in graph.nodes)


def test_relative_root_selector_is_canonicalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "root.etcm"
    source.write_text(
        "spec Root:\n  value: int = 1\n  impl default:\n    value: 2\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    graph = resolve("root.etcm#Root:default")

    assert graph.root_selector == f"{source.resolve().as_posix()}#Root:default"


@pytest.mark.parametrize(
    "source_text",
    [
        "$spec: #Base\n\nimpl default:\n  value: 1\n",
        "spec Child <- base.etcm#Base:default:\n  value: int\n",
        "spec Root:\n  $child: child.etcm#Child:default\n",
        (
            "spec Root:\n"
            "  $child: child.etcm#Child\n"
            "  impl default:\n"
            "    $child: child.etcm#Child\n"
        ),
        (
            "spec Root:\n"
            "  value: int\n"
            "  impl child <- root.etcm#Root:\n"
            "    value: 1\n"
        ),
    ],
)
def test_selector_roles_are_enforced_during_parsing(source_text: str) -> None:
    with pytest.raises(ETCMError) as raised:
        parse_document(source_text, "config.etcm")

    assert raised.value.diagnostic.code == "E_PARSE_SELECTOR"


@pytest.mark.parametrize(
    "selector",
    [
        "root.etcm",
        "root.etcm#Root",
        "root.etcm#default",
        "#Root:default",
        ":default",
    ],
)
def test_root_selector_rejects_incomplete_and_local_forms(selector: str) -> None:
    with pytest.raises(ETCMError) as raised:
        resolve(selector)

    assert raised.value.diagnostic.code == "E_MISSING_SELECTOR"
