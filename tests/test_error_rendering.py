import pytest

from modern_di import Scope, exceptions, suggester


def _step(name: str, scope: Scope = Scope.APP, location: str | None = None) -> exceptions.ResolutionStep:
    return exceptions.ResolutionStep(scope=scope, name=name, location=location)


def test_error_without_docs_slug_renders_body_unchanged() -> None:
    # Base classes (ModernDIError itself, ContainerError, ResolutionError, RegistrationError)
    # keep docs_slug unset and are never raised directly, so __str__ must not append a trailer.
    error = exceptions.ModernDIError("boom")
    assert error.docs_slug is None
    assert str(error) == "boom"


def test_render_chain_is_a_pure_function_of_its_steps() -> None:
    # The drawer is exercisable without a container, a cycle, or a raise — it is the
    # single home of the indent-and-arrow glyphs, shared by every chain-shaped error.
    assert exceptions._render_chain([_step("A"), _step("B", location="app:31"), _step("A")]) == [  # noqa: SLF001
        "  APP  A",
        "  APP  └─> B (app:31)",
        "  APP      └─> A",
    ]


def test_render_chain_aligns_the_scope_column_to_the_widest_name() -> None:
    lines = exceptions._render_chain([_step("A"), _step("B", scope=Scope.REQUEST)])  # noqa: SLF001
    assert lines == ["  APP      A", "  REQUEST  └─> B"]


@pytest.mark.parametrize(
    ("suggestion", "expected"),
    [
        (
            suggester.Suggestion(name="PostgresDatabase", reason="registered subclass", scope=Scope.APP),
            "  - PostgresDatabase (registered subclass, scope=APP)",
        ),
        (
            suggester.Suggestion(name="Repository", reason="similar name", scope=Scope.REQUEST),
            "  - Repository (similar name, scope=REQUEST)",
        ),
        # A kwarg suggestion carries no scope: a parameter name has no provider behind it.
        (suggester.Suggestion(name="'kwargs'", reason="did you mean 'kwarg'?"), "  - 'kwargs' (did you mean 'kwarg'?)"),
        # ...and an unknown kwarg with no near match has nothing to say beyond its own name.
        (suggester.Suggestion(name="'zzz'"), "  - 'zzz'"),
    ],
)
def test_render_suggestion_lines_covers_every_format(suggestion: suggester.Suggestion, expected: str) -> None:
    # One bullet format for all three suggestion kinds — the registry no longer owns half of it.
    assert exceptions._render_suggestion_lines([suggestion]) == [expected]  # noqa: SLF001


def test_render_suggestions_prepends_the_header_and_is_empty_when_there_is_nothing_to_say() -> None:
    assert exceptions._render_suggestions([]) == ""  # noqa: SLF001
    assert (
        exceptions._render_suggestions(  # noqa: SLF001
            [suggester.Suggestion(name="Repository", reason="similar name", scope=Scope.APP)]
        )
        == "Did you mean:\n  - Repository (similar name, scope=APP)"
    )


def test_circular_dependency_error_renders_cycle_as_arrow_chain() -> None:
    error = exceptions.CircularDependencyError(steps=[_step("A"), _step("B"), _step("A")])
    # cycle_path / cycle_locations survive as views derived from the one list of steps,
    # so the two-parallel-lists invariant (equal length) is structural, not enforced at render.
    assert error.cycle_path == ["A", "B", "A"]
    assert error.cycle_locations == [None, None, None]
    assert str(error) == (
        "Circular dependency detected:\n"
        "  APP  A\n"
        "  APP  └─> B\n"
        "  APP      └─> A\n"
        "Check your provider graph for unintended cycles.\n"
        "See: https://modern-di.modern-python.org/troubleshooting/circular-dependency/"
    )


def test_validation_failed_error_groups_by_kind_and_indents_multiline() -> None:
    # Sub-errors (here CircularDependencyError, which carries its own docs_slug) render
    # trailer-free inside the grouped report — only the outer ValidationFailedError report
    # carries a trailer, and it is the report's own final line. Repeating each sub-error's
    # "See: ..." line would be noise (same URL N times for N errors of one kind) and would
    # break "one trailer, always last line."
    cycle = exceptions.CircularDependencyError(steps=[_step("A"), _step("B"), _step("A")])
    boom = RuntimeError("boom")
    error = exceptions.ValidationFailedError(errors=[boom, cycle])
    assert error.errors == [boom, cycle]  # list content preserved, order as given
    assert str(error) == (
        "Container.validate() found 2 issue(s): CircularDependencyError, RuntimeError\n"
        "\n"
        "CircularDependencyError (1):\n"
        "  - Circular dependency detected:\n"
        "      APP  A\n"
        "      APP  └─> B\n"
        "      APP      └─> A\n"
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


def test_invalid_child_scope_error_derives_the_allowed_scopes() -> None:
    # allowed_scopes is a pure function of parent_scope, so the error derives it rather than
    # being handed it — the same comprehension used to be written out at two raise sites.
    error = exceptions.InvalidChildScopeError(parent_scope=Scope.REQUEST, child_scope=Scope.APP)
    assert error.allowed_scopes == ["ACTION", "STEP"]
    assert "Possible scopes are ['ACTION', 'STEP']." in str(error)


def test_unknown_factory_kwarg_error_derives_its_own_suggestions() -> None:
    # The error already receives unknown_keys and known_keys; it can run the match itself
    # instead of the raise site pre-computing a did-you-mean map for it.
    def creator(timeout: int, retries: int) -> int:
        return timeout + retries

    assert creator(1, retries=2) == creator(2, retries=1)  # exercise the body; only __name__ is read below

    error = exceptions.UnknownFactoryKwargError(
        creator=creator, unknown_keys=["timout", "zzz"], known_keys=["retries", "timeout"]
    )
    assert error.suggestions == [
        suggester.Suggestion(name="'timout'", reason="did you mean 'timeout'?"),
        suggester.Suggestion(name="'zzz'"),
    ]
    assert str(error) == (
        "Factory kwargs contain unknown key(s) not in creator signature:\n"
        "  - 'timout' (did you mean 'timeout'?)\n"
        "  - 'zzz'\n"
        "Known parameters: ['retries', 'timeout']\n"
        "See: https://modern-di.modern-python.org/troubleshooting/unknown-factory-kwarg-error/"
    )


def test_context_value_not_set_error_message_and_hierarchy() -> None:
    error = exceptions.ContextValueNotSetError(context_type=str, scope_name="APP")
    assert isinstance(error, exceptions.ResolutionError)
    assert str(error) == (
        "No context value is set for <class 'str'> (scope APP). "
        "Pass context={...} to the container or call set_context().\n"
        "See: https://modern-di.modern-python.org/troubleshooting/context-not-set/"
    )
