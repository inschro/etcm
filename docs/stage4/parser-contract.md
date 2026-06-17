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
- spec inheritance by fragment-free path
- implementation inheritance by selector
- field declarations with type expressions and `Field(...)` metadata
- literal assignments
- `$field` reference assignments
- inline strings, numbers, booleans, nulls, lists, and mappings
- YAML-style `#` comments, blank lines, and spaces-only indentation

`#` starts a comment only at the beginning of a line or after whitespace,
outside quoted strings. Attached selector fragments such as `models/lm.etcm#tiny`
are not comments. Fragment-bearing spec paths such as
`$spec: specs/base.etcm#bad` and `spec Child <- specs/base.etcm#bad:` are
syntax errors rather than truncated comments.

## Explicit Non-Responsibilities

The parser does not:

- check that referenced files exist
- resolve omitted selector fragments to `#default`
- resolve refs or inheritance
- check type assignability
- enforce path existence or path kind policy
- generate Pydantic models
- implement CLI behavior
