"""Unit tests for topic normalization and slugification (T3.2)."""

from __future__ import annotations

import pytest

from sahayak.modules.academics.domain.topics import (
    MAX_INPUT_LENGTH,
    normalize_topic,
    slugify,
)


def test_photosynthesis_normalization_variants() -> None:
    """Spoken variants of Photosynthesis must resolve to identical canonical key."""
    variants = [
        "Photosynthesis",
        "photosynthesis!",
        "  PHOTOSYNTHESIS ",
        "Photosynthesis...",
        "photosynthesis",
        "  photosynthesis\n",
    ]
    for variant in variants:
        key, display = normalize_topic(variant)
        assert key == "photosynthesis"
        assert display == "Photosynthesis"


def test_alias_table_mappings() -> None:
    """Common spoken shorthand and acronyms must map to curated canonical topics."""
    assert normalize_topic("ap bio") == ("ap-biology", "AP Biology")
    assert normalize_topic("AP Biology") == ("ap-biology", "AP Biology")
    assert normalize_topic("us history") == ("united-states-history", "United States History")
    assert normalize_topic("U.S. History") == ("united-states-history", "United States History")
    assert normalize_topic("american history") == ("united-states-history", "United States History")
    assert normalize_topic("calc 1") == ("calculus-1", "Calculus I")
    assert normalize_topic("calculus i") == ("calculus-1", "Calculus I")
    assert normalize_topic("ww2") == ("world-war-2", "World War II")
    assert normalize_topic("world war ii") == ("world-war-2", "World War II")
    assert normalize_topic("linear algebra") == ("linear-algebra", "Linear Algebra")


def test_complex_and_multi_word_topics() -> None:
    """Arbitrary subjects must produce clean hyphens and proper title-casing."""
    key, display = normalize_topic("introduction to quantum mechanics")
    assert key == "introduction-to-quantum-mechanics"
    assert display == "Introduction to Quantum Mechanics"

    key, display = normalize_topic("DNA replication and repair")
    assert key == "dna-replication-and-repair"
    assert display == "DNA Replication and Repair"


def test_slugify_helper() -> None:
    """slugify function produces clean kebab-case slugs."""
    assert slugify("Machine Learning 101!") == "machine-learning-101"
    assert slugify("---Multiple---Hyphens---") == "multiple-hyphens"
    assert slugify("Special & Characters @ Test #") == "special-characters-test"


def test_validation_errors_on_invalid_input() -> None:
    """Invalid input must raise ValueError with descriptive explanation."""
    with pytest.raises(ValueError, match="empty"):
        normalize_topic("")

    with pytest.raises(ValueError, match="empty"):
        normalize_topic("   \n\t  ")

    with pytest.raises(ValueError, match="no valid alphanumeric"):
        normalize_topic("!@#$%^&*()_+=-")

    too_long = "a" * (MAX_INPUT_LENGTH + 1)
    with pytest.raises(ValueError, match="maximum allowed length"):
        normalize_topic(too_long)
