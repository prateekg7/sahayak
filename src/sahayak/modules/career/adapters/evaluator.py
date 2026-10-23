"""LLM rubric evaluation adapter for mock interviews (T8.1)."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from sahayak.modules.career.domain.rubric import RubricScore, parse_rubric_evaluation
from sahayak.modules.career.ports import InterviewEvaluationPort
from sahayak.shared.llm.ports import LLMClient

logger = logging.getLogger(__name__)


class LLMRubricOutput(BaseModel):
    """Pydantic schema for structured LLM rubric evaluation."""

    clarity_score: int = Field(ge=1, le=5, description="Clarity and structure of response 1-5")
    relevance_score: int = Field(ge=1, le=5, description="Relevance to the interview question 1-5")
    depth_score: int = Field(ge=1, le=5, description="Depth and concrete details 1-5")
    feedback_tips: list[str] = Field(default_factory=list, description="Actionable tips max 2")
    feedback_spoken: str = Field(
        description="Short spoken summary without markdown under 280 chars"
    )


class LLMInterviewEvaluator(InterviewEvaluationPort):
    """Adapter that evaluates interview answers using structured LLM prompts."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client

    async def evaluate(
        self,
        *,
        role: str,
        level: str,
        question: str,
        answer: str,
    ) -> RubricScore:
        if self._llm is None:
            return parse_rubric_evaluation("", question, answer)

        prompt = (
            f"You are an expert hiring manager evaluating a candidate for a {level} level "
            f"{role} position.\n"
            f"Question: {question}\n"
            f"Candidate Answer: {answer}\n\n"
            "Evaluate the answer based on:\n"
            "1. clarity_score (1-5): structure and articulation\n"
            "2. relevance_score (1-5): directly addresses the prompt\n"
            "3. depth_score (1-5): technical or situational depth and concrete metrics\n"
            "4. feedback_tips: list of at most 2 brief actionable tips\n"
            "5. feedback_spoken: concise voice feedback suitable for Alexa, "
            "strictly under 250 characters, no markdown, no quotes, no emojis.\n"
            "Respond in structured JSON matching the schema."
        )

        try:
            res = await self._llm.generate_json(
                prompt=prompt,
                schema=LLMRubricOutput,
                temperature=0.2,
                max_tokens=500,
            )
            if isinstance(res.parsed, LLMRubricOutput):
                from sahayak.modules.career.domain.rubric import sanitize_spoken_text

                return RubricScore(
                    clarity_score=res.parsed.clarity_score,
                    relevance_score=res.parsed.relevance_score,
                    depth_score=res.parsed.depth_score,
                    feedback_tips=[sanitize_spoken_text(t) for t in res.parsed.feedback_tips[:2]],
                    feedback_spoken=sanitize_spoken_text(res.parsed.feedback_spoken),
                    prompt_version="v1",
                )
            if isinstance(res.parsed, dict):
                import json

                return parse_rubric_evaluation(json.dumps(res.parsed), question, answer)

            return parse_rubric_evaluation(res.content, question, answer)
        except Exception as exc:
            logger.warning("LLM evaluation failed, falling back to deterministic rubric: %s", exc)
            return parse_rubric_evaluation("", question, answer)
