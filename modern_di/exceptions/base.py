"""The root error class every family builds on."""

import typing

from modern_di.exceptions import _pickling


_TROUBLESHOOTING_BASE_URL = "https://modern-di.modern-python.org/troubleshooting"


class ModernDIError(RuntimeError):
    """Base class for all modern-di errors. A ``RuntimeError``, so ``except RuntimeError`` catches every one of them.

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
        if (frozen := _pickling.frozen_message(self)) is not None:
            return frozen
        body = self._render_body()
        if self.docs_slug is None:
            return body
        return f"{body}\nSee: {_TROUBLESHOOTING_BASE_URL}/{self.docs_slug}/"

    def __reduce_ex__(self, protocol: typing.SupportsIndex) -> tuple[typing.Any, ...]:
        return _pickling.reduce_error(self, int(protocol))

    def __copy__(self) -> typing.Self:
        return _pickling.copy_error(self)

    def __deepcopy__(self, memo: dict[int, typing.Any]) -> typing.Self:
        return _pickling.deepcopy_error(self, memo)
