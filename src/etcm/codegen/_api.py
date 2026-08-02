from __future__ import annotations

from typing import Any

from etcm._contracts import ViewTarget
from etcm.codegen._materializer import _Materializer
from etcm.errors import Diagnostic, ETCMError
from etcm.resolve.graph import ResolvedGraph


def convert(
    graph: ResolvedGraph,
    *,
    target: ViewTarget = "pydantic",
    force: bool = False,
) -> Any:
    if target not in ("pydantic", "dataclass", "dict"):
        raise ValueError("target must be one of: pydantic, dataclass, dict")
    if not graph.validated and not force:
        _raise_generated_view(
            "Cannot convert an unvalidated graph. Call validate(graph) first or pass force=True.",
            graph=graph,
            details={"target": target, "validated": graph.validated},
        )

    materializer = _Materializer(graph)
    if target == "dict":
        return materializer.to_dict_payload()
    if target == "dataclass":
        return materializer.to_dataclass()
    return materializer.to_pydantic()


def pydantic_schema_summary(graph: ResolvedGraph) -> dict[str, Any]:
    return _Materializer(graph).pydantic_schema_summary()


def _raise_generated_view(
    message: str,
    *,
    graph: ResolvedGraph,
    details: dict[str, Any] | None = None,
) -> None:
    source_path = graph.sources[0] if graph.sources else None
    raise ETCMError(
        Diagnostic(
            code="E_GENERATED_VIEW",
            message=message,
            source_path=source_path,
            details=details,
        )
    )


__all__ = ["ViewTarget", "convert", "pydantic_schema_summary"]
