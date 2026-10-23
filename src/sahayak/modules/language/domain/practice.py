"""Domain logic for language conversational practice and translate-and-explain (T11.2)."""

from __future__ import annotations

from sahayak.core.errors import InvalidInputError
from sahayak.modules.language.domain.vocab import sanitize_spoken_text

MAX_SPOKEN_CHARS: int = 300
DEFAULT_MAX_TURNS: int = 5
MAX_SESSION_TURNS_LIMIT: int = 10

SUPPORTED_SCENARIOS: tuple[str, ...] = (
    "general",
    "ordering_food",
    "asking_directions",
    "meeting_friends",
    "travel",
    "shopping",
)

SCENARIO_STARTERS: dict[tuple[str, str], tuple[str, str]] = {
    # (language, scenario): (partner_greeting, english_meaning)
    ("spanish", "general"): ("Hola, que tal?", "Hello, how are you?"),
    ("spanish", "ordering_food"): (
        "Buenas tardes, bienvenido al restaurante. Que desea tomar?",
        "Good afternoon, welcome to the restaurant. What would you like to drink?",
    ),
    ("spanish", "asking_directions"): (
        "Disculpe, me parece que esta perdido. A donde va?",
        "Excuse me, you look lost. Where are you going?",
    ),
    ("spanish", "meeting_friends"): (
        "Hola amigo! Cuanto tiempo sin verte. Como estas?",
        "Hello friend! Long time no see. How are you?",
    ),
    ("french", "general"): ("Bonjour, comment ca va?", "Hello, how is it going?"),
    ("french", "ordering_food"): (
        "Bonjour, qu est-ce que je vous sers?",
        "Hello, what can I serve you?",
    ),
    ("german", "general"): ("Hallo, wie geht es dir?", "Hello, how are you?"),
    ("hindi", "general"): (
        "Namaste! Aapka din kaisa chal raha hai?",
        "Hello! How is your day going?",
    ),
    ("japanese", "general"): ("Konnichiwa! O-genki desu ka?", "Hello! How are you?"),
}


def normalize_scenario(raw_scenario: str | None) -> str:
    """Normalize and validate conversational scenario."""
    if not raw_scenario:
        return "general"

    clean = raw_scenario.strip().lower().replace(" ", "_")
    scenario_aliases: dict[str, str] = {
        "food": "ordering_food",
        "cafe": "ordering_food",
        "restaurant": "ordering_food",
        "coffee": "ordering_food",
        "ordering_coffee": "ordering_food",
        "directions": "asking_directions",
        "navigation": "asking_directions",
        "friends": "meeting_friends",
        "friend": "meeting_friends",
        "shop": "shopping",
        "store": "shopping",
        "market": "shopping",
        "airport": "travel",
        "train": "travel",
        "hotel": "travel",
    }
    resolved = scenario_aliases.get(clean, clean)
    if resolved not in SUPPORTED_SCENARIOS:
        supported_str = ", ".join(SUPPORTED_SCENARIOS)
        raise InvalidInputError(
            f"Unsupported scenario '{raw_scenario}'. Supported scenarios: {supported_str}."
        )
    return resolved


def get_scenario_starter(language: str, scenario: str) -> tuple[str, str]:
    """Retrieve initial greeting and English meaning for language and scenario."""
    key = (language.lower(), scenario.lower())
    if key in SCENARIO_STARTERS:
        return SCENARIO_STARTERS[key]
    gen_key = (language.lower(), "general")
    if gen_key in SCENARIO_STARTERS:
        return SCENARIO_STARTERS[gen_key]
    return ("Hello, let us practice!", "Hello, let us practice!")


def format_start_conversation_spoken(
    language: str,
    scenario: str,
    partner_greeting: str,
    english_meaning: str,
) -> str:
    """Format voice summary for starting a conversation."""
    lang_display = language.capitalize()
    scenario_display = scenario.replace("_", " ")
    prompt = (
        f"Starting {scenario_display} practice in {lang_display}. "
        f"Your partner says: {partner_greeting}, meaning {english_meaning}. "
        "How do you reply?"
    )
    clean = sanitize_spoken_text(prompt)
    if len(clean) > MAX_SPOKEN_CHARS:
        clean = sanitize_spoken_text(
            f"Starting practice in {lang_display}. "
            f"Partner says: {partner_greeting}. How do you reply?"
        )
    return clean[:MAX_SPOKEN_CHARS]


def format_reply_turn_spoken(
    partner_reply: str,
    english_meaning: str,
    turns_left: int,
    correction: str | None = None,
    explanation: str | None = None,
) -> str:
    """Format voice turn with partner response, feedback, and turns left."""
    feedback_part = ""
    if correction:
        note_part = f" Note: {explanation}." if explanation else ""
        feedback_part = f"Quick tip: say {correction}.{note_part} "

    turns_part = (
        " Final turn."
        if turns_left == 1
        else f" {turns_left} turns left."
        if turns_left > 1
        else ""
    )

    full = f"{feedback_part}Partner says: {partner_reply}, meaning {english_meaning}.{turns_part}"
    clean = sanitize_spoken_text(full)
    if len(clean) > MAX_SPOKEN_CHARS:
        # Truncate meaning if needed to keep partner reply and tip
        full_compact = f"{feedback_part}Partner says: {partner_reply}.{turns_part}"
        clean = sanitize_spoken_text(full_compact)
        if len(clean) > MAX_SPOKEN_CHARS:
            clean = sanitize_spoken_text(f"Partner: {partner_reply}.{turns_part}")
    return clean[:MAX_SPOKEN_CHARS]


def format_session_completed_spoken(
    language: str,
    scenario: str,
    turns_completed: int,
) -> str:
    """Format spoken congratulation after concluding a conversation."""
    lang_display = language.capitalize()
    scenario_display = scenario.replace("_", " ")
    msg = (
        f"Great practice! You completed {turns_completed} turns of "
        f"{scenario_display} in {lang_display}. "
        "Say start conversation to practice again or review vocabulary."
    )
    clean = sanitize_spoken_text(msg)
    return clean[:MAX_SPOKEN_CHARS]


def format_translate_explain_spoken(
    original: str,
    translation: str,
    grammar_note: str,
    example_sentence: str,
) -> str:
    """Format spoken explanation and translation."""
    msg = f"{original} translates to {translation}. {grammar_note} Example: {example_sentence}."
    clean = sanitize_spoken_text(msg)
    if len(clean) > MAX_SPOKEN_CHARS:
        compact = f"{original} translates to {translation}. {grammar_note}."
        clean = sanitize_spoken_text(compact)
        if len(clean) > MAX_SPOKEN_CHARS:
            clean = sanitize_spoken_text(f"{original} translates to {translation}.")
    return clean[:MAX_SPOKEN_CHARS]
