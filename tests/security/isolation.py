"""User isolation testing harness and auto-discovery verification (T1.9)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer


@dataclass(frozen=True)
class ToolIsolationSpec:
    """Security and user isolation specification for an MCP tool."""

    name: str
    allows_anonymous: bool
    required_scopes: list[str] = field(default_factory=list)
    sample_args: dict[str, Any] = field(default_factory=dict)
    custom_isolation_check: (
        Callable[[ClientSession, ClientSession], Coroutine[Any, Any, None]] | None
    ) = None
    setup_sample_args: Callable[[ClientSession], Coroutine[Any, Any, dict[str, Any]]] | None = None


ISOLATION_REGISTRY: dict[str, ToolIsolationSpec] = {}


def register_isolation_spec(spec: ToolIsolationSpec) -> None:
    """Register isolation test coverage for a specific tool."""
    ISOLATION_REGISTRY[spec.name] = spec


def get_untested_tools(server: MCPServer) -> list[str]:
    """Return all tool names registered on the server that lack an isolation spec."""
    tools = server._tool_manager.list_tools()
    registered_names = set(ISOLATION_REGISTRY.keys())
    return [t.name for t in tools if t.name not in registered_names]


def make_test_jwt(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "",
    expires_in: int = 3600,
) -> str:
    """Helper to mint a valid test token."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": "https://auth.example.com",
        "aud": "sahayak-api",
        "exp": now + expires_in,
        "iat": now,
        "nbf": now,
        "scope": scope,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "sec-test-key"})


async def assert_user_isolation(
    spec: ToolIsolationSpec,
    app: Any,
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Assert that a tool strictly enforces anonymous/authenticated isolation."""
    asgi_transport = httpx.ASGITransport(app=app)

    # 1. Test anonymous access
    async with (
        httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
        streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (r, w),
        ClientSession(r, w) as session,
    ):
        await session.initialize()
        args = (
            await spec.setup_sample_args(session)
            if spec.setup_sample_args is not None
            else spec.sample_args
        )
        res = await session.call_tool(spec.name, arguments=args)
        data = json.loads(getattr(res.content[0], "text", "{}"))

        if spec.allows_anonymous:
            assert data.get("ok") is True, f"Anonymous tool {spec.name} failed: {data}"
        else:
            assert data.get("ok") is False, (
                f"Protected tool {spec.name} should fail anonymously: {data}"
            )
            assert data.get("error_code") == "auth_required"

    # 2. If tool requires scopes, test missing scope rejection
    if not spec.allows_anonymous and spec.required_scopes:
        token_wrong_scope = make_test_jwt(rsa_key, sub="user-wrong-scope", scope="unrelated.scope")
        headers = {"Authorization": f"Bearer {token_wrong_scope}"}

        async with (
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers
            ) as client,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                r,
                w,
            ),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            args = (
                await spec.setup_sample_args(session)
                if spec.setup_sample_args is not None
                else spec.sample_args
            )
            res = await session.call_tool(spec.name, arguments=args)
            data = json.loads(getattr(res.content[0], "text", "{}"))
            assert data.get("ok") is False
            assert data.get("error_code") == "forbidden"

    # 3. Test cross-user isolation when authenticated
    if not spec.allows_anonymous or spec.custom_isolation_check is not None:
        token_user_a = make_test_jwt(
            rsa_key, sub="user-a", scope=" ".join(spec.required_scopes or ["academics.read"])
        )
        token_user_b = make_test_jwt(
            rsa_key, sub="user-b", scope=" ".join(spec.required_scopes or ["academics.read"])
        )

        headers_a = {"Authorization": f"Bearer {token_user_a}"}
        headers_b = {"Authorization": f"Bearer {token_user_b}"}

        async with (
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers_a
            ) as client_a,
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers_b
            ) as client_b,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client_a)) as (
                ra,
                wa,
            ),
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client_b)) as (
                rb,
                wb,
            ),
            ClientSession(ra, wa) as session_a,
            ClientSession(rb, wb) as session_b,
        ):
            await session_a.initialize()
            await session_b.initialize()

            # Execute standard call under User A
            args_a = (
                await spec.setup_sample_args(session_a)
                if spec.setup_sample_args is not None
                else spec.sample_args
            )
            res_a = await session_a.call_tool(spec.name, arguments=args_a)
            data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
            assert data_a.get("ok") is True, f"User A failed to call {spec.name}: {data_a}"

            # Execute standard call under User B
            args_b = (
                await spec.setup_sample_args(session_b)
                if spec.setup_sample_args is not None
                else spec.sample_args
            )
            res_b = await session_b.call_tool(spec.name, arguments=args_b)
            data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
            assert data_b.get("ok") is True, f"User B failed to call {spec.name}: {data_b}"

            # If custom isolation check provided, run it
            if spec.custom_isolation_check is not None:
                await spec.custom_isolation_check(session_a, session_b)


# Register initial built-in tool isolation specifications
register_isolation_spec(
    ToolIsolationSpec(
        name="ping_echo",
        allows_anonymous=True,
        sample_args={"message": "hello security"},
    )
)

register_isolation_spec(
    ToolIsolationSpec(
        name="quiz_start",
        allows_anonymous=True,
        sample_args={"topic": "General Science", "num_questions": 3},
    )
)


async def _quiz_answer_setup(session: ClientSession) -> dict[str, Any]:
    res = await session.call_tool("quiz_start", {"topic": "General Science", "num_questions": 3})
    data = json.loads(getattr(res.content[0], "text", "{}"))
    quiz_id = data.get("data", {}).get("quiz_id", "")
    return {"quiz_id": quiz_id, "answer": "A"}


async def _quiz_answer_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A starts a quiz
    res_a = await session_a.call_tool(
        "quiz_start", {"topic": "General Science", "num_questions": 3}
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    quiz_id_a = data_a.get("data", {}).get("quiz_id", "")
    assert quiz_id_a, "Failed to get quiz_id for User A"

    # User B tries to answer User A's quiz
    res_b = await session_b.call_tool("quiz_answer", {"quiz_id": quiz_id_a, "answer": "A"})
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is False, (
        f"User B should be forbidden from answering User A's quiz: {data_b}"
    )
    assert data_b.get("error_code") == "forbidden"


register_isolation_spec(
    ToolIsolationSpec(
        name="quiz_answer",
        allows_anonymous=True,
        setup_sample_args=_quiz_answer_setup,
        custom_isolation_check=_quiz_answer_cross_user_isolation,
    )
)


async def _flashcards_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A creates a flashcard
    res_a = await session_a.call_tool(
        "flashcards",
        {"action": "add", "front": "Mitosis stage 1", "back": "Prophase", "deck": "Biology"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to add flashcard: {data_a}"
    card_id = data_a.get("data", {}).get("card", {}).get("card_id", "")
    assert card_id, "Failed to get card_id from User A's response"

    # User B lists due cards - User A's card must not appear
    res_b_list = await session_b.call_tool("flashcards", {"action": "list_due"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_card_ids = [c.get("card_id") for c in data_b_list.get("data", {}).get("cards", [])]
    assert card_id not in b_card_ids, "User A's card leaked into User B's due list"

    # User B attempts to grade User A's card - must fail with not_found
    res_b_grade = await session_b.call_tool(
        "flashcards",
        {"action": "grade", "card_id": card_id, "rating": "good"},
    )
    data_b_grade = json.loads(getattr(res_b_grade.content[0], "text", "{}"))
    assert data_b_grade.get("ok") is False
    assert data_b_grade.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="flashcards",
        allows_anonymous=False,
        sample_args={"action": "list_due"},
        custom_isolation_check=_flashcards_cross_user_isolation,
    )
)


async def _study_plan_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A creates a study plan
    res_a = await session_a.call_tool(
        "study_plan",
        {
            "action": "create",
            "goal": "Organic Chemistry",
            "exam_date": "2026-11-20",
            "topics": ["Alkanes", "Alkenes"],
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to create study plan: {data_a}"
    plan_id = data_a.get("data", {}).get("plan_id", "")
    assert plan_id, "Failed to get plan_id from User A's response"

    # User B lists study plans - User A's plan must not appear
    res_b_list = await session_b.call_tool("study_plan", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_plan_ids = [p.get("plan_id") for p in data_b_list.get("data", {}).get("plans", [])]
    assert plan_id not in b_plan_ids, "User A's plan leaked into User B's list"

    # User B attempts to access User A's plan today tasks with plan_id - must fail with not_found
    res_b_today = await session_b.call_tool(
        "study_plan",
        {"action": "today", "plan_id": plan_id},
    )
    data_b_today = json.loads(getattr(res_b_today.content[0], "text", "{}"))
    assert data_b_today.get("ok") is False
    assert data_b_today.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="study_plan",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_study_plan_cross_user_isolation,
    )
)


async def _progress_report_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # 1. User B reads initial quiz count
    res_b_before = await session_b.call_tool("progress_report", {"scope": "summary"})
    data_b_before = json.loads(getattr(res_b_before.content[0], "text", "{}"))
    assert data_b_before.get("ok") is True, (
        f"User B initial progress_report failed: {data_b_before}"
    )
    quizzes_b_before = data_b_before.get("data", {}).get("total_quizzes", 0)

    # 2. User A starts a quiz on seeded topic General Science
    res_start = await session_a.call_tool(
        "quiz_start",
        {"topic": "General Science", "num_questions": 3},
    )
    data_start = json.loads(getattr(res_start.content[0], "text", "{}"))
    assert data_start.get("ok") is True, f"User A quiz_start failed: {data_start}"

    # 3. User B calls progress_report - User B's total quizzes is unchanged
    res_b_after = await session_b.call_tool("progress_report", {"scope": "summary"})
    data_b_after = json.loads(getattr(res_b_after.content[0], "text", "{}"))
    assert data_b_after.get("ok") is True, f"User B progress_report after failed: {data_b_after}"
    quizzes_b_after = data_b_after.get("data", {}).get("total_quizzes", 0)
    assert quizzes_b_after == quizzes_b_before, (
        "User A's new quiz leaked into User B's total_quizzes count"
    )


register_isolation_spec(
    ToolIsolationSpec(
        name="progress_report",
        allows_anonymous=False,
        sample_args={"scope": "summary"},
        custom_isolation_check=_progress_report_cross_user_isolation,
    )
)

register_isolation_spec(
    ToolIsolationSpec(
        name="topic_brief",
        allows_anonymous=True,
        sample_args={"topic": "General Science", "length": "short"},
    )
)


async def _tasks_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A creates a task
    res_a = await session_a.call_tool(
        "tasks",
        {
            "action": "create",
            "title": "Private task for User A",
            "due_date": "tomorrow",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    task_id = data_a.get("data", {}).get("task", {}).get("id")
    assert task_id

    # User B lists tasks - User A's task must not appear
    res_b_list = await session_b.call_tool("tasks", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_task_ids = [t.get("id") for t in data_b_list.get("data", {}).get("tasks", [])]
    assert task_id not in b_task_ids

    # User B attempts to complete User A's task - must fail with not_found
    res_b_comp = await session_b.call_tool(
        "tasks",
        {"action": "complete", "task_id": task_id},
    )
    data_b_comp = json.loads(getattr(res_b_comp.content[0], "text", "{}"))
    assert data_b_comp.get("ok") is False
    assert data_b_comp.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="tasks",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_tasks_cross_user_isolation,
    )
)


async def _habits_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A creates a habit
    res_a = await session_a.call_tool(
        "habits",
        {
            "action": "create",
            "name": "User A Private Meditation",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    habit_id = data_a.get("data", {}).get("habit", {}).get("id")
    assert habit_id

    # User B lists habits - User A's habit must not appear
    res_b_list = await session_b.call_tool("habits", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_habit_ids = [h.get("id") for h in data_b_list.get("data", {}).get("habits", [])]
    assert habit_id not in b_habit_ids

    # User B attempts to log User A's habit - must fail with not_found
    res_b_log = await session_b.call_tool(
        "habits",
        {"action": "log", "habit_id": habit_id},
    )
    data_b_log = json.loads(getattr(res_b_log.content[0], "text", "{}"))
    assert data_b_log.get("ok") is False
    assert data_b_log.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="habits",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_habits_cross_user_isolation,
    )
)


async def _notes_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A creates a note
    res_a = await session_a.call_tool(
        "notes",
        {
            "action": "add",
            "content": "Secret password phrase 12345",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    note_id = data_a.get("data", {}).get("note", {}).get("id")
    assert note_id

    # User B searches notes for phrase - User A's note must not appear
    res_b_search = await session_b.call_tool(
        "notes",
        {"action": "search", "query": "Secret"},
    )
    data_b_search = json.loads(getattr(res_b_search.content[0], "text", "{}"))
    assert data_b_search.get("ok") is True
    b_notes = data_b_search.get("data", {}).get("notes", [])
    b_note_ids = [n.get("id") for n in b_notes]
    assert note_id not in b_note_ids

    # User B attempts to delete User A's note - must fail with not_found
    res_b_del = await session_b.call_tool(
        "notes",
        {"action": "delete", "note_id": note_id},
    )
    data_b_del = json.loads(getattr(res_b_del.content[0], "text", "{}"))
    assert data_b_del.get("ok") is False
    assert data_b_del.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="notes",
        allows_anonymous=False,
        sample_args={"action": "add", "content": "Sample note content"},
        custom_isolation_check=_notes_cross_user_isolation,
    )
)


async def _focus_timer_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A starts a 25 minute focus session
    res_a = await session_a.call_tool(
        "focus_timer",
        {
            "action": "start",
            "duration_minutes": 25,
            "task_label": "User A Private Study",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    session_id = data_a.get("data", {}).get("session", {}).get("id")
    assert session_id

    # User B checks status - User B must have no active session
    res_b_stat = await session_b.call_tool(
        "focus_timer",
        {"action": "status"},
    )
    data_b_stat = json.loads(getattr(res_b_stat.content[0], "text", "{}"))
    assert data_b_stat.get("ok") is True
    assert "not have an active focus session" in data_b_stat.get("spoken_summary", "")

    # User B attempts to stop session - must fail with not_found
    res_b_stop = await session_b.call_tool(
        "focus_timer",
        {"action": "stop"},
    )
    data_b_stop = json.loads(getattr(res_b_stop.content[0], "text", "{}"))
    assert data_b_stop.get("ok") is False
    assert data_b_stop.get("error_code") == "not_found"

    # User A stops their own session
    res_a_stop = await session_a.call_tool(
        "focus_timer",
        {"action": "stop"},
    )
    data_a_stop = json.loads(getattr(res_a_stop.content[0], "text", "{}"))
    assert data_a_stop.get("ok") is True


register_isolation_spec(
    ToolIsolationSpec(
        name="focus_timer",
        allows_anonymous=False,
        sample_args={"action": "status"},
        custom_isolation_check=_focus_timer_cross_user_isolation,
    )
)


async def _daily_briefing_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A creates a task due today
    res_a_task = await session_a.call_tool(
        "tasks",
        {
            "action": "create",
            "title": "Private briefing task for User A",
            "due_date": "today",
        },
    )
    data_a_task = json.loads(getattr(res_a_task.content[0], "text", "{}"))
    assert data_a_task.get("ok") is True

    # User A daily briefing includes the task
    res_a_brief = await session_a.call_tool("daily_briefing", {})
    data_a_brief = json.loads(getattr(res_a_brief.content[0], "text", "{}"))
    assert data_a_brief.get("ok") is True
    assert data_a_brief.get("data", {}).get("tasks_due_count", 0) >= 1

    # User B daily briefing does NOT include User A's task
    res_b_brief = await session_b.call_tool("daily_briefing", {})
    data_b_brief = json.loads(getattr(res_b_brief.content[0], "text", "{}"))
    assert data_b_brief.get("ok") is True
    b_tasks = data_b_brief.get("data", {}).get("tasks_due", [])
    assert "Private briefing task for User A" not in b_tasks


register_isolation_spec(
    ToolIsolationSpec(
        name="daily_briefing",
        allows_anonymous=False,
        sample_args={},
        custom_isolation_check=_daily_briefing_cross_user_isolation,
    )
)


async def _expense_log_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A logs an expense
    res_a = await session_a.call_tool(
        "expense_log",
        {
            "action": "add",
            "amount": 250,
            "currency": "INR",
            "category": "groceries",
            "note": "Private Organic Groceries",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    exp_id = data_a.get("data", {}).get("expense", {}).get("id")
    assert exp_id

    # User B lists expenses - User A's expense must not appear
    res_b_list = await session_b.call_tool("expense_log", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_ids = [e.get("id") for e in data_b_list.get("data", {}).get("expenses", [])]
    assert exp_id not in b_ids

    # User B attempts to delete User A's expense - must fail with not_found
    res_b_del = await session_b.call_tool(
        "expense_log",
        {"action": "delete", "expense_id": exp_id},
    )
    data_b_del = json.loads(getattr(res_b_del.content[0], "text", "{}"))
    assert data_b_del.get("ok") is False
    assert data_b_del.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="expense_log",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_expense_log_cross_user_isolation,
    )
)
