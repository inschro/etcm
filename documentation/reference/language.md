# Language reference

This page is an exact syntax lookup. Start with the
[quickstart](../getting-started/quickstart.md) or
[basic tutorial](../tutorials/basic.md) if `spec`, `impl`, and selectors are new
to you.

## Identifiers and indentation

Spec, implementation, field, and assertion names start with a letter or underscore
and continue with letters, digits, or underscores.

Indentation is significant and must use spaces. Tabs in indentation are invalid.

## Document forms

Most files declare one or more specs. Implementations are nested inside the spec
they satisfy:

```text
spec Pet:
  name: str

  impl pepper:
    name: "Pepper"
```

A spec-reuse file imports one external spec and adds top-level implementations:

```text
$spec: pets.etcm#Pet

impl luna:
  name: "Luna"
```

A file cannot mix inline specs with top-level `$spec` reuse.

## Specs

```text
spec Name:
  # fields, assertions, and implementations
```

Spec inheritance uses `<-` with a spec selector:

```text
spec Dog <- animals.etcm#Animal:
  favorite_walk_minutes: int
```

A child adds fields and assertions. It cannot redefine an inherited field, replace
an inherited assertion, or participate in an inheritance cycle.

## Fields

```text
required: int
with_default: int = 2
derived: int := @required * @with_default
constrained: int [>0; <=100]
```

- No assignment means the field is required.
- `=` declares a default.
- `:=` declares a derived expression owned by the spec.
- `[]` contains constraints and metadata separated by semicolons.

### Nested fields

Indentation and dotted declarations produce the same canonical field paths:

```text
feeding:
  meals_per_day: int = 2

feeding.grams_per_meal: int
```

Implementations accept the same two forms:

```text
impl pepper:
  feeding:
    grams_per_meal: 150
  feeding.meals_per_day: 2
```

A value cannot be assigned at a path that also has assigned descendants.

## Types

| Syntax | Accepted value |
| --- | --- |
| `str` | String |
| `int` | Integer, excluding Boolean values |
| `float` | Integer or floating-point number |
| `bool` | `true` or `false` |
| `null` | `null` |
| `Path` | Filesystem path |
| `list[T]` | Homogeneous list |
| `dict[str, T]` | String-keyed mapping |
| `T \| U` | Union |
| `File[str]` | Strict UTF-8 file content |
| `File[bytes]` | Exact file bytes |
| `File[json]` | Decoded JSON |
| `File[yaml]` | Safely decoded YAML 1.2 |

See the [file-types reference](files.md) for `File[...]` behavior.

## Literals

```text
"Pepper"
42
-3
0.25
true
false
null
["cat", "dog"]
{meals: 2, bowl: "blue"}
{"quoted-key": "value"}
```

Strings use double quotes and JSON-style escapes. Mapping keys are identifiers or
double-quoted strings. Lists and mappings allow trailing commas.

## Implementations

An implementation belongs to its surrounding spec:

```text
impl pepper:
  name: "Pepper"
```

Implementation inheritance uses `<-` and an implementation selector:

```text
impl long_stay <- :weekend:
  nights: 5
```

Parent values are resolved before local assignments. Parents may be same-file or
external, must satisfy a compatible spec, and cannot form cycles.

An implementation named `default` has no implicit behavior; callers still select
`:default` explicitly.

## Selectors

| Form | Target |
| --- | --- |
| `path.etcm#Spec` | Spec in another file |
| `#Spec` | Spec in the current file |
| `path.etcm#Spec:impl` | Implementation in another file |
| `#Spec:impl` | Implementation in the current file |
| `:impl` | Implementation in the active local spec |

CLI and Python root calls require the complete
`path.etcm#Spec:implementation` form. Paths inside ETCM files are relative to the
file containing the selector.

## Typed references

A `$` field declares a child object and selects the spec it must satisfy:

```text
spec Stay:
  $pet: pets.etcm#Pet
```

An implementation assignment selects the concrete child:

```text
impl pepper_weekend:
  $pet: pets.etcm#Pet:pepper
```

Same-file selectors are valid:

```text
$pet: #Pet
$pet: #Pet:pepper
```

A child field may be patched after selecting a reference:

```text
impl special_stay:
  $pet: pets.etcm#Pet:pepper
  pet.daily_food_grams: 320
```

The patch is copy-on-write for that resolved graph. It does not mutate the source
implementation.

## Constraints and field metadata

Semicolons separate entries:

```text
nights: int [>0; <=30]
kind: str [in ["cat", "dog"]]
name: str [min_length=1; max_length=80]
slug: str [regex="^[a-z0-9-]+$"]
photo: Path [path_exists="must_exist"; path_kind="file"]
tags: list[str] = [] [override="append"]
```

| Name | Values or purpose |
| --- | --- |
| `gt`, `ge`, `lt`, `le`, `ne` | Atomic comparison metadata |
| `min_length`, `max_length` | String or collection length |
| `regex` | String regular expression |
| `path_exists` | `resolver`, `allow_missing`, `must_exist` |
| `path_kind` | `any`, `file`, `dir` |
| `override` | `allow`, `deny`, `force_only`, `append`, `merge` |

Operator constraints such as `[>0]` are equivalent to the corresponding atomic
comparison metadata. Use `in [...]` for a finite set of accepted values.

Override policy behavior is defined in the [override reference](overrides.md).

## Parameter references and expressions

`@` reads another declared field relative to the containing object:

```text
@nights
@pet.daily_food_grams
```

References may descend through inline objects and typed references. They cannot
move upward, index a list, traverse mapping keys, or inspect decoded `File[...]`
content.

Derived values support numeric and scalar literals, parentheses, unary `+` and
`-`, and arithmetic operators:

```text
+  -  *  /  //  %  **
```

Constraints and assertions support `==`, `!=`, `<`, `<=`, `>`, and `>=`.
Assertions additionally support `not`, `and`, and `or`. Function calls, arbitrary
Python, string concatenation, and chained comparisons are not part of the
language. See [resolution and validation](resolution.md) for evaluation details.

## Assertions

A named assertion contains one or more predicates:

```text
assert reasonable_stay:
  @nights > 0
  @total_food_grams >= @pet.daily_food_grams
```

All predicates must be true. Assertions may read several branches below their
containing object and support Boolean composition:

```text
assert optional_value:
  @value == null or @value > 0
```

Inherited assertion names cannot be reused or disabled.

## Comments

Comments begin with `#` at the start of a line or after whitespace:

```text
# whole-line comment
nights: 2  # end-of-line comment
label: "#not-a-comment"
```

Where a selector is expected, `#Pet` is a same-file selector rather than a
comment.

## Deliberately unsupported

ETCM does not include implicit default implementation selection, wildcard
selectors, environment interpolation, URL-backed files, arbitrary Python
execution, collection indexing in field paths, or file value unions other than
`File[T] | null`.
