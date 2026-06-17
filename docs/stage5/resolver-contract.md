# Stage 5 Resolver Contract

Stage 5 starts from `parse_document()` output and resolves semantic meaning.

## Public API

```python
from etcm import Resolver, resolve, validate

graph = resolve("configs/train.etcm#smoke")
validate("configs/train.etcm#smoke")
```

`Resolver.load(..., as_="pydantic")` remains a Stage 6 generated-view boundary.

## Semantics

- root selector paths resolve relative to the current working directory
- nested selectors resolve relative to the file that declares the selector
- omitted implementation fragments resolve to `#default`
- `$spec` imports an external spec unchanged
- spec inheritance merges parent fields before child fields
- implementation inheritance applies parent values before local assignments
- `$field` refs materialize graph edges and node values
- `Path` values resolve relative to the file where the value was declared

## Type Rules

- `str`, `int`, `float`, `bool`, `null`, and `Path` are primitive types
- `float` accepts integer and float literals
- `int` does not accept booleans
- `list[T]`, `dict[str, T]`, and unions are checked structurally
- named non-primitive fields require references
- referenced implementations must be assignable through spec inheritance
- fields without defaults must be supplied by inheritance or local assignment

## Override Rules

Inherited values can be changed only according to field policy:

- `allow`: replace
- `deny`: fail
- `force_only`: fail in Stage 5 because no force API exists yet
- `append`: append list values
- `merge`: merge mapping values
