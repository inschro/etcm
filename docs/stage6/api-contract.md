# Stage 6 API Contract

The public API is an orthogonal pipeline:

```python
from etcm import convert, load, resolve, validate

graph = resolve("configs/train.etcm#smoke")
graph = validate(graph)
cfg = convert(graph, target="pydantic")

cfg = load("configs/train.etcm#smoke", target="pydantic")
```

`load()` is the main ergonomic API for application code. It orchestrates:

```text
selector -> resolve() -> graph -> validate() -> validated graph -> convert()
```

## Functions

- `resolve(selector, *, path_exists="allow_missing") -> ResolvedGraph`
- `validate(graph: ResolvedGraph) -> ResolvedGraph`
- `convert(graph, *, target="pydantic", force=False) -> object`
- `load(selector, *, target="pydantic", path_exists="allow_missing") -> object`

`Resolver` exposes the same methods for callers that want reusable settings.

## Semantics

- `resolve()` builds a graph and may fail only on graph-build blockers.
- `validate()` checks semantic validity and returns a new graph with
  `validated=True`.
- `convert()` requires a validated graph unless `force=True`.
- `force=True` bypasses only the validated-graph guard; it does not bypass field
  policies or constraints.
- `target` values are `pydantic`, `dataclass`, and `dict`.
