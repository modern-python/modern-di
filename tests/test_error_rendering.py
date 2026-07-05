from modern_di import exceptions


def test_circular_dependency_error_renders_cycle_as_arrow_chain() -> None:
    error = exceptions.CircularDependencyError(cycle_path=["A", "B", "A"])
    assert error.cycle_path == ["A", "B", "A"]
    assert str(error) == (
        "Circular dependency detected:\n  A\n  └─> B\n      └─> A\nCheck your provider graph for unintended cycles."
    )


def test_validation_failed_error_groups_by_kind_and_indents_multiline() -> None:
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
        "  - boom"
    )


def test_validation_failed_error_renders_message_less_sub_error() -> None:
    error = exceptions.ValidationFailedError(errors=[RuntimeError()])
    assert str(error) == ("Container.validate() found 1 issue(s): RuntimeError\n\nRuntimeError (1):\n  -")
