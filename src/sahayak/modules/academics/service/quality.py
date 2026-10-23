"""Quality service managing question flagging, quarantine threshold enforcement, and lifecycle."""

from __future__ import annotations

import logging
import uuid

from sahayak.modules.academics.models import Question
from sahayak.modules.academics.ports import QuestionBankPort

logger = logging.getLogger(__name__)

DEFAULT_QUARANTINE_THRESHOLD = 3


class QuestionQualityService:
    """Service managing quality reviews, user/admin flags, and automatic quarantine transitions."""

    def __init__(
        self,
        question_bank: QuestionBankPort,
        quarantine_threshold: int = DEFAULT_QUARANTINE_THRESHOLD,
    ) -> None:
        self._bank = question_bank
        self._quarantine_threshold = quarantine_threshold

    async def flag_question(
        self,
        question_id: uuid.UUID,
        reason: str | None = None,
    ) -> Question | None:
        """Flag a question for factual inaccuracies, ambiguity, or poor formatting.

        If the question reaches the quarantine threshold, it automatically transitions
        to QUARANTINED status and drops out of active serving queries.
        """
        question = await self._bank.flag_question(
            question_id=question_id,
            quarantine_threshold=self._quarantine_threshold,
        )
        if question is None:
            logger.warning("Attempted to flag non-existent question %s", question_id)
            return None

        logger.info(
            "Question %s flagged (flag_count=%d, status=%s, reason=%s)",
            question_id,
            question.flag_count,
            question.status.value,
            reason or "No reason provided",
        )
        return question

    async def quarantine_question(
        self,
        question_id: uuid.UUID,
        reason: str | None = None,
    ) -> Question | None:
        """Immediately quarantine a question regardless of current flag count."""
        question = await self._bank.quarantine_question(question_id=question_id)
        if question is None:
            logger.warning("Attempted to quarantine non-existent question %s", question_id)
            return None

        logger.warning(
            "Question %s manually quarantined (reason=%s)",
            question_id,
            reason or "Manual quarantine action",
        )
        return question
