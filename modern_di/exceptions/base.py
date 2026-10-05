"""The root error class and the breadcrumb mixin every family builds on."""

import copy
import pickle
import typing

from modern_di.exceptions.rendering import ResolutionStep, render_chain


_TROUBLESHOOTING_BASE_URL = "https://modern-di.modern-python.org/troubleshooting"
_RENDERED_KEY = "_rendered_message"
_Group: typing.TypeAlias = tuple[str, list[BaseException]]
_Snapshot: typing.TypeAlias = tuple[
    "type[ModernDIError]", str, _Group | None, tuple[typing.Any, ...], dict[str, typing.Any]
]


class ModernDIError(RuntimeError):
    """Base class for all modern-di errors. Inherits from RuntimeError for backwards compatibility.

    ``docs_slug`` names this class's page under ``docs/troubleshooting/``; ``__str__`` appends it
    as a trailing ``See: <url>`` line, always the final line of the rendered message. Base classes
    (this one, :class:`ContainerError`, :class:`ResolutionError`, :class:`RegistrationError`) are
    never raised directly and keep ``docs_slug`` unset; every concrete subclass sets one (enforced
    by the census test in ``tests/test_docs_slug_census.py``).
    """

    docs_slug: typing.ClassVar[str | None] = None

    __slots__ = ()

    def _render_body(self) -> str:
        """Message body without the docs trailer. Subclasses with custom rendering override this, not `__str__`."""
        return RuntimeError.__str__(self)

    def __str__(self) -> str:
        if (rendered := vars(self).get(_RENDERED_KEY)) is not None:
            return typing.cast("str", rendered)
        body = self._render_body()
        if self.docs_slug is None:
            return body
        return f"{body}\nSee: {_TROUBLESHOOTING_BASE_URL}/{self.docs_slug}/"

    def __reduce__(self) -> tuple[typing.Any, ...]:
        return _restore, _snapshot(self, _pickle_round_trip)

    def __copy__(self) -> typing.Self:
        return _restore(*_snapshot(self, lambda value: value))

    def __deepcopy__(self, memo: dict[int, typing.Any]) -> typing.Self:
        return _restore(*_snapshot(self, lambda value: copy.deepcopy(value, memo)))


def _pickle_round_trip(value: object) -> object:
    pickle.loads(pickle.dumps(value))  # noqa: S301
    return value


def _safe_repr(value: object) -> str:
    try:
        return repr(value)
    except Exception:  # noqa: BLE001
        return object.__repr__(value)


def _kept(value: object, keep: typing.Callable[[object], object]) -> object:
    try:
        return keep(value)
    except Exception:  # noqa: BLE001
        return _safe_repr(value)


def _kept_exception(error: BaseException, keep: typing.Callable[[object], object]) -> BaseException:
    try:
        return typing.cast("BaseException", keep(error))
    except Exception:  # noqa: BLE001
        return RuntimeError(_safe_repr(error))


def _state(error: ModernDIError) -> dict[str, typing.Any]:
    names = {
        name
        for klass in type(error).__mro__
        for name in vars(klass).get("__slots__", ())
        if name not in {"__dict__", "__weakref__"} and hasattr(error, name)
    }
    state = {name: getattr(error, name) for name in sorted(names)}
    state.update(vars(error))
    return state


def _snapshot(error: ModernDIError, keep: typing.Callable[[object], object]) -> _Snapshot:
    """Capture what rebuilding ``error`` needs, passing each value through ``keep`` or its repr when that raises."""
    group = None
    args: tuple[typing.Any, ...] = ()
    if isinstance(error, BaseExceptionGroup):
        group = (error.message, [_kept_exception(e, keep) for e in error.exceptions])
    else:
        args = tuple(_kept(arg, keep) for arg in error.args)
    state = {name: _kept(value, keep) for name, value in _state(error).items()}
    return type(error), str(error), group, args, state


def _restore(
    cls: type[ModernDIError],
    rendered: str,
    group: _Group | None,
    args: tuple[typing.Any, ...],
    state: dict[str, typing.Any],
) -> typing.Any:  # noqa: ANN401
    """Rebuild an error from `_snapshot` without calling its keyword-only ``__init__``; ``str()`` stays ``rendered``."""
    if group is not None:
        error = BaseExceptionGroup.__new__(cls, *group)  # ty: ignore[invalid-argument-type]
    else:
        error = BaseException.__new__(cls)
        error.args = args
    for name, value in state.items():
        setattr(error, name, value)
    vars(error)[_RENDERED_KEY] = rendered
    return error


class DependencyPathMixin:
    """Breadcrumb machinery behind :class:`ResolutionError`.

    Owns `prepend_step` and the chain-rendering `_render_body` (the body `ModernDIError.__str__`
    appends the docs trailer to), so any error raised inside a resolution frame can accumulate the
    chain of provider names as it propagates back up to the caller. With an empty `dependency_path`
    (the error never passed through a resolution frame) `_render_body` returns the base message
    unchanged.
    """

    def __init__(self, message: str) -> None:
        self._base_message = message
        self.dependency_path: list[ResolutionStep] = []
        # Mixin's own base is `object`; the real MRO (via ResolutionError ->
        # ModernDIError -> RuntimeError) accepts the arg at runtime.
        super().__init__(message)  # ty: ignore[too-many-positional-arguments]

    def prepend_step(self, *steps: ResolutionStep) -> None:
        """Put `steps` in front of the chain, in the order given."""
        self.dependency_path[:0] = steps
        self.args = (str(self),)

    def _render_body(self) -> str:
        if not self.dependency_path:
            return self._base_message

        lines = [
            "Cannot resolve dependency chain:",
            *render_chain(self.dependency_path),
            f"  caused by: {self._base_message}",
        ]
        return "\n".join(lines)
