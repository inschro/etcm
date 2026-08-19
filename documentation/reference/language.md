# Language reference

This page is a compact reference for ETCM syntax. The guides explain the same
features in context.

## Identifiers and indentation

Spec, implementation, field, and assertion names start with a letter or underscore
and continue with letters, digits, or underscores. Indentation is significant and
must use spaces; tab indentation is invalid.

## Document forms

An inline-spec document contains one or more specs:

```text
spec First:
  value: int

  impl default:
    value: 1

spec Second:
  enabled: bool = true
```

A spec-reuse document imports exactly one external spec and contains top-level
implementations:

```text
$spec: specs/base.etcm#Base

impl first:
  value: 1

impl second:
  value: 2
```

The two document forms cannot be mixed.

## Specs

```text
spec Name:
  # fields, assertions, and implementations
```

Spec inheritance uses `<-` and a spec selector:

```text
spec Child <- parent.etcm#Parent:
  child_field: str
```

A child adds fields and assertions. It cannot redefine an inherited field or reuse
an inherited assertion name.

## Fields

```text
required: int
with_default: int = 1
derived: int := @required + @with_default
validated: int [>0; <=100]
```

Multi-line derived expressions use an indented block:

```text
total: int :=
  @first
  + @second
  + @third
```

Anonymous objects use indentation or dotted paths:

```text
optimizer:
  learning_rate: float = 0.001

optimizer.weight_decay: float = 0.0
```

A typed reference field begins with `$` and selects a spec:

```text
$model: models/model.etcm#Model
$runtime.launcher: runtime/launcher.etcm#Launcher
```

## Types

| Syntax | Meaning |
| --- | --- |
| `str` | String |
| `int` | Integer |
| `float` | Integer or floating-point number |
| `bool` | Boolean |
| `null` | Null |
| `Path` | Filesystem path |
| `list[T]` | Homogeneous list |
| `dict[str, T]` | String-keyed mapping |
| `T | U` | Union |
| `File[str]` | Strict UTF-8 file |
| `File[bytes]` | Binary file |
| `File[json]` | JSON file |
| `File[yaml]` | Safe YAML 1.2 file |

Typed reference fields acquire their expected spec type from the declaration
selector rather than from a scalar type expression.

## Literals

```text
"string"
42
-3
0.001
true
false
null
[1, 2, 3]
{name: "example", retries: 2}
{"quoted-key": "value"}
```

Strings use double quotes and JSON-style escapes. Map keys are identifiers or
double-quoted strings. Trailing commas are accepted in lists and maps.

## Implementations

An implementation belongs to the containing spec:

```text
impl local:
  host: "127.0.0.1"
  port: 8080
```

Implementation inheritance uses an implementation selector:

```text
impl child <- :parent:
  workers: 4
```

Assignments use literal values. `$` assignments select referenced
implementations:

```text
impl training:
  $model: models/model.etcm#Model:base
  model.hidden_size: 512
```

## Selectors

| Selector | Meaning |
| --- | --- |
| `path.etcm#Spec` | Spec in another file |
| `#Spec` | Same-file spec |
| `path.etcm#Spec:impl` | Implementation in another file |
| `#Spec:impl` | Same-file implementation with explicit spec |
| `:impl` | Implementation in the active local spec |

API and CLI root selectors must use the complete
`path.etcm#Spec:implementation` form. An implementation named `default` is never
implicit.

## Field constraints and metadata

Semicolons separate entries inside `[]`:

```text
count: int [>0; <=100]
mode: str [in ["fast", "safe"]]
name: str [min_length=1; max_length=80]
slug: str [regex="^[a-z0-9-]+$"]
input: Path [path_exists="must_exist"; path_kind="file"]
tags: list[str] = [] [override="append"]
```

Supported metadata names are:

| Name | Accepted purpose |
| --- | --- |
| `gt`, `ge`, `lt`, `le`, `ne` | Atomic comparisons |
| `min_length`, `max_length` | Length bounds |
| `regex` | String pattern |
| `path_exists` | `resolver`, `allow_missing`, `must_exist` |
| `path_kind` | `any`, `file`, `dir` |
| `override` | `allow`, `deny`, `force_only`, `append`, `merge` |

`in [...]` is the preferred syntax for finite choices.

## Parameter references

References begin with `@` and contain field-name segments:

```text
@batch_size
@dataloader.local_batch_size
@dataloader.sampler.seed
```

They are relative to their containing object and may descend only through declared
inline objects and typed references. They cannot move upward, index collections,
traverse mappings, or enter `File[...]` content.

## Arithmetic expressions

Derived values and constraints support:

```text
+  -  *  /  //  %  **
```

They also support unary `+` and `-`, parentheses, numeric and scalar literals, and
parameter references. Comparisons use:

```text
==  !=  <  <=  >  >=
```

Assertions additionally support `not`, `and`, and `or`. Chained comparisons,
function calls, indexing, attribute access, string concatenation, and arbitrary
Python expressions are unsupported.

## Assertions

Inline form:

```text
assert positive_total: @total > 0
```

Block form:

```text
assert valid_shape:
  @hidden_size % @attention_heads == 0
  @partition_size * @devices == @hidden_size
```

Each line in a block is a separate predicate. Parentheses allow one predicate to
span physical lines.

## Comments

`#` begins a comment at line start or after whitespace:

```text
# whole-line comment
timeout: float = 30.0  # trailing comment
label: str = "prod#primary"
```

In a selector position, `#Spec` is a same-file selector rather than a comment.

## Unsupported constructs

ETCM does not currently support:

- upward or root-relative parameter references
- list indexing or mapping traversal in field paths
- selectors inside expressions
- chained comparisons or ternary expressions
- function calls or user-defined operators
- unions of multiple `File[...]` codecs
- URL-backed files
- arbitrary Python execution
