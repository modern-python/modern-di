CONTAINER_SCOPE_IS_LOWER_ERROR = (
    "Scope of child container cannot be {child_scope} if parent scope is {parent_scope} "
    "(child scope value must be strictly greater than parent scope value). "
    "Possible scopes are {allowed_scopes}."
)
CONTAINER_MAX_SCOPE_REACHED_ERROR = (
    "Max scope of {parent_scope} is reached. "
    "To go deeper, build a child container with a custom IntEnum scope whose value is higher."
)
CONTAINER_NOT_INITIALIZED_SCOPE_ERROR = (
    "Provider of scope {provider_scope} cannot be resolved in container of scope {container_scope}."
)
CONTAINER_SCOPE_IS_SKIPPED_ERROR = (
    "No {provider_scope}-scope container exists in this chain; "
    "this chain starts at {container_scope}. "
    "Build a {provider_scope}-scope container as the root."
)
CONTAINER_MISSING_PROVIDER_ERROR = "Provider of type {provider_type} is not registered in providers registry."
SUGGESTION_HEADER = "Did you mean:"
SUGGESTION_SUBCLASS = "  - {type_name} (registered subclass, scope={scope})"
SUGGESTION_BASECLASS = "  - {type_name} (registered base class, scope={scope})"
SUGGESTION_SIMILAR = "  - {type_name} (similar name, scope={scope})"
FACTORY_ARGUMENT_RESOLUTION_ERROR = (
    "Argument {arg_name} of type {arg_type} cannot be resolved. Trying to build dependency {bound_type}."
)
FACTORY_ARGUMENT_UNANNOTATED_ERROR = (
    "Argument {arg_name} has no usable type annotation, so it cannot be resolved by type. "
    "Pass it via the kwargs parameter or add a type annotation. Trying to build dependency {bound_type}."
)
CYCLE_DEPENDENCY_ERROR = "Circular dependency detected: {cycle_path}. Check your provider graph for unintended cycles."
PROVIDER_DUPLICATE_TYPE_ERROR = (
    "Provider is duplicated by type {provider_type}. "
    "To resolve this issue:\n"
    "1. Set bound_type=None on one of the providers to make it unresolvable by type\n"
    "2. Explicitly pass dependencies via the kwargs parameter to avoid automatic resolution\n"
    "See https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/ for more details"
)
ALIAS_SOURCE_NOT_REGISTERED_ERROR = (
    "Alias source type {source_type} is not registered in providers registry. "
    "Register a provider for {source_type} before defining the alias."
)
INVALID_SCOPE_DEPENDENCY_ERROR = (
    "Provider {provider_name} (scope {provider_scope}) declares parameter "
    "{parameter_name!r} typed as a provider of {dep_name} at deeper scope "
    "{dep_scope}. A provider cannot depend on a deeper-scoped provider."
)
INVALID_SCOPE_TYPE_ERROR = "Container scope must be an enum.IntEnum member; got {scope_repr} ({scope_type})."
FACTORY_UNSUPPORTED_PARAMETER_ERROR = (
    "Parameter {parameter_name!r} of {creator_name} cannot be injected: {reason}. "
    "Pass the value via the kwargs parameter, give the parameter a default, "
    "or use skip_creator_parsing=True with an explicit bound_type."
)
