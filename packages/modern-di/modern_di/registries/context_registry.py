import dataclasses
import typing


T = typing.TypeVar("T")


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ContextRegistry:
    context: dict[type[typing.Any], typing.Any]

    def find_context(self, context_type: type[T]) -> T | None:
        if context_type and (context := self.context.get(context_type)):
            return typing.cast(T, context)

        return None
