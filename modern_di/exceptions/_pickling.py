"""Pickle and copy support for ``ModernDIError``: rebuild an error from its parts, never through ``__init__``."""

import copy
import functools
import io
import pickle
import typing

from modern_di.exceptions import base


ErrorT = typing.TypeVar("ErrorT", bound="base.ModernDIError")

_RENDERED_KEY = "_rendered_message"
_NESTED_ERROR = "modern-di-error"


class Blueprint(typing.NamedTuple, typing.Generic[ErrorT]):
    """What creating the bare error object needs; the rest arrives as attribute state afterwards."""

    cls: type[ErrorT]
    args: tuple[typing.Any, ...]
    group_message: str | None
    group_exceptions: list[BaseException]


def frozen_message(error: "base.ModernDIError") -> str | None:
    """Return the message a pickled or copied error keeps instead of re-rendering, or ``None`` for an original."""
    return vars(error).get(_RENDERED_KEY)


class _ProbePickler(pickle.Pickler):
    def persistent_id(self, obj: object) -> str | None:
        return _NESTED_ERROR if isinstance(obj, base.ModernDIError) else None


class _ProbeUnpickler(pickle.Unpickler):
    def persistent_load(self, pid: object) -> None:  # noqa: ARG002
        return None


def _loadable(value: object, protocol: int) -> object:
    """Return ``value`` if it pickles and unpickles at ``protocol``, else raise.

    Nested modern-di errors are stubbed out: each one checks its own attributes when it is pickled.
    """
    buffer = io.BytesIO()
    _ProbePickler(buffer, protocol).dump(value)
    buffer.seek(0)
    _ProbeUnpickler(buffer).load()
    return value


def _unchanged(value: object) -> object:
    return value


def _safe_repr(value: object) -> str:
    try:
        return repr(value)
    except Exception:  # noqa: BLE001
        return object.__repr__(value)


def _preserved(
    value: object, carry: typing.Callable[[object], object], fallback: typing.Callable[[str], object] = str
) -> object:
    """``carry(value)``, or ``fallback`` applied to the value's repr when ``carry`` raises."""
    try:
        return carry(value)
    except Exception:  # noqa: BLE001
        return fallback(_safe_repr(value))


def _blueprint(error: ErrorT, carry: typing.Callable[[object], object]) -> Blueprint[ErrorT]:
    if isinstance(error, BaseExceptionGroup):
        exceptions = [typing.cast("BaseException", _preserved(e, carry, RuntimeError)) for e in error.exceptions]
        return Blueprint(type(error), (), error.message, exceptions)
    return Blueprint(type(error), tuple(_preserved(arg, carry) for arg in error.args), None, [])


def _state(error: "base.ModernDIError") -> dict[str, typing.Any]:
    names = {
        name
        for klass in type(error).__mro__
        for name in vars(klass).get("__slots__", ())
        if name not in {"__dict__", "__weakref__"} and hasattr(error, name)
    }
    state = {name: getattr(error, name) for name in sorted(names)}
    state.update(vars(error))
    state[_RENDERED_KEY] = str(error)
    return state


def _restore(blueprint: Blueprint[ErrorT]) -> ErrorT:
    """Create the bare error described by ``blueprint``, without calling its keyword-only ``__init__``."""
    if blueprint.group_message is not None:
        return BaseExceptionGroup.__new__(
            blueprint.cls,  # ty: ignore[invalid-argument-type]
            blueprint.group_message,
            blueprint.group_exceptions,
        )
    error = BaseException.__new__(blueprint.cls)
    error.args = blueprint.args
    return error


def _apply(error: "base.ModernDIError", state: dict[str, typing.Any]) -> None:
    for name, value in state.items():
        setattr(error, name, value)


def reduce_error(error: "base.ModernDIError", protocol: int) -> tuple[typing.Any, ...]:
    """``__reduce_ex__``: values that cannot round-trip at ``protocol`` are replaced by their repr."""
    loadable = functools.partial(_loadable, protocol=protocol)
    state = {name: _preserved(value, loadable) for name, value in _state(error).items()}
    return _restore, (_blueprint(error, loadable),), state


def copy_error(error: ErrorT) -> ErrorT:
    """``__copy__``: a new error sharing every attribute value with ``error``."""
    clone = _restore(_blueprint(error, _unchanged))
    _apply(clone, _state(error))
    return clone


def deepcopy_error(error: ErrorT, memo: dict[int, typing.Any]) -> ErrorT:
    """``__deepcopy__``: values that cannot be deep-copied are replaced by their repr."""
    deep = functools.partial(copy.deepcopy, memo=memo)
    clone = _restore(_blueprint(error, deep))
    memo[id(error)] = clone
    _apply(clone, {name: _preserved(value, deep) for name, value in _state(error).items()})
    return clone
