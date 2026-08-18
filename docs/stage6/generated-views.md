# Stage 6 Generated Views

Generated views consume only `ResolvedGraph`. They must not read ETCM files or
repeat resolver logic.

## dict

`target="dict"` returns a nested Python payload.

- references become nested dictionaries
- `Path` values become POSIX strings
- file leaves retain materialized Python values unchanged, including `str` and
  `bytes`
- graph metadata stays in `ResolvedGraph`, not in the payload

Ordinary ETCM values remain JSON-compatible. Safe YAML may contain native
values outside the JSON model; serialization is checked only at an actual JSON
output boundary. Typed `File[bytes]` leaves project to `null` at that boundary;
the Python dict itself retains bytes.

## dataclass

`target="dataclass"` returns frozen generated dataclass instances.

- references become nested dataclass instances
- `Path` values remain `Path`
- `File[str]` and `File[bytes]` are annotated `str` and `bytes`; structured
  file leaves remain unchanged and are annotated `Any`
- generated classes are implementation details

## pydantic

`target="pydantic"` returns frozen Pydantic v2 model instances.

- models are built with `create_model()`
- model config is frozen and `extra="forbid"`
- references become nested Pydantic objects
- `File[str]` and `File[bytes]` are annotated `str` and `bytes`; structured
  file leaves remain unchanged and are annotated `Any`
- representable constraints are mirrored into Pydantic fields
- named assertions remain ETCM validation rules and are listed in schema
  summaries rather than installed as Pydantic model validators

ETCM validation remains the source of truth. Pydantic constraints are included
for view fidelity and future schema export.
