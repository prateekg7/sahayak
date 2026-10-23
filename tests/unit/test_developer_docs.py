"""Unit tests verifying developer documentation and contribution guides (T4.10)."""

from __future__ import annotations

from pathlib import Path


def test_readme_completeness() -> None:
    """Verify README.md contains quickstart, architecture, and commands."""
    root = Path(__file__).resolve().parents[2]
    readme = root / "README.md"
    assert readme.exists(), "README.md must exist"

    content = readme.read_text(encoding="utf-8")
    assert "Quick Start" in content
    assert "make dev" in content
    assert "make test" in content
    assert "make lint" in content
    assert "make snapshot-check" in content
    assert "Architecture Highlights" in content


def test_contributing_guide_completeness() -> None:
    """Verify CONTRIBUTING.md contains non-negotiables and review checklist."""
    root = Path(__file__).resolve().parents[2]
    contrib = root / "CONTRIBUTING.md"
    assert contrib.exists(), "CONTRIBUTING.md must exist"

    content = contrib.read_text(encoding="utf-8")
    assert "Non-Negotiable Rules" in content
    assert "Never Commit Secrets" in content
    assert "Never Import Across Module Boundaries" in content
    assert "No Floating-Point Money" in content
    assert "Pull Request & Review Checklist" in content


def test_developer_guides_and_architecture() -> None:
    """Verify dev-guide.md, module-authoring.md, architecture.md, and ADR index exist."""
    root = Path(__file__).resolve().parents[2]
    docs = root / "docs"

    dev_guide = docs / "dev-guide.md"
    mod_guide = docs / "module-authoring.md"
    arch = docs / "architecture.md"
    adr_idx = docs / "adr" / "index.md"

    for file_path in [dev_guide, mod_guide, arch, adr_idx]:
        assert file_path.exists(), f"Document {file_path.name} must exist"
        assert len(file_path.read_text(encoding="utf-8")) > 200

    dev_text = dev_guide.read_text(encoding="utf-8")
    assert "Alembic" in dev_text
    assert "Snapshot" in dev_text

    mod_text = mod_guide.read_text(encoding="utf-8")
    assert "_template" in mod_text
    assert "export_user_data" in mod_text

    arch_text = arch.read_text(encoding="utf-8")
    assert "mermaid" in arch_text
    assert "Layering & Dependency Rules" in arch_text
