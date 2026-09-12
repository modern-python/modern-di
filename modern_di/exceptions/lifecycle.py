"""Errors outside the register and resolve paths: closing a container, constructing a group."""

from modern_di.exceptions.base import ModernDIError


class FinalizerError(ModernDIError):
    """One or more finalizers raised during close. Inspect ``.finalizer_errors`` and ``.is_async``."""

    docs_slug = "finalizer-error"

    __slots__ = ("finalizer_errors", "is_async")

    def __init__(self, *, finalizer_errors: list[BaseException], is_async: bool) -> None:
        self.finalizer_errors = finalizer_errors
        self.is_async = is_async
        kind = "async" if is_async else "sync"
        super().__init__(f"Errors during {kind} cleanup: {finalizer_errors}")


class AsyncFinalizerInSyncCloseError(ModernDIError):
    """Raised when ``close_sync`` encounters a cached resource with an async finalizer."""

    docs_slug = "async-finalizer-in-sync-close-error"

    __slots__ = ("finalizer_type",)

    def __init__(self, *, finalizer_type: type) -> None:
        self.finalizer_type = finalizer_type
        super().__init__(
            f"Cannot run async finalizer for {finalizer_type.__name__} during sync close. "
            "Use `await container.close_async()` (or `async with container:`) instead."
        )


class GroupInstantiationError(ModernDIError):
    """A ``Group`` subclass was instantiated. Inspect ``.group_name``; groups are namespaces, never objects."""

    docs_slug = "group-instantiation-error"

    __slots__ = ("group_name",)

    def __init__(self, *, group_name: str) -> None:
        self.group_name = group_name
        super().__init__(f"{group_name} cannot be instantiated")
