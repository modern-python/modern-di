---
summary: Add Group.get_named_providers() returning a name→provider dict; reimplement get_providers() on top of it so the MRO traversal and dedup/masking semantics live in one place.
---

# Design: Name-preserving provider accessor on `Group`

## Summary

`Group.get_providers()` walks the MRO and returns the providers it finds, but
discards the attribute name each provider was declared under. Downstream
integrations that need the names (notably `modern-di-litestar`'s autowiring,
which keys Litestar dependencies by attribute name) are forced to reconstruct
them with a fragile `id()`-keyed reverse lookup over `group.__dict__`. Add
`Group.get_named_providers() -> dict[str, AbstractProvider]` as the
name-preserving primitive, and reimplement `get_providers()` as
`list(cls.get_named_providers().values())` so the MRO walk and the
dedup/masking rules exist in exactly one place.

## Motivation

`modern-di-litestar` currently does this in `on_app_init`:

```python
name_by_provider_id = {id(v): k for k, v in group.__dict__.items() if isinstance(v, providers.AbstractProvider)}
for provider in group.get_providers():
    name = name_by_provider_id[id(provider)]
```

`name_by_provider_id` is built from `group.__dict__` only, while
`get_providers()` walks the full MRO. A `Group` subclass that **inherits** a
provider from a base `Group` therefore raises `KeyError`: the inherited
provider comes back from `get_providers()` but its name isn't in the
subclass `__dict__`. This is reproduced today — autowiring `class Child(Base)`
where `Base` declares a provider raises `KeyError: <id>`.

The names are `Group`'s knowledge — it owns how providers are declared and
traversed. Exposing them here fixes the bug at its source and gives every
integration one small interface instead of each re-deriving names.

## Non-goals

- Changing `get_providers()`'s return type, order, or de-duplication
  semantics — they stay identical, just sourced differently.
- Touching the downstream `modern-di-litestar` autowiring — that is a separate
  PR gated on this one's release (`modern-di 2.20.0`).

## Design

### 1. `get_named_providers()`

A new classmethod mirroring `get_providers()`'s traversal but keyed by name:

```python
@classmethod
def get_named_providers(cls) -> dict[str, AbstractProvider[typing.Any]]:
    seen_names: set[str] = set()
    collected: dict[str, AbstractProvider[typing.Any]] = {}
    for klass in cls.__mro__:
        if klass is Group or klass is object:
            continue
        for name, value in klass.__dict__.items():
            if name in seen_names:
                continue
            seen_names.add(name)
            if isinstance(value, AbstractProvider):
                collected[name] = value
    return collected
```

Semantics preserved from the current `get_providers()`:

- **MRO order** — most-derived class first; dict insertion order matches the
  old list order.
- **First-seen-name wins** — `seen_names` de-dups across the MRO (diamond
  inheritance returns each provider once, under its declared name).
- **Non-provider masking** — a subclass attribute that shadows a parent
  provider with a non-provider value marks the name seen and excludes the
  parent provider, so it appears in neither the dict nor `get_providers()`.

### 2. `get_providers()` reimplemented

```python
@classmethod
def get_providers(cls) -> list[AbstractProvider[typing.Any]]:
    return list(cls.get_named_providers().values())
```

The traversal, dedup, and masking logic now exist once. `get_providers()`
becomes a one-line adapter over the named map.

## Testing

New tests in `tests/test_group.py` pinning `get_named_providers()`:

- maps each provider (own and inherited) to its declared attribute name;
- a non-provider override masks the parent provider (name absent from the map);
- diamond inheritance yields a single named entry;
- `get_providers()` equals `list(get_named_providers().values())` (order +
  membership stay consistent).

The existing `get_providers()` tests (inheritance, override, diamond, masking)
must stay green unchanged — they prove the reimplementation is behavior-neutral.
Full gate: `just test-ci` (100% line coverage).

## Risk

Low. Additive public API plus a behavior-neutral reimplementation of an
existing method, both covered by the existing and new test suites. The only
behavioral surface is `get_named_providers()` itself; `get_providers()`'s
contract is unchanged and independently tested.
