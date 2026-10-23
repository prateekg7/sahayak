"""Unit tests for language practice domain logic and speech formatters (T11.2)."""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.language.domain.practice import (
    MAX_SPOKEN_CHARS,
    format_reply_turn_spoken,
    format_session_completed_spoken,
    format_start_conversation_spoken,
    format_translate_explain_spoken,
    get_scenario_starter,
    normalize_scenario,
)


def test_scenario_normalization() -> None:
    """Validate scenario normalization, aliases, and error rejection."""
    assert normalize_scenario(None) == "general"
    assert normalize_scenario("ordering_food") == "ordering_food"
    assert normalize_scenario("restaurant") == "ordering_food"
    assert normalize_scenario("cafe") == "ordering_food"
    assert normalize_scenario("directions") == "asking_directions"
    assert normalize_scenario("friends") == "meeting_friends"
    assert normalize_scenario("shop") == "shopping"

    with pytest.raises(InvalidInputError, match="Unsupported scenario 'space_battle'"):
        normalize_scenario("space_battle")


def test_scenario_starters() -> None:
    """Verify scenario starters exist for languages and scenarios."""
    greeting, meaning = get_scenario_starter("spanish", "ordering_food")
    assert "restaurante" in greeting
    assert "restaurant" in meaning

    greeting_fr, meaning_fr = get_scenario_starter("french", "general")
    assert "Bonjour" in greeting_fr


def test_spoken_summary_formatters() -> None:
    """Verify all spoken summaries adhere to voice UX rules and length caps."""
    spoken_start = format_start_conversation_spoken(
        language="spanish",
        scenario="ordering_food",
        partner_greeting="Buenas tardes, bienvenido al restaurante. Que desea tomar?",
        english_meaning="Good afternoon, welcome to the restaurant. What would you like to drink?",
    )
    assert len(spoken_start) <= MAX_SPOKEN_CHARS
    assert "*" not in spoken_start
    assert '"' not in spoken_start
    assert "'" not in spoken_start

    spoken_reply = format_reply_turn_spoken(
        partner_reply="Aqui tiene su cafe con leche. Algo mas?",
        english_meaning="Here is your coffee with milk. Anything else?",
        turns_left=3,
        correction="Yo quiero un cafe",
        explanation="Use masculine article un with cafe",
    )
    assert len(spoken_reply) <= MAX_SPOKEN_CHARS
    assert "Quick tip: say Yo quiero un cafe" in spoken_reply
    assert "3 turns left" in spoken_reply

    spoken_completed = format_session_completed_spoken(
        language="spanish",
        scenario="ordering_food",
        turns_completed=5,
    )
    assert len(spoken_completed) <= MAX_SPOKEN_CHARS
    assert "completed 5 turns" in spoken_completed

    spoken_trans = format_translate_explain_spoken(
        original="Where is the train station?",
        translation="Donde esta la estacion de tren?",
        grammar_note="Use esta for location.",
        example_sentence="Donde esta la estacion de tren mas cercana?",
    )
    assert len(spoken_trans) <= MAX_SPOKEN_CHARS
    assert "translates to" in spoken_trans
