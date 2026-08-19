# File-types reference

`File[T]` stores a source path in ETCM and exposes decoded file content in the
resolved graph. The
[advanced tutorial](../tutorials/advanced.md#load-a-small-json-manifest) uses a
JSON-backed field in an application before this page defines the exact behavior.

## Codecs

| Declaration | Resolved Python value | Decoder |
| --- | --- | --- |
| `File[str]` | `str` | Strict UTF-8 |
| `File[bytes]` | `bytes` | Exact bytes |
| `File[json]` | JSON-compatible value | Python standard-library JSON |
| `File[yaml]` | Safe YAML 1.2 value | ruamel.yaml safe loader |

The codec is explicit. ETCM never infers it from the filename or content.

## Accepted type shapes

File types may appear directly and inside supported containers:

```text
instructions: File[str]
optional_record: File[yaml] | null
photos: list[File[bytes]]
records: dict[str, File[json]]
```

A file type may share a union only with `null`, as in `File[yaml] | null`.
`File[json] | str` and unions of different file types are invalid. Nested lists
and string-keyed mappings preserve their declared value types.

## Configured values

An ETCM assignment supplies a string path:

```text
instructions: "pepper-care.txt"
```

Python overrides additionally accept `pathlib.Path`. Other configured value types
fail type validation before a file is opened.

## Path resolution

Paths from ETCM source are relative to the file that contributed the effective
value. That base survives spec inheritance, implementation inheritance, and typed
references.

External Python and CLI overrides use `override_base` when supplied, otherwise the
process working directory. Overrides compose before file loading, so a replaced
file default is not opened.

## Decoding

`File[str]` rejects invalid UTF-8 rather than replacing bytes. `File[bytes]`
preserves the file exactly.

`File[json]` accepts standard JSON. `File[yaml]` uses safe YAML 1.2 and does not
construct arbitrary Python objects. Decoded JSON or YAML content is opaque to ETCM
field paths, parameter expressions, and deep overrides.

## Runtime views

Generated Pydantic and dataclass views use these annotations:

| ETCM type | Python annotation |
| --- | --- |
| `File[str]` | `str` |
| `File[bytes]` | `bytes` |
| `File[json]` | `Any` |
| `File[yaml]` | `Any` |

Dictionary views contain the same decoded values.

## JSON output boundary

Graph and CLI output is JSON. Values declared as `File[bytes]` are projected to
`null` at that boundary; the Python graph and runtime views retain the bytes.
Projection also applies inside lists and mappings.

Safe YAML can decode values outside standard JSON, including dates, sets, binary
values, or mappings with non-string keys. Python views preserve them. JSON output
fails with `E_SERIALIZATION` rather than stringifying them silently.

`validate --short` does not serialize the graph and can succeed for such values.

## Diagnostics

Read, UTF-8, JSON, and YAML failures use `E_FILE_LOAD`. Invalid configured values
or unsupported `File[...]` shapes use `E_TYPE_MISMATCH`. Diagnostics identify the
field, source path, resolved path, codec, and decoder location when available.
