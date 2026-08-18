# Stage 5 Resolver Contract

Stage 5 starts from `parse_document()` output and resolves semantic meaning.

## Public API

```python
from etcm import Resolver, resolve, validate

graph = resolve("configs/train.etcm#TrainRun:smoke")
graph = validate(graph)
```

`Resolver.load(..., target="pydantic")` is implemented by Stage 6 as a
resolve/validate/convert convenience.

## Semantics

- root selector paths resolve relative to the current working directory
- nested selectors resolve relative to the file that declares the selector
- root selectors require `path.etcm#Spec:impl`
- spec selectors use `path.etcm#Spec` or same-file `#Spec`
- implementation selectors use `path.etcm#Spec:impl`, same-file `#Spec:impl`,
  or active-spec `:impl`
- relative and absolute paths are accepted, and every selector path ends in
  `.etcm`
- selectors never infer a spec, search for a unique implementation, or infer
  an implementation named `default`
- `$spec` imports an external spec unchanged
- spec inheritance merges parent fields before child fields
- implementation inheritance applies parent values before local assignments
- `$field` refs materialize graph edges and node values
- `Path` values resolve relative to the file where the value was declared
- `File[str]`, `File[bytes]`, `File[json]`, and `File[yaml]` paths are
  materialized after effective overrides are composed, relative to the source
  that declared each path

## Type Rules

- `str`, `int`, `float`, `bool`, `null`, and `Path` are scalar types
- `File[str]`, `File[bytes]`, `File[json]`, and `File[yaml]` are opaque,
  file-backed leaf types
- `float` accepts integer and float literals
- `int` does not accept booleans
- `list[T]`, `dict[str, T]`, and unions are checked structurally
- file leaves declare exactly one codec and compose recursively in lists and
  dictionary values; filename suffixes never select a codec
- named spec/object fields require references
- referenced implementations must be assignable through spec inheritance
- fields without defaults must be supplied by inheritance or local assignment

## Override Rules

Inherited values can be changed only according to field policy:

- `allow`: replace
- `deny`: fail
- `force_only`: fail in Stage 5 because no force API exists yet
- `append`: append list values
- `merge`: merge mapping values
