import dataclasses
import typing


T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(slots=True, frozen=True)
class ContextRegistry:
    context: dict[type[typing.Any], typing.Any]

    def find_context(self, context_type: type[T_co]) -> T_co | None:
        if context_type and (context := self.context.get(context_type)):
            return typing.cast(T_co, context)

        return None
