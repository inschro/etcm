# Python API

The top-level `etcm` package exposes the normal load pipeline:

```python
from etcm import OverrideInput, Resolver, convert, load, resolve, validate
```

## One-step loading

```python
def load(
    selector: str,
    *,
    target: Literal["pydantic", "dataclass", "dict"] = "pydantic",
    path_exists: Literal["allow_missing", "must_exist"] = "allow_missing",
    overrides: OverrideInput | None = None,
    force_overrides: bool = False,
    override_base: str | Path | None = None,
) -> Any: ...
```

`load()` resolves, validates, and converts the selected implementation.

```python
from etcm import load

cfg = load("configs/train.etcm#TrainRun:smoke")
print(cfg.model.hidden_size)
```

Targets:

| Target | Result |
| --- | --- |
| `pydantic` | Generated Pydantic model hierarchy |
| `dataclass` | Generated dataclass hierarchy |
| `dict` | Nested mapping payload |

All targets are created only after successful validation.

## Staged pipeline

Use the staged functions when you need to inspect or store the graph:

```python
from etcm import convert, resolve, validate

graph = resolve("configs/train.etcm#TrainRun:smoke")
assert graph.validated is False

graph = validate(graph)
assert graph.validated is True

cfg = convert(graph, target="pydantic")
```

### `resolve()`

```python
def resolve(
    selector: str,
    *,
    path_exists: Literal["allow_missing", "must_exist"] = "allow_missing",
    overrides: OverrideInput | None = None,
    force_overrides: bool = False,
    override_base: str | Path | None = None,
) -> ResolvedGraph: ...
```

Resolution loads ETCM sources, selects specs and implementations, composes
inheritance and references, applies overrides, loads effective typed files, and
computes derived values. It returns an inspectable graph whose `validated` flag is
false.

Some failures necessarily occur during resolution, including syntax errors, missing
selectors, inheritance cycles, invalid schemas, missing required inputs for a
derivation, and derived-expression failures.

### `validate()`

```python
def validate(graph: ResolvedGraph) -> ResolvedGraph: ...
```

Validation checks resolved types, reference assignability, override policy,
filesystem policy, field constraints, relational constraints, and named assertions.
It returns a new graph with `validated == True`.

### `convert()`

```python
def convert(
    graph: ResolvedGraph,
    *,
    target: Literal["pydantic", "dataclass", "dict"] = "pydantic",
    force: bool = False,
) -> Any: ...
```

Conversion normally requires a validated graph. `force=True` permits conversion of
an unvalidated graph and should be reserved for inspection or specialized tooling;
it does not perform validation.

## Resolver objects

`Resolver` holds the default `Path` existence policy and exposes the same pipeline
as methods:

```python
from etcm import Resolver

resolver = Resolver(path_exists="must_exist")
graph = resolver.resolve("configs/train.etcm#TrainRun:production")
graph = resolver.validate(graph)
cfg = resolver.convert(graph, target="dataclass")
```

```python
@dataclass(frozen=True)
class Resolver:
    path_exists: Literal["allow_missing", "must_exist"] = "allow_missing"

    def resolve(...) -> ResolvedGraph: ...
    def validate(graph: ResolvedGraph) -> ResolvedGraph: ...
    def convert(...) -> Any: ...
    def load(...) -> Any: ...
```

Use one resolver when multiple loads should share the same path policy. Each call
still creates independent resolution state.

## Overrides

`OverrideInput` accepts either a mapping or a sequence of strings:

```python
type OverrideInput = Mapping[str, Any] | Sequence[str]
```

```python
from pathlib import Path

from etcm import load

cfg = load(
    "configs/train.etcm#TrainRun:debug",
    overrides={
        "runtime.devices": 2,
        "checkpoint": Path("runs/latest.ckpt"),
    },
    override_base="/srv/project",
)
```

Mapping values are normalized from native Python scalars, `Path`, lists, and
string-keyed mappings. Sequence entries use `PATH=VALUE` and ETCM literal syntax.
See the [override guide](../guides/overrides.md) for reference replacement, force
authorization, and audit behavior.

## Resolved graphs

Graph types are available from `etcm.resolve`:

```python
from etcm.resolve import ResolvedEdge, ResolvedField, ResolvedGraph, ResolvedNode
```

Important `ResolvedGraph` attributes:

| Attribute | Description |
| --- | --- |
| `root_selector` | Canonical selected implementation |
| `validated` | Whether validation completed |
| `nodes` | Typed resolved object nodes |
| `edges` | Relationships between nodes |
| `sources` | ETCM source files used by the graph |
| `path_resolution` | Resolved `Path` and typed-file path records |

Serialize the graph to a JSON-compatible mapping with `to_dict()`:

```python
payload = graph.to_dict()
portable = graph.to_dict(path_base="/srv/project")
```

`path_base` makes paths underneath that base relative in the output. Typed binary
file values are projected to `null` at this JSON boundary; the Python graph retains
the bytes.

Nodes expose field definitions, materialized values, source locations, assertion
definitions, and per-field `ResolvedValue` audit records.

## Errors and diagnostics

ETCM operational failures raise `ETCMError`:

```python
from etcm import load
from etcm.errors import ETCMError

try:
    cfg = load("configs/train.etcm#TrainRun:production")
except ETCMError as exc:
    diagnostic = exc.diagnostic
    print(diagnostic.code)
    print(diagnostic.message)
    print(diagnostic.source_path)
    print(diagnostic.line, diagnostic.column)
    print(diagnostic.selector)
    print(diagnostic.graph_path)
    print(diagnostic.details)
```

`Diagnostic` is immutable and may contain:

- stable error code and human-readable message
- source path and source span
- selector and graph path
- structured, error-specific details

Invalid Python argument shapes and unsupported target or policy strings may raise
`TypeError` or `ValueError` instead.

## Static typing boundary

`load()` and `convert()` return `Any`. ETCM validates before materialization, but
the generated runtime class is dynamic from the perspective of pyright, Pylance,
and mypy. This keeps object-style access ergonomic, but static checkers cannot catch
misspelled fields or incompatible usage after that boundary unless the consuming
project supplies separate Python-visible types.
