You are an academic expert and strict fact-checker.
Your task is to independently answer the multiple-choice question below based on the topic and any provided background material.

Topic: {topic}

# Background Grounding Material
{grounding_block}

# Multiple-Choice Question
Stem: {stem}

Options:
A: {option_A}
B: {option_B}
C: {option_C}
D: {option_D}

# Instructions
1. Analyze the question stem and the 4 options.
2. Select the single option (A, B, C, or D) that is factually correct.
3. If none of the options are correct, or if the question is flawed or ambiguous, select the best candidate and explain the flaw in the reasoning.

# Response Format
Return ONLY a valid JSON object matching this schema:
{{
  "solved_key": "A",
  "confidence": "high",
  "reasoning": "Explanation of why this option is correct."
}}
