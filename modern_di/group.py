import enum
import typing

from modern_di import exceptions
from modern_di.providers.abstract import AbstractProvider


class Group:
    """A namespace of providers, declared as class attributes and passed to ``Container(groups=[...])``.

    ``class G(Group, scope=Scope.REQUEST)`` gives that default scope to each ``Factory`` and
    ``ContextProvider`` declared in its body without its own ``scope=``. A group is never instantiated.
    """

    def __new__(cls, *_: object, **__: object) -> typing.Self:
        raise exceptions.GroupInstantiationError(group_name=cls.__name__)

    _default_scope: typing.ClassVar["enum.IntEnum | None"] = None

    def __init_subclass__(cls, scope: "enum.IntEnum | None" = None, **kwargs: object) -> None:
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
        """Return every provider declared on this group and its bases, keyed by attribute name.

        A subclass attribute shadows a base attribute of the same name.
        """
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
        """Return the providers of :meth:`get_named_providers` as a list."""
        # A direct subclass has no inherited providers to merge or shadow.
        if cls.__bases__ == (Group,):
            return [value for value in cls.__dict__.values() if isinstance(value, AbstractProvider)]
        return list(cls.get_named_providers().values())
