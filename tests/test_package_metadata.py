from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_describes_standalone_apache_package() -> None:
    project = _pyproject()["project"]

    assert project["name"] == "etcm"
    assert project["requires-python"] == ">=3.12"
    assert project["scripts"]["etcm"] == "etcm.cli:main"
    assert project["license"] == {"file": "LICENSE"}
    assert "License :: OSI Approved :: Apache Software License" in project["classifiers"]


def test_sdist_scope_keeps_release_artifact_focused() -> None:
    include = set(_pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])

    assert "/LICENSE" in include
    assert "/src/etcm" in include
    assert "/examples" in include
    assert "/docs/install.md" in include
    assert not any(path.startswith("/tests") for path in include)
    assert not any(path.startswith("/docs/stage") for path in include)


def test_required_package_resources_are_present_in_source_tree() -> None:
    assert (ROOT / "src/etcm/py.typed").is_file()
    assert (ROOT / "src/etcm/syntax/grammar.lark").is_file()


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
