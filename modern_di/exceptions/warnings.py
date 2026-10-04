"""Warnings; none descend from ``ModernDIError``."""


class ValidateArgumentWarning(DeprecationWarning):
    """`Container(validate=...)` is ignored; call `Container.validate()` instead."""

    def __init__(self) -> None:
        super().__init__(
            "`Container(validate=...)` is ignored as of 3.1 and is removed in 4.0: "
            "graph validation runs only when you call `container.validate()`."
        )


class UnvalidatedContainerWarning(FutureWarning):
    """No longer emitted; kept importable for back-compat.

    In modern-di 2.x this warned when a root container was built without an explicit ``validate``
    argument. Nothing raises or warns this class today: graph validation runs only when
    :meth:`Container.validate` is called explicitly, and never implicitly at any point in the
    lifecycle. The class stays importable so an existing::

        warnings.filterwarnings("error", category=exceptions.UnvalidatedContainerWarning)

    does not break at import time.
    """


class ContextValueNoneWarning(DeprecationWarning):
    """Retained for back-compat of existing ``filterwarnings`` configs; no longer emitted.

    In modern-di 2.x this warned when a direct resolve of an unset ``ContextProvider`` returned
    ``None``. As of 3.0 that resolve raises :class:`ContextValueNotSetError` instead, so this
    warning is never raised — the class stays importable so an existing::

        warnings.filterwarnings("error", category=exceptions.ContextValueNoneWarning)

    does not break at import time.
    """
