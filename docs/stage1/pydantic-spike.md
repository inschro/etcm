# Pydantic Runtime Spike

## Goal

Prove that generated Pydantic v2 models can support the first runtime view:

- runtime-created model classes
- field constraints
- `Path` coercion
- immutable/extra-forbid configuration

## Local Result

Base environment did not have Pydantic installed. The spike used `uv run --with
pydantic`, which installed an isolated Pydantic v2 environment.

Command:

```bash
uv run --with pydantic python - <<'PY'
from pathlib import Path
from pydantic import ConfigDict, Field, ValidationError, create_model

Dynamic = create_model(
    'DataConfig',
    __config__=ConfigDict(frozen=True, extra='forbid'),
    steps=(int, Field(gt=0)),
    dataset_path=(Path, Field()),
)
instance = Dynamic(steps=2, dataset_path='data/smoke.txt')
print(type(instance.dataset_path).__name__, instance.dataset_path)
print(instance.model_dump())
try:
    Dynamic(steps=0, dataset_path='data/smoke.txt')
except ValidationError as exc:
    print(exc.errors()[0]['type'])
PY
```

Observed output:

```text
PosixPath data/smoke.txt
{'steps': 2, 'dataset_path': PosixPath('data/smoke.txt')}
greater_than
```

## Decision

Generate Pydantic v2 models for the first runtime view.

## Consequences

- Use `create_model()` with `__config__=ConfigDict(...)`, not `model_config=...`.
- ETCM must perform path existence and source-relative path resolution before or
  during Pydantic view generation. Pydantic can coerce to `Path`, but ETCM owns
  field-level and resolver-level path policy.
- Pydantic validation errors should be wrapped in ETCM diagnostics that include
  source spans and graph paths.
- Generated Pydantic classes should be implementation details of the view layer,
  not canonical graph nodes.

## Risks

- Pydantic docs warn that dynamic model creation can execute arbitrary code if
  string annotations require evaluation. ETCM should generate concrete Python
  types, not string annotations.
- Dynamic class names must be deterministic and collision-resistant for nested
  specs and repeated loads.
- JSON serialization of `Path` should be controlled by ETCM's dict/JSON export,
  since Pydantic `model_dump()` in Python mode returns `Path` objects.

