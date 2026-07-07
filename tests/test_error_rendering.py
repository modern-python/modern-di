from modern_di import exceptions


def test_error_without_docs_slug_renders_body_unchanged() -> None:
    # Base classes (ModernDIError itself, ContainerError, ResolutionError, RegistrationError)
    # keep docs_slug unset and are never raised directly, so __str__ must not append a trailer.
    error = exceptions.ModernDIError("boom")
    assert error.docs_slug is None
    assert str(error) == "boom"


def test_circular_dependency_error_renders_cycle_as_arrow_chain() -> None:
    error = exceptions.CircularDependencyError(cycle_path=["A", "B", "A"])
    assert error.cycle_path == ["A", "B", "A"]
    assert str(error) == (
        "Circular dependency detected:\n  A\n  └─> B\n      └─> A\nCheck your provider graph for unintended cycles.\n"
        "See: https://modern-di.modern-python.org/troubleshooting/circular-dependency/"
    )


def test_validation_failed_error_groups_by_kind_and_indents_multiline() -> None:
    # Sub-errors (here CircularDependencyError, which carries its own docs_slug) render
    # trailer-free inside the grouped report — only the outer ValidationFailedError report
    # carries a trailer, and it is the report's own final line. Repeating each sub-error's
    # "See: ..." line would be noise (same URL N times for N errors of one kind) and would
    # break "one trailer, always last line."
    cycle = exceptions.CircularDependencyError(cycle_path=["A", "B", "A"])
    boom = RuntimeError("boom")
    error = exceptions.ValidationFailedError(errors=[boom, cycle])
    assert error.errors == [boom, cycle]  # list content preserved, order as given
    assert str(error) == (
        "Container.validate() found 2 issue(s): CircularDependencyError, RuntimeError\n"
        "\n"
        "CircularDependencyError (1):\n"
        "  - Circular dependency detected:\n"
        "      A\n"
        "      └─> B\n"
        "          └─> A\n"
        "    Check your provider graph for unintended cycles.\n"
        "\n"
        "RuntimeError (1):\n"
        "  - boom\n"
        "See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/"
    )


def test_validation_failed_error_renders_message_less_sub_error() -> None:
    error = exceptions.ValidationFailedError(errors=[RuntimeError()])
    assert str(error) == (
        "Container.validate() found 1 issue(s): RuntimeError\n\nRuntimeError (1):\n  -\n"
        "See: https://modern-di.modern-python.org/troubleshooting/validation-failed-error/"
    )


def test_duplicate_provider_type_error_url_unchanged_by_mechanism() -> None:
    # DuplicateProviderTypeError used to hand-roll its own inline URL; the docs_slug mechanism
    # now generates the trailer instead. The remediation steps stay put, and the URL the user
    # lands on is unchanged even though the surrounding sentence isn't verbatim-identical.
    error = exceptions.DuplicateProviderTypeError(provider_type=str)
    rendered = str(error)
    assert "https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/" in rendered
    assert rendered.endswith("See: https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/")
    assert rendered.count("https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/") == 1


def test_context_value_not_set_error_message_and_hierarchy() -> None:
    error = exceptions.ContextValueNotSetError(context_type=str, scope_name="APP")
    assert isinstance(error, exceptions.ResolutionError)
    assert str(error) == (
        "No context value is set for <class 'str'> (scope APP). "
        "Pass context={...} to the container or call set_context().\n"
        "See: https://modern-di.modern-python.org/troubleshooting/context-not-set/"
    )
