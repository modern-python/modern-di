CONTAINER_SCOPE_IS_LOWER_ERROR = (
    "Scope of child container cannot be {child_scope} if parent scope is {parent_scope}. "
    "Possible scopes are {allowed_scopes}."
)
CONTAINER_MAX_SCOPE_REACHED_ERROR = "Max scope of {parent_scope} is reached."
CONTAINER_NOT_INITIALIZED_SCOPE_ERROR = (
    "Provider of scope {provider_scope} cannot be resolved in container of scope {container_scope}."
)
CONTAINER_SCOPE_IS_SKIPPED_ERROR = "Provider of scope {provider_scope} is skipped in the chain of containers."
CONTAINER_MISSING_PROVIDER_ERROR = "Provider of type {provider_type} is not registered in providers registry."
SUGGESTION_HEADER = "Did you mean:"
SUGGESTION_SUBCLASS = "  - {type_name} (registered subclass, scope={scope})"
SUGGESTION_BASECLASS = "  - {type_name} (registered base class, scope={scope})"
SUGGESTION_SIMILAR = "  - {type_name} (similar name, scope={scope})"
FACTORY_ARGUMENT_RESOLUTION_ERROR = (
    "Argument {arg_name} of type {arg_type} cannot be resolved. Trying to build dependency {bound_type}."
)
CYCLE_DEPENDENCY_ERROR = "Circular dependency detected: {cycle_path}. Check your provider graph for unintended cycles."
PROVIDER_DUPLICATE_TYPE_ERROR = (
    "Provider is duplicated by type {provider_type}. "
    "To resolve this issue:\n"
    "1. Set bound_type=None on one of the providers to make it unresolvable by type\n"
    "2. Explicitly pass dependencies via the kwargs parameter to avoid automatic resolution\n"
    "See https://modern-di.readthedocs.io/latest/troubleshooting/duplicate-type-error/ for more details"
)
ALIAS_SOURCE_NOT_REGISTERED_ERROR = (
    "Alias source type {source_type} is not registered in providers registry. "
    "Register a provider for {source_type} before defining the alias."
)
