import subprocess
import sys


def test_modern_di_imports_without_typing_extensions() -> None:
    """modern-di advertises zero runtime dependencies; `typing_extensions` must be type-checking only.

    Runs in a fresh subprocess with `typing_extensions` import blocked, to catch any
    unconditional runtime `import typing_extensions` (see container.py / group.py).
    """
    code = (
        "import sys\n"
        "sys.modules['typing_extensions'] = None\n"  # makes `import typing_extensions` raise ImportError
        "import modern_di\n"
        "from modern_di import Container, Scope\n"
        "container = Container(scope=Scope.APP)\n"
        "child = container.build_child_container(scope=Scope.REQUEST)\n"
        "print('OK', child.scope.name)\n"
    )
    result = subprocess.run(  # noqa: S603 — fixed literal command, no untrusted input
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "OK REQUEST" in result.stdout
