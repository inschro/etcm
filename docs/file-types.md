# Typed Files

`File[T]` links an ETCM field to a local file and materializes it during
resolution. The configured value is a path string; Python callers receive the
decoded or raw value directly:

```etcm
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

cfg = load("assets.etcm#Assets:default", target="pydantic")
print(cfg.prompt)
assert isinstance(cfg.weights, bytes)
```

The four exact codecs are:

| Type | Resolved Python value |
| --- | --- |
| `File[str]` | Strict UTF-8 `str` |
| `File[bytes]` | Exact file bytes |
| `File[json]` | Standard Python JSON value |
| `File[yaml]` | Safe YAML 1.2 value |

Bare `bytes`, `json`, and `yaml` are not value types; use `File[...]`. Bare
`str` remains the ordinary inline string type.

Every non-null `File[...]` value must be a path string. Passing already
materialized text, bytes, mappings, lists, or scalars is a type error.

## Type Composition

Put value-level structure outside `File[...]`:

```etcm
optional: File[bytes] | null = null
templates: list[File[str]] = ["one.txt", "two.md"]
artifacts: dict[str, File[bytes]] = {model: "model.bin"}
json_documents: list[File[json]] = ["train.json", "eval.json"]
yaml_documents: list[File[yaml]] = ["train.yaml", "eval.yml"]
```

Every file leaf declares exactly one codec. Nullability and containers belong
outside `File[...]`, and all codec unions are rejected:

```etcm
mixed_text: File[str | json]
mixed_binary: File[bytes | yaml]
mixed_raw: File[str | bytes]
nullable_codec: File[json | null]
split_union: File[json] | File[yaml]
keyed: dict[File[json], str]
```

Write `File[json] | null` instead of `File[json | null]`. For structured files,
choose `File[json]` or `File[yaml]` explicitly; ETCM does not infer a decoder
from a path or try codec alternatives. File types can be fields, list items, or
dictionary values, but not dictionary keys or members of other container types.

## Exact Codecs

Every codec ignores the filename suffix:

```etcm
text: File[str] = "prompt.json"      # returns the JSON source text
binary: File[bytes] = "weights.txt"  # returns the exact bytes
json_data: File[json] = "data.txt"
yaml_data: File[yaml] = "data.json"
```

`File[str]` uses strict UTF-8. It does not strip a UTF-8 byte-order mark,
normalize line endings, trim trailing newlines, or detect another encoding.
Invalid UTF-8 is an `E_FILE_LOAD` decode error with byte offsets.

`File[json]` always invokes the JSON decoder and `File[yaml]` always invokes the
safe YAML 1.2 decoder, whether the path has a matching suffix, another suffix,
or no suffix. A decode failure is final.

## Paths And Overrides

A path written in an ETCM file is resolved relative to the file containing
that value. A path supplied through a Python override or CLI `--set` is
resolved relative to `override_base`, which defaults to the current working
directory.

Overrides are fully composed before files are opened. Consequently, a replaced
default is never loaded, and `append` or `merge` containers retain the correct
base for every path contributed by different sources:

```etcm
spec Inputs:
  files: list[File[str]] = ["base.txt"] [override="append"]

  impl default:
    files: []
```

```python
from etcm import load

cfg = load(
    "inputs.etcm#Inputs:default",
    overrides={"files": ["extra.txt"]},
    override_base="/srv/run",
)
```

Only local files are supported. ETCM does not fetch URLs, watch files, reload
them, or add them to the resolved graph's ETCM source list.

## Opaque Content Boundary

ETCM owns and validates the link, not the materialized content's schema. File
contents cannot be traversed by parameter relations, targeted by deep
overrides, or constrained with field validation syntax. If content needs ETCM
validation, model it as typed ETCM fields or a referenced spec instead.

Constraints on an ETCM-owned surrounding container remain valid:

```etcm
files: list[File[str]] = ["one.txt"] [min_length=1]
```

Normal override policy is also available directly on `File[...]` fields.

Dict, dataclass, Pydantic, and raw graph values preserve materialized file
values. Generated Python annotations use `str` for `File[str]`, `bytes` for
`File[bytes]`, and `Any` for JSON/YAML leaves. Schema summaries retain the
original `File[...]` type.

## JSON Output

ETCM's graph and CLI formats are JSON. At these typed JSON boundaries, each
`File[bytes]` leaf is emitted as `null`; Python graph values and `load()` views
still contain the exact bytes. This applies recursively inside lists and
dictionaries. For `File[bytes] | null`, JSON intentionally cannot distinguish
an absent value from omitted byte content. The configured path remains visible
in graph defaults, literals, and override audit values.

This projection applies only to values typed as `File[bytes]`. Decoder-native
bytes inside YAML and any other non-JSON value still fail graph or CLI output
with `E_SERIALIZATION`; ETCM does not silently normalize them. `validate
--short` performs no JSON serialization and can still validate those values.

Read, UTF-8 decode, and structured parse failures use `E_FILE_LOAD`. Wrong
input values and unsupported file type shapes use `E_TYPE_MISMATCH`.
Diagnostics identify the ETCM field, original and resolved paths, declared
codec, and decoder position details when available.
