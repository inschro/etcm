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
- `--target pydantic`: print `model_dump(mode="json")`

The CLI normalizes `Path` values to POSIX strings so every target can be emitted
as JSON.

For example:

```bash
etcm load tests/fixtures/valid/spec_inheritance_resolver/cuda.etcm#default
```

prints:

```json
{
  "device": "cuda",
  "gpus": 2
}
```
