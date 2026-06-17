from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


def test_fixture_directories_exist() -> None:
    for name in ("valid", "invalid", "golden"):
        assert (FIXTURES / name).is_dir()


def test_initial_fixture_files_exist_and_are_non_empty() -> None:
    paths = [
        FIXTURES / "valid" / "inline_spec.etcm",
        FIXTURES / "valid" / "spec_ref_impls.etcm",
        FIXTURES / "invalid" / "duplicate_field.etcm",
        FIXTURES / "invalid" / "malformed_syntax.etcm",
        FIXTURES / "golden" / "README.md",
    ]

    for path in paths:
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()
