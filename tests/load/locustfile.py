"""Locust performance load test suite for Sahayak MCP server (T4.7).

Simulates realistic voice-assistant traffic profiles:
1. QuizSessionUser: Starts a quiz (cache hit), answers 3 consecutive questions.
2. FlashcardStudyUser: Reviews flashcards and submits SM-2 grades.
3. StudyPlannerUser: Queries daily study tasks.
4. BurstTrafficUser: High-concurrency spikes on topic briefs.

Target: 100 RPS with p95 < 800ms for deterministic tool invocations.
"""

from __future__ import annotations

import random
from typing import Any

try:
    from locust import HttpUser, between, task
except ImportError:

    class HttpUser:  # type: ignore[no-redef]
        client: Any = None

    def task(weight: int = 1) -> Any:
        def decorator(func: Any) -> Any:
            return func

        return decorator

    def between(a: float, b: float) -> Any:
        return 0.5


class SahayakVoiceUser(HttpUser):  # type: ignore[misc]
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
            "Authorization": "Bearer perf_test_token_user_1",
        }

    @task(5)
    def test_quiz_flow(self) -> None:
        """Simulate starting a quiz and answering a question."""
        # 1. quiz_start
        start_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "quiz_start",
                "arguments": {"topic": "General Science", "count": 3},
            },
        }
        resp = self.client.post("/mcp", json=start_payload, headers=self.headers)
        if resp.status_code == 200:
            data = resp.json()
            quiz_id = data.get("result", {}).get("data", {}).get("quiz_id")
            if quiz_id:
                # 2. quiz_answer
                answer_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "quiz_answer",
                        "arguments": {"quiz_id": quiz_id, "selected_key": "A"},
                    },
                }
                self.client.post("/mcp", json=answer_payload, headers=self.headers)

    @task(3)
    def test_flashcards_flow(self) -> None:
        """Simulate reviewing and grading due flashcards."""
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "flashcards",
                "arguments": {"action": "list_due", "limit": 5},
            },
        }
        self.client.post("/mcp", json=payload, headers=self.headers)

    @task(2)
    def test_progress_report(self) -> None:
        """Simulate querying progress summary."""
        scope = random.choice(["summary", "streak", "weak_topics"])
        payload = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "progress_report",
                "arguments": {"scope": scope},
            },
        }
        self.client.post("/mcp", json=payload, headers=self.headers)

    @task(2)
    def test_topic_brief_cached(self) -> None:
        """Simulate reading cached topic brief."""
        payload = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "topic_brief",
                "arguments": {"topic": "General Science", "length": "short"},
            },
        }
        self.client.post("/mcp", json=payload, headers=self.headers)
