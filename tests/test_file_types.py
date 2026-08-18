from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from textwrap import indent
from typing import Any, cast

import pytest

from etcm import convert, load, resolve, validate
from etcm.cli import main
from etcm.cli._output import loaded_json_payload
from etcm.codegen import pydantic_schema_summary
from etcm.errors import ETCMError


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _write_bytes(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _config(
    tmp_path: Path,
    fields: str,
    assignments: str = "",
    *,
    name: str = "config.etcm",
) -> Path:
    assignment_lines = "    marker: true"
    if assignments.strip():
        assignment_lines = f"{assignment_lines}\n{indent(assignments.strip(), '    ')}"
    return _write(
        tmp_path / name,
        "\n".join(
            [
                "spec Config:",
                "  marker: bool = false",
                indent(fields.strip(), "  "),
                "",
                "  impl default:",
                assignment_lines,
                "",
            ]
        ),
    )


def _selector(source: Path) -> str:
    return f"{source}#Config:default"


def _root_value(graph: Any, field_name: str) -> Any:
    root = next(node for node in graph.nodes if node.id == "root")
    return root.field_values[field_name].value


def test_json_and_yaml_are_loaded_during_resolve_and_preserved_in_views(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "prompts.json",
        json.dumps({"system": "Be precise", "temperatures": [0.0, 0.7]}),
    )
    _write(tmp_path / "launcher.yaml", "enabled: true\nmode: on\n")
    source = _config(
        tmp_path,
        'prompts: File[json] = "prompts.json"\nlauncher: File[yaml] = "launcher.yaml"',
    )

    graph = resolve(_selector(source))

    assert _root_value(graph, "prompts") == {
        "system": "Be precise",
        "temperatures": [0.0, 0.7],
    }
    assert _root_value(graph, "launcher") == {"enabled": True, "mode": "on"}

    validated = validate(graph)
    dict_value = cast(dict[str, Any], convert(validated, target="dict"))
    dataclass_value: Any = convert(validated, target="dataclass")
    pydantic_value: Any = convert(validated, target="pydantic")
    assert dict_value["prompts"]["system"] == "Be precise"
    assert dataclass_value.launcher == {"enabled": True, "mode": "on"}
    assert pydantic_value.prompts["temperatures"] == [0.0, 0.7]


def test_str_and_bytes_are_loaded_exactly_and_use_native_view_types(
    tmp_path: Path,
) -> None:
    text_bytes = b"\xef\xbb\xbfline one\r\nGr\xc3\xbc\xc3\x9fe\r\n"
    binary = bytes(range(256))
    _write_bytes(tmp_path / "prompt.json", text_bytes)
    _write_bytes(tmp_path / "weights.txt", binary)
    source = _config(
        tmp_path,
        'prompt: File[str] = "prompt.json"\nweights: File[bytes] = "weights.txt"',
    )

    graph = resolve(_selector(source))

    assert _root_value(graph, "prompt") == "\ufeffline one\r\nGr\u00fc\u00dfe\r\n"
    assert _root_value(graph, "weights") == binary

    validated = validate(graph)
    dict_value = cast(dict[str, Any], convert(validated, target="dict"))
    dataclass_value: Any = convert(validated, target="dataclass")
    pydantic_value: Any = convert(validated, target="pydantic")

    assert dict_value["prompt"] == "\ufeffline one\r\nGr\u00fc\u00dfe\r\n"
    assert dict_value["weights"] == binary
    assert dataclass_value.weights == binary
    assert pydantic_value.prompt.endswith("\r\n")
    assert type(dataclass_value).__annotations__["prompt"] is str
    assert type(dataclass_value).__annotations__["weights"] is bytes
    assert type(pydantic_value).model_fields["prompt"].annotation is str
    assert type(pydantic_value).model_fields["weights"].annotation is bytes


def test_str_and_bytes_compose_in_nullable_list_and_dictionary_fields(
    tmp_path: Path,
) -> None:
    _write_bytes(tmp_path / "empty.txt", b"")
    _write_bytes(tmp_path / "one.bin", b"\x00\x01")
    _write_bytes(tmp_path / "two.bin", b"\xfe\xff")
    source = _config(
        tmp_path,
        "\n".join(
            [
                'empty: File[str] = "empty.txt"',
                "optional: File[bytes] | null = null",
                'blobs: list[File[bytes]] = ["one.bin", "two.bin"]',
                "named: dict[str, File[str]] = {empty: \"empty.txt\"}",
            ]
        ),
    )

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["empty"] == ""
    assert value["optional"] is None
    assert value["blobs"] == [b"\x00\x01", b"\xfe\xff"]
    assert value["named"] == {"empty": ""}


def test_invalid_utf8_is_a_structured_file_load_error(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "invalid.txt", b"ok\xfftail")
    source = _config(tmp_path, 'prompt: File[str] = "invalid.txt"')

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "E_FILE_LOAD"
    assert diagnostic.details is not None
    assert diagnostic.details["reason"] == "decode_error"
    assert diagnostic.details["codec"] == "str"
    assert diagnostic.details["encoding"] == "utf-8"
    assert diagnostic.details["byte_start"] == 2
    assert diagnostic.details["byte_end"] == 3
    assert "invalid start byte" in diagnostic.details["decoder_error"]


def test_exact_file_codecs_ignore_filename_suffix(tmp_path: Path) -> None:
    _write(tmp_path / "json-content.yaml", '{"kind": "json"}')
    _write(tmp_path / "yaml-content.json", "kind: yaml\n")
    source = _config(
        tmp_path,
        'json_value: File[json] = "json-content.yaml"\n'
        'yaml_value: File[yaml] = "yaml-content.json"',
    )

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["json_value"] == {"kind": "json"}
    assert value["yaml_value"] == {"kind": "yaml"}


def test_required_file_can_be_supplied_by_an_implementation(tmp_path: Path) -> None:
    _write(tmp_path / "data.json", '{"supplied": true}')
    source = _config(tmp_path, "document: File[json]", 'document: "data.json"')

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["document"] == {"supplied": True}


def test_file_fields_keep_normal_override_policy(tmp_path: Path) -> None:
    _write(tmp_path / "data.json", '{"source": "default"}')
    _write(tmp_path / "other.json", '{"source": "override"}')
    source = _config(
        tmp_path,
        'document: File[json] = "data.json" [override="deny"]',
    )

    with pytest.raises(ETCMError) as raised:
        validate(
            resolve(
                _selector(source),
                overrides={"document": "other.json"},
                override_base=tmp_path,
            )
        )

    assert raised.value.diagnostic.code == "E_INVALID_OVERRIDE"


def test_exact_file_codecs_compose_in_nullable_and_container_fields(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "one.JSON", '{"format": "json"}')
    _write(tmp_path / "two.YML", "format: yaml\n")
    _write(tmp_path / "three.yaml", "format: yaml-long\n")
    source = _config(
        tmp_path,
        "\n".join(
            [
                'single: File[json] = "one.JSON"',
                'many: list[File[yaml]] = ["two.YML", "three.yaml"]',
                "named: dict[str, File[yaml]] = {",
                '  short: "two.YML",',
                '  long: "three.yaml",',
                "}",
                "optional: File[json] | null = null",
                "optional_many: list[File[yaml]] | null = null",
                "nested: dict[str, list[File[json]]] = {",
                '  documents: ["one.JSON", "one.JSON"],',
                "}",
            ]
        ),
    )

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["single"] == {"format": "json"}
    assert value["many"] == [{"format": "yaml"}, {"format": "yaml-long"}]
    assert value["named"] == {
        "short": {"format": "yaml"},
        "long": {"format": "yaml-long"},
    }
    assert value["optional"] is None
    assert value["optional_many"] is None
    assert value["nested"] == {
        "documents": [{"format": "json"}, {"format": "json"}]
    }


def test_exact_file_codec_ignores_the_written_symlink_suffix(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "payload", "format: yaml\n")
    try:
        (tmp_path / "document.json").symlink_to("payload")
    except OSError:
        pytest.skip("symlinks are not available")
    source = _config(tmp_path, 'document: File[yaml] = "document.json"')

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["document"] == {"format": "yaml"}


def test_json_file_roots_may_be_any_json_value(tmp_path: Path) -> None:
    documents = {
        "array": [1, 2],
        "string": "value",
        "number": 3.5,
        "boolean": True,
        "nothing": None,
    }
    for name, value in documents.items():
        _write(tmp_path / f"{name}.json", json.dumps(value))
    source = _config(
        tmp_path,
        "\n".join(f'{name}: File[json] = "{name}.json"' for name in documents),
    )

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert {name: value[name] for name in documents} == documents


def test_yaml_native_values_are_preserved_for_python_callers(tmp_path: Path) -> None:
    _write(
        tmp_path / "native.yaml",
        (
            "created: 2026-08-18\n"
            "labels: !!set\n"
            "  alpha:\n"
            "  beta:\n"
            "numeric_keys:\n"
            "  1: one\n"
        ),
    )
    source = _config(tmp_path, 'document: File[yaml] = "native.yaml"')

    graph = validate(resolve(_selector(source)))
    value = cast(dict[str, Any], convert(graph, target="dict"))["document"]
    dataclass_value: Any = convert(graph, target="dataclass")
    pydantic_value: Any = convert(graph, target="pydantic")
    graph_value = _root_value(graph, "document")

    assert value["created"] == date(2026, 8, 18)
    assert value["labels"] == {"alpha", "beta"}
    assert value["numeric_keys"] == {1: "one"}
    assert graph_value["created"] == date(2026, 8, 18)
    assert dataclass_value.document["created"] == date(2026, 8, 18)
    assert pydantic_value.document["labels"] == {"alpha", "beta"}
    assert graph.to_dict()["nodes"][0]["values"]["document"]["labels"] == {
        "alpha",
        "beta",
    }


@pytest.mark.parametrize("target", ["dict", "dataclass", "pydantic"])
def test_non_json_yaml_values_fail_only_at_cli_json_serialization(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
) -> None:
    _write(tmp_path / "native.yaml", "created: 2026-08-18\n")
    source = _config(tmp_path, 'document: File[yaml] = "native.yaml"')
    selector = _selector(source)

    assert main(["validate", selector, "--short"]) == 0
    short_output = capsys.readouterr()
    assert short_output.err == ""
    assert short_output.out.startswith("OK:")

    assert main(["load", selector, "--target", target]) == 1
    loaded_output = capsys.readouterr()
    assert loaded_output.out == ""
    assert "E_SERIALIZATION" in loaded_output.err
    assert "$.document.created" in loaded_output.err

    assert main(["resolve", selector]) == 1
    graph_output = capsys.readouterr()
    assert graph_output.out == ""
    assert "E_SERIALIZATION" in graph_output.err


def test_generic_cli_payload_keeps_existing_mapping_key_normalization() -> None:
    assert loaded_json_payload({1: "one"}) == {"1": "one"}


def test_file_bytes_become_null_only_at_typed_json_boundaries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_bytes(tmp_path / "one.bin", b"\x00\xff")
    _write_bytes(tmp_path / "two.bin", b"two")
    source = _config(
        tmp_path,
        "\n".join(
            [
                'blob: File[bytes] = "one.bin"',
                'blobs: list[File[bytes]] = ["one.bin", "two.bin"]',
                "optional: File[bytes] | null = null",
            ]
        ),
    )
    selector = _selector(source)

    graph = validate(resolve(selector))
    assert _root_value(graph, "blob") == b"\x00\xff"
    assert _root_value(graph, "blobs") == [b"\x00\xff", b"two"]

    graph_payload = graph.to_dict(path_base=tmp_path)
    root = next(node for node in graph_payload["nodes"] if node["id"] == "root")
    assert root["field_values"]["blob"]["value"] is None
    assert root["field_values"]["blob"]["literal"]["value"] == "one.bin"
    assert root["values"]["blob"] is None
    assert root["values"]["blobs"] == [None, None]
    assert root["values"]["optional"] is None

    loaded = cast(dict[str, Any], convert(graph, target="dict"))
    assert loaded["blob"] == b"\x00\xff"
    assert loaded["blobs"] == [b"\x00\xff", b"two"]
    assert loaded_json_payload(loaded, graph=graph)["blob"] is None
    assert loaded_json_payload(loaded, graph=graph)["blobs"] == [None, None]

    assert main(["resolve", selector]) == 0
    resolve_output = capsys.readouterr()
    assert resolve_output.err == ""
    resolved_payload = json.loads(resolve_output.out)
    resolved_root = next(
        node for node in resolved_payload["nodes"] if node["id"] == "root"
    )
    assert resolved_root["values"]["blob"] is None

    assert main(["validate", selector]) == 0
    validate_output = capsys.readouterr()
    assert validate_output.err == ""
    validated_payload = json.loads(validate_output.out)
    validated_root = next(
        node for node in validated_payload["nodes"] if node["id"] == "root"
    )
    assert validated_root["values"]["blobs"] == [None, None]

    for target in ("dict", "dataclass", "pydantic"):
        assert main(["load", selector, "--target", target]) == 0
        load_output = capsys.readouterr()
        assert load_output.err == ""
        assert json.loads(load_output.out)["blob"] is None


def test_file_bytes_keep_paths_in_override_audit_json(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "default.bin", b"default")
    _write_bytes(tmp_path / "selected.bin", b"selected")
    source = _config(tmp_path, 'blob: File[bytes] = "default.bin"')

    graph = resolve(
        _selector(source),
        overrides={"blob": "selected.bin"},
        override_base=tmp_path,
    )

    assert _root_value(graph, "blob") == b"selected"
    payload = graph.to_dict(path_base=tmp_path)
    root = next(node for node in payload["nodes"] if node["id"] == "root")
    field_value = root["field_values"]["blob"]
    assert field_value["value"] is None
    assert field_value["literal"]["value"] == "selected.bin"
    assert field_value["previous_value"] == "default.bin"
    assert field_value["local_value"] == "selected.bin"


def test_yaml_native_bytes_still_fail_json_serialization(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path / "native.yaml", "payload: !!binary AP8=\n")
    source = _config(tmp_path, 'document: File[yaml] = "native.yaml"')
    selector = _selector(source)

    value = cast(dict[str, Any], load(selector, target="dict"))
    assert value["document"] == {"payload": b"\x00\xff"}

    assert main(["load", selector, "--target", "dict"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "E_SERIALIZATION" in output.err
    assert "$.document.payload" in output.err


def test_ordinary_str_fields_and_relations_are_unchanged(tmp_path: Path) -> None:
    source = _config(
        tmp_path,
        'label: str = "ready"\nconfirmation: str = "ready" [== @label]',
    )

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["label"] == "ready"
    assert value["confirmation"] == "ready"


def test_overridden_file_default_is_never_opened(tmp_path: Path) -> None:
    _write(tmp_path / "actual.json", '{"loaded": true}')
    source = _config(
        tmp_path,
        'document: File[json] = "missing-default.unknown"',
        'document: "actual.json"',
    )

    graph = resolve(_selector(source))
    root = next(node for node in graph.nodes if node.id == "root")
    document = root.field_values["document"]

    assert document.value == {"loaded": True}
    assert document.previous_value == "missing-default.unknown"
    assert document.local_value == "actual.json"


def test_file_override_uses_override_base(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    override_dir = tmp_path / "override"
    config_dir.mkdir()
    override_dir.mkdir()
    _write(config_dir / "default.json", '{"source": "default"}')
    _write(config_dir / "config-list.json", '{"source": "config"}')
    _write(override_dir / "selected.json", '{"source": "override"}')
    _write(override_dir / "override-list.json", '{"source": "override-list"}')
    source = _config(
        config_dir,
        '\n'.join(
            [
                'document: File[json] = "default.json"',
                'documents: list[File[json]] = ["config-list.json"] [override="append"]',
            ]
        ),
    )

    value = cast(
        dict[str, Any],
        load(
            _selector(source),
            target="dict",
            overrides={
                "document": "selected.json",
                "documents": ["override-list.json"],
            },
            override_base=override_dir,
        ),
    )

    assert value["document"] == {"source": "override"}
    assert value["documents"] == [
        {"source": "config"},
        {"source": "override-list"},
    ]


def test_referenced_file_paths_use_their_declaring_source(tmp_path: Path) -> None:
    child_dir = tmp_path / "child"
    child_dir.mkdir()
    _write(child_dir / "data.json", '{"source": "child"}')
    _write(
        child_dir / "child.etcm",
        """spec Child:
  document: File[json] = "data.json"
  marker: bool = false

  impl default:
    marker: true
""",
    )
    source = _write(
        tmp_path / "root.etcm",
        """spec Root:
  $child: child/child.etcm#Child

  impl default:
    $child: child/child.etcm#Child:default
""",
    )

    value = cast(dict[str, Any], load(f"{source}#Root:default", target="dict"))

    assert value["child"]["document"] == {"source": "child"}


def test_append_and_merge_compose_file_paths_before_loading(tmp_path: Path) -> None:
    _write(tmp_path / "one.json", '{"id": 1}')
    _write(tmp_path / "two.json", '{"id": 2}')
    _write(tmp_path / "base.yaml", "kind: base\n")
    _write(tmp_path / "local.yaml", "kind: local\n")
    source = _config(
        tmp_path,
        "\n".join(
            [
                'documents: list[File[json]] = ["one.json"] [override="append"]',
                "named: dict[str, File[yaml]] = {",
                '  base: "base.yaml",',
                '} [override="merge"]',
            ]
        ),
        "\n".join(
            [
                'documents: ["two.json"]',
                'named: {local: "local.yaml"}',
            ]
        ),
    )

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["documents"] == [{"id": 1}, {"id": 2}]
    assert value["named"] == {
        "base": {"kind": "base"},
        "local": {"kind": "local"},
    }


def test_repeated_file_links_do_not_share_mutable_results(tmp_path: Path) -> None:
    _write(tmp_path / "shared.json", '{"items": [1]}')
    source = _config(
        tmp_path,
        'left: File[json] = "shared.json"\nright: File[json] = "shared.json"',
    )

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["left"] == value["right"]
    assert value["left"] is not value["right"]
    value["left"]["items"].append(2)
    assert value["right"]["items"] == [1]


@pytest.mark.parametrize(
    ("type_expr", "reason"),
    [
        ("json", "codec_requires_file"),
        ("yaml", "codec_requires_file"),
        ("list[json]", "codec_requires_file"),
        ("bytes", "codec_requires_file"),
        ("File", "invalid_file_type"),
        ("File[json, yaml]", "invalid_file_type"),
        ("File[json | yaml]", "file_codec_union"),
        ("File[str | json]", "file_codec_union"),
        ("File[bytes | yaml]", "file_codec_union"),
        ("File[str | bytes]", "file_codec_union"),
        ("File[bytes | json | yaml]", "file_codec_union"),
        ("File[json | null]", "file_codec_union"),
        ("File[list[json]]", "unsupported_file_codec"),
        ("File[json] | File[yaml]", "file_value_union"),
        ("File[json] | str", "file_value_union"),
        ("dict[File[json], str]", "file_dictionary_key"),
        ("set[File[json]]", "unsupported_file_container"),
    ],
)
def test_invalid_file_type_positions_are_rejected(
    tmp_path: Path,
    type_expr: str,
    reason: str,
) -> None:
    source = _config(tmp_path, f"document: {type_expr} = null")

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    assert raised.value.diagnostic.code == "E_TYPE_MISMATCH"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["reason"] == reason


@pytest.mark.parametrize(
    ("type_expr", "hint"),
    [
        (
            "File[json | yaml]",
            "Choose one explicit codec: File[json] or File[yaml].",
        ),
        (
            "File[json | null]",
            "Move null outside the file type: File[json] | null.",
        ),
    ],
)
def test_file_codec_union_diagnostic_requires_an_explicit_codec(
    tmp_path: Path,
    type_expr: str,
    hint: str,
) -> None:
    source = _config(tmp_path, f"document: {type_expr} = null")

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    diagnostic = raised.value.diagnostic
    assert diagnostic.details is not None
    assert diagnostic.details["reason"] == "file_codec_union"
    assert diagnostic.details["hint"] == hint


def test_bare_codec_diagnostic_points_to_file_syntax(tmp_path: Path) -> None:
    source = _config(tmp_path, 'payload: json = "payload.json"')

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "E_TYPE_MISMATCH"
    assert diagnostic.details is not None
    assert diagnostic.details["reason"] == "codec_requires_file"
    assert diagnostic.details["codec"] == "json"
    assert diagnostic.details["hint"] == "Use File[json]."


@pytest.mark.parametrize(
    ("legacy_type", "hint"),
    [
        (
            "json | yaml",
            "Choose one explicit file codec, such as File[json] or File[yaml].",
        ),
        (
            "json | yaml | null",
            "Choose one explicit file codec, such as File[json] or File[yaml].",
        ),
        (
            "list[json | yaml]",
            "Choose one explicit file codec, such as File[json] or File[yaml].",
        ),
        ("dict[str, yaml]", "Use dict[str, File[yaml]]."),
        ("bytes", "Use File[bytes]."),
        ("list[bytes]", "Use list[File[bytes]]."),
    ],
)
def test_legacy_codec_diagnostic_migrates_the_complete_type_shape(
    tmp_path: Path,
    legacy_type: str,
    hint: str,
) -> None:
    source = _config(tmp_path, f"payload: {legacy_type} = null")

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    diagnostic = raised.value.diagnostic
    assert diagnostic.details is not None
    assert diagnostic.details["hint"] == hint


@pytest.mark.parametrize("spec_name", ["bytes", "json", "yaml"])
def test_codec_names_remain_available_as_explicit_spec_references(
    tmp_path: Path,
    spec_name: str,
) -> None:
    child = _write(
        tmp_path / "child.etcm",
        f"""spec {spec_name}:
  value: int = 1

  impl default:
    value: 2
""",
    )
    source = _write(
        tmp_path / "root.etcm",
        f"""spec Root:
  $payload: {child.name}#{spec_name}

  impl default:
    $payload: {child.name}#{spec_name}:default
""",
    )

    value = cast(dict[str, Any], load(f"{source}#Root:default", target="dict"))

    assert value["payload"] == {"value": 2}


@pytest.mark.parametrize(
    "field",
    [
        'document: File[json] = "data.json" [min_length=1]',
        'document: File[yaml] = "data.yaml" [in ["data.yaml"]]',
        'document: File[str] = "data.txt" [min_length=1]',
        'document: File[bytes] = "data.bin" [min_length=1]',
        'document: File[json] = "data.json" [path_exists="must_exist"]',
    ],
)
def test_file_content_constraints_are_rejected(tmp_path: Path, field: str) -> None:
    source = _config(tmp_path, field)

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    assert raised.value.diagnostic.code == "E_TYPE_MISMATCH"
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["reason"] == "file_content_constraint"


def test_constraints_apply_to_etcm_owned_file_containers(tmp_path: Path) -> None:
    _write(tmp_path / "data.json", '{"value": 1}')
    source = _config(
        tmp_path,
        'documents: list[File[json]] = ["data.json"] [min_length=2]',
    )

    graph = resolve(_selector(source))

    with pytest.raises(ETCMError) as raised:
        validate(graph)

    assert raised.value.diagnostic.code == "E_CONSTRAINT"


@pytest.mark.parametrize("filename", ["document", "document.toml", "document.json.gz"])
def test_exact_file_codec_accepts_any_filename(tmp_path: Path, filename: str) -> None:
    _write(tmp_path / filename, '{"value": 1}')
    source = _config(tmp_path, f'document: File[json] = "{filename}"')

    value = cast(dict[str, Any], load(_selector(source), target="dict"))

    assert value["document"] == {"value": 1}


def test_exact_file_codec_reports_its_parser_failure(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "mislabeled.json", "valid: yaml\n")
    source = _config(tmp_path, 'document: File[json] = "mislabeled.json"')

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "E_FILE_LOAD"
    assert diagnostic.details is not None
    assert diagnostic.details["codec"] == "json"
    assert diagnostic.details["reason"] == "parse_error"


@pytest.mark.parametrize(
    ("field", "expected_reason"),
    [
        ("document: File[json] = {inline: true}", "file_path_required"),
        ("documents: list[File[json]] = [{inline: true}]", "file_path_required"),
        ('document: File[json] = "missing.json"', "missing"),
        ('document: File[json] = "."', "not_file"),
    ],
)
def test_file_input_and_filesystem_failures_are_diagnostic(
    tmp_path: Path,
    field: str,
    expected_reason: str,
) -> None:
    source = _config(tmp_path, field)

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    assert raised.value.diagnostic.code in {"E_TYPE_MISMATCH", "E_FILE_LOAD"}
    assert raised.value.diagnostic.details is not None
    assert raised.value.diagnostic.details["reason"] == expected_reason
    if raised.value.diagnostic.code == "E_FILE_LOAD":
        assert raised.value.diagnostic.details["codec"] == "json"


@pytest.mark.parametrize(
    ("filename", "contents", "codec"),
    [
        ("broken.json", '{"missing": }', "json"),
        ("broken.yaml", "value: [unterminated\n", "yaml"),
        ("unsafe.yaml", "value: !!python/object:builtins.object {}\n", "yaml"),
    ],
)
def test_parser_failures_are_wrapped(
    tmp_path: Path,
    filename: str,
    contents: str,
    codec: str,
) -> None:
    _write(tmp_path / filename, contents)
    source = _config(tmp_path, f'document: File[{codec}] = "{filename}"')

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "E_FILE_LOAD"
    assert diagnostic.details is not None
    assert diagnostic.details["reason"] == "parse_error"
    assert diagnostic.details["codec"] == codec
    assert diagnostic.details["file_line"] >= 1
    assert diagnostic.details["file_column"] >= 1


@pytest.mark.parametrize("file_type", ["File[json]", "File[str]", "File[bytes]"])
def test_file_values_remain_outside_parameter_relations(
    tmp_path: Path,
    file_type: str,
) -> None:
    _write(tmp_path / "data.json", '{"value": 1}')
    source = _config(
        tmp_path,
        f'document: {file_type} = "data.json"\nconfirmation: int = 1 [== @document]',
    )

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    assert raised.value.diagnostic.code == "E_EXPRESSION_TYPE"


def test_file_values_remain_outside_named_assertions(tmp_path: Path) -> None:
    _write(tmp_path / "data.json", '{"value": 1}')
    source = _config(
        tmp_path,
        """
document: File[json] = "data.json"

assert opaque:
  @document == @document
""",
    )

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source))

    assert raised.value.diagnostic.code == "E_EXPRESSION_TYPE"


def test_file_contents_cannot_be_targeted_by_deep_overrides(tmp_path: Path) -> None:
    _write(tmp_path / "data.json", '{"value": 1}')
    source = _config(tmp_path, 'document: File[json] = "data.json"')

    with pytest.raises(ETCMError) as raised:
        resolve(_selector(source), overrides={"document.value": 2})

    assert raised.value.diagnostic.code == "E_INVALID_PATH"


def test_file_schema_annotations_remain_visible(tmp_path: Path) -> None:
    _write(tmp_path / "data.json", '{"value": 1}')
    source = _config(
        tmp_path,
        "\n".join(
            [
                'document: File[json] = "data.json"',
                'documents: list[File[json]] = ["data.json"]',
                'text: File[str] = "data.json"',
                'binary: File[bytes] = "data.json"',
            ]
        ),
    )
    graph = validate(resolve(_selector(source)))

    summary = pydantic_schema_summary(graph)
    fields = {field["name"]: field for field in summary["classes"][0]["fields"]}

    assert fields["document"]["annotation"] == "File[json]"
    assert fields["documents"]["annotation"] == "list[File[json]]"
    assert fields["text"]["annotation"] == "File[str]"
    assert fields["binary"]["annotation"] == "File[bytes]"


def test_file_paths_are_not_added_as_path_values_or_graph_sources(tmp_path: Path) -> None:
    _write(tmp_path / "data.json", '{"value": 1}')
    source = _config(tmp_path, 'document: File[json] = "data.json"')

    graph = resolve(_selector(source))

    assert graph.path_resolution == ()
    assert graph.sources == (source.resolve(),)
    payload = graph.to_dict(path_base=tmp_path)
    root = next(node for node in payload["nodes"] if node["id"] == "root")
    assert root["fields"]["document"]["default"] == "data.json"
    assert root["field_values"]["document"]["literal"] == {
        "kind": "string",
        "value": "data.json",
    }
    assert root["field_values"]["document"]["value"] == {"value": 1}
