# Alexa+ Multi-Turn Test Plans & Utterance Scripts

This document defines the repeatable test procedures for testing Sahayak in the **Alexa Developer Console Web Simulator**, **Local Inspector**, and **Physical Echo Devices** per tasks.md T4.6.

---

## 1. Dialog 1: Quiz Happy Path (3-Question Quiz)

| Turn | User Spoken Utterance | Target MCP Tool | Expected Voice Response Criteria |
|---|---|---|---|
| 1 | *"Alexa, quiz me on photosynthesis"* | `quiz_start(topic="photosynthesis", count=3)` | Question 1 is read aloud with options (A, B, C, D). **Correct answer must NOT be revealed.** Question count stated. |
| 2 | *"Option B"* | `quiz_answer(quiz_id=..., selected_key="B")` | Feedback given ("That's correct! Photosynthesis occurs in chloroplasts."). Question 2 is read immediately. |
| 3 | *"It's A"* | `quiz_answer(quiz_id=..., selected_key="A")` | Feedback given. Question 3 is read immediately. |
| 4 | *"Option C"* | `quiz_answer(quiz_id=..., selected_key="C")` | Feedback given. Final score spoken: *"You finished the quiz! You scored 3 out of 3."* Next step suggested (review cards or check progress). |

---

## 2. Dialog 2: Speech Recognition & Ambiguous Answers

| Turn | User Spoken Utterance | Target MCP Tool | Expected Voice Response Criteria |
|---|---|---|---|
| 1 | *"Alexa, answer 'chlorophyll'"* (content instead of letter) | `quiz_answer(quiz_id=..., selected_text="chlorophyll")` | Fuzzy matcher matches "chlorophyll" to Option B text. Grades correctly without frustrating the user. |
| 2 | *"Second option"* (ordinal) | `quiz_answer(quiz_id=..., selected_key="B")` | Fuzzy matcher maps ordinal "second" $\rightarrow$ "B". |
| 3 | *"I don't know, skip"* | `quiz_answer(quiz_id=..., selected_key="skip")` | Records incorrect/skipped. Reveals correct answer and moves to next question. |

---

## 3. Dialog 3: Expired Quiz & Invalid Handles

| Turn | User Spoken Utterance | Target MCP Tool | Expected Voice Response Criteria |
|---|---|---|---|
| 1 | Resuming a quiz after 2 hours (TTL expired) | `quiz_answer(quiz_id="expired-id", ...)` | Spoken message: *"This quiz session has expired. Would you like to start a fresh quiz on photosynthesis?"* (No internal stack traces). |

---

## 4. Dialog 4: Unlinked vs. Linked Account Authorization Matrix

| Tool | Anonymous (Unlinked) Expected Result | Linked (Authenticated) Expected Result |
|---|---|---|
| `quiz_start` | Allowed (`ok: true`, quiz created with `user_id: null`) | Allowed (`ok: true`, quiz saved to profile) |
| `quiz_answer` | Allowed (`ok: true`, grading works) | Allowed (`ok: true`, stats updated in `topic_stats`) |
| `topic_brief` | Allowed (`ok: true`, brief spoken) | Allowed (`ok: true`) |
| `flashcards` | **Blocked:** `auth_required` error with prompt to link account | Allowed (`ok: true`) |
| `study_plan` | **Blocked:** `auth_required` error with prompt to link account | Allowed (`ok: true`) |
| `progress_report` | **Blocked:** `auth_required` error with prompt to link account | Allowed (`ok: true`) |

---

## 5. Dialog 5: Spaced Repetition Flashcards

| Turn | User Spoken Utterance | Target MCP Tool | Expected Voice Response Criteria |
|---|---|---|---|
| 1 | *"Alexa, review my flashcards"* | `flashcards(action="review_next")` | Front prompt read: *"What is the primary function of ribosomes?"* |
| 2 | *"Alexa, flip card"* | `flashcards(action="reveal", card_id=...)` | Back prompt read: *"Protein synthesis. How well did you remember this: 1, 2, 3, 4, or 5?"* |
| 3 | *"Grade 4"* | `flashcards(action="grade", card_id=..., rating=4)` | SM-2 updated: *"Got it! Next review scheduled in 6 days. You have 2 cards remaining today."* |

---

## 6. Dialog 6: Exam Study Planner

| Turn | User Spoken Utterance | Target MCP Tool | Expected Voice Response Criteria |
|---|---|---|---|
| 1 | *"Alexa, make a study plan for my chemistry exam on the 15th"* | `study_plan(action="create", ...)` | Generates schedule: *"I've created your study plan for Chemistry through November 15th. You have 14 study days, with dedicated review on the final two days. Today's task: Organic Nomenclature."* |
| 2 | *"What should I study today?"* | `study_plan(action="today")` | Lists today's tasks and duration in minutes. |
| 3 | *"Mark task 1 done"* | `study_plan(action="update", mark_done=true, task_id=...)` | Confirms task completed and updates remaining minutes. |

---

## 7. Dialog 7: Progress Report & Weak Topics Quiz

| Turn | User Spoken Utterance | Target MCP Tool | Expected Voice Response Criteria |
|---|---|---|---|
| 1 | *"Alexa, how am I doing in my quizzes?"* | `progress_report(scope="summary")` | Spoken: *"You're on a 5-day study streak! You've answered 42 questions across 4 topics with an 81% overall accuracy."* |
| 2 | *"What are my weak topics?"* | `progress_report(scope="weak_topics")` | Spoken: *"Your lowest accuracy topics are Cell Division at 45% and Thermodynamics at 60%."* |
| 3 | *"Quiz me on my weak topics"* | `quiz_start(source="weak_topics")` | Initiates customized quiz focusing on Cell Division and Thermodynamics. |

---

## 8. Dialog 8: Topic Brief

| Turn | User Spoken Utterance | Target MCP Tool | Expected Voice Response Criteria |
|---|---|---|---|
| 1 | *"Give me a quick brief on the French Revolution"* | `topic_brief(topic="French Revolution", length="short")` | Grounded summary $\le 300$ chars with Wikipedia citation. No URLs or markdown spoken. |

---

## 9. Local Inspector & Physical Device Checklists

### Local Inspector Checklist
- [x] All 6 tools discovered (`quiz_start`, `quiz_answer`, `flashcards`, `study_plan`, `progress_report`, `topic_brief`).
- [x] Tool input schemas validate correctly without loose untyped objects.
- [x] Voice response preview widget renders cleanly within 300 character limits.

### Physical Echo Device Checklist
- [x] Speech synthesis does not read URLs (`https://...`), brackets, or markdown formatting (`**`, `##`).
- [x] Numbers read as spoken text ("three out of three", "November 15th").
- [x] Audio prompt ends with clear turn-taking cue ("Option A or B?", "Ready for question two?").

---

## 10. Post-Redeploy Smoke Test (3 Quick Turns)
After any container or add-on redeploy, execute:
1. `topic_brief(topic="General Science")` $\rightarrow$ verifies Wikipedia grounding and LLM routing.
2. `quiz_start(topic="General Science", count=1)` $\rightarrow$ verifies DB question bank and quiz state machine.
3. `progress_report(scope="streak")` $\rightarrow$ verifies authenticated database access and event auditing.
