# Core concepts

ETCM treats configuration as a typed graph of objects rather than an unstructured
mapping. Specs define object shapes, implementations supply named values, selectors
identify exact definitions, and references connect objects into a graph.

## Documents

An `.etcm` file can take one of two forms:

1. Define one or more specs, with their implementations nested inside each spec.
2. Import one external spec with top-level `$spec` and define implementations for
   that imported spec.

A file cannot mix inline specs with top-level `$spec`, and top-level implementations
are valid only in a `$spec` file.

## Specs and fields

A spec owns its fields, defaults, validation, derived expressions, assertions, and
override policies:

```text title="service.etcm"
spec Service:
  host: str = "127.0.0.1"
  port: int [>0; <=65535]
  workers: int = 1 [>0]
  endpoint: str

  impl local:
    port: 8080
    endpoint: "http://127.0.0.1:8080"
```

`port` and `endpoint` are required because they have no default or derived
expression. `host` and `workers` are available to every implementation unless the
implementation replaces them under their override policy.

The field operators have distinct meanings:

| Syntax | Meaning |
| --- | --- |
| `field: T` | A required field of type `T` |
| `field: T = value` | A field with a declaration default |
| `field: T := expression` | A value computed by ETCM |
| `field: T [rules]` | Validation and field metadata |

## Value and container types

ETCM supports these value shapes:

| Type | Value |
| --- | --- |
| `str` | Double-quoted string |
| `int` | Integer, excluding Boolean values |
| `float` | Integer or floating-point number |
| `bool` | `true` or `false` |
| `null` | `null` |
| `Path` | A source-relative filesystem path |
| `list[T]` | List whose items match `T` |
| `dict[str, T]` | String-keyed map whose values match `T` |
| `T | null` | Nullable value |
| `File[T]` | File-backed value decoded with an explicit codec |

Lists and maps use compact literal syntax:

```text
tags: list[str] = ["training", "local"]
limits: dict[str, int] = {cpu: 4, memory: 16}
timeout: float | null = null
```

See [typed files](typed-files.md) for the supported `File[T]` codecs and their
composition rules.

## Inline objects and field paths

Indentation defines anonymous nested objects:

```text
spec Training:
  optimizer:
    learning_rate: float = 0.001 [>0]
    weight_decay: float = 0.0 [>=0]
```

Dotted declarations are equivalent:

```text
spec Training:
  optimizer.learning_rate: float = 0.001 [>0]
  optimizer.weight_decay: float = 0.0 [>=0]
```

The two forms can be mixed, and implementations accept the same paths:

```text
spec Training:
  optimizer:
    learning_rate: float = 0.001 [>0]
  optimizer.weight_decay: float = 0.0 [>=0]

  impl fast:
    optimizer.learning_rate: 0.003
    optimizer:
      weight_decay: 0.01
```

A path inside an indented block is relative to that block. Duplicate canonical
paths and conflicts between assigning a value and assigning one of its descendants
are errors.

## Implementations

An `impl` is a named concrete configuration owned by a spec:

```text
spec Model:
  hidden_size: int [>0]
  layers: int [>0]

  impl tiny:
    hidden_size: 256
    layers: 4

  impl base:
    hidden_size: 768
    layers: 12
```

Implementation names are identities, not special keywords. An implementation named
`default` is still selected explicitly as `:default`; ETCM never chooses it
automatically.

Implementations can inherit from other implementations. Specs and implementations
can also compose definitions across files; see [composition](composition.md).

## Selectors

Selectors identify a target without opening the target file to guess its contents.

| Form | Target |
| --- | --- |
| `path.etcm#Spec` | Spec in another file |
| `#Spec` | Spec in the current file |
| `path.etcm#Spec:impl` | Implementation in another file |
| `#Spec:impl` | Implementation in the current file |
| `:impl` | Implementation in the active local spec |

Root calls always use a complete implementation selector:

```python
from etcm import load

cfg = load("configs/train.etcm#TrainRun:smoke")
```

Spec selectors appear in inheritance, top-level `$spec`, and reference declarations.
Implementation selectors appear in inheritance and reference assignments.

## Paths

`Path` is a first-class field type:

```text
spec Dataset:
  input_file: Path [path_exists="must_exist"; path_kind="file"]
  output_dir: Path [path_exists="allow_missing"; path_kind="dir"]
  cache_dir: Path [path_exists="resolver"; path_kind="dir"]
```

Paths written in an ETCM file are resolved relative to the file that contributed
the value. This identity is retained through references and inheritance. The
supported policies are:

| Setting | Values |
| --- | --- |
| `path_exists` | `must_exist`, `allow_missing`, or `resolver` |
| `path_kind` | `file`, `dir`, or `any` |

`resolver` delegates existence checking to `Resolver.path_exists`, which defaults
to `allow_missing`. Existing paths are always checked against `path_kind`.

## Comments and indentation

Comments start with `#` at the beginning of a line or after whitespace. A `#` inside
a quoted string remains part of the string. Where the grammar expects a selector,
`#Spec` begins a same-file selector instead of a comment.

Indentation is significant and must use spaces. Tab indentation is rejected with a
source diagnostic.

## Processing model

The public pipeline separates inspection from validation and conversion:

```text
parse → resolve defaults/references/overrides → derive values → validate → convert
```

- `resolve()` returns an inspectable, unvalidated `ResolvedGraph`.
- `validate()` checks types, paths, policies, constraints, and assertions.
- `convert()` materializes a validated graph as Pydantic, dataclass, or dictionary.
- `load()` performs all three operations in one call.

Read the [Python API reference](../reference/python-api.md) for signatures and return
types.
