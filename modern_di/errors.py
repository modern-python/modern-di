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
FACTORY_ARGUMENT_RESOLUTION_ERROR = (
    "Argument {arg_name} of type {arg_type} cannot be resolved. Trying to build dependency {bound_type}."
)
PROVIDER_DUPLICATE_TYPE_ERROR = "Provider is duplicated by type {provider_type}"
