# Typed files

`File[T]` links a field to a local file and materializes it during resolution. The
configured value is a path string; Python callers receive the decoded or raw content.

```text title="assets.etcm"
spec Assets:
  prompt: File[str] = "prompts/system.txt"
  weights: File[bytes] = "models/weights.bin"
  prompts: File[json] = "prompts/prompts.json"
  launcher: File[yaml] = "runtime/launcher.yaml"

  impl default:
    prompt: "prompts/default.txt"
```

```python
from etcm import load

cfg = load("assets.etcm#Assets:default")
print(cfg.prompt)
assert isinstance(cfg.weights, bytes)
```

## Codecs

Every `File[T]` names exactly one codec:

| Type | Resolved Python value |
| --- | --- |
| `File[str]` | Strict UTF-8 `str` |
| `File[bytes]` | Exact file bytes |
| `File[json]` | Standard decoded JSON value |
| `File[yaml]` | Safely decoded YAML 1.2 value |

Bare `bytes`, `json`, and `yaml` are not value types. Use them only as codecs inside
`File[...]`. Bare `str` remains an ordinary inline string type.

Every non-null file value must be a path string. Passing already materialized text,
bytes, lists, mappings, or scalars is a type error.

## Type composition

Put value-level nullability and containers outside `File[...]`:

```text
optional: File[bytes] | null = null
templates: list[File[str]] = ["one.txt", "two.md"]
artifacts: dict[str, File[bytes]] = {model: "model.bin"}
json_documents: list[File[json]] = ["train.json", "eval.json"]
```

Every file leaf still chooses one codec. These shapes are rejected:

```text
mixed_text: File[str | json]
mixed_binary: File[bytes | yaml]
nullable_codec: File[json | null]
split_union: File[json] | File[yaml]
keyed: dict[File[json], str]
```

Write `File[json] | null` instead of `File[json | null]`. File types can be fields,
list items, or dictionary values, but not dictionary keys. Unions of multiple file
codecs are deliberately unsupported.

## Exact decoding

The codec ignores the filename suffix:

```text
text: File[str] = "prompt.json"      # returns JSON source text
binary: File[bytes] = "weights.txt"  # returns exact bytes
json_data: File[json] = "data.txt"
yaml_data: File[yaml] = "data.json"
```

`File[str]` uses strict UTF-8. It does not strip a byte-order mark, normalize line
endings, trim trailing newlines, or detect another encoding. Invalid UTF-8 is an
`E_FILE_LOAD` diagnostic with byte-offset details.

`File[json]` always invokes the JSON decoder. `File[yaml]` always invokes the safe
YAML 1.2 decoder. A decode failure is final; ETCM does not fall back to another
codec.

## Paths and overrides

A file path written in ETCM is resolved relative to the file containing that value.
A path supplied through Python or CLI overrides is resolved relative to
`override_base`, which defaults to the current working directory.

```python
from etcm import load

cfg = load(
    "assets.etcm#Assets:default",
    overrides={"prompts": "runtime/prompts.json"},
    override_base="/srv/run",
)
```

Overrides are fully composed before files are opened. A replaced default is never
loaded. Lists using `append` and mappings using `merge` preserve the base associated
with every path contributed from different sources.

Only local files are supported. ETCM does not fetch URLs, watch files, reload them,
or add materialized files to the graph's list of ETCM source documents.

See [overrides](overrides.md) for deep paths, reference replacement, and external
path rules.

## Opaque content boundary

ETCM validates the link and decoder, not the decoded document's schema. File content
cannot be:

- traversed by parameter references
- targeted by deep overrides
- read by named assertions
- constrained directly with field validation syntax

For example, these file fields are invalid because they attempt to constrain decoded
content:

```text
document: File[json] = "data.json" [min_length=1]
prompt: File[str] = "prompt.txt" [regex="..."]
```

Constraints remain valid on an ETCM-owned surrounding container:

```text
documents: list[File[json]] = ["one.json"] [min_length=1]
```

Normal override policies also remain valid directly on file fields.

If data needs ETCM-owned schema validation, model it as ordinary typed fields or a
referenced spec rather than opaque file content.

## Python views

Dictionary, dataclass, Pydantic, and raw graph values preserve materialized file
values. Generated Python annotations use:

| ETCM type | Python annotation |
| --- | --- |
| `File[str]` | `str` |
| `File[bytes]` | `bytes` |
| `File[json]` | `Any` |
| `File[yaml]` | `Any` |

Schema summaries retain the original `File[...]` declaration.

## JSON output boundaries

The graph and CLI formats are JSON. At those boundaries, each typed `File[bytes]`
leaf is emitted as `null`; Python graph values and `load()` views still retain exact
bytes. This applies recursively inside lists and dictionaries.

For `File[bytes] | null`, JSON output intentionally cannot distinguish an absent
value from omitted binary content. Configured paths remain visible in field
defaults, literals, and override audit records.

This projection applies only to values typed as `File[bytes]`. Safe YAML may decode
native values such as dates, sets, binary values, or mappings with non-string keys.
Python views preserve them, but graph or CLI JSON output fails with
`E_SERIALIZATION` when such a value is outside standard JSON. ETCM never silently
stringifies it.

`validate --short` performs no graph serialization and can still succeed for those
values.

## Diagnostics

Read, UTF-8, JSON, and YAML failures use `E_FILE_LOAD`. Wrong configured values and
unsupported `File[...]` shapes use `E_TYPE_MISMATCH`. Diagnostics include the ETCM
field, source path, resolved path, declared codec, and decoder position where
available.
