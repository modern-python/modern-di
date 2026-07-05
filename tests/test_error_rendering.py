from modern_di import exceptions


def test_circular_dependency_error_renders_cycle_as_arrow_chain() -> None:
    error = exceptions.CircularDependencyError(cycle_path=["A", "B", "A"])
    assert error.cycle_path == ["A", "B", "A"]
    assert str(error) == (
        "Circular dependency detected:\n"
        "  A\n"
        "  └─> B\n"
        "      └─> A\n"
        "Check your provider graph for unintended cycles."
    )
