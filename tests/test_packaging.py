import ast
import pathlib
import subprocess
import sys

import modern_di


_PKG_ROOT = pathlib.Path(modern_di.__file__).parent


def _providers_chain_files() -> list[pathlib.Path]:
    """Modules that load while `modern_di.providers/__init__` is still executing."""
    return [*sorted((_PKG_ROOT / "providers").glob("*.py")), _PKG_ROOT / "wiring.py"]


def test_provider_layer_imports_concrete_modules_not_the_package() -> None:
    """Providers-chain modules must import siblings by concrete submodule, not the package.

    Modules that load while `modern_di/providers/__init__` is still executing (providers/*.py
    and wiring.py) must not `from modern_di.providers import ...`: that back-references a
    half-initialized `__init__` and only works because of the statement order there. Pinning
    concrete-module imports keeps that order from being load-bearing. External consumers
    (e.g. `registries/`) may still use the package API — they load after it is initialized.
    """
    offenders = [
        f"{path.name}:{node.lineno}"
        for path in _providers_chain_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "modern_di.providers"
    ]
    assert not offenders, f"import from the providers package __init__ (use a concrete submodule): {offenders}"


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
