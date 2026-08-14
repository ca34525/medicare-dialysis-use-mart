"""Smoke tests for the locked local development toolchain."""

import sys
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

import pytest

import kidney_care_mart

EXPECTED_LOCKED_DISTRIBUTION_VERSIONS = {
    "dbt-core": "1.11.13",
    "dbt-duckdb": "1.11.0",
    "duckdb": "1.5.5",
    "setuptools": "84.0.0",
}

RUNTIME_MODULES = (
    "dbt.adapters.duckdb",
    "dbt.cli.main",
    "duckdb",
)


def test_package_import() -> None:
    """The project package is importable through the configured src layout."""
    assert kidney_care_mart.__name__ == "kidney_care_mart"


def test_python_version() -> None:
    """The interpreter matches the supported Python minor version."""
    assert sys.version_info[:2] == (3, 12), (
        f"Expected Python 3.12, found {sys.version_info.major}.{sys.version_info.minor}"
    )


@pytest.mark.parametrize("module_name", RUNTIME_MODULES)
def test_runtime_dependency_import(module_name: str) -> None:
    """The approved runtime libraries import successfully on this platform."""
    assert import_module(module_name) is not None


@pytest.mark.parametrize(
    ("distribution_name", "expected_version"),
    EXPECTED_LOCKED_DISTRIBUTION_VERSIONS.items(),
)
def test_locked_dependency_version(
    distribution_name: str,
    expected_version: str,
) -> None:
    """Installed distributions match the approved compatibility baseline."""
    try:
        installed_version = version(distribution_name)
    except PackageNotFoundError:
        pytest.fail(f"Required distribution is not installed: {distribution_name}")

    assert installed_version == expected_version, (
        f"Expected {distribution_name}=={expected_version}, found {installed_version}"
    )
