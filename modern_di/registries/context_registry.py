import typing

from modern_di import types


class ContextRegistry:
    __slots__ = ("context",)

    def __init__(self, context: dict[type[typing.Any], typing.Any]) -> None:
        self.context = context

    def set_context(self, context_type: type[types.T], obj: types.T) -> None:
        self.context[context_type] = obj
