# Resolution and validation reference

This page defines when ETCM computes values, when it rejects them, and which API
stage owns each operation. For a worked example, read the
[basic tutorial](../tutorials/basic.md#derive-a-value-from-other-fields).

## Processing order

The observable pipeline is:

1. Parse source documents.
2. Resolve specs, implementations, inheritance, and object references.
3. Apply declaration defaults and implementation assignments.
4. Apply external Python or CLI overrides.
5. Load the effective `File[...]` values.
6. Compute derived fields in dependency order.
7. Validate field and reference types, paths, metadata, and field constraints.
8. Evaluate named assertions.
9. Convert the graph when a runtime view is requested.

Syntax, missing selector, inheritance, reference, override, file-load, and derived
expression failures may therefore occur during `resolve()`. `validate()` handles
the checks that require the complete resolved graph.

## Public stages

```python
from etcm import convert, load, resolve, validate

graph = resolve("stays.etcm#Stay:pepper_weekend")
assert graph.validated is False

graph = validate(graph)
assert graph.validated is True

stay = convert(graph, target="dict")
```

`load()` runs the same three stages in one call:

```python
stay = load("stays.etcm#Stay:pepper_weekend", target="dict")
```

Conversion normally requires `validated == True`. `convert(..., force=True)` is an
inspection escape hatch; it does not validate the graph.

## Value origins

Each resolved field value retains an origin such as declaration default,
implementation, parent implementation, derived expression, or external override.
The graph also records source paths, spans, previous values for overrides, and
typed reference edges.

Later sources compose according to the field's override policy. A derived field is
never assigned by an implementation or external caller.

## Derived dependencies

Derived fields use `:=` and may read declared fields through `@` references:

```text
total_food_grams: int := @nights * @pet.daily_food_grams
```

ETCM builds a dependency graph, evaluates dependencies before their consumers,
and rejects cycles with `E_DERIVED_CYCLE`. Declaration order does not control the
result.

Arithmetic precedence follows Python's arithmetic precedence. Exponentiation is
right-associative; `/` returns a float. Division by zero, non-finite or complex
results, and integer exponents with magnitude above 10,000 fail safely.

Arithmetic and ordering require numeric operands. Equality supports compatible
scalar values, nullable values, and `Path`-to-`Path` comparison. Collections,
strings, and file contents do not gain implicit arithmetic behavior.

## Constraints

Field constraints run after derivation. A field may have several constraints, and
all must pass:

```text
nights: int [>0; <=30]
```

An expression constraint may read another field:

```text
food: int [>= @pet.daily_food_grams]
```

References are relative to the containing object and can descend only through
declared object fields.

## Named assertions

Assertions run after field constraints and are appropriate for relationships that
do not produce a value:

```text
assert enough_food:
  @total_food_grams >= @pet.daily_food_grams
```

Multiple predicates under one assertion are all required. Boolean `and` and `or`
short-circuit. Direct comparisons with `null` narrow nullable scalar values for the
guarded branch.

## Path validation

`Path` fields may declare:

- `path_exists="must_exist"` or `"allow_missing"`
- `path_exists="resolver"` to use `Resolver.path_exists`
- `path_kind="file"`, `"dir"`, or `"any"`

Paths are resolved relative to the source file that contributed the effective
value. Existing paths are always checked against `path_kind`.

## Diagnostics

Operational failures raise `ETCMError` with a structured `Diagnostic`. The CLI
prints that diagnostic on standard error and exits with status `1`.

Common relational codes include:

| Code | Meaning |
| --- | --- |
| `E_PARAMETER_REFERENCE` | Invalid or unknown `@` path |
| `E_EXPRESSION_TYPE` | Operator or result types are incompatible |
| `E_DERIVED_CYCLE` | Derived dependencies form a cycle |
| `E_DERIVED_ASSIGNMENT` | A caller assigns a derived field |
| `E_EXPRESSION_EVALUATION` | Safe evaluation cannot produce a value |
| `E_CONSTRAINT` | A field constraint is false |
| `E_ASSERTION` | A named assertion predicate is false |
| `E_DUPLICATE_ASSERTION` | An assertion name is repeated or shadows an inherited name |

Relational diagnostics include the written expression, resolved operands, and
substituted evaluation when available. Syntax and other resolver diagnostics use
their own stable codes and source spans.
