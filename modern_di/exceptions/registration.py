"""Errors raised while providers and groups are declared."""

import enum
import typing

from modern_di import suggester
from modern_di.exceptions.base import ModernDIError
from modern_di.exceptions.rendering import ResolutionStep, _render_chain, _render_suggestion_lines


if typing.TYPE_CHECKING:
    from modern_di.providers.abstract import AbstractProvider


class RegistrationError(ModernDIError):
    """Base class for errors raised while registering providers."""

    __slots__ = ()


class DuplicateProviderTypeError(RegistrationError):
    """Two providers were registered for the same ``.provider_type``."""

    docs_slug = "duplicate-type-error"

    __slots__ = ("provider_type",)

    def __init__(self, *, provider_type: type) -> None:
        self.provider_type = provider_type
        super().__init__(
            f"Provider is duplicated by type {provider_type}. "
            "To resolve this issue:\n"
            "1. Set bound_type=None on one of the providers to make it unresolvable by type\n"
            "2. Explicitly pass dependencies via the kwargs parameter to avoid automatic resolution"
        )


class ChildContainerRegistrationError(RegistrationError):
    """``add_providers`` was called on a child container; registration is root-only. Inspect ``.scope``."""

    docs_slug = "child-container-registration-error"

    __slots__ = ("scope",)

    def __init__(self, *, scope: enum.IntEnum) -> None:
        self.scope = scope
        super().__init__(
            f"Container.add_providers can only be called on a root container: the providers "
            f"registry is shared tree-wide, so registering on a child container (scope {scope.name}) "
            "would mutate every container in the tree. Call add_providers on the root container instead."
        )


class ProviderScopeFrozenError(RegistrationError):
    """A group tried to change the scope of a provider that is already registered.

    Inspect ``.provider_name``, ``.group_name``, ``.current_scope``, ``.new_scope``.
    """

    docs_slug = "provider-scope-frozen-error"

    __slots__ = ("current_scope", "group_name", "new_scope", "provider_name")

    def __init__(
        self,
        *,
        provider_name: str,
        group_name: str,
        current_scope: enum.IntEnum,
        new_scope: enum.IntEnum,
    ) -> None:
        self.provider_name = provider_name
        self.group_name = group_name
        self.current_scope = current_scope
        self.new_scope = new_scope
        super().__init__(
            f"Group {group_name} would change the scope of provider {provider_name} from "
            f"{current_scope.name} to {new_scope.name}, but it is already registered with a "
            f"container. Resolvers compiled before this point captured {current_scope.name}, so the "
            f"change would apply inconsistently. Declare {group_name} before building the container, "
            f"or set scope= explicitly on the provider."
        )


class GroupScopeConflictError(RegistrationError):
    """A scope-defaulted provider is shared by two groups with different default scopes.

    Inspect ``.provider_name``, ``.first_group``/``.first_scope``, ``.second_group``/``.second_scope``.
    """

    docs_slug = "group-scope-conflict-error"

    __slots__ = ("first_group", "first_scope", "provider_name", "second_group", "second_scope")

    def __init__(
        self,
        *,
        provider_name: str,
        first_group: str,
        first_scope: enum.IntEnum,
        second_group: str,
        second_scope: enum.IntEnum,
    ) -> None:
        self.provider_name = provider_name
        self.first_group = first_group
        self.first_scope = first_scope
        self.second_group = second_group
        self.second_scope = second_scope
        super().__init__(
            f"Provider {provider_name} is shared by groups with conflicting default scopes: "
            f"{first_group} (scope {first_scope.name}) and {second_group} (scope {second_scope.name}). "
            f"Set scope= explicitly on the provider, or align the group defaults."
        )


class UnknownFactoryKwargError(RegistrationError):
    """Factory kwargs had unknown keys. Attrs: ``creator``, ``unknown_keys``, ``known_keys``, ``suggestions``."""

    docs_slug = "unknown-factory-kwarg-error"

    __slots__ = ("creator", "known_keys", "suggestions", "unknown_keys")

    def __init__(
        self,
        *,
        creator: "typing.Callable[..., typing.Any]",
        unknown_keys: list[str],
        known_keys: list[str],
    ) -> None:
        self.creator = creator
        self.unknown_keys = unknown_keys
        self.known_keys = known_keys
        # Derived, not handed over: matching the unknown keys against the known ones needs
        # nothing the error was not already given. A kwarg has no provider, so no scope.
        self.suggestions = [
            suggester.Suggestion(
                name=repr(key),
                reason=f"did you mean {matches[0]!r}?"
                if (matches := suggester.close_matches(key, known_keys, n=1))
                else None,
            )
            for key in unknown_keys
        ]
        creator_name = getattr(creator, "__name__", repr(creator))
        parts = [
            f"Factory kwargs contain unknown key(s) not in {creator_name} signature:",
            *_render_suggestion_lines(self.suggestions),
            f"Known parameters: {known_keys}",
        ]
        super().__init__("\n".join(parts))


class UnsupportedCreatorParameterError(RegistrationError):
    """A creator parameter cannot be wired by type. Inspect ``.creator``, ``.parameter_name``, ``.reason``."""

    docs_slug = "unsupported-creator-parameter-error"

    __slots__ = ("creator", "parameter_name", "reason")

    def __init__(self, *, creator: "typing.Callable[..., typing.Any]", parameter_name: str, reason: str) -> None:
        self.creator = creator
        self.parameter_name = parameter_name
        self.reason = reason
        creator_name = getattr(creator, "__name__", repr(creator))
        super().__init__(f"Parameter {parameter_name!r} of {creator_name} cannot be injected: {reason}")


class InvalidScopeDependencyError(RegistrationError):
    """A provider depends on a deeper-scoped one. Inspect ``.provider``, ``.parameter_name``, ``.dep_chain``.

    ``dep_chain`` runs from the declared dependency to the provider that actually supplies it,
    following redirects; ``.dep_provider`` and ``.dep_terminal`` are its ends. The two differ only
    when the dependency is reached through an ``Alias``, which is also the case where the declared
    type alone cannot tell a reader which provider owns the offending scope.
    """

    docs_slug = "scope-chain"

    __slots__ = ("dep_chain", "parameter_name", "provider")

    def __init__(
        self,
        *,
        provider: "AbstractProvider[typing.Any]",
        parameter_name: str,
        dep_chain: "list[AbstractProvider[typing.Any]]",
    ) -> None:
        self.provider = provider
        self.parameter_name = parameter_name
        self.dep_chain = dep_chain
        super().__init__(
            f"{provider.display_name} (scope {provider.scope.name}) declares parameter "
            f"{parameter_name!r} typed as a provider of {self.dep_terminal.display_name} at deeper "
            f"scope {self.dep_terminal.scope.name}. A provider cannot depend on a deeper-scoped provider."
        )

    @property
    def dep_provider(self) -> "AbstractProvider[typing.Any]":
        """The dependency as declared: the type the parameter is annotated with."""
        return self.dep_chain[0]

    @property
    def dep_terminal(self) -> "AbstractProvider[typing.Any]":
        """The provider that actually supplies the dependency, once redirects are followed."""
        return self.dep_chain[-1]

    def _render_body(self) -> str:
        terminal_scope = self.dep_terminal.scope
        steps = [
            ResolutionStep(
                scope=self.provider.scope, name=self.provider.display_name, location=self.provider.definition_site
            ),
            # Every hop before the terminal is a redirect, so its own `scope` is a default it never
            # declared; the scope it resolves at is the terminal's.
            *(
                ResolutionStep(scope=terminal_scope, name=p.display_name, location=p.definition_site)
                for p in self.dep_chain
            ),
        ]
        lines = [
            "Provider at a deeper scope reached through this chain:",
            *_render_chain(steps),
            f"  caused by: {RuntimeError.__str__(self)}",
        ]
        return "\n".join(lines)
