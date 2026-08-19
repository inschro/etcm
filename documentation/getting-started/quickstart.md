# Quickstart

This quickstart does one thing: define a named pet configuration, validate it,
and load it from Python. Later guides add composition and validation rules.

You can copy the finished file from the
[runnable example](../examples/pet-boarding/01-quickstart/pets.etcm).

## 1. Define the contract

Save this as `pets.etcm`:

```text title="pets.etcm"
spec Pet:
  name: str
```

A **spec** is a configuration contract. `spec Pet` says what a valid `Pet`
contains; it does not describe a particular pet yet.

The indented line declares one field:

- `name` is the field name.
- `str` is the required type.
- There is no default, so every concrete `Pet` must supply a name.

## 2. Add one named configuration

Extend the same file:

```text title="pets.etcm"
spec Pet:
  name: str

  impl pepper:
    name: "Pepper"
```

An **implementation**, written `impl`, supplies concrete values for a spec.
`pepper` is its name. It can now be selected independently from any other `Pet`
implementations we add later.

At this point the file contains exactly two ideas: a contract and one named set of
values that satisfies it.

## 3. Validate the implementation

Run:

```console
$ etcm validate pets.etcm#Pet:pepper --short
OK: /path/to/pets.etcm#Pet:pepper
```

The argument is a **selector**, an exact address with three parts:

- `pets.etcm` is the file.
- `Pet` is the spec after `#`.
- `pepper` is the implementation after `:`.

ETCM parses the file, finds that exact implementation, and checks it against
`Pet`.

### See a missing-field failure

Now extend the contract with the amount of food a pet needs each day, but leave
the existing implementation unchanged:

```text title="pets.etcm"
spec Pet:
  name: str
  daily_food_grams: int

  impl pepper:
    name: "Pepper"
```

`daily_food_grams` has no default, so every `Pet` implementation must now supply
it. Run the same validation command:

```console
$ etcm validate pets.etcm#Pet:pepper --short
E_MISSING_FIELD: Missing required field 'daily_food_grams'.
source: /path/to/pets.etcm:3:3
graph_path: root.daily_food_grams
details: {"field": "daily_food_grams"}
```

ETCM exits with status `1`. The source location points to the declaration that
made the field required, while `root.daily_food_grams` identifies the missing
value in the resolved configuration.

If `300` is the normal daily amount, define it once as a default in the spec:

```text title="pets.etcm"
spec Pet:
  name: str
  daily_food_grams: int = 300

  impl pepper:
    name: "Pepper"
```

`=` gives `daily_food_grams` a declaration default. An implementation inherits
that value when it does not supply its own.

Validation succeeds again:

```console
$ etcm validate pets.etcm#Pet:pepper --short
OK: /path/to/pets.etcm#Pet:pepper
```

## 4. Load it from Python

`load()` performs the same validation and then creates a runtime view. Save this
beside `pets.etcm` as `show_pet.py`:

```python title="show_pet.py"
from etcm import load

pet = load("pets.etcm#Pet:pepper")
print(pet.name)
```

Run it:

```console
$ python show_pet.py
Pepper
```

The default view is a generated Pydantic model, which is why attribute access
works. Use `target="dict"` when a mapping is a better boundary:

```python
pet = load("pets.etcm#Pet:pepper", target="dict")
assert pet == {"name": "Pepper", "daily_food_grams": 300}
```

You now know the minimum ETCM workflow: define a spec, add an implementation,
address it with a selector, and validate or load it.

## Give a coding agent the same feedback loop

ETCM validation is fast enough to run after an agent edits configuration. Copy
the following block into your agent's repository-instruction file. Codex uses
[`AGENTS.md`](https://learn.chatgpt.com/codex/agent-configuration/agents-md);
other agents may use a different filename.

```markdown title="AGENTS.md"
## ETCM configuration

- Use ETCM (`*.etcm`) for configuration management.
- After every change to code or configuration, validate each affected ETCM
  implementation with:
  `etcm validate path/to/file.etcm#Spec:implementation --short`
- If a shared spec or reference changed, or the affected implementations are
  uncertain, run:
  `etcm validate-all path/to/configs`
- Treat ETCM validation failures as blocking.

Syntax:
- `spec Name:` defines a configuration contract.
- `field: Type` is required; `field: Type = value` adds a default.
- `field: Type [rule]` validates; `field: Type := @other` derives a value.
- `impl name:` supplies named concrete values.
- `$field: path#Spec` declares a typed child; `$field: path#Spec:impl` selects one.
- Root selectors use `path/to/file.etcm#Spec:implementation`.
```

Keep the block close to the configuration it governs. For a large repository,
replace `path/to/configs` with the smallest directory that contains every
potentially affected implementation.

## Continue learning

The quickstart used a pet to keep the first file small. The
[basic tutorial](../tutorials/basic.md) now applies the same concepts to a
multi-file ML training configuration. The [advanced tutorial](../tutorials/advanced.md)
extends it with inheritance, controlled overrides, file-backed JSON, paths, and
an argparse application boundary.
