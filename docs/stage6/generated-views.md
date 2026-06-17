# Stage 6 Generated Views

Generated views consume only `ResolvedGraph`. They must not read ETCM files or
repeat resolver logic.

## dict

`target="dict"` returns a JSON-compatible nested payload.

- references become nested dictionaries
- `Path` values become POSIX strings
- graph metadata stays in `ResolvedGraph`, not in the payload

## dataclass

`target="dataclass"` returns frozen generated dataclass instances.

- references become nested dataclass instances
- `Path` values remain `Path`
- generated classes are implementation details

## pydantic

`target="pydantic"` returns frozen Pydantic v2 model instances.

- models are built with `create_model()`
- model config is frozen and `extra="forbid"`
- references become nested Pydantic objects
- representable constraints are mirrored into Pydantic fields

ETCM validation remains the source of truth. Pydantic constraints are included
for view fidelity and future schema export.
