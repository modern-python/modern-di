import enum
import typing

from modern_di import exceptions
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    import typing_extensions


class Group:
    def __new__(cls, *_: typing.Any, **__: typing.Any) -> "typing_extensions.Self":  # noqa: ANN401
        raise exceptions.GroupInstantiationError(group_name=cls.__name__)

    _default_scope: typing.ClassVar["enum.IntEnum | None"] = None

    def __init_subclass__(cls, scope: "enum.IntEnum | None" = None, **kwargs: typing.Any) -> None:  # noqa: ANN401
        """Record a group-default scope and stamp it onto scope-defaulted providers in this class body."""
        super().__init_subclass__(**kwargs)
        if scope is not None:
            if not isinstance(scope, enum.IntEnum):
                raise exceptions.InvalidScopeTypeError(scope_value=scope)
            cls._default_scope = scope
        default_scope = cls._default_scope
        if default_scope is None:
            return
        for value in cls.__dict__.values():
            if isinstance(value, AbstractProvider):
                value._stamp_group_scope(default_scope, cls.__name__)  # noqa: SLF001

    @classmethod
    def get_named_providers(cls) -> dict[str, AbstractProvider[typing.Any]]:
        seen_names: set[str] = set()
        collected: dict[str, AbstractProvider[typing.Any]] = {}
        for klass in cls.__mro__:
            if klass is Group or klass is object:
                continue
            for name, value in klass.__dict__.items():
                if name in seen_names:
                    continue
                seen_names.add(name)
                if isinstance(value, AbstractProvider):
                    collected[name] = value
        return collected

    @classmethod
    def get_providers(cls) -> list[AbstractProvider[typing.Any]]:
        return list(cls.get_named_providers().values())
