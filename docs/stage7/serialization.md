# Stage 7 Serialization

CLI stdout is always text. Commands that produce structured data write indented
JSON.

## Graph JSON

`resolve` and `validate` print `ResolvedGraph.to_dict()`:

- paths are POSIX strings
- nodes and edges use stable ordering from the graph exporter
- `resolve` preserves `validated: false`
- `validate` returns a new graph and prints `validated: true`

## Loaded Config JSON

`load` first builds the selected generated view, then serializes it:

- `--target dict`: print the returned dict payload
- `--target dataclass`: print `dataclasses.asdict(...)`
- `--target pydantic`: obtain `model_dump(mode="python")`, then apply the shared
  JSON output check

The CLI normalizes `Path` values to POSIX strings so every target can be emitted
as JSON.

Decoded `File[json]`/`File[yaml]` leaves are not normalized. Safe YAML can
contain dates, sets, binary values, non-string mapping keys, and other
decoder-native values. If any payload falls outside the standard JSON data
model, the CLI raises `E_SERIALIZATION` with the offending payload path instead
of coercing it. This rule is shared by graph and loaded-config output.
`validate --short` performs no JSON serialization.

An exact `File[bytes]` leaf has an explicit typed projection: JSON output uses
`null`, recursively through ETCM-owned lists and dictionaries, while Python
graph values and generated views retain the bytes. The projection does not
apply to bytes nested inside YAML or another non-byte file value.

For example:

```bash
etcm load tests/fixtures/valid/spec_inheritance_resolver/cuda.etcm#CudaRuntime:default
```

prints:

```json
{
  "device": "cuda",
  "gpus": 2
}
```
