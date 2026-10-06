"""Errors outside the register and resolve paths: closing a container, constructing a group."""

import typing
from collections.abc import Sequence

from modern_di.exceptions.base import ModernDIError


class FinalizerError(ModernDIError, ExceptionGroup[Exception]):
    """One or more finalizers raised during close.

    An ``ExceptionGroup``: ``.exceptions`` holds the finalizer errors, so ``except*`` can catch them
    by type. ``.is_async`` records which close path ran, and splits keep it.
    """

    docs_slug = "finalizer-error"

    __slots__ = ("is_async",)

    def __new__(cls, *, finalizer_errors: Sequence[Exception], is_async: bool) -> typing.Self:
        return ExceptionGroup.__new__(cls, _cleanup_message(finalizer_errors, is_async=is_async), finalizer_errors)

    def __init__(self, *, finalizer_errors: Sequence[Exception], is_async: bool) -> None:
        self.is_async = is_async
        super().__init__(self.message, finalizer_errors)

    def _render_body(self) -> str:
        return self.message

    def derive(self, excs: Sequence[Exception]) -> "FinalizerError":
        return FinalizerError(finalizer_errors=excs, is_async=self.is_async)


def _cleanup_message(finalizer_errors: Sequence[Exception], *, is_async: bool) -> str:
    kind = "async" if is_async else "sync"
    return f"Errors during {kind} cleanup: {list(finalizer_errors)}"


class AsyncFinalizerInSyncCloseError(ModernDIError):
    """``close_sync`` reached a cached instance whose finalizer is async. Inspect ``.instance_type``."""

    docs_slug = "async-finalizer-in-sync-close-error"

    __slots__ = ("instance_type",)

    def __init__(self, *, instance_type: type) -> None:
        self.instance_type = instance_type
        super().__init__(
            f"Cannot run async finalizer for {instance_type.__name__} during sync close. "
            "Use `await container.close_async()` (or `async with container:`) instead."
        )


class GroupInstantiationError(ModernDIError):
    """A ``Group`` subclass was instantiated. Inspect ``.group_name``; groups are namespaces, never objects."""

    docs_slug = "group-instantiation-error"

    __slots__ = ("group_name",)

    def __init__(self, *, group_name: str) -> None:
        self.group_name = group_name
        super().__init__(f"{group_name} cannot be instantiated")
