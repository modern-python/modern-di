import dataclasses
import typing

from modern_di import types


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ContextRegistry:
    context: dict[type[typing.Any], typing.Any]

    def find_context(self, context_type: type[types.T]) -> types.T | None:
        if context_type and (context := self.context.get(context_type)):
            return typing.cast(types.T, context)

        return None

    def set_context(self, context_type: type[types.T], obj: types.T) -> None:
        self.context[context_type] = obj
