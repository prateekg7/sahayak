"""Question generation pipeline: grounding, prompt assembly, LLM call, and validation."""

from __future__ import annotations

import hashlib
import logging
import secrets
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sahayak.modules.academics.adapters.verification import QuestionVerifier
from sahayak.modules.academics.domain.topics import normalize_topic
from sahayak.modules.academics.models import (
    DifficultyLevel,
    Question,
    QuestionStatus,
)
from sahayak.shared.content.wikipedia import WikipediaClient
from sahayak.shared.llm.ports import LLMClient

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
PROMPT_PATH = Path("prompts/quiz_gen_v1.md")

# Validation limits
MIN_STEM_LEN = 10
MAX_STEM_LEN = 500
MAX_OPTION_LEN = 150
MAX_EXPLANATION_LEN = 500
DISALLOWED_SYMBOLS = set("*#_[]~`$")


class RawQuestionItem(BaseModel):
    """Raw question payload expected from structured LLM output."""

    stem: str = Field(description="Question stem")
    options: dict[str, str] = Field(description="Mapping of option letters to answer texts")
    correct_key: str = Field(description="Key of the correct option ('A', 'B', 'C', or 'D')")
    explanation: str = Field(description="Explanation of why the correct option is right")


class RawQuizGenerationOutput(BaseModel):
    """Container model for structured JSON quiz generation."""

    questions: list[RawQuestionItem] = Field(default_factory=list)


@dataclass(frozen=True)
class GenerationResult:
    """Outcome of running the question generation pipeline."""

    topic_key: str
    display_name: str
    questions: list[Question]
    grounded: bool
    source_url: str | None
    source_hash: str | None
    total_generated: int
    total_accepted: int
    total_rejected: int
    rejection_reasons: dict[str, int]


def compute_content_hash(stem: str, options: dict[str, str]) -> str:
    """Compute deterministic SHA-256 hash of normalized stem and option values."""
    normalized_stem = stem.strip().lower()
    normalized_opts = sorted(opt.strip().lower() for opt in options.values())
    payload = f"{normalized_stem}|{'|'.join(normalized_opts)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_and_shuffle_question(
    item: RawQuestionItem,
    topic_id: Any,
    difficulty: DifficultyLevel,
    model_name: str,
    source_url: str | None = None,
    source_hash: str | None = None,
) -> tuple[Question | None, str | None]:
    """Validate question quality and shuffle option order to eliminate position bias.

    Returns:
        (Question, None) if valid, or (None, rejection_reason) if invalid.
    """
    stem = item.stem.strip()
    explanation = item.explanation.strip()

    # 1. Stem length check
    if len(stem) < MIN_STEM_LEN or len(stem) > MAX_STEM_LEN:
        return None, f"Stem length ({len(stem)}) outside bounds [{MIN_STEM_LEN}, {MAX_STEM_LEN}]."

    # 2. Markdown / formatting symbol check
    if any(ch in DISALLOWED_SYMBOLS for ch in stem):
        return None, "Stem contains disallowed formatting characters or markdown."

    # 3. Explanation length check
    if not explanation or len(explanation) > MAX_EXPLANATION_LEN:
        return None, "Explanation missing or exceeds maximum allowed length."

    # 4. Check option keys
    cleaned_options: dict[str, str] = {
        k.strip().upper(): v.strip() for k, v in item.options.items()
    }
    required_keys = {"A", "B", "C", "D"}
    if set(cleaned_options.keys()) != required_keys:
        got_keys = set(cleaned_options.keys())
        return None, f"Options keys must be exactly {required_keys}, got {got_keys}."

    # 5. Check option distinctness and non-emptiness
    unique_values = {v.lower() for v in cleaned_options.values()}
    if len(unique_values) != 4:
        return None, "Options must be 4 distinct non-duplicate texts."

    for k, v in cleaned_options.items():
        if not v or len(v) > MAX_OPTION_LEN:
            return None, f"Option '{k}' is empty or exceeds {MAX_OPTION_LEN} chars."
        if any(ch in DISALLOWED_SYMBOLS for ch in v):
            return None, f"Option '{k}' contains disallowed markdown or symbols."

    # 6. Correct key check
    correct_key = item.correct_key.strip().upper()
    if correct_key not in required_keys:
        return None, f"Correct key '{correct_key}' is not one of {required_keys}."

    correct_answer_text = cleaned_options[correct_key]

    # 7. Answer leakage in stem (verbatim substring check for answers >= 4 chars)
    if len(correct_answer_text) >= 4 and correct_answer_text.lower() in stem.lower():
        return (
            None,
            f"Answer leakage detected: correct answer '{correct_answer_text}' found in stem.",
        )

    # 8. Shuffle options to prevent LLM position bias
    option_items = list(cleaned_options.values())
    # Deterministic or cryptographically secure shuffle
    secrets.SystemRandom().shuffle(option_items)
    new_keys = ["A", "B", "C", "D"]
    shuffled_options = dict(zip(new_keys, option_items, strict=True))

    # Identify new correct key
    new_correct_key: str | None = None
    for k, v in shuffled_options.items():
        if v == correct_answer_text:
            new_correct_key = k
            break

    if new_correct_key is None:
        return None, "Internal error re-mapping correct key after shuffle."

    content_hash = compute_content_hash(stem, shuffled_options)

    question = Question(
        topic_id=topic_id,
        difficulty=difficulty,
        stem=stem,
        options=shuffled_options,
        correct_key=new_correct_key,
        explanation=explanation,
        source_url=source_url,
        source_hash=source_hash,
        content_hash=content_hash,
        prompt_version=PROMPT_VERSION,
        model=model_name,
        status=QuestionStatus.APPROVED,
    )
    return question, None


class QuestionGenerationPipeline:
    """Pipeline generating grounded multiple-choice questions via Wikipedia and LLM."""

    def __init__(
        self,
        llm_client: LLMClient,
        wikipedia_client: WikipediaClient | None = None,
        verifier: QuestionVerifier | None = None,
        prompt_path: Path = PROMPT_PATH,
    ) -> None:
        self._llm = llm_client
        self._wikipedia = wikipedia_client
        self._verifier = verifier
        self._prompt_path = prompt_path
        self._prompt_template: str | None = None

    def _load_prompt_template(self) -> str:
        if self._prompt_template is None:
            if not self._prompt_path.is_file():
                raise FileNotFoundError(f"Missing prompt template at {self._prompt_path}")
            self._prompt_template = self._prompt_path.read_text(encoding="utf-8")
        return self._prompt_template

    async def generate_questions(
        self,
        topic: str,
        difficulty: DifficultyLevel,
        count: int = 5,
        topic_id: Any = None,
        model: str | None = None,
    ) -> GenerationResult:
        """Execute grounding retrieval, prompt assembly, LLM generation, and validation."""
        topic_key, display_name = normalize_topic(topic)

        # 1. Fetch grounding text from Wikipedia if available
        grounded = False
        source_url: str | None = None
        source_hash: str | None = None
        grounding_block = ""

        if self._wikipedia is not None:
            try:
                g_res = await self._wikipedia.get_grounding(display_name)
                if g_res is not None and g_res.raw_extract:
                    grounded = True
                    source_url = g_res.url
                    source_hash = hashlib.sha256(g_res.raw_extract.encode("utf-8")).hexdigest()
                    grounding_block = g_res.wrapped_prompt_text
            except Exception as exc:
                logger.warning("Wikipedia grounding fetch failed for '%s': %s", display_name, exc)

        # 2. Assemble prompt (request count + 2 buffer to absorb validation rejects)
        target_count = count + 2
        template = self._load_prompt_template()
        prompt = template.format(
            topic=display_name,
            difficulty=difficulty.value,
            count=target_count,
            grounding_block=grounding_block,
        )

        # 3. Call LLM for structured JSON output
        response = await self._llm.generate_json(
            prompt=prompt,
            schema=RawQuizGenerationOutput,
            temperature=0.7,
            model=model,
        )

        if isinstance(response.parsed, RawQuizGenerationOutput):
            raw_output = response.parsed
        elif isinstance(response.parsed, dict):
            raw_output = RawQuizGenerationOutput.model_validate(response.parsed)
        else:
            raw_output = RawQuizGenerationOutput.model_validate_json(response.content)

        model_name = response.model or model or "unknown"

        # 4. Validate, shuffle, and deduplicate
        validated: list[Question] = []
        seen_hashes: set[str] = set()
        rejections: Counter[str] = Counter()

        for item in raw_output.questions:
            q, reason = validate_and_shuffle_question(
                item=item,
                topic_id=topic_id,
                difficulty=difficulty,
                model_name=model_name,
                source_url=source_url,
                source_hash=source_hash,
            )
            if q is None:
                rejections[reason or "Unknown validation error"] += 1
                continue

            if q.content_hash in seen_hashes:
                rejections["Duplicate question content within batch"] += 1
                continue

            if self._verifier is not None:
                v_res = await self._verifier.verify_question(
                    question=q,
                    topic_name=display_name,
                    grounding_block=grounding_block,
                )
                if not v_res.is_verified:
                    rejections[f"Verification rejected: {v_res.reason}"] += 1
                    continue

            seen_hashes.add(q.content_hash)
            validated.append(q)
            if len(validated) >= count:
                break

        return GenerationResult(
            topic_key=topic_key,
            display_name=display_name,
            questions=validated,
            grounded=grounded,
            source_url=source_url,
            source_hash=source_hash,
            total_generated=len(raw_output.questions),
            total_accepted=len(validated),
            total_rejected=sum(rejections.values()),
            rejection_reasons=dict(rejections),
        )
