from __future__ import annotations

import concurrent.futures
import json
from collections import Counter
from functools import partial
from multiprocessing import get_context
from pathlib import Path

import pytest

from etcm.cli import main
from etcm.ir import Document
from etcm.resolve import ResolvedGraph, Resolver
from etcm.syntax import parser as syntax_parser

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def test_resolve_command_prints_unvalidated_graph_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#TrainRun:smoke")

    exit_code = main(["resolve", selector])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["root_selector"] == selector
    assert payload["validated"] is False
    assert [node["id"] for node in payload["nodes"]] == ["root", "root.model"]


def test_validate_command_prints_validated_graph_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#TrainRun:smoke")

    exit_code = main(["validate", selector])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["root_selector"] == selector
    assert payload["validated"] is True


def test_validate_short_reports_success(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#TrainRun:smoke")

    exit_code = main(["validate", selector, "--short"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == f"OK: {selector}\n"
    assert captured.err == ""


def test_validate_command_reports_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(FIXTURES / "invalid/missing_required.etcm#MissingRequired:default")

    exit_code = main(["validate", selector])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "E_MISSING_FIELD: Missing required field 'name'." in captured.err
    assert "graph_path: root.name" in captured.err


def test_validate_command_formats_relational_evaluation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "model.etcm"
    source.write_text(
        """spec Model:
  heads: int [>0]
  hidden: int [% @heads == 0]

  impl invalid:
    heads: 12
    hidden: 512
""",
        encoding="utf-8",
    )

    exit_code = main(["validate", f"{source}#Model:invalid"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "constraint:\n  % @heads == 0" in captured.err
    assert "resolved values:\n  hidden: 512\n  heads: 12" in captured.err
    assert "evaluation:\n  512 % 12 == 0\n  8 == 0" in captured.err


def test_resolve_command_includes_derived_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(
        FIXTURES
        / "valid/parameter_relations/training.etcm#TrainingConfig:distributed"
    )

    exit_code = main(["resolve", selector])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    root = next(node for node in payload["nodes"] if node["id"] == "root")
    assert exit_code == 0
    assert captured.err == ""
    assert root["values"]["global_batch_size"] == 32
    assert root["field_values"]["global_batch_size"]["origin"] == "derived"


def test_load_command_defaults_to_dict_target(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(
        FIXTURES / "valid/spec_inheritance_resolver/cuda.etcm#CudaRuntime:default"
    )

    exit_code = main(["load", selector])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {"device": "cuda", "gpus": 2}


@pytest.mark.parametrize("target", ["dict", "dataclass", "pydantic"])
def test_load_command_target_modes_emit_json(
    target: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(
        FIXTURES / "valid/spec_inheritance_resolver/cuda.etcm#CudaRuntime:default"
    )

    exit_code = main(["load", selector, "--target", target])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {"device": "cuda", "gpus": 2}


def test_load_dataclass_target_serializes_paths_as_strings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/path_policies/data.etcm#DataConfig:default")

    exit_code = main(["load", selector, "--target", "dataclass"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert isinstance(payload["existing_file"], str)
    assert payload["existing_file"].endswith(
        "tests/fixtures/valid/path_policies/data/existing.txt"
    )


def test_load_command_reports_diagnostic(capsys: pytest.CaptureFixture[str]) -> None:
    selector = str(FIXTURES / "invalid/missing_required.etcm#MissingRequired:default")

    exit_code = main(["load", selector])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "E_MISSING_FIELD: Missing required field 'name'." in captured.err


def test_validate_all_scans_directory_recursively(capsys: pytest.CaptureFixture[str]) -> None:
    root = FIXTURES / "valid/typed_refs"

    exit_code = main(["validate-all", str(root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out == "4 total, 4 OK, 0 fail\n"


def test_validate_all_reuses_parsed_documents_within_a_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path.resolve()
    first = root / "first.etcm"
    second = root / "second.etcm"
    shared = root / "shared.etcm"
    shared.write_text("spec Shared:\n  value: int\n", encoding="utf-8")
    first.write_text(
        "$spec: shared.etcm#Shared\n\nimpl one:\n  value: 1\n\nimpl two:\n  value: 2\n",
        encoding="utf-8",
    )
    second.write_text("$spec: shared.etcm#Shared\n\nimpl three:\n  value: 3\n", encoding="utf-8")

    calls: Counter[Path] = Counter()
    sources: list[tuple[Path, ...]] = []
    parse_document = syntax_parser.parse_document
    validate = Resolver.validate

    def track_parse(text: str, source_path: str | Path) -> Document:
        calls[Path(source_path)] += 1
        return parse_document(text, source_path)

    def track_sources(resolver: Resolver, graph: ResolvedGraph) -> ResolvedGraph:
        sources.append(graph.sources)
        return validate(resolver, graph)

    monkeypatch.setattr(syntax_parser, "parse_document", track_parse)
    monkeypatch.setattr(Resolver, "validate", track_sources)

    args = ["validate-all", str(root), str(second)]
    assert main(args) == 0
    assert capsys.readouterr().out == "3 total, 3 OK, 0 fail\n"
    assert calls == {first: 1, second: 1, shared: 1}
    assert sources == [(first, shared), (first, shared), (second, shared)]

    shared.write_text("spec Shared:\n  value: str\n", encoding="utf-8")
    assert main(args) == 1
    assert capsys.readouterr().out.endswith("3 total, 0 OK, 3 fail\n")
    assert calls == {first: 2, second: 2, shared: 2}


@pytest.mark.parametrize("output_args", [("--verbose",), ("--format", "json")])
def test_validate_all_parallel_matches_serial(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    output_args: tuple[str, ...],
) -> None:
    (tmp_path / "a.etcm").write_text(
        "spec Good:\n  value: int\n  impl default:\n    value: 1\n", encoding="utf-8"
    )
    (tmp_path / "b.etcm").write_text(
        'spec Strict:\n  path: Path\n  impl default:\n    path: "absent.txt"\n', encoding="utf-8"
    )
    (tmp_path / "c.etcm").write_text("spec Broken:\n  value: int\n  value: int\n", encoding="utf-8")
    args = [
        "validate-all",
        str(tmp_path),
        str(tmp_path / "missing"),
        "--path-exists",
        "must_exist",
        *output_args,
    ]

    assert main([*args, "--jobs", "1"]) == 1
    serial = capsys.readouterr()
    assert serial.err == ""
    assert "E_MISSING_SELECTOR" in serial.out
    assert "E_INVALID_PATH" in serial.out
    assert "E_DUPLICATE_FIELD" in serial.out
    if "--format" in output_args:
        payload = json.loads(serial.out)
        assert (payload["total"], payload["ok"], payload["fail"]) == (4, 1, 3)
        assert [result["artifact"] for result in payload["results"]] == [
            (tmp_path / "missing").as_posix(),
            f"{(tmp_path / 'a.etcm').resolve().as_posix()}#Good:default",
            f"{(tmp_path / 'b.etcm').resolve().as_posix()}#Strict:default",
            (tmp_path / "c.etcm").resolve().as_posix(),
        ]
        assert payload["results"][3]["diagnostic"]["source_path"] == (
            tmp_path / "c.etcm"
        ).resolve().as_posix()

    monkeypatch.setattr(
        concurrent.futures,
        "ProcessPoolExecutor",
        partial(concurrent.futures.ProcessPoolExecutor, mp_context=get_context("spawn")),
    )
    assert main([*args, "--jobs", "4"]) == 1
    assert capsys.readouterr() == serial


@pytest.mark.parametrize("jobs", ["0", "-1", "many"])
def test_validate_all_rejects_invalid_jobs(capsys: pytest.CaptureFixture[str], jobs: str) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["validate-all", "--jobs", jobs])

    assert raised.value.code == 2
    assert "--jobs" in capsys.readouterr().err


def test_validate_all_enumerates_multi_spec_implementations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = FIXTURES / "valid/multiple_specs.etcm"

    exit_code = main(["validate-all", str(source), "--verbose"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert f"OK: {source.resolve().as_posix()}#TrainConfig:smoke" in captured.out
    assert f"OK: {source.resolve().as_posix()}#EvalConfig:default" in captured.out
    assert captured.out.endswith("2 total, 2 OK, 0 fail\n")


def test_validate_all_enumerates_spec_ref_implementations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = FIXTURES / "valid/spec_reuse/variants.etcm"

    exit_code = main(["validate-all", str(source), "--verbose"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert f"OK: {source.resolve().as_posix()}#DataConfig:smoke" in captured.out
    assert captured.out.endswith("1 total, 1 OK, 0 fail\n")


def test_validate_all_enumerates_exact_spec_ref(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = tmp_path / "spec.etcm"
    spec.write_text(
        "\n".join(
            [
                "spec DataConfig:",
                "  value: int",
                "",
            ]
        ),
        encoding="utf-8",
    )
    source = tmp_path / "variants.etcm"
    source.write_text(
        "\n".join(
            [
                "$spec: spec.etcm#DataConfig",
                "",
                "impl smoke:",
                "  value: 1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(["validate-all", str(source), "--verbose"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert f"OK: {source.resolve().as_posix()}#DataConfig:smoke" in captured.out
    assert captured.out.endswith("1 total, 1 OK, 0 fail\n")


def test_validate_all_skips_spec_only_files(capsys: pytest.CaptureFixture[str]) -> None:
    source = FIXTURES / "valid/no_impl.etcm"

    exit_code = main(["validate-all", str(source)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out == "0 total, 0 OK, 0 fail\n"


def test_validate_all_reports_all_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    valid = tmp_path / "valid.etcm"
    valid.write_text(
        "\n".join(
            [
                "spec Good:",
                "  value: int",
                "",
                "  impl default:",
                "    value: 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    missing_required = tmp_path / "missing.etcm"
    missing_required.write_text(
        "\n".join(
                [
                    "spec Missing:",
                    "  value: int",
                    "  other: int = 1",
                    "",
                    "  impl default:",
                    "    other: 2",
                    "",
                ]
            ),
        encoding="utf-8",
    )
    malformed = tmp_path / "malformed.etcm"
    malformed.write_text("spec Broken:\n  value int\n", encoding="utf-8")

    exit_code = main(["validate-all", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == ""
    assert f"FAIL: {malformed.resolve().as_posix()}" in captured.out
    assert f"FAIL: {missing_required.resolve().as_posix()}#Missing:default" in captured.out
    assert "E_PARSE_UNEXPECTED_TOKEN" in captured.out
    assert "E_MISSING_FIELD" in captured.out
    assert captured.out.endswith("3 total, 1 OK, 2 fail\n")


def test_validate_all_quiet_prints_only_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "missing.etcm"
    source.write_text(
        "\n".join(
                [
                    "spec Missing:",
                    "  value: int",
                    "  other: int = 1",
                    "",
                    "  impl default:",
                    "    other: 2",
                    "",
                ]
        ),
        encoding="utf-8",
    )

    exit_code = main(["validate-all", str(tmp_path), "--quiet"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == ""
    assert captured.out == "1 total, 0 OK, 1 fail\n"


def test_validate_all_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    source = FIXTURES / "valid/multiple_specs.etcm"

    exit_code = main(["validate-all", str(source), "--format", "json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["total"] == 2
    assert payload["ok"] == 2
    assert payload["fail"] == 0
    assert [result["ok"] for result in payload["results"]] == [True, True]


def test_validate_all_propagates_path_exists_policy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = FIXTURES / "valid/path_policies/data.etcm"

    exit_code = main(["validate-all", str(source), "--path-exists", "must_exist"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == ""
    assert "FAIL:" in captured.out
    assert "E_INVALID_PATH" in captured.out
    assert captured.out.endswith("1 total, 0 OK, 1 fail\n")


def test_validate_all_missing_scan_path_fails(capsys: pytest.CaptureFixture[str]) -> None:
    missing = FIXTURES / "does-not-exist"

    exit_code = main(["validate-all", str(missing)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == ""
    assert "FAIL:" in captured.out
    assert "E_MISSING_SELECTOR" in captured.out
    assert captured.out.endswith("1 total, 0 OK, 1 fail\n")


@pytest.mark.parametrize("command", ["inspect", "graph"])
def test_removed_commands_fail_argparse(
    command: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selector = str(FIXTURES / "valid/typed_refs/train.etcm#TrainRun:smoke")

    with pytest.raises(SystemExit) as raised:
        main([command, selector])

    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert captured.out == ""
    assert "invalid choice" in captured.err
