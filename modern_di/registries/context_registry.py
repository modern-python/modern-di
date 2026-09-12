import dataclasses
import typing

from modern_di import types


@dataclasses.dataclass(kw_only=True, slots=True)
class ContextRegistry:
    context: dict[type[typing.Any], typing.Any]

    def find_context(self, context_type: type[types.T]) -> "types.T | types.UnsetType":
        # Not `.get(key, UNSET)`: that skips a dict subclass's `__contains__`/`__getitem__`.
        if context_type in self.context:
            return self.context[context_type]
        return types.UNSET

    def set_context(self, context_type: type[types.T], obj: types.T) -> None:
        self.context[context_type] = obj
