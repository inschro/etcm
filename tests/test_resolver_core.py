from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from etcm import Resolver, resolve, validate
from etcm.errors import Diagnostic, ETCMError
from etcm.resolve import ResolvedGraph

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"

VALID_RESOLVER_FIXTURES = {
    "typed_refs": "valid/typed_refs/train.etcm#smoke",
    "spec_reuse": "valid/spec_reuse/variants.etcm#smoke",
    "spec_inheritance": "valid/spec_inheritance_resolver/cuda.etcm",
    "impl_inheritance": "valid/impl_inheritance_resolver/runtime.etcm#child",
    "path_policies": "valid/path_policies/data.etcm",
    "source_relative_paths": "valid/source_relative_paths/train.etcm",
}

INVALID_RESOLVER_FIXTURES = {
    "missing_selector": ("invalid/missing_selector.etcm", "E_MISSING_SELECTOR"),
    "spec_cycle": ("invalid/spec_cycle/a.etcm", "E_SPEC_CYCLE"),
    "impl_cycle": ("invalid/impl_cycle.etcm#a", "E_IMPL_CYCLE"),
    "ref_cycle": ("invalid/ref_cycle/node.etcm#a", "E_REF_CYCLE"),
    "type_mismatch": ("invalid/type_mismatch.etcm", "E_TYPE_MISMATCH"),
    "missing_required": ("invalid/missing_required.etcm", "E_MISSING_FIELD"),
    "denied_override": ("invalid/denied_override.etcm#child", "E_INVALID_OVERRIDE"),
    "invalid_path_kind": ("invalid/invalid_path_kind.etcm", "E_INVALID_PATH"),
    "missing_path_must_exist": ("invalid/missing_path_must_exist.etcm", "E_INVALID_PATH"),
}


@pytest.mark.parametrize(("name", "selector"), VALID_RESOLVER_FIXTURES.items())
def test_valid_resolver_fixtures_match_graph_golden(name: str, selector: str) -> None:
    graph = resolve(str(FIXTURES / selector))

    assert isinstance(graph, ResolvedGraph)
    assert graph.to_dict(path_base=FIXTURES) == _read_golden("graph", name)


@pytest.mark.parametrize(("name", "case"), INVALID_RESOLVER_FIXTURES.items())
def test_invalid_resolver_fixtures_match_diagnostic_golden(
    name: str,
    case: tuple[str, str],
) -> None:
    selector, code = case

    with pytest.raises(ETCMError) as raised:
        resolve(str(FIXTURES / selector))

    assert raised.value.diagnostic.code == code
    assert _diagnostic_summary(raised.value.diagnostic) == _read_golden(
        "resolver_diagnostics",
        name,
    )


def test_validate_returns_none_for_valid_selector() -> None:
    assert validate(str(FIXTURES / "valid/typed_refs/train.etcm#smoke")) is None


def test_resolver_path_policy_controls_delegated_paths() -> None:
    selector = str(FIXTURES / "valid/path_policies/data.etcm")

    assert Resolver(path_exists="allow_missing").validate(selector) is None
    with pytest.raises(ETCMError) as raised:
        Resolver(path_exists="must_exist").validate(selector)

    assert raised.value.diagnostic.code == "E_INVALID_PATH"
    assert raised.value.diagnostic.graph_path == "root.cache_dir"


def _read_golden(kind: str, name: str) -> dict[str, Any]:
    path = FIXTURES / "golden" / kind / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _diagnostic_summary(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "code": diagnostic.code,
        "message": diagnostic.message,
        "source_path": _relative(diagnostic.source_path),
        "span": {
            "line": diagnostic.line,
            "column": diagnostic.column,
            "end_line": diagnostic.end_line,
            "end_column": diagnostic.end_column,
        },
        "selector": diagnostic.selector,
        "graph_path": diagnostic.graph_path,
        "details": _normalize_details(diagnostic.details),
    }


def _normalize_details(details: Any) -> Any:
    if details is None:
        return {}
    if isinstance(details, Mapping):
        return {key: _normalize_details(value) for key, value in details.items()}
    if isinstance(details, list):
        return [_normalize_details(value) for value in details]
    if isinstance(details, str):
        return _relative_string(details)
    return details


def _relative(path: Path | None) -> str | None:
    if path is None:
        return None
    return _relative_string(path.as_posix())


def _relative_string(value: str) -> str:
    try:
        return Path(value).resolve().relative_to(FIXTURES).as_posix()
    except ValueError:
        return value
