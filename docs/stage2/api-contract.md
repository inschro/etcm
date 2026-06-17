# Stage 2 API Contract

Stage 2 creates the public API shape without implementing behavior.

## Public Imports

```python
from etcm import Resolver, load, resolve, validate
```

These imports must work after the scaffold exists.

## Placeholder Behavior

```python
load("configs/train.etcm#smoke")
resolve("configs/train.etcm#smoke")
validate("configs/train.etcm#smoke")
Resolver().load("configs/train.etcm#smoke")
```

All behavior methods should raise `NotImplementedError` with messages that make
the stage boundary explicit:

```text
ETCM resolver behavior is not implemented in Stage 2.
```

## Resolver Placeholder

`Resolver` should accept explicit configuration now so future behavior does not
need to change the constructor shape.

Minimum constructor:

```python
Resolver(path_exists="allow_missing")
```

Accepted `path_exists` values:

- `allow_missing`
- `must_exist`

Validation of constructor values may be implemented in Stage 2 because it is
local and does not require resolver semantics.

## Public API Rules

- CLI code must call this API later.
- No public return value may expose Lark objects.
- Public errors should use ETCM diagnostic types once implemented.
- Placeholder functions may import only lightweight local modules.

