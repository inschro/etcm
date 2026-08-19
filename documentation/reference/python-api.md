# Python API reference

The top-level package exposes the normal configuration pipeline:

```python
from etcm import OverrideInput, Resolver, convert, load, resolve, validate
```

## `load()`

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

`load()` resolves, validates, and converts one complete implementation selector:

```python
from etcm import load

pet = load("pets.etcm#Pet:pepper")
print(pet.name)
```

Targets:

| Target | Result |
| --- | --- |
| `pydantic` | Generated Pydantic model hierarchy; default |
| `dataclass` | Generated dataclass hierarchy |
| `dict` | Nested ordinary mapping |

All targets are created only after successful validation.

## Staged pipeline

Use the staged functions when a tool needs to inspect the graph:

```python
from etcm import convert, resolve, validate

graph = resolve("stays.etcm#Stay:pepper_weekend")
assert graph.validated is False

graph = validate(graph)
assert graph.validated is True

stay = convert(graph, target="dict")
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

Resolution selects and composes specs, implementations, inheritance, references,
defaults, external overrides, typed files, and derived fields. The returned graph
is inspectable but not validated.

### `validate()`

```python
def validate(graph: ResolvedGraph) -> ResolvedGraph: ...
```

Validation checks resolved types, reference assignability, paths, metadata, field
constraints, and named assertions. It returns a new graph with
`validated == True`.

### `convert()`

```python
def convert(
    graph: ResolvedGraph,
    *,
    target: Literal["pydantic", "dataclass", "dict"] = "pydantic",
    force: bool = False,
) -> Any: ...
```

Conversion requires a validated graph unless `force=True`. Force conversion is
for inspection; it does not perform or bypass validation successfully.

The exact stage ordering is documented in
[resolution and validation](resolution.md).

## `Resolver`

`Resolver` stores the default path-existence policy and exposes the same pipeline
as methods:

```python
from etcm import Resolver

resolver = Resolver(path_exists="must_exist")
graph = resolver.resolve("stays.etcm#Stay:pepper_weekend")
graph = resolver.validate(graph)
stay = resolver.convert(graph, target="dataclass")
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

Calls do not share mutable resolution state.

## Overrides

`OverrideInput` accepts a mapping or sequence of `PATH=VALUE` strings:

```python
type OverrideInput = Mapping[str, Any] | Sequence[str]
```

```python
stay = load(
    "stays.etcm#Stay:pepper_weekend",
    target="dict",
    overrides={"nights": 5},
)
```

Mappings accept native Python scalar values, `Path`, lists, and string-keyed
mappings. Sequence values use ETCM literal syntax. See the
[override reference](overrides.md) for reference replacement, policy, and path
base behavior.

## Resolved graph

Graph types live in `etcm.resolve`:

```python
from etcm.resolve import ResolvedEdge, ResolvedField, ResolvedGraph, ResolvedNode
```

Important `ResolvedGraph` attributes:

| Attribute | Description |
| --- | --- |
| `root_selector` | Canonical selected implementation |
| `validated` | Whether validation completed |
| `nodes` | Resolved object nodes |
| `edges` | Typed relationships between nodes |
| `sources` | ETCM files used during resolution |
| `path_resolution` | Resolved `Path` and typed-file path records |

Serialize the graph for inspection:

```python
payload = graph.to_dict()
portable = graph.to_dict(path_base="/srv/project")
```

`path_base` makes paths below that directory relative in the output. The mapping
is intended for JSON output; typed binary file values are represented as `null` at
that boundary.

Nodes expose their fields, resolved values, source identity, assertions, and
per-field origin or override audit records.

## Errors

Operational failures raise `ETCMError`:

```python
from etcm import load
from etcm.errors import ETCMError

try:
    load("pets.etcm#Pet:missing")
except ETCMError as exc:
    print(exc.diagnostic.code)
    print(exc.diagnostic.message)
```

`Diagnostic` is immutable and may include a source path and span, selector, graph
path, and error-specific structured details. Invalid Python argument shapes or
unsupported policy and target strings may raise `TypeError` or `ValueError`.

## Static typing boundary

`load()` and `convert()` return `Any` because ETCM creates the runtime model from
the selected spec. ETCM validates the object, but a static checker cannot infer
fields from a selector string. Consumers that require static field checking should
define a separate Python-visible protocol or model at their application boundary.
