# Parser Spike

## Goal

Prove that Lark can support the v0 parser requirements before writing package
code:

- comments
- basic `spec`, `$spec`, `impl`, refs, fields, metadata, and nested literals
- source spans on parse tree nodes
- useful error context

## Local Result

Environment:

```text
python: Python 3.14.5
lark: 1.3.1
```

Command summary:

```bash
python - <<'PY'
from lark import Lark

grammar = r'''
start: item+
?item: spec | impl | spec_ref
spec_ref: "$spec" ":" PATH
spec: "spec" NAME inheritance? ":" field+
impl: "impl" NAME impl_inheritance? ":" assignment+
inheritance: "<-" PATH
impl_inheritance: "<-" selector
field: NAME ":" type_expr field_meta? ","?
assignment: ref_assignment | value_assignment
ref_assignment: "$" NAME ":" selector
value_assignment: NAME ":" value
field_meta: "=" "Field" "(" [meta_pair ("," meta_pair)* ","?] ")"
meta_pair: NAME "=" value
?type_expr: NAME | NAME "[" type_expr "]" | type_expr "|" type_expr
?value: ESCAPED_STRING | SIGNED_NUMBER | "true" | "false" | "null" | list | mapping
list: "[" [value ("," value)* ","?] "]"
mapping: "{" [map_pair ("," map_pair)* ","?] "}"
map_pair: NAME ":" value
selector: PATH ["#" NAME]
PATH: /[A-Za-z0-9_\.\/:-]+/
%import common.CNAME -> NAME
%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.WS
%ignore WS
COMMENT: /#[^\n]*/
%ignore COMMENT
'''

sample = '''
# sample
$spec: specs/data.etcm

impl smoke:
  $model: models/lm.etcm#tiny
  data_path: "data/smoke.txt"
'''
parser = Lark(grammar, parser='lalr', propagate_positions=True, maybe_placeholders=False)
tree = parser.parse(sample)
print(tree.data, tree.meta.line, tree.meta.column, tree.meta.end_line, tree.meta.end_column)
for subtree in tree.find_data('impl'):
    print(subtree.data, subtree.meta.line, subtree.meta.column, subtree.meta.end_line, subtree.meta.end_column)
try:
    parser.parse('spec Broken:\n  x: [\n')
except Exception as exc:
    print(type(exc).__name__)
    print(exc.get_context('spec Broken:\n  x: [\n').strip())
PY
```

Observed output:

```text
start 3 1 7 30
impl 5 1 7 30
UnexpectedToken
x: [
     ^
```

## Decision

Use Lark for the first parser implementation.

## Indentation Spike

The first parser spike did not cover indentation-sensitive parsing. A second
local spike used Lark's `Indenter` with `parser="lalr"` and
`propagate_positions=True`.

Observed output:

```text
start 1 1 10 1
spec 2 1 6 1
impl 6 1 10 1
UnexpectedToken
x: int
        ^
```

Interpretation:

- Indentation-shaped `spec` and `impl` blocks are viable with Lark.
- Bad nested indentation produces a parse error with context.
- Blank-line handling must be explicit in the grammar.

## Alternative Parser Smoke Test

A lightweight pyparsing smoke test was run through `uv run --with pyparsing`.

Observed output:

```text
Installed 1 package in 5ms
pyparsing 3.3.2
IndentedBlock True
locatedExpr True
smoke 1
ParseException 3 5
```

Interpretation:

- pyparsing can parse indentation-shaped blocks and report locations.
- The quick grammar was less aligned with a standalone language grammar than
  Lark's EBNF-style grammar.
- pyparsing remains a fallback if Lark fails Stage 2 fixture gates.

## Consequences

- Stage 2 should create a real grammar file under package resources, not inline
  grammar strings.
- Parser conversion should immediately convert Lark trees/tokens into ETCM
  syntax nodes and IR. Lark classes should not cross into `etcm.ir`.
- Stage 2 must formalize indentation, blank-line, comment, and tab behavior in
  grammar fixtures.
- Source spans are viable with `propagate_positions=True`.
- Error context is viable through Lark's `UnexpectedInput.get_context()`.

## Risks

- ETCM examples currently read like indentation-based syntax. Implementing true
  indentation may require Lark post-lexing or a grammar shape adjustment.
- `PATH` token ambiguity with identifiers, numbers, and selectors needs careful
  grammar design.
- Comments were ignored successfully, but preserving comments for future
  formatter/docs tooling is out of v0 scope.
