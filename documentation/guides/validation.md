# Validation and derived values

ETCM keeps schema-owned rules in the configuration language. A field can validate
its own value, derive a value from other parameters, or participate in a named
object assertion.

```text
=   supplies a default value
:=  defines a derived value
[]  validates a field or configures its metadata
assert name:  validates an object-level invariant
```

## Field constraints

Constraints live in a field's `[]` annotation. The declared field is the implicit
left-hand operand:

```text
spec Runtime:
  workers: int [>0]
  port: int [>=1024; <=65535]
  environment: str [in ["development", "production"]]
```

Semicolons separate ordered checks. A constraint can compare with another
parameter:

```text
spec Window:
  minimum: int
  maximum: int [>= @minimum]
```

`maximum: int [>= @minimum]` means `maximum >= minimum`; it does not assign a
value to `maximum`.

An arithmetic operator at the start of a constraint continues from the current
field value:

```text
spec Model:
  attention_heads: int [>0]
  hidden_size: int [>0; % @attention_heads == 0]
```

The second `hidden_size` rule means
`hidden_size % attention_heads == 0`.

## Atomic metadata

Field metadata covers common scalar, collection, path, and override rules:

| Metadata | Meaning |
| --- | --- |
| `gt`, `ge`, `lt`, `le` | Numeric bounds |
| `ne` | Rejected value |
| `min_length`, `max_length` | String or collection length bounds |
| `regex` | String regular-expression match |
| `in [...]` | Finite set of valid values |
| `path_exists`, `path_kind` | Filesystem policy for `Path` |
| `override` | Assignment composition policy |

For example:

```text
spec User:
  name: str [min_length=1; max_length=80]
  slug: str [regex="^[a-z0-9-]+$"]
  retries: int [ge=0; le=10]
  input_file: Path [path_exists="must_exist"; path_kind="file"]
```

Comparison syntax such as `[>=0; <=10]` is equivalent to the numeric bound metadata
for runtime validation and generated Pydantic views.

See [overrides](overrides.md) for override policy and
[core concepts](core-concepts.md#paths) for path policy.

## Parameter references

`@` begins a parameter reference:

```text
@attention_heads
@dataloader.local_batch_size
@dataloader.sampler.seed
```

A reference is anchored at the object containing the declaration. Every segment
after the first must follow a declared inline object or typed `$field` reference.

```text
spec Parent:
  inline:
    minimum: int = 1

  $external: child.etcm#Child

  inline_copy: int := @inline.minimum
  external_copy: int := @external.value
```

Relations cannot move upward to a parent or root, select unrelated objects, index
collections, traverse mappings, access Python attributes, or inspect `File[...]`
contents. A parameter reference must end at a scalar leaf.

## Derived values

`:=` defines a value computed during resolution:

```text
spec Training:
  micro_batch_size: int [>0]
  accumulation_steps: int = 1 [>0]
  world_size: int = 1 [>0]

  global_batch_size: int :=
    @micro_batch_size * @accumulation_steps * @world_size
```

Derived values appear in the resolved graph and every converted view. They are
recomputed after inheritance and overrides, so they never become stale. An
implementation or external caller cannot assign a derived field.

Derived fields may depend on other derived fields. ETCM orders those calculations
by dependency and reports `E_DERIVED_CYCLE` when no valid order exists:

```text
first: int := @second + 1
second: int := @first + 1
```

A derived field may also carry validation:

```text
total: int := @left + @right [>0]
```

## Named assertions

Use a named assertion when an invariant has no natural field subject or spans
multiple branches:

```text
spec Training:
  $model: model.etcm#Model
  $runtime: runtime.etcm#Runtime

  assert distributed_shape:
    @model.hidden_size % @model.attention_heads == 0
    @model.hidden_size == @runtime.partition_size * @runtime.devices
```

Each top-level line in a block is an independent predicate. ETCM evaluates them in
source order and stops at the first failure. A single expression can span lines
inside parentheses:

```text
assert cuda_runtime:
  (
    @runtime.accelerator != "cuda"
    or @runtime.devices > 0
  )
  @runtime.devices <= @runtime.maximum_devices
```

Assertions also have an inline form:

```text
assert batch_limit: @global_batch_size <= 1024
```

Boolean evaluation short-circuits. Direct null guards narrow nullable scalar values:

```text
assert optional_timeout:
  @timeout == null or @timeout > 0
  @retry_delay != null and @retry_delay >= 0
```

An assertion inside an inline object is anchored at that object. Put a rule at the
common owning object when it needs to read multiple branches.

## Expressions

Derived values and constraints support literals, references, parentheses, unary
`+` and `-`, and these arithmetic operators:

```text
+  -  *  /  //  %  **
```

Constraints and assertions support:

```text
==  !=  <  <=  >  >=
```

Assertions additionally support `not`, `and`, and `or`. Precedence follows Python's
arithmetic order:

```text
parentheses
**
unary + and -
* / // %
+ -
comparison
not
and
or
```

Exponentiation is right-associative. Chained comparisons are not supported; use
separate field constraints or separate assertion predicates.

Arithmetic and ordering require numeric operands. `/` produces a float. ETCM
allows compatible `int` and `float` comparison, scalar equality, nullable equality,
and `Path`-to-`Path` equality. It does not support string concatenation, collection
arithmetic, function calls, or arbitrary Python execution.

Non-finite or complex results, division by zero, and exponents whose integer
magnitude exceeds 10,000 fail safely with `E_EXPRESSION_EVALUATION`.

## Evaluation order

The observable value pipeline is:

1. Resolve specs, implementations, inheritance, and object references.
2. Apply declaration defaults and implementation assignments.
3. Apply external Python or CLI overrides.
4. Load the effective `File[...]` values.
5. Compute derived parameters in dependency order.
6. Validate field and reference types, paths, metadata, and field constraints.
7. Evaluate named assertions.
8. Convert the validated graph when requested.

`resolve()` performs the resolution and derivation portion and returns a graph with
`validated == False`. `validate()` performs the remaining validation and returns a
graph with `validated == True`. `load()` runs the complete pipeline.

## Diagnostics

Failures raise `ETCMError` with a structured `Diagnostic`. Relational failures
include the written expression, resolved operands, and substituted evaluation. Key
codes include:

| Code | Meaning |
| --- | --- |
| `E_PARAMETER_REFERENCE` | Invalid or unknown parameter path |
| `E_EXPRESSION_TYPE` | Operator or result types are incompatible |
| `E_DERIVED_CYCLE` | Derived dependencies form a cycle |
| `E_DERIVED_ASSIGNMENT` | A caller tries to assign a derived field |
| `E_EXPRESSION_EVALUATION` | Safe evaluation cannot produce a value |
| `E_CONSTRAINT` | A field constraint evaluates to false |
| `E_ASSERTION` | A named assertion evaluates to false |
| `E_DUPLICATE_ASSERTION` | An assertion name is repeated or shadows an inherited one |

The [CLI](../reference/cli.md) formats these diagnostics on standard error and exits
with status `1`.
