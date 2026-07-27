# Stage 4 Parser Contract

The parser accepts ETCM source text and returns parser-independent objects.
Lark trees and tokens must stay inside `etcm.syntax`.

## Public Syntax API

Stage 4 adds:

```python
from etcm.syntax import parse_document, parse_file, parse_syntax
```

- `parse_syntax(text, source_path)` returns a syntax document.
- `parse_document(text, source_path)` returns `etcm.ir.Document`.
- `parse_file(path)` reads a file and returns `etcm.ir.Document`.

## Supported Syntax

- inline `spec` blocks
- top-level `$spec`
- `impl` blocks
- spec inheritance by selector
- implementation inheritance by selector
- field declarations with type expressions, direct defaults, and bracket metadata
- literal assignments
- `$field` reference assignments
- inline strings, numbers, booleans, nulls, lists, and mappings
- YAML-style `#` comments, blank lines, and spaces-only indentation

Outside quoted strings, `#` at line start or after whitespace begins a same-file
selector where the grammar expects a selector and begins a comment otherwise.
This keeps `#Spec`, attached fragments such as
`models/lm.etcm#LMConfig:tiny`, and YAML-style comments unambiguous.

## Explicit Non-Responsibilities

The parser does not:

- check that referenced files exist
- resolve selector paths or active-spec `:implementation` selectors
- resolve refs or inheritance
- check type assignability
- enforce path existence or path kind policy
- generate Pydantic models
- implement CLI behavior
