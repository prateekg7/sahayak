"""LLM adapter for conversational practice turns and translations (T11.2)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sahayak.modules.language.domain.vocab import sanitize_spoken_text
from sahayak.shared.llm.ports import LLMClient

logger = logging.getLogger(__name__)


class LLMConversationTurnOutput(BaseModel):
    """Pydantic schema for structured conversational partner turn."""

    partner_response: str = Field(
        ...,
        description="Next conversational turn spoken in target language, max 2 short sentences.",
    )
    partner_response_english: str = Field(
        ...,
        description="English meaning of partner response.",
    )
    correction: str | None = Field(
        None,
        description="Corrected user sentence if user made a grammar error, otherwise None.",
    )
    explanation: str | None = Field(
        None,
        description="Brief one-sentence grammar tip explaining the correction, otherwise None.",
    )


class LLMTranslateOutput(BaseModel):
    """Pydantic schema for grammar-aware translation."""

    translation: str = Field(
        ...,
        description="Accurate translation into target language.",
    )
    pronunciation_hint: str = Field(
        ...,
        description="Phonetic pronunciation guide in plain text.",
    )
    grammar_note: str = Field(
        ...,
        description="One-line grammar note or part-of-speech context.",
    )
    example_sentence: str = Field(
        ...,
        description="Natural example sentence demonstrating usage.",
    )


class LLMLanguagePracticeEvaluator:
    """Evaluates conversational turns and translations using structured LLM outputs."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client

    async def generate_turn(
        self,
        *,
        language: str,
        scenario: str,
        level: str,
        history: list[dict[str, Any]],
        user_message: str,
    ) -> LLMConversationTurnOutput:
        """Generate structured next conversational turn with optional grammar correction."""
        if self._llm is None:
            # Deterministic offline fallback
            clean_msg = user_message.lower().strip()
            correction = None
            explanation = None
            if "yo quiero un" in clean_msg and "cafe" in clean_msg:
                # Good Spanish input
                partner_resp = "Aqui tiene su cafe. Desea algo de comer?"
                partner_eng = "Here is your coffee. Would you like something to eat?"
            elif "quiero cafe" in clean_msg:
                partner_resp = "Perfecto, un cafe en camino. Para tomar aqui o llevar?"
                partner_eng = "Perfect, one coffee on the way. For here or to go?"
            else:
                scen_name = scenario.replace("_", " ")
                partner_resp = f"Entendido. Que mas te gustaria hacer en {scen_name}?"
                partner_eng = f"Understood. What else would you like to do in {scen_name}?"

            return LLMConversationTurnOutput(
                partner_response=partner_resp,
                partner_response_english=partner_eng,
                correction=correction,
                explanation=explanation,
            )

        prompt = (
            f"You are a friendly language practice partner in {language.capitalize()} "
            f"for a {level} student.\n"
            f"Scenario: {scenario}\n"
            f"Recent history: {history[-4:] if history else 'None'}\n"
            f"User spoken message: {user_message}\n\n"
            "Task:\n"
            "1. partner_response: Respond naturally in 1-2 short sentences in target language.\n"
            "2. partner_response_english: Provide the English meaning of your partner response.\n"
            "3. correction: If user made a grammar, vocabulary, or gender error, "
            "provide the corrected sentence in target language. If correct, set null.\n"
            "4. explanation: If corrected, provide a single gentle grammar tip. Otherwise null.\n"
            "Output must strictly conform to JSON schema. Keep spoken text under 250 chars."
        )

        try:
            res = await self._llm.generate_json(
                prompt=prompt,
                schema=LLMConversationTurnOutput,
                temperature=0.3,
                max_tokens=400,
            )
            if isinstance(res.parsed, LLMConversationTurnOutput):
                return LLMConversationTurnOutput(
                    partner_response=sanitize_spoken_text(res.parsed.partner_response),
                    partner_response_english=sanitize_spoken_text(
                        res.parsed.partner_response_english
                    ),
                    correction=(
                        sanitize_spoken_text(res.parsed.correction)
                        if res.parsed.correction
                        else None
                    ),
                    explanation=(
                        sanitize_spoken_text(res.parsed.explanation)
                        if res.parsed.explanation
                        else None
                    ),
                )
            if isinstance(res.parsed, dict):
                return LLMConversationTurnOutput.model_validate(res.parsed)
        except Exception as exc:
            logger.warning("LLM turn generation failed, using fallback: %s", exc)

        return LLMConversationTurnOutput(
            partner_response="Muy bien, entiendo lo que dices. Continuemos.",
            partner_response_english="Very well, I understand what you say. Let us continue.",
            correction=None,
            explanation=None,
        )

    async def translate_and_explain(
        self,
        *,
        query: str,
        target_language: str,
    ) -> LLMTranslateOutput:
        """Translate phrase and provide phonetic guide and one-line grammar note."""
        if self._llm is None:
            # Deterministic fallback
            return LLMTranslateOutput(
                translation=f"Traduccion de {query}",
                pronunciation_hint="trah-dook-syohn",
                grammar_note="Common expression in Spanish.",
                example_sentence=f"Siempre usamos {query} con amigos.",
            )

        prompt = (
            f"You are a linguistic teacher translating into {target_language.capitalize()}.\n"
            f"Expression: {query}\n\n"
            "Provide:\n"
            "1. translation: Accurate translation in target language.\n"
            "2. pronunciation_hint: Plain-text phonetic pronunciation guide (e.g. 'oh-lah').\n"
            "3. grammar_note: Brief one-line grammar context or word type.\n"
            "4. example_sentence: Natural example sentence.\n"
            "Output must strictly conform to JSON schema."
        )

        try:
            res = await self._llm.generate_json(
                prompt=prompt,
                schema=LLMTranslateOutput,
                temperature=0.2,
                max_tokens=400,
            )
            if isinstance(res.parsed, LLMTranslateOutput):
                return LLMTranslateOutput(
                    translation=sanitize_spoken_text(res.parsed.translation),
                    pronunciation_hint=sanitize_spoken_text(res.parsed.pronunciation_hint),
                    grammar_note=sanitize_spoken_text(res.parsed.grammar_note),
                    example_sentence=sanitize_spoken_text(res.parsed.example_sentence),
                )
            if isinstance(res.parsed, dict):
                return LLMTranslateOutput.model_validate(res.parsed)
        except Exception as exc:
            logger.warning("LLM translation failed, using fallback: %s", exc)

        return LLMTranslateOutput(
            translation=f"Traduccion de {query}",
            pronunciation_hint="trah-dook-syohn",
            grammar_note="Common expression in Spanish.",
            example_sentence=f"Siempre usamos {query} con amigos.",
        )
