"""Unit tests for the second-pass question verification adapter and quality service (T3.4)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from sahayak.modules.academics.adapters.generation import (
    QuestionGenerationPipeline,
    RawQuestionItem,
    RawQuizGenerationOutput,
)
from sahayak.modules.academics.adapters.verification import (
    QuestionVerifier,
    RawVerificationOutput,
)
from sahayak.modules.academics.models import (
    DifficultyLevel,
    Question,
    QuestionStatus,
)
from sahayak.modules.academics.service.quality import (
    QuestionQualityService,
)
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.llm.ports import LLMResponse


@pytest.fixture
def sample_question() -> Question:
    return Question(
        topic_id=uuid.uuid4(),
        difficulty=DifficultyLevel.MEDIUM,
        stem="Which gas do plants primarily absorb during photosynthesis?",
        options={
            "A": "Oxygen",
            "B": "Carbon dioxide",
            "C": "Nitrogen",
            "D": "Hydrogen",
        },
        correct_key="B",
        explanation="Plants absorb carbon dioxide to produce glucose.",
        content_hash="dummyhash123",
        prompt_version="v1",
        model="fake-model",
        status=QuestionStatus.APPROVED,
    )


@pytest.mark.asyncio
async def test_verifier_agrees_with_correct_answer(sample_question: Question) -> None:
    """Verifier returns same correct_key as question -> verification passes."""
    canned_payload = RawVerificationOutput(
        solved_key="B",
        confidence="high",
        reasoning="Carbon dioxide is absorbed by plants during photosynthesis.",
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned_payload.model_dump_json())])
    verifier = QuestionVerifier(llm_client=fake_llm)

    result = await verifier.verify_question(
        question=sample_question,
        topic_name="Photosynthesis",
    )

    assert result.is_verified is True
    assert result.generator_key == "B"
    assert result.verifier_key == "B"
    assert "agree" in result.reason.lower()


@pytest.mark.asyncio
async def test_verifier_rejects_on_disagreement(sample_question: Question) -> None:
    """Verifier returns a different option -> verification fails and reject metrics recorded."""
    canned_payload = RawVerificationOutput(
        solved_key="A",
        confidence="high",
        reasoning="Incorrect verifier reasoning selecting Oxygen.",
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned_payload.model_dump_json())])
    verifier = QuestionVerifier(llm_client=fake_llm)

    result = await verifier.verify_question(
        question=sample_question,
        topic_name="Photosynthesis",
    )

    assert result.is_verified is False
    assert result.generator_key == "B"
    assert result.verifier_key == "A"
    assert "disagreement" in result.reason.lower()


@pytest.mark.asyncio
async def test_verifier_handles_llm_failure_gracefully(sample_question: Question) -> None:
    """If the verifier LLM call raises an error, the question is safely discarded."""
    mock_llm = AsyncMock()
    mock_llm.generate_json.side_effect = RuntimeError("LLM service timeout")

    verifier = QuestionVerifier(llm_client=mock_llm)

    result = await verifier.verify_question(
        question=sample_question,
        topic_name="Photosynthesis",
    )

    assert result.is_verified is False
    assert result.verifier_key is None
    assert "verification failure" in result.reason.lower()


@pytest.mark.asyncio
async def test_generation_pipeline_filters_out_disagreed_questions() -> None:
    """Pipeline with verifier accepts agreed question and discards disagreed question."""
    generator_payload = RawQuizGenerationOutput(
        questions=[
            # Question 1: will be verified as correct
            RawQuestionItem(
                stem="What is the chemical formula for water?",
                options={"A": "H2O", "B": "CO2", "C": "NaCl", "D": "CH4"},
                correct_key="A",
                explanation="H2O is water.",
            ),
            # Question 2: seeded wrong-answer question where verifier will disagree
            RawQuestionItem(
                stem="What is the boiling point of water at standard atmospheric pressure?",
                options={
                    "A": "50 degrees C",
                    "B": "100 degrees C",
                    "C": "200 degrees C",
                    "D": "0 degrees C",
                },
                correct_key="A",  # Generator incorrectly claims 50 C
                explanation="Water boils at 50 C.",
            ),
        ]
    )

    # Fake LLM for generator
    generator_llm = FakeLLMClient(canned_json=[json.loads(generator_payload.model_dump_json())])

    # Fake LLM for verifier:
    # 1st call (for Q1): verifier says H2O
    # 2nd call (for Q2): verifier says "100 degrees C", generator said "50 degrees C"
    # -> disagreement!
    class DynamicVerifierLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_json(
            self,
            prompt: str,
            schema: type[BaseModel] | dict[str, object],
            *,
            model: str | None = None,
            temperature: float = 0.2,
            max_tokens: int = 2000,
            timeout: float = 8.0,
        ) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                # Find key for H2O in prompt
                solved = "A"
                for line in prompt.splitlines():
                    if "H2O" in line:
                        solved = line.split(":")[0].strip()
                        break
                client = FakeLLMClient(
                    canned_json=[
                        {"solved_key": solved, "confidence": "high", "reasoning": "H2O is water."}
                    ]
                )
                return await client.generate_json(
                    prompt,
                    schema,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )

            # Second call: verifier correctly identifies 100 degrees C
            solved = "B"
            for line in prompt.splitlines():
                if "100 degrees C" in line:
                    solved = line.split(":")[0].strip()
                    break
            client = FakeLLMClient(
                canned_json=[
                    {
                        "solved_key": solved,
                        "confidence": "high",
                        "reasoning": "100 C is boiling point.",
                    }
                ]
            )
            return await client.generate_json(
                prompt,
                schema,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )

    verifier = QuestionVerifier(llm_client=DynamicVerifierLLM())  # type: ignore[arg-type]

    pipeline = QuestionGenerationPipeline(
        llm_client=generator_llm,
        verifier=verifier,
    )

    result = await pipeline.generate_questions(
        topic="Chemistry Basics",
        difficulty=DifficultyLevel.EASY,
        count=2,
    )

    assert result.total_generated == 2
    assert result.total_accepted == 1
    assert result.total_rejected == 1
    assert any("Verification rejected" in k for k in result.rejection_reasons)


@pytest.mark.asyncio
async def test_quality_service_flag_and_quarantine_lifecycle() -> None:
    """Flagging increments flag_count and triggers QUARANTINED status at threshold."""
    q_id = uuid.uuid4()
    question = Question(
        id=q_id,
        topic_id=uuid.uuid4(),
        difficulty=DifficultyLevel.EASY,
        stem="Sample question stem?",
        options={"A": "1", "B": "2", "C": "3", "D": "4"},
        correct_key="A",
        explanation="Explanation",
        content_hash="hashabc",
        prompt_version="v1",
        model="model",
        status=QuestionStatus.APPROVED,
        flag_count=0,
    )

    mock_bank = AsyncMock()

    async def mock_flag(question_id: uuid.UUID, quarantine_threshold: int = 3) -> Question | None:
        if question_id != q_id:
            return None
        question.flag_count += 1
        if question.flag_count >= quarantine_threshold:
            question.status = QuestionStatus.QUARANTINED
        else:
            question.status = QuestionStatus.FLAGGED
        return question

    mock_bank.flag_question.side_effect = mock_flag

    service = QuestionQualityService(question_bank=mock_bank, quarantine_threshold=3)

    # 1. Non-existent question
    res_none = await service.flag_question(uuid.uuid4())
    assert res_none is None

    # 2. First flag: status FLAGGED
    res1 = await service.flag_question(q_id, reason="Typo in option")
    assert res1 is not None
    assert res1.flag_count == 1
    assert res1.status == QuestionStatus.FLAGGED

    # 3. Second flag: status remains FLAGGED
    res2 = await service.flag_question(q_id, reason="Ambiguous wording")
    assert res2 is not None
    assert res2.flag_count == 2
    assert res2.status == QuestionStatus.FLAGGED

    # 4. Third flag (reaches threshold of 3): status becomes QUARANTINED
    res3 = await service.flag_question(q_id, reason="Wrong answer")
    assert res3 is not None
    assert res3.flag_count == 3
    assert res3.status == QuestionStatus.QUARANTINED


@pytest.mark.asyncio
async def test_quality_service_manual_quarantine() -> None:
    """Manual quarantine directly sets status to QUARANTINED."""
    q_id = uuid.uuid4()
    question = Question(
        id=q_id,
        topic_id=uuid.uuid4(),
        difficulty=DifficultyLevel.EASY,
        stem="Sample question stem?",
        options={"A": "1", "B": "2", "C": "3", "D": "4"},
        correct_key="A",
        explanation="Explanation",
        content_hash="hashabc",
        prompt_version="v1",
        model="model",
        status=QuestionStatus.APPROVED,
        flag_count=0,
    )

    mock_bank = AsyncMock()

    async def mock_quarantine(question_id: uuid.UUID) -> Question | None:
        if question_id != q_id:
            return None
        question.status = QuestionStatus.QUARANTINED
        return question

    mock_bank.quarantine_question.side_effect = mock_quarantine

    service = QuestionQualityService(question_bank=mock_bank)

    res = await service.quarantine_question(q_id, reason="Flagged by moderator")
    assert res is not None
    assert res.status == QuestionStatus.QUARANTINED
