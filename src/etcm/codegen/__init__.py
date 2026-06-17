from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import make_dataclass
from pathlib import Path
from typing import Any, Literal, Union, cast

from pydantic import ConfigDict, Field, create_model

from etcm.errors import Diagnostic, ETCMError
from etcm.ir import TypeExpr
from etcm.resolve.graph import ResolvedField, ResolvedGraph, ResolvedNode

ViewTarget = Literal["pydantic", "dataclass", "dict"]


def convert(
    graph: ResolvedGraph,
    *,
    target: ViewTarget = "pydantic",
    force: bool = False,
) -> object:
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


class _Materializer:
    def __init__(self, graph: ResolvedGraph) -> None:
        self._graph = graph
        self._nodes = {node.id: node for node in graph.nodes}
        self._ref_targets: dict[tuple[str, str], str] = {}
        for edge in graph.edges:
            if edge.kind == "ref" and len(edge.field_path) == 1:
                self._ref_targets[(edge.source, edge.field_path[0])] = edge.target
        self._class_names = self._class_name_map()
        self._dataclass_types: dict[str, type[Any]] = {}
        self._pydantic_types: dict[str, type[Any]] = {}

    def to_dict_payload(self) -> dict[str, Any]:
        return self._node_to_dict(self._root)

    def to_dataclass(self) -> object:
        root = self._root
        root_type = self._dataclass_type(root)
        return root_type(**self._node_to_object_values(root, mode="dataclass"))

    def to_pydantic(self) -> object:
        root = self._root
        root_type = self._pydantic_type(root)
        return root_type(**self._node_to_object_values(root, mode="pydantic"))

    def pydantic_schema_summary(self) -> dict[str, Any]:
        classes = []
        for node in sorted(self._graph.nodes, key=lambda item: self._class_names[item.id]):
            classes.append(
                {
                    "name": self._class_names[node.id],
                    "frozen": True,
                    "fields": [
                        {
                            "name": field.name,
                            "annotation": self._annotation_text(node, field),
                            "required": True,
                            "metadata": dict(field.metadata),
                        }
                        for field in node.fields.values()
                    ],
                }
            )
        return {"classes": classes}

    @property
    def _root(self) -> ResolvedNode:
        return self._nodes["root"]

    def _node_to_dict(self, node: ResolvedNode) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field_name in node.fields:
            value = node.field_values[field_name].value
            target = self._ref_targets.get((node.id, field_name))
            if target is not None:
                payload[field_name] = self._node_to_dict(self._nodes[target])
            else:
                payload[field_name] = _json_compatible(value)
        return payload

    def _node_to_object_values(self, node: ResolvedNode, *, mode: ViewTarget) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field_name in node.fields:
            value = node.field_values[field_name].value
            target = self._ref_targets.get((node.id, field_name))
            if target is not None:
                target_node = self._nodes[target]
                if mode == "dataclass":
                    target_type = self._dataclass_type(target_node)
                else:
                    target_type = self._pydantic_type(target_node)
                payload[field_name] = target_type(
                    **self._node_to_object_values(target_node, mode=mode)
                )
            else:
                payload[field_name] = value
        return payload

    def _dataclass_type(self, node: ResolvedNode) -> type[Any]:
        cached = self._dataclass_types.get(node.id)
        if cached is not None:
            return cached
        fields = [
            (field.name, self._python_annotation(node, field))
            for field in node.fields.values()
        ]
        created = make_dataclass(self._class_names[node.id], fields, frozen=True)
        self._dataclass_types[node.id] = created
        return created

    def _pydantic_type(self, node: ResolvedNode) -> type[Any]:
        cached = self._pydantic_types.get(node.id)
        if cached is not None:
            return cached
        field_defs: dict[str, Any] = {}
        for field in node.fields.values():
            annotation = self._pydantic_annotation(node, field)
            field_defs[field.name] = (annotation, Field(**_pydantic_constraints(field)))
        created = create_model(
            self._class_names[node.id],
            __config__=ConfigDict(frozen=True, extra="forbid"),
            **field_defs,
        )
        self._pydantic_types[node.id] = created
        return created

    def _python_annotation(self, node: ResolvedNode, field: ResolvedField) -> Any:
        target = self._ref_targets.get((node.id, field.name))
        if target is not None:
            return self._dataclass_type(self._nodes[target])
        return _annotation_from_type(field.type_expr)

    def _pydantic_annotation(self, node: ResolvedNode, field: ResolvedField) -> Any:
        target = self._ref_targets.get((node.id, field.name))
        if target is not None:
            return self._pydantic_type(self._nodes[target])
        choices = field.metadata.get("choices")
        if isinstance(choices, list) and choices:
            literal_type = cast(Any, Literal)
            return literal_type.__getitem__(tuple(choices))
        return _annotation_from_type(field.type_expr)

    def _annotation_text(self, node: ResolvedNode, field: ResolvedField) -> str:
        target = self._ref_targets.get((node.id, field.name))
        if target is not None:
            return self._class_names[target]
        return _type_text(field.type_expr)

    def _class_name_map(self) -> dict[str, str]:
        spec_counts: dict[str, int] = {}
        for node in self._graph.nodes:
            spec_counts[node.spec_name] = spec_counts.get(node.spec_name, 0) + 1
        result: dict[str, str] = {}
        for node in self._graph.nodes:
            base = _identifier(node.spec_name)
            if spec_counts[node.spec_name] > 1:
                base = f"{base}_{_identifier(node.id)}"
            result[node.id] = base
        return result


def _annotation_from_type(type_expr: TypeExpr) -> Any:
    if type_expr.kind == "union":
        union_type = cast(Any, Union)
        return union_type.__getitem__(tuple(_annotation_from_type(arg) for arg in type_expr.args))
    if type_expr.kind == "generic":
        if type_expr.name == "list" and len(type_expr.args) == 1:
            return list[_annotation_from_type(type_expr.args[0])]
        if type_expr.name == "dict" and len(type_expr.args) == 2:
            return dict[
                _annotation_from_type(type_expr.args[0]),
                _annotation_from_type(type_expr.args[1]),
            ]
        return Any
    if type_expr.kind != "named":
        return Any
    return {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "null": type(None),
        "Path": Path,
    }.get(str(type_expr.name), Any)


def _type_text(type_expr: TypeExpr) -> str:
    if type_expr.kind == "named":
        return str(type_expr.name)
    if type_expr.kind == "generic":
        return f"{type_expr.name}[{', '.join(_type_text(arg) for arg in type_expr.args)}]"
    if type_expr.kind == "union":
        return " | ".join(_type_text(arg) for arg in type_expr.args)
    return type_expr.kind


def _pydantic_constraints(field: ResolvedField) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    for source, target in (
        ("gt", "gt"),
        ("ge", "ge"),
        ("lt", "lt"),
        ("le", "le"),
        ("min_length", "min_length"),
        ("max_length", "max_length"),
        ("regex", "pattern"),
    ):
        if source in field.metadata:
            constraints[target] = field.metadata[source]
    return constraints


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_compatible(item) for item in value]
    return value


def _identifier(value: str) -> str:
    cleaned = re.sub(r"\W+", "_", value).strip("_")
    if not cleaned:
        return "Generated"
    if cleaned[0].isdigit():
        return f"Generated_{cleaned}"
    return cleaned


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
