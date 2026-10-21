"""Smoke tests for the repository scaffold."""

from sahayak import __version__


def test_package_exposes_a_version() -> None:
    """Expose a package version so distributions are traceable."""
    assert __version__ == "0.0.0"
