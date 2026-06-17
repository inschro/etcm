# Stage 2 Fixture Contract

Stage 2 creates the first fixture tree. These fixtures are not expected to be
fully parsed yet. They define the target language examples and failure cases
that Stage 3 parser work must satisfy.

## Directory Layout

```text
tests/fixtures/
  valid/
  invalid/
  golden/
```

## Initial Valid Fixtures

`valid/inline_spec.etcm`

```etcm
spec DataConfig:
  train_file: Path = Field(path_exists="must_exist", path_kind="file")
  retries: int = Field(default=2, gt=0)

impl smoke:
  train_file: "data/smoke.txt"
  retries: 2
```

`valid/spec_ref_impls.etcm`

```etcm
$spec: specs/data.etcm

impl smoke:
  train_file: "data/smoke.txt"
  retries: 2
```

## Initial Invalid Fixtures

`invalid/duplicate_field.etcm`

```etcm
spec BadConfig:
  retries: int
  retries: int
```

`invalid/malformed_syntax.etcm`

```etcm
spec Broken:
  retries: [
```

## Golden Outputs

Stage 2 should add `tests/fixtures/golden/README.md` describing future golden
files:

- parsed AST summary
- normalized IR summary
- resolved graph JSON
- generated Pydantic schema summary
- diagnostic text

Do not add full golden outputs until the parser and IR serializer exist.

## Fixture Tests

Stage 2 tests should only verify:

- fixture directories exist
- initial fixture files exist
- fixture files are non-empty
- golden README exists

Parser correctness starts in Stage 3.

