# Parameter Relations

ETCM parameters can validate themselves against other parameters and can derive
their values from typed expressions. Relations are local to the ETCM object
that contains the declaration, but a reference may follow child-object fields
with stable dot notation.

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

The three declaration operators remain visibly distinct:

```text
=   supplies a default value
:=  defines a derived value
[]  validates a resolved value
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

Dot notation in a relation is read-only. Implementation assignments retain
their existing rules: dot paths may configure inline nested fields, but cannot
write through a `$field` reference.

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

Chained comparisons and Boolean expressions are not supported. Write separate
constraints instead:

```etcm
value: int [>0; <100]
```

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
6. Produce the validated configuration.
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

## Initial scope

The initial feature deliberately excludes cross-spec assertions, upward or
root-relative navigation, collection indexing, mapping traversal, function
calls, conditionals, Boolean operators, user-defined operators, and arbitrary
Python execution.

```etcm
# Not supported
@parent.hidden_size
@root.training.batch_size
@values[0]
max(@a, @b)
@a if @enabled else @b
@a > 0 and @b > 0
```

The central distinction is:

```text
A constraint asks whether a configured value is valid.
A derived expression defines what the value is.
```
