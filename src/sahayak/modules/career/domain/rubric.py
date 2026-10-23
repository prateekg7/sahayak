"""Career interview practice domain logic and rubric evaluation (T8.1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

SPOKEN_FEEDBACK_MAX_CHARS = 280

CURATED_QUESTION_BANK: dict[str, dict[str, list[str]]] = {
    "software engineer": {
        "junior": [
            "Tell me about a challenging bug you debugged and how you resolved it.",
            "Explain the difference between synchronous and asynchronous programming.",
            "How do you ensure your code is well tested before deploying it to production?",
            "Describe a time you collaborated with team members to build a new feature.",
            "How do you handle learning a brand new programming language or framework?",
        ],
        "mid": [
            "Walk me through a project where you had to make an important architectural tradeoff.",
            "How do you optimize a database query or backend endpoint that is performing poorly?",
            "Tell me about a time you handled a production outage or critical regression.",
            "How do you conduct code reviews to maintain high engineering standards?",
            "Describe how you design an API to ensure backwards compatibility.",
        ],
        "senior": [
            "How do you design a distributed system that scales to millions of users?",
            "Tell me about a time you resolved a technical disagreement across engineering teams.",
            "How do you balance tech debt repayment with delivering aggressive milestones?",
            "Describe your strategy for mentoring engineers and fostering technical excellence.",
            "Walk me through how you evaluate and adopt new infrastructure technologies.",
        ],
    },
    "product manager": {
        "junior": [
            "How do you prioritize competing feature requests from different stakeholders?",
            "Tell me about a time you gathered user feedback to improve an existing product.",
            "How do you define and measure success metrics for a brand new user feature?",
            "Describe how you work day-to-day with software engineers and designers.",
            "Walk me through your favorite mobile application and how you would improve it.",
        ],
        "mid": [
            "Tell me about a time you decided to sunset a feature that was underperforming.",
            "How do you align cross-functional teams when there is no formal authority?",
            "Walk me through how you build a product roadmap for the next two quarters.",
            "Describe a situation where qualitative feedback contradicted analytics data.",
            "How do you identify product market fit for an early stage capability?",
        ],
        "senior": [
            "How do you communicate long term multi-year product strategy to executives?",
            "Tell me about a high-stakes product pivot you led and how you managed risk.",
            "How do you balance platform scalability investments with top-line growth features?",
            "Describe how you coach and scale an organization of multiple product managers.",
            "Walk me through how you evaluate build versus buy versus partner decisions.",
        ],
    },
    "general": {
        "mid": [
            "Tell me about yourself and walk me through your professional background.",
            "Describe a time you dealt with a difficult conflict in the workplace.",
            "Tell me about a project that did not go as planned and what you learned from it.",
            "What is your greatest professional strength and an area you are actively improving?",
            "Where do you see your career heading over the next three to five years?",
        ]
    },
}


@dataclass(frozen=True)
class RubricScore:
    """Rubric scoring result for an interview answer."""

    clarity_score: int
    relevance_score: int
    depth_score: int
    feedback_tips: list[str] = field(default_factory=list)
    feedback_spoken: str = ""
    prompt_version: str = "v1"

    @property
    def average_score(self) -> float:
        return round((self.clarity_score + self.relevance_score + self.depth_score) / 3.0, 1)


def sanitize_spoken_text(text: str) -> str:
    """Ensure voice string contains no markdown, quotes, emojis, or forbidden symbols."""
    # Remove markdown symbols (*, _, #, `, ~, >, [])
    cleaned = re.sub(r"[*_#`~>\[\]]", "", text)
    # Remove quotes
    cleaned = cleaned.replace('"', "").replace("'", "")
    # Remove any emoji or non-ascii/speech symbols except basic punctuation
    cleaned = re.sub(r"[^\w\s.,?!-]", " ", cleaned)
    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > SPOKEN_FEEDBACK_MAX_CHARS:
        cleaned = cleaned[: SPOKEN_FEEDBACK_MAX_CHARS - 3].rsplit(" ", 1)[0] + "..."
    return cleaned


def get_questions_for_role(role: str, level: str = "mid", count: int = 5) -> list[str]:
    """Retrieve curated interview questions for a role and seniority level."""
    normalized_role = role.strip().lower()
    normalized_level = level.strip().lower()
    if normalized_level not in ("junior", "mid", "senior"):
        normalized_level = "mid"

    role_bank = CURATED_QUESTION_BANK.get(normalized_role)
    if not role_bank:
        for known_role in CURATED_QUESTION_BANK:
            if known_role in normalized_role:
                role_bank = CURATED_QUESTION_BANK[known_role]
                break

    if not role_bank:
        role_bank = CURATED_QUESTION_BANK["general"]

    questions = (
        role_bank.get(normalized_level)
        or role_bank.get("mid")
        or CURATED_QUESTION_BANK["general"]["mid"]
    )

    if len(questions) < count:
        # Pad with general questions if needed
        general_q = CURATED_QUESTION_BANK["general"]["mid"]
        for q in general_q:
            if q not in questions:
                questions.append(q)
            if len(questions) >= count:
                break

    return questions[:count]


def parse_rubric_evaluation(raw_text: str, question: str, answer: str) -> RubricScore:
    """Parse and validate LLM evaluation output into a RubricScore."""
    try:
        # Extract JSON from potential markdown wrapping
        json_str = raw_text.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```", 1)[1].split("```", 1)[0].strip()

        data = json.loads(json_str)
        clarity = int(data.get("clarity_score", 3))
        relevance = int(data.get("relevance_score", 3))
        depth = int(data.get("depth_score", 3))

        # Clamp scores between 1 and 5
        clarity = max(1, min(5, clarity))
        relevance = max(1, min(5, relevance))
        depth = max(1, min(5, depth))

        raw_tips = data.get("feedback_tips", [])
        tips: list[str] = []
        if isinstance(raw_tips, list):
            for t in raw_tips[:2]:
                if isinstance(t, str) and t.strip():
                    tips.append(sanitize_spoken_text(t.strip()))

        spoken = str(data.get("feedback_spoken", "")).strip()
        if not spoken:
            avg_val = round((clarity + relevance + depth) / 3.0, 1)
            spoken = f"Scored {avg_val} out of 5. Good clarity with structured points."

        sanitized_spoken = sanitize_spoken_text(spoken)

        return RubricScore(
            clarity_score=clarity,
            relevance_score=relevance,
            depth_score=depth,
            feedback_tips=tips,
            feedback_spoken=sanitized_spoken,
            prompt_version="v1",
        )
    except Exception:
        # Fallback rubric evaluation if LLM output was malformed or unavailable
        answer_words = len(answer.split())
        clarity = 4 if answer_words >= 15 else 3
        relevance = (
            4 if any(w in answer.lower() for w in question.lower().split() if len(w) > 4) else 3
        )
        depth = 4 if answer_words >= 30 else 3

        tips = [
            "Use the STAR method situation task action result for behavioral stories.",
            "Include concrete metrics to quantify the impact of your work.",
        ]
        avg = round((clarity + relevance + depth) / 3.0, 1)
        spoken = (
            f"Your answer scored {avg} out of 5. You communicated clearly. "
            "For more depth add measurable results."
        )

        return RubricScore(
            clarity_score=clarity,
            relevance_score=relevance,
            depth_score=depth,
            feedback_tips=tips,
            feedback_spoken=sanitize_spoken_text(spoken),
            prompt_version="v1",
        )
