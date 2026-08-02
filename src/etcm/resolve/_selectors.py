from __future__ import annotations

from pathlib import Path

from etcm.ir import Selector
from etcm.resolve._diagnostics import raise_error


def selector_text(
    source_path: Path,
    spec: str | None = None,
    implementation: str | None = None,
) -> str:
    text = source_path.as_posix()
    if spec is not None:
        text = f"{text}#{spec}"
        if implementation is not None:
            text = f"{text}:{implementation}"
        return text
    if implementation is not None:
        return f"{text}#{implementation}"
    return text


def resolve_path(path: Path, base: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def normalize_selector(
    selector: Selector,
    *,
    declaring_source: Path,
    active_spec: str | None,
    require_path: bool = False,
) -> Selector:
    if selector.path is None:
        if require_path:
            raise_error(
                "E_MISSING_SELECTOR",
                "This selector position requires a '.etcm' file path.",
                source_path=declaring_source.resolve(),
                selector=selector.raw,
            )
        path = declaring_source.resolve()
    else:
        path = resolve_path(selector.path, declaring_source.parent)

    spec = selector.spec or active_spec
    if spec is None:
        raise_error(
            "E_MISSING_SELECTOR",
            "The ':implementation' shortcut requires an active spec.",
            source_path=declaring_source.resolve(),
            selector=selector.raw,
        )
    return Selector(
        path=path,
        spec=spec,
        implementation=selector.implementation,
        raw=selector.raw,
    )


def selector_from_ir(
    selector: Selector,
    declaring_source: Path,
    *,
    active_spec: str | None,
) -> Selector:
    return normalize_selector(
        selector,
        declaring_source=declaring_source,
        active_spec=active_spec,
    )


def selector_from_raw(raw: str) -> Selector:
    try:
        selector = Selector.parse(raw)
    except ValueError as exc:
        raise_error(
            "E_MISSING_SELECTOR",
            f"Invalid root selector '{raw}': {exc}.",
            selector=raw,
        )
    if selector.target != "implementation":
        raise_error(
            "E_MISSING_SELECTOR",
            "Root selectors must use 'path.etcm#Spec:implementation'.",
            selector=raw,
        )
    if selector.path is None:
        raise_error(
            "E_MISSING_SELECTOR",
            "Root selectors must include a '.etcm' file path.",
            selector=raw,
        )
    return normalize_selector(
        selector,
        declaring_source=Path.cwd() / "__root__.etcm",
        active_spec=None,
        require_path=True,
    )


def canonical_selector(selector: Selector) -> str:
    if selector.path is None or selector.spec is None:
        raise AssertionError("normalized selector is incomplete")
    return selector_text(selector.path, selector.spec, selector.implementation)
