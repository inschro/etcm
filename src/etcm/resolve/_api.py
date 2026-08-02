from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from etcm._contracts import PathExistsPolicy, ViewTarget
from etcm.resolve._engine import _ResolverState
from etcm.resolve._validation import validate_graph
from etcm.resolve.graph import ResolvedGraph


@dataclass(frozen=True)
class Resolver:
    path_exists: PathExistsPolicy = "allow_missing"

    def __post_init__(self) -> None:
        if self.path_exists not in ("allow_missing", "must_exist"):
            raise ValueError("path_exists must be 'allow_missing' or 'must_exist'")

    def load(self, selector: str, *, target: ViewTarget = "pydantic") -> Any:
        return self.convert(self.validate(self.resolve(selector)), target=target)

    def resolve(self, selector: str) -> ResolvedGraph:
        state = _ResolverState(self)
        return state.resolve(selector)

    def validate(self, graph: ResolvedGraph) -> ResolvedGraph:
        return validate_graph(graph)

    def convert(
        self,
        graph: ResolvedGraph,
        *,
        target: ViewTarget = "pydantic",
        force: bool = False,
    ) -> Any:
        from etcm.codegen import convert

        return convert(graph, target=target, force=force)


def load(
    selector: str,
    *,
    target: ViewTarget = "pydantic",
    path_exists: PathExistsPolicy = "allow_missing",
) -> Any:
    return Resolver(path_exists=path_exists).load(selector, target=target)


def resolve(
    selector: str,
    *,
    path_exists: PathExistsPolicy = "allow_missing",
) -> ResolvedGraph:
    return Resolver(path_exists=path_exists).resolve(selector)


def validate(graph: ResolvedGraph) -> ResolvedGraph:
    return Resolver().validate(graph)


def convert(
    graph: ResolvedGraph,
    *,
    target: ViewTarget = "pydantic",
    force: bool = False,
) -> Any:
    return Resolver().convert(graph, target=target, force=force)


__all__ = [
    "PathExistsPolicy",
    "Resolver",
    "ViewTarget",
    "convert",
    "load",
    "resolve",
    "validate",
]
