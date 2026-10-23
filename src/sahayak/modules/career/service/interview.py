"""Career interview practice service (T8.1)."""

from __future__ import annotations

import uuid
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.career.adapters.evaluator import LLMInterviewEvaluator
from sahayak.modules.career.adapters.interviews import SQLAlchemyInterviewRepository
from sahayak.modules.career.domain.rubric import (
    get_questions_for_role,
    sanitize_spoken_text,
)
from sahayak.modules.career.ports import InterviewEvaluationPort
from sahayak.shared.llm.ports import LLMClient


class InterviewService:
    """Orchestrates mock interview session workflows and turn evaluations."""

    def __init__(
        self,
        session_factory: Any,
        evaluator: InterviewEvaluationPort | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._evaluator = evaluator or LLMInterviewEvaluator(llm_client=llm_client)

    async def start_session(
        self,
        *,
        user_id: uuid.UUID,
        role: str,
        level: str,
        total_questions: int = 5,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Start a new mock interview practice session."""
        total_questions = max(1, min(5, total_questions))
        role_cleaned = role.strip() or "Software Engineer"
        level_cleaned = level.strip().lower()
        if level_cleaned not in ("junior", "mid", "senior"):
            level_cleaned = "mid"

        raw_questions = get_questions_for_role(role_cleaned, level_cleaned, total_questions)
        q_objs = [{"index": idx, "text": q} for idx, q in enumerate(raw_questions)]

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyInterviewRepository(uow.session)
            session = await repo.create_session(
                user_id=user_id,
                role=role_cleaned,
                level=level_cleaned,
                total_questions=total_questions,
                questions=q_objs,
            )
            session_id = str(session.id)
            await uow.session.commit()

        first_q = raw_questions[0]
        spoken = sanitize_spoken_text(
            f"Starting your {level_cleaned} {role_cleaned} mock interview. "
            f"Question 1 of {total_questions}: {first_q}. "
            "Please state your answer."
        )

        data = {
            "session_id": session_id,
            "role": role_cleaned,
            "level": level_cleaned,
            "status": "in_progress",
            "current_question_index": 0,
            "total_questions": total_questions,
            "current_question": first_q,
        }
        next_actions = [
            f"interview_practice(action='answer', session_id='{session_id}', answer='...')",
            f"interview_practice(action='finish', session_id='{session_id}')",
        ]
        return data, spoken, next_actions

    async def answer_question(
        self,
        *,
        user_id: uuid.UUID,
        session_id_str: str,
        answer: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Submit an answer to the current question and receive rubric feedback."""
        try:
            session_id = uuid.UUID(session_id_str)
        except (ValueError, TypeError):
            raise InvalidInputError(
                "Please provide a valid session ID for the interview."
            ) from None

        if not answer or not answer.strip():
            raise InvalidInputError("Please provide an answer to evaluate.")

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyInterviewRepository(uow.session)
            session = await repo.get_session(session_id=session_id, user_id=user_id)
            if not session:
                raise NotFoundError(
                    "Interview session not found. Would you like to start a new one?"
                )

            if session.status != "in_progress":
                raise InvalidInputError(
                    f"This interview session has already {session.status}. "
                    "Please start a new session."
                )

            q_idx = session.current_question_index
            if q_idx >= len(session.questions):
                await repo.update_session_progress(
                    session_id=session.id,
                    current_question_index=q_idx,
                    status="completed",
                )
                await uow.session.commit()
                raise InvalidInputError("All questions for this session are already completed.")

            current_q_obj = session.questions[q_idx]
            current_q_text = current_q_obj.get("text", "")
            role = session.role
            level = session.level
            total_questions = session.total_questions

            # Rubric evaluation
            score = await self._evaluator.evaluate(
                role=role,
                level=level,
                question=current_q_text,
                answer=answer.strip(),
            )

            await repo.create_turn(
                session_id=session.id,
                question_index=q_idx,
                question_text=current_q_text,
                user_answer=answer.strip(),
                score=score,
            )

            next_idx = q_idx + 1
            is_completed = next_idx >= total_questions

            if is_completed:
                updated_sess = await repo.update_session_progress(
                    session_id=session.id,
                    current_question_index=next_idx,
                    status="completed",
                )
                all_turns = await repo.get_turns(session_id=session.id)
                await uow.session.commit()

                avg_clarity = sum(t.clarity_score for t in all_turns) / len(all_turns)
                avg_relevance = sum(t.relevance_score for t in all_turns) / len(all_turns)
                avg_depth = sum(t.depth_score for t in all_turns) / len(all_turns)
                overall_avg = round((avg_clarity + avg_relevance + avg_depth) / 3.0, 1)

                spoken = sanitize_spoken_text(
                    f"{score.feedback_spoken} You completed all {total_questions} questions "
                    f"with an overall average score of {overall_avg} out of 5. "
                    "Excellent practice session!"
                )
                data = {
                    "session_id": str(session.id),
                    "status": "completed",
                    "question_index": q_idx,
                    "score": {
                        "clarity_score": score.clarity_score,
                        "relevance_score": score.relevance_score,
                        "depth_score": score.depth_score,
                        "average_score": score.average_score,
                        "feedback_tips": score.feedback_tips,
                        "feedback_spoken": score.feedback_spoken,
                    },
                    "overall_summary": {
                        "total_questions": total_questions,
                        "overall_average_score": overall_avg,
                        "completed_at": updated_sess.finished_at.isoformat()
                        if updated_sess and updated_sess.finished_at
                        else None,
                    },
                }
                next_actions = [
                    "interview_practice(action='start')",
                    "interview_practice(action='history')",
                ]
                return data, spoken, next_actions

            # Advance to next question
            await repo.update_session_progress(
                session_id=session.id,
                current_question_index=next_idx,
                status="in_progress",
            )
            next_q_text = session.questions[next_idx].get("text", "")
            await uow.session.commit()

        next_turn_num = next_idx + 1
        spoken = sanitize_spoken_text(
            f"{score.feedback_spoken} Next is question {next_turn_num} of "
            f"{total_questions}: {next_q_text}"
        )
        data = {
            "session_id": str(session_id),
            "status": "in_progress",
            "question_index": q_idx,
            "next_question_index": next_idx,
            "next_question": next_q_text,
            "score": {
                "clarity_score": score.clarity_score,
                "relevance_score": score.relevance_score,
                "depth_score": score.depth_score,
                "average_score": score.average_score,
                "feedback_tips": score.feedback_tips,
                "feedback_spoken": score.feedback_spoken,
            },
        }
        next_actions = [
            f"interview_practice(action='answer', session_id='{session_id}', answer='...')",
            f"interview_practice(action='finish', session_id='{session_id}')",
        ]
        return data, spoken, next_actions

    async def finish_session(
        self,
        *,
        user_id: uuid.UUID,
        session_id_str: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Finish or conclude an interview session early."""
        try:
            session_id = uuid.UUID(session_id_str)
        except (ValueError, TypeError):
            raise InvalidInputError("Please provide a valid session ID.") from None

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyInterviewRepository(uow.session)
            session = await repo.get_session(session_id=session_id, user_id=user_id)
            if not session:
                raise NotFoundError("Interview session not found.")

            turns = await repo.get_turns(session_id=session.id)
            new_status = "completed" if len(turns) > 0 else "abandoned"

            await repo.update_session_progress(
                session_id=session.id,
                current_question_index=session.current_question_index,
                status=new_status,
            )
            await uow.session.commit()

        spoken = sanitize_spoken_text(
            f"Interview session finished. You answered {len(turns)} out of "
            f"{session.total_questions} questions."
        )
        data = {
            "session_id": str(session.id),
            "status": new_status,
            "answered_questions": len(turns),
            "total_questions": session.total_questions,
        }
        next_actions = [
            "interview_practice(action='start')",
            "interview_practice(action='history')",
        ]
        return data, spoken, next_actions

    async def get_history(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 5,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """List past mock interview practice sessions and scores."""
        limit = max(1, min(20, limit))
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyInterviewRepository(uow.session)
            sessions = await repo.list_sessions(user_id=user_id, limit=limit)

            summary_list = []
            for s in sessions:
                turns = await repo.get_turns(session_id=s.id)
                avg_score = None
                if turns:
                    total_pts = sum(
                        t.clarity_score + t.relevance_score + t.depth_score for t in turns
                    )
                    avg_score = round(total_pts / (len(turns) * 3.0), 1)

                summary_list.append(
                    {
                        "session_id": str(s.id),
                        "role": s.role,
                        "level": s.level,
                        "status": s.status,
                        "questions_completed": len(turns),
                        "total_questions": s.total_questions,
                        "average_score": avg_score,
                        "created_at": s.created_at.isoformat() if s.created_at else None,
                    }
                )

        if not summary_list:
            spoken = (
                "You haven't completed any mock interview sessions yet. "
                "Say start interview to begin."
            )
        else:
            latest = summary_list[0]
            spoken = sanitize_spoken_text(
                f"You have {len(summary_list)} recorded mock interview sessions. "
                f"Your most recent was for {latest['level']} {latest['role']}."
            )

        data = {"sessions": summary_list}
        next_actions = ["interview_practice(action='start')"]
        return data, spoken, next_actions
