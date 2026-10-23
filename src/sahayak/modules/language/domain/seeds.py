"""Curated seed vocabulary for supported languages and levels."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedWord:
    """Seed vocabulary word entry."""

    language: str
    level: str
    word: str
    translation: str
    pronunciation_hint: str
    example_sentence: str
    example_translation: str
    part_of_speech: str | None = None


SEED_WORDS: tuple[SeedWord, ...] = (
    # Spanish - Beginner
    SeedWord(
        language="spanish",
        level="beginner",
        word="hola",
        translation="hello",
        pronunciation_hint="oh-lah",
        example_sentence="Hola, como estas?",
        example_translation="Hello, how are you?",
        part_of_speech="interjection",
    ),
    SeedWord(
        language="spanish",
        level="beginner",
        word="gracias",
        translation="thank you",
        pronunciation_hint="grah-syahs",
        example_sentence="Muchas gracias por tu ayuda.",
        example_translation="Thank you very much for your help.",
        part_of_speech="noun",
    ),
    SeedWord(
        language="spanish",
        level="beginner",
        word="amigo",
        translation="friend",
        pronunciation_hint="ah-mee-goh",
        example_sentence="Juan es mi buen amigo.",
        example_translation="Juan is my good friend.",
        part_of_speech="noun",
    ),
    SeedWord(
        language="spanish",
        level="beginner",
        word="desayuno",
        translation="breakfast",
        pronunciation_hint="deh-sah-yoo-noh",
        example_sentence="Que quieres para el desayuno?",
        example_translation="What do you want for breakfast?",
        part_of_speech="noun",
    ),
    SeedWord(
        language="spanish",
        level="beginner",
        word="tiempo",
        translation="time or weather",
        pronunciation_hint="tyehm-poh",
        example_sentence="No tengo mucho tiempo hoy.",
        example_translation="I do not have much time today.",
        part_of_speech="noun",
    ),
    # Spanish - Intermediate
    SeedWord(
        language="spanish",
        level="intermediate",
        word="desarrollo",
        translation="development",
        pronunciation_hint="deh-sah-rroh-yoh",
        example_sentence="El desarrollo economico es muy importante.",
        example_translation="Economic development is very important.",
        part_of_speech="noun",
    ),
    SeedWord(
        language="spanish",
        level="intermediate",
        word="esperanza",
        translation="hope",
        pronunciation_hint="ehs-peh-rahn-sah",
        example_sentence="Siempre tenemos esperanza para el futuro.",
        example_translation="We always have hope for the future.",
        part_of_speech="noun",
    ),
    # French - Beginner
    SeedWord(
        language="french",
        level="beginner",
        word="bonjour",
        translation="hello or good morning",
        pronunciation_hint="bohn-zhoor",
        example_sentence="Bonjour, comment allez-vous?",
        example_translation="Hello, how are you?",
        part_of_speech="interjection",
    ),
    SeedWord(
        language="french",
        level="beginner",
        word="merci",
        translation="thank you",
        pronunciation_hint="mehr-see",
        example_sentence="Merci beaucoup pour le cadeau.",
        example_translation="Thank you very much for the gift.",
        part_of_speech="interjection",
    ),
    SeedWord(
        language="french",
        level="beginner",
        word="maison",
        translation="house",
        pronunciation_hint="meh-zohn",
        example_sentence="La maison est belle et grande.",
        example_translation="The house is beautiful and big.",
        part_of_speech="noun",
    ),
    # German - Beginner
    SeedWord(
        language="german",
        level="beginner",
        word="guten tag",
        translation="good day or hello",
        pronunciation_hint="goo-ten tahk",
        example_sentence="Guten Tag, wie geht es Ihnen?",
        example_translation="Good day, how are you?",
        part_of_speech="phrase",
    ),
    SeedWord(
        language="german",
        level="beginner",
        word="danke",
        translation="thank you",
        pronunciation_hint="dahn-keh",
        example_sentence="Danke schon fur Ihre Hilfe.",
        example_translation="Thank you very much for your help.",
        part_of_speech="interjection",
    ),
    # Hindi - Beginner
    SeedWord(
        language="hindi",
        level="beginner",
        word="namaste",
        translation="greetings or hello",
        pronunciation_hint="nuh-muh-stay",
        example_sentence="Namaste, aap kaise hain?",
        example_translation="Greetings, how are you?",
        part_of_speech="interjection",
    ),
    SeedWord(
        language="hindi",
        level="beginner",
        word="dhanyavad",
        translation="thank you",
        pronunciation_hint="dhun-yuh-vaad",
        example_sentence="Aapki madad ke liye dhanyavad.",
        example_translation="Thank you for your help.",
        part_of_speech="noun",
    ),
    # Japanese - Beginner
    SeedWord(
        language="japanese",
        level="beginner",
        word="arigato",
        translation="thank you",
        pronunciation_hint="ah-ree-gah-toh",
        example_sentence="Tetsudatte kurete arigato.",
        example_translation="Thank you for helping me.",
        part_of_speech="phrase",
    ),
    SeedWord(
        language="japanese",
        level="beginner",
        word="konnichiwa",
        translation="hello or good afternoon",
        pronunciation_hint="kohn-nee-chee-wah",
        example_sentence="Konnichiwa, o-genki desu ka?",
        example_translation="Hello, how are you?",
        part_of_speech="phrase",
    ),
)


def get_seed_words_for(language: str, level: str | None = None) -> list[SeedWord]:
    """Retrieve curated seed words matching language and optional level."""
    target_lang = language.lower()
    target_level = level.lower() if level else None
    return [
        s
        for s in SEED_WORDS
        if s.language == target_lang and (target_level is None or s.level == target_level)
    ]
