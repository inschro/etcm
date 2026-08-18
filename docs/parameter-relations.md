# Parameter Relations

ETCM parameters can validate themselves against other parameters, derive their
values from typed expressions, and participate in named object assertions.
Relations are local to the ETCM object that contains the declaration, but a
reference may follow child-object fields with stable dot notation.

```etcm
spec TrainingConfig:
  $dataloader: dataloader.etcm#DataLoaderConfig
  gradient_accumulation_steps: int = 1 [>0]
  world_size: int = 1 [>0]

  global_batch_size: int :=
    @dataloader.local_batch_size
    * @gradient_accumulation_steps
    * @world_size

  seed: int [== @dataloader.sampler.seed]
```

Field operators and named assertions remain visibly distinct:

```text
=   supplies a default value
:=  defines a derived value
[]  validates a resolved value
assert name:  validates one or more explicit predicates
```

## Parameter references

`@` begins a parameter reference:

```etcm
@attention_heads
@dataloader.local_batch_size
@dataloader.sampler.seed
```

A reference is anchored at the object containing the declaration. Each path
segment after the first must traverse an ETCM object field. Object fields may
be declared inline or with a typed `$field` spec reference.

```etcm
spec Parent:
  inline:
    minimum: int = 1

  $external: child.etcm#Child

  inline_copy: int := @inline.minimum
  external_copy: int := @external.value
```

Relations do not traverse dictionaries, lists, Python attributes, or arbitrary
runtime objects. These forms are invalid:

```etcm
@values[0]
@mapping.key
@python_object.attribute
```

The target field may be declared before or after the relation. A reference must
end at a scalar leaf; referring to an object as the expression value is an
error. A scalar cannot be traversed further.

Named assertions use the same anchor. An assertion declared in a spec can read
any scalar descendant of that spec, including values reached through typed
references in other files. An assertion inside an inline object starts at that
object. It cannot discover its parent or the root:

```etcm
spec Training:
  model:
    hidden_size: int
    attention_heads: int

    assert local_shape:
      @hidden_size % @attention_heads == 0

  runtime:
    partition_size: int
    devices: int

  assert distributed_shape:
    @model.hidden_size == @runtime.partition_size * @runtime.devices
```

The nested `local_shape` assertion cannot see `runtime`; a rule involving both
branches belongs at their common owning object. Names such as `root` and
`parent` have no special meaning, and assertions cannot contain selectors.

Dot notation in a relation is read-only. Declarations and implementation
assignments may use either dotted paths or equivalent indented blocks. Both
assignment forms may patch descendants of an already selected `$field`
reference. ETCM applies those writes with copy-on-write and checks the override
policy of the leaf field. See [Overrides](overrides.md).

## Validation constraints

Constraints stay inside the field's `[]` annotation. The declared parameter is
the implicit left-hand subject:

```etcm
maximum: int [>= @minimum]
confirmation: str [== @password]
secondary_port: int [!= @primary_port]
worker_timeout: float [<= @request_timeout]
```

For example, `maximum: int [>= @minimum]` means
`maximum >= minimum`. A right-hand expression does not assign the field:

```etcm
positional_embedding_size: int [
  >= @stream_size + @num_aux_tokens
]
```

The user still chooses `positional_embedding_size`; ETCM only verifies the
chosen value.

Some checks transform the current value before comparing it. An arithmetic
operator at the beginning of a constraint continues from the implicit current
parameter:

```etcm
hidden_size: int [% @attention_heads == 0]
```

This means `hidden_size % attention_heads == 0`.

Constraints are ordered and may repeat. Semicolons separate independent
checks:

```etcm
hidden_size: int [
  >=64;
  == @attention_heads * @head_size;
  % @attention_heads == 0
]
```

Derived fields may have constraints too. ETCM computes the value during
resolution and validates its constraints during validation:

```etcm
total: int := @left + @right [>0]
```

## Named assertions

Use `[]` when a rule naturally validates the field being declared. Use a named
assertion when an invariant has no single field subject or spans object
branches. Assertions support an inline form and a block form:

```etcm
assert batch_limit: @global_batch_size <= 1024

assert model_shape:
  @model.hidden_size % @model.attention_heads == 0
  @model.hidden_size == @runtime.partition_size * @runtime.devices
```

Each top-level expression in a block is an independent predicate. The block is
their implicit conjunction; ETCM evaluates them in source order and stops at
the first failure. A long individual predicate can span physical lines inside
parentheses:

```etcm
assert cuda_runtime:
  (
    @runtime.accelerator != "cuda"
    or @runtime.devices > 0
  )
  @runtime.devices <= @runtime.maximum_devices
```

Assertion predicates support arithmetic, comparisons, Boolean scalar values,
parentheses, and `not`, `and`, and `or`. Boolean evaluation short-circuits.
Direct null guards narrow nullable scalar values:

```etcm
assert optional_timeout:
  @timeout == null or @timeout > 0
  @retry_delay != null and @retry_delay >= 0
```

Assertions are schema-owned. Spec inheritance accumulates parent assertions;
a child may add new assertion names but cannot replace or disable an inherited
one. Referenced child specs validate their own assertions, while a parent may
declare additional assertions over child values.

## Derived parameters

`:=` defines a value that ETCM computes:

```etcm
spec TrainingConfig:
  micro_batch_size: int [>0]
  gradient_accumulation_steps: int = 1 [>0]
  world_size: int = 1 [>0]

  global_batch_size: int :=
    @micro_batch_size
    * @gradient_accumulation_steps
    * @world_size
```

Derived values are present in the graph returned by `resolve()` and in every
generated view. An implementation cannot assign them independently. For
example, assigning `global_batch_size` above produces
`E_DERIVED_ASSIGNMENT` and reports the defining expression.

Derived parameters may depend on required, defaulted, or other derived
parameters. ETCM computes local derived dependencies in topological order and
rejects cycles with `E_DERIVED_CYCLE`:

```etcm
first: int := @second + 1
second: int := @first + 1
```

Changing a source value through implementation inheritance recomputes all
affected derived values; a derived value is never inherited as stale data.

## Expressions and precedence

Relations support numeric and scalar literals, parameter references,
parentheses, unary `+` and `-`, and these arithmetic operators:

```text
+  -  *  /  //  %  **
```

They support these comparison operators at the constraint boundary:

```text
==  !=  <  <=  >  >=
```

Precedence follows Python's arithmetic rules. From tightest to loosest:

```text
parenthesized expressions
**
unary + and -
* / // %
+ -
comparison boundary
```

Exponentiation is right-associative and binds more tightly than unary
operators on its left:

```text
-2 ** 2      == -(2 ** 2) == -4
2 ** 3 ** 2  == 2 ** (3 ** 2) == 512
```

Parentheses change the order explicitly:

```etcm
grouped: int := (-2) ** 2
total_size: int [== (@header_size + @payload_size) * @replicas]
```

Chained comparisons and Boolean expressions are not supported inside field
constraints. Write separate constraints, or use a named assertion when Boolean
logic is required:

```etcm
value: int [>0; <100]
```

Assertion predicates add comparison, `not`, `and`, and `or` levels below the
arithmetic precedence shown above. Chained comparisons remain invalid.

## Type rules

Relation leaves are `int`, `float`, `str`, `bool`, `null`, or `Path` values.
Arithmetic and ordering require numeric operands. Equality and inequality
allow compatible scalar values, including numeric `int`/`float` comparison,
nullable equality, and `Path`-to-`Path` equality.

```etcm
total: int [== @left + @right]
ratio: float [== @used / @available]
confirmation: str [== @password]
enabled: bool [== @feature_enabled]
maybe: int | null [== null]
same_path: Path [== @source_path]
```

String concatenation, collection arithmetic, and remainder on floats are not
part of the language. `/` always produces a float, so its derived destination
must accept `float`; `//` can be used for whole-number grouping. The result of
a derived expression must be assignable to its declared field type.

Expression evaluation never invokes Python `eval` and never calls user code.
Non-finite numeric results, complex results, division by zero, and exponents
whose integer magnitude exceeds 10,000 fail with
`E_EXPRESSION_EVALUATION`.

## Resolution and validation order

The observable pipeline is:

```text
1. Resolve explicit implementation values and object references.
2. Apply defaults and implementation inheritance.
3. Compute derived parameters.
4. Validate field and reference types.
5. Validate paths, atomic metadata, and relational constraints.
6. Evaluate named assertions.
7. Produce the validated configuration.
```

`resolve()` performs steps 1–3 and returns an unvalidated graph whose derived
values are already inspectable. `validate()` performs the remaining checks.
Missing values needed by a derivation fail during resolution.

The spec itself is checked before values are evaluated. ETCM rejects unknown
path segments, scalar traversal, object-valued terminals, incompatible
operators, invalid derived result types, self-references, and derived cycles
without executing arbitrary expressions.

## Diagnostics

Relation failures carry structured details. A failed validation reports the
written constraint, the current value and referenced operands in encounter
order, and both the substituted and simplified evaluation:

```text
validation failed for ModelConfig.hidden_size

constraint:
  % @attention_heads == 0

resolved values:
  hidden_size: 512
  attention_heads: 12

evaluation:
  512 % 12 == 0
  8 == 0
```

Important diagnostic codes are:

| Code | Meaning |
| --- | --- |
| `E_PARAMETER_REFERENCE` | An unknown, self, scalar-traversing, or object-terminal reference |
| `E_EXPRESSION_TYPE` | A relation is invalid for its declared operand/result types |
| `E_DERIVED_CYCLE` | Derived parameters contain a dependency cycle |
| `E_DERIVED_ASSIGNMENT` | An implementation tries to assign a derived parameter |
| `E_EXPRESSION_EVALUATION` | Safe arithmetic evaluation cannot produce a value |
| `E_CONSTRAINT` | A well-typed relation evaluates to false |
| `E_ASSERTION` | A named assertion predicate evaluates to false |
| `E_DUPLICATE_ASSERTION` | An assertion name is duplicated locally or through inheritance |

## Initial scope

The feature deliberately excludes upward or root-relative navigation,
selector-based access to unrelated specs, collection indexing, mapping
traversal, function calls, ternary conditionals, chained comparisons,
user-defined operators, and arbitrary Python execution. Boolean operators are
available only in named assertions.

```etcm
# Not supported
@values[0]
max(@a, @b)
@a if @enabled else @b
configs/model.etcm#Model:base
```

The central distinction is:

```text
A constraint asks whether a configured value is valid.
A derived expression defines what the value is.
A named assertion validates an explicit invariant owned by an object.
```
