# Golden Output Format

Golden files are reviewable text or JSON snapshots. They are not opaque binary
snapshots, and they are not generated from undocumented object reprs.

## General Rules

- JSON uses UTF-8, two-space indentation, sorted object keys where ordering is
  not semantically meaningful, and a trailing newline.
- Lists preserve semantic order when order matters, such as file order,
  inheritance order, assignment order, and graph traversal order.
- Paths are normalized relative to the fixture root unless the behavior under
  test requires an absolute path.
- Source spans use one-based line and column numbers.
- Golden output must not include wall-clock time, host-specific temp paths, hash
  randomization, or environment-dependent values.
- Each golden file declares the ETCM stage that first owns it in the test name
  or directory README.

## Parsed AST Summary

Owned by Stage 4 parser tests.

Suggested path:

```text
tests/fixtures/golden/ast/<fixture-name>.json
```

Required shape:

```json
{
  "source_path": "valid/inline_spec.etcm",
  "items": [
    {
      "kind": "spec",
      "name": "DataConfig",
      "span": {"line": 1, "column": 1, "end_line": 3, "end_column": 42}
    },
    {
      "kind": "impl",
      "name": "smoke",
      "span": {"line": 5, "column": 1, "end_line": 7, "end_column": 13}
    }
  ]
}
```

The AST summary checks syntax ownership only. It should not resolve imports,
check type assignability, or validate paths.

## Normalized IR Summary

Owned by Stage 4 transformer tests.

Suggested path:

```text
tests/fixtures/golden/ir/<fixture-name>.json
```

Required shape:

```json
{
  "source_path": "valid/inline_spec.etcm",
  "spec": {
    "name": "DataConfig",
    "parent": null,
    "fields": [
      {
        "name": "train_file",
        "type": {"kind": "named", "name": "Path"},
        "default": null,
        "metadata": {"path_exists": "must_exist", "path_kind": "file"},
        "override": "default"
      }
    ]
  },
  "spec_ref": null,
  "implementations": [
    {
      "name": "smoke",
      "parent": null,
      "assignments": [
        {
          "kind": "literal",
          "field_path": ["train_file"],
          "value": {"kind": "string", "value": "data/smoke.txt"}
        }
      ]
    }
  ]
}
```

The IR summary may include spans, but span assertions should be separately
targeted so harmless formatting changes do not make every golden diff noisy.

## Resolved Graph JSON

Owned by Stage 5 resolver tests.

Suggested path:

```text
tests/fixtures/golden/graph/<fixture-name>.json
```

Required top-level keys:

- `root_selector`
- `nodes`
- `edges`
- `sources`
- `values`
- `path_resolution`
- `overrides`

Required graph properties:

- stable node ids derived from selector identity and graph path, not object id
- explicit source file for every node and value
- parent edges for spec and implementation inheritance
- ref edges for `$field` references
- graph paths for nested values and referenced children
- path values record original text, declaring source file, resolved path, field
  policy, resolver policy, and validation result

## Generated Pydantic Schema Summary

Owned by Stage 6 generated-view tests.

Suggested path:

```text
tests/fixtures/golden/pydantic/<fixture-name>.json
```

Required shape:

```json
{
  "classes": [
    {
      "name": "DataConfig",
      "frozen": true,
      "fields": [
        {
          "name": "train_file",
          "annotation": "Path",
          "required": true,
          "metadata": {"path_exists": "must_exist", "path_kind": "file"}
        }
      ]
    }
  ]
}
```

This summary checks generated API shape, not Pydantic's entire JSON Schema
output. Full JSON Schema export can be added later if it becomes a product
surface.

## Diagnostic Output

Owned by the first stage that can detect the failure.

Suggested paths:

```text
tests/fixtures/golden/diagnostics/<fixture-name>.json
tests/fixtures/golden/diagnostics/<fixture-name>.txt
```

JSON is the stable machine contract. Text is the human-facing rendering contract.

Required JSON shape:

```json
{
  "code": "E_DUPLICATE_FIELD",
  "message": "Duplicate field 'retries' in spec 'BadConfig'.",
  "source_path": "invalid/duplicate_field.etcm",
  "span": {"line": 3, "column": 3, "end_line": 3, "end_column": 15},
  "selector": null,
  "graph_path": null,
  "details": {
    "field": "retries",
    "previous_span": {"line": 2, "column": 3, "end_line": 2, "end_column": 15}
  }
}
```

Text diagnostics should be concise by default and may include a source excerpt.
Verbose diagnostics can add selector chains, graph paths, and extra context
without changing the JSON contract.
