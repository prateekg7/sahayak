"""Unit tests verifying certification readiness checklist and legal policy documents (T4.9)."""

from __future__ import annotations

from pathlib import Path


def test_certification_checklist_coverage() -> None:
    """Verify certification.md exists and covers all required compliance sections."""
    root = Path(__file__).resolve().parents[2]
    cert_file = root / "docs" / "alexa" / "certification.md"
    assert cert_file.exists(), "docs/alexa/certification.md must exist"

    content = cert_file.read_text(encoding="utf-8")
    assert "Metadata & Listing Quality" in content
    assert "Policy & Compliance" in content
    assert "Voice UX & Dialogue Standards" in content
    assert "Security & Account Linking" in content
    assert "amzn1.alexa-addon.sahayak-study-v1" in content


def test_legal_documents_exist() -> None:
    """Verify privacy policy and terms of service documents are present and complete."""
    root = Path(__file__).resolve().parents[2]
    privacy = root / "docs" / "legal" / "privacy-policy.md"
    terms = root / "docs" / "legal" / "terms.md"

    assert privacy.exists(), "privacy-policy.md must exist"
    assert terms.exists(), "terms.md must exist"

    privacy_text = privacy.read_text(encoding="utf-8")
    assert "Right to be Forgotten" in privacy_text or "deletion" in privacy_text.lower()
    assert "support@sahayak.app" in privacy_text

    terms_text = terms.read_text(encoding="utf-8")
    assert "Terms of Service" in terms_text
    assert "support@sahayak.app" in terms_text
