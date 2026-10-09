import ast
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import zipfile

import modern_di


_PKG_ROOT = pathlib.Path(modern_di.__file__).parent
_REPO_ROOT = _PKG_ROOT.parent


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
    unconditional runtime `import typing_extensions`.
    """
    code = (
        "import sys\n"
        "sys.modules['typing_extensions'] = None\n"  # makes `import typing_extensions` raise ImportError
        "import modern_di\n"
        "from modern_di import Container, Scope\n"
        "container = Container(scope=Scope.APP)\n"
        "container.open()\n"
        "child = container.build_child_container(scope=Scope.REQUEST)\n"
        "print('OK', child.scope.name)\n"
    )
    result = subprocess.run(  # noqa: S603 — fixed literal command, no untrusted input
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "OK REQUEST" in result.stdout


def test_package_init_imports_every_name_it_exports() -> None:
    """Every name in `modern_di.__all__` is bound by an import in `__init__` itself."""
    tree = ast.parse((_PKG_ROOT / "__init__.py").read_text(encoding="utf-8"))
    imported = {
        alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom) for alias in node.names
    }
    assert set(modern_di.__all__) <= imported


def test_package_exports_the_types_in_public_signatures() -> None:
    """The return and element types of public calls are importable from the package root."""
    assert modern_di.__all__ == [
        "UNSET",
        "Container",
        "Group",
        "OverrideHandle",
        "Scope",
        "Suggestion",
        "UnsetType",
        "exceptions",
        "integrations",
        "providers",
    ]
    assert isinstance(
        modern_di.Container().override(modern_di.providers.container_provider, None), modern_di.OverrideHandle
    )
    assert type(modern_di.UNSET) is modern_di.UnsetType


def test_built_distributions_ship_the_license_and_the_wheel_imports(tmp_path: pathlib.Path) -> None:
    """The wheel and sdist that `just publish` uploads carry the MIT notice, and the wheel imports."""
    uv = shutil.which("uv")
    assert uv is not None
    subprocess.run(  # noqa: S603 - uv from shutil.which, fixed arguments
        [uv, "build", "--quiet", "--out-dir", str(tmp_path), str(_REPO_ROOT)], check=True
    )
    (wheel,) = tmp_path.glob("*.whl")
    (sdist,) = tmp_path.glob("*.tar.gz")
    with zipfile.ZipFile(wheel) as wheel_zip:
        wheel_names = wheel_zip.namelist()
    with tarfile.open(sdist) as sdist_tar:
        sdist_names = sdist_tar.getnames()
    assert any(name.endswith(".dist-info/licenses/LICENSE") for name in wheel_names), wheel_names
    assert any(name.endswith("/LICENSE") for name in sdist_names), sdist_names
    imported = subprocess.run(
        [sys.executable, "-c", "import modern_di; print(modern_di.__file__)"],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(wheel)},
    )
    assert imported.stdout.startswith(str(wheel)), imported.stdout
