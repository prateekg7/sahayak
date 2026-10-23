"""Pure domain functions for spoken multiple-choice answer matching."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from rapidfuzz import fuzz

FUZZY_CONFIDENCE_THRESHOLD = 75.0
AMBIGUITY_SCORE_DELTA = 15.0

# Mapping of spoken position/ordinals to 0-based option index
ORDINAL_INDEX_MAP: dict[str, int] = {
    "first": 0,
    "1st": 0,
    "the first": 0,
    "the first one": 0,
    "first one": 0,
    "first option": 0,
    "first choice": 0,
    "second": 1,
    "2nd": 1,
    "the second": 1,
    "the second one": 1,
    "second one": 1,
    "second option": 1,
    "second choice": 1,
    "third": 2,
    "3rd": 2,
    "the third": 2,
    "the third one": 2,
    "third one": 2,
    "third option": 2,
    "third choice": 2,
    "fourth": 3,
    "4th": 3,
    "the fourth": 3,
    "the fourth one": 3,
    "fourth one": 3,
    "fourth option": 3,
    "fourth choice": 3,
}

# Mapping of numerals and word numerals to 0-based option index
NUMERAL_INDEX_MAP: dict[str, int] = {
    "1": 0,
    "one": 0,
    "won": 0,  # ASR homophone
    "number 1": 0,
    "number one": 0,
    "option 1": 0,
    "option one": 0,
    "choice 1": 0,
    "choice one": 0,
    "2": 1,
    "two": 1,
    "to": 1,  # ASR homophone
    "too": 1,  # ASR homophone
    "number 2": 1,
    "number two": 1,
    "option 2": 1,
    "option two": 1,
    "choice 2": 1,
    "choice two": 1,
    "3": 2,
    "three": 2,
    "number 3": 2,
    "number three": 2,
    "option 3": 2,
    "option three": 2,
    "choice 3": 2,
    "choice three": 2,
    "4": 3,
    "four": 3,
    "for": 3,  # ASR homophone
    "fore": 3,  # ASR homophone
    "number 4": 3,
    "number four": 3,
    "option 4": 3,
    "option four": 3,
    "choice 4": 3,
    "choice four": 3,
}

# ASR phonetic homophones for option keys
HOMOPHONE_KEY_MAP: dict[str, str] = {
    "ay": "A",
    "eh": "A",
    "be": "B",
    "bee": "B",
    "see": "C",
    "sea": "C",
    "dee": "D",
}


@dataclass(frozen=True)
class AnswerMatchResult:
    """Outcome of attempting to match a spoken utterance to a multiple-choice option."""

    matched_key: str | None
    is_ambiguous: bool
    confidence: float
    reason: str


def _clean_text(text: str) -> str:
    """Normalize text by lowercasing, stripping punctuation and extra whitespace."""
    lower = text.strip().lower()
    no_apostrophe = re.sub(r"['’]", "", lower)
    cleaned = re.sub(r"[^\w\s]", " ", no_apostrophe)
    return re.sub(r"\s+", " ", cleaned).strip()


def match_spoken_answer(
    spoken_answer: str,
    options: Mapping[str, str],
) -> AnswerMatchResult:
    """Resolve a spoken answer string against a mapping of option keys to text.

    Deterministic precedence order:
    1. Direct letter or explicit key phrasing ("A", "option B", "it's C")
    2. ASR phonetic homophones ("bee" -> "B", "see" -> "C")
    3. Ordinals ("first option" -> 1st key, "second" -> 2nd key)
    4. Numerals ("1", "number 2", "three")
    5. Exact text match against option content
    6. Substring text match against option content
    7. Fuzzy matching via RapidFuzz with ambiguity detection
    """
    if not spoken_answer or not spoken_answer.strip():
        return AnswerMatchResult(
            matched_key=None,
            is_ambiguous=False,
            confidence=0.0,
            reason="Spoken answer is empty.",
        )

    if not options:
        return AnswerMatchResult(
            matched_key=None,
            is_ambiguous=False,
            confidence=0.0,
            reason="Question contains no options.",
        )

    cleaned = _clean_text(spoken_answer)
    sorted_keys = sorted(options.keys())

    # 1. Check for multi-letter ambiguity (e.g. "A or B", "A and C")
    letter_tokens = re.findall(r"\b([a-d])\b", cleaned)
    if len(letter_tokens) > 1 and len(set(letter_tokens)) > 1:
        return AnswerMatchResult(
            matched_key=None,
            is_ambiguous=True,
            confidence=50.0,
            reason=f"Utterance mentions multiple option letters: {letter_tokens}.",
        )

    # 2. Direct letter match (single letter or explicit option phrase)
    explicit_pattern = r"^(?:option|choice|letter|answer|it is|its|is it)?\s*([a-d])\.?$"
    m = re.match(explicit_pattern, cleaned)
    if m:
        key = m.group(1).upper()
        if key in options:
            return AnswerMatchResult(
                matched_key=key,
                is_ambiguous=False,
                confidence=100.0,
                reason=f"Explicit option letter '{key}' matched.",
            )

    # 3. Trailing/leading option letter phrases, e.g. "my answer is B", "I think it is C"
    phrase_pattern = r"\b(?:option|choice|letter|answer)\s+([a-d])\b"
    m_phrase = re.search(phrase_pattern, cleaned)
    if m_phrase:
        key = m_phrase.group(1).upper()
        if key in options:
            return AnswerMatchResult(
                matched_key=key,
                is_ambiguous=False,
                confidence=95.0,
                reason=f"Option letter phrase '{key}' matched.",
            )

    # 4. ASR Phonetic homophones ("bee" -> "B", "see" -> "C", "dee" -> "D")
    homophone_pattern = (
        r"^(?:option|choice|letter|answer|it is|it's)?\s*(ay|eh|be|bee|see|sea|dee)$"
    )
    m_homophone = re.match(homophone_pattern, cleaned)
    if m_homophone:
        h_word = m_homophone.group(1)
        mapped_key = HOMOPHONE_KEY_MAP.get(h_word)
        if mapped_key and mapped_key in options:
            return AnswerMatchResult(
                matched_key=mapped_key,
                is_ambiguous=False,
                confidence=90.0,
                reason=f"ASR homophone '{h_word}' matched option '{mapped_key}'.",
            )

    # 5. Ordinal match ("first", "second", "third", "fourth")
    for ordinal_phrase, idx in ORDINAL_INDEX_MAP.items():
        if (cleaned == ordinal_phrase or cleaned.endswith(f" {ordinal_phrase}")) and idx < len(
            sorted_keys
        ):
            key = sorted_keys[idx]
            return AnswerMatchResult(
                matched_key=key,
                is_ambiguous=False,
                confidence=95.0,
                reason=f"Ordinal '{ordinal_phrase}' matched option index {idx} ('{key}').",
            )

    # 6. Numeral match ("1", "two", "number 3")
    for numeral_phrase, idx in NUMERAL_INDEX_MAP.items():
        if (cleaned == numeral_phrase or cleaned.endswith(f" {numeral_phrase}")) and idx < len(
            sorted_keys
        ):
            key = sorted_keys[idx]
            return AnswerMatchResult(
                matched_key=key,
                is_ambiguous=False,
                confidence=95.0,
                reason=f"Numeral '{numeral_phrase}' matched option index {idx} ('{key}').",
            )

    # 7. Exact text match against option content
    cleaned_options = {k: _clean_text(v) for k, v in options.items()}
    cleaned_nospace = cleaned.replace(" ", "")
    for key, text_val in cleaned_options.items():
        if cleaned == text_val or (
            cleaned_nospace and cleaned_nospace == text_val.replace(" ", "")
        ):
            return AnswerMatchResult(
                matched_key=key,
                is_ambiguous=False,
                confidence=100.0,
                reason=f"Exact match on text of option '{key}'.",
            )

    # 8. Substring / prefix match (if cleaned is a significant sub-phrase of one option)
    if len(cleaned) >= 4:
        substring_matches = [k for k, text_val in cleaned_options.items() if cleaned in text_val]
        if len(substring_matches) == 1:
            key = substring_matches[0]
            return AnswerMatchResult(
                matched_key=key,
                is_ambiguous=False,
                confidence=85.0,
                reason=f"Unambiguous substring match on option '{key}'.",
            )
        if len(substring_matches) > 1:
            return AnswerMatchResult(
                matched_key=None,
                is_ambiguous=True,
                confidence=60.0,
                reason=f"Ambiguous substring match on options {substring_matches}.",
            )

    # 9. Fuzzy matching with RapidFuzz
    scores: list[tuple[str, float]] = []
    for key, text_val in cleaned_options.items():
        token_ratio = float(fuzz.token_set_ratio(cleaned, text_val))
        nospace_ratio = float(fuzz.ratio(cleaned_nospace, text_val.replace(" ", "")))
        ratio = max(token_ratio, nospace_ratio)
        scores.append((key, ratio))

    # Sort descending by similarity score
    scores.sort(key=lambda x: x[1], reverse=True)
    top_key, top_score = scores[0]
    runner_up_key, runner_up_score = scores[1] if len(scores) > 1 else (None, 0.0)

    if top_score >= FUZZY_CONFIDENCE_THRESHOLD:
        # Check for ambiguity between top candidate and runner-up
        if runner_up_key and (top_score - runner_up_score) < AMBIGUITY_SCORE_DELTA:
            return AnswerMatchResult(
                matched_key=None,
                is_ambiguous=True,
                confidence=top_score,
                reason=(
                    f"Ambiguous match between '{top_key}' ({top_score:.1f}%) "
                    f"and '{runner_up_key}' ({runner_up_score:.1f}%)."
                ),
            )
        return AnswerMatchResult(
            matched_key=top_key,
            is_ambiguous=False,
            confidence=top_score,
            reason=f"Fuzzy match on option '{top_key}' with {top_score:.1f}% confidence.",
        )

    return AnswerMatchResult(
        matched_key=None,
        is_ambiguous=False,
        confidence=top_score,
        reason=f"No matching option found (top confidence {top_score:.1f}% below threshold).",
    )
