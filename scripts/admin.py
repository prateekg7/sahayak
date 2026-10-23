"""Administrative CLI for operator maintenance, quarantine, and audit (T13.3).

Commands:
    inspect-user <user_id_or_sub>
    flag-question <question_id> --reason <reason>
    quarantine-topic <topic_id_or_name>
    replay-dead-letter [--id <event_id> | --all]
    audit-log [--limit 50]
    set-flag <flag_name> [--enable | --disable] [--rollout <0-100>]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sahayak.core.audit import AuditLogger, AuditLogRecord
from sahayak.core.config import get_settings
from sahayak.core.events import DeadLetterEventRecord, OutboxEventRecord
from sahayak.core.flags import FeatureFlagRecord, UserPreferenceRecord
from sahayak.modules.academics.models import Question, QuestionStatus, Topic
from sahayak.shared.users.models import User, UserIdentity


async def inspect_user(session: AsyncSession, identifier: str) -> None:
    """Inspect user profile, external identities, and module preferences."""
    audit = AuditLogger()
    user: User | None = None

    # Check if identifier is a UUID
    try:
        user_uuid = uuid.UUID(identifier)
        stmt = select(User).where(User.id == user_uuid)
        res = await session.execute(stmt)
        user = res.scalars().first()
    except ValueError:
        pass

    # If not found, lookup by identity subject
    if user is None:
        stmt_ident = select(UserIdentity).where(UserIdentity.subject == identifier)
        res_ident = await session.execute(stmt_ident)
        ident = res_ident.scalars().first()
        if ident is not None:
            user = await session.get(User, ident.user_id)

    if user is None:
        print(f"Error: User '{identifier}' not found.", file=sys.stderr)
        sys.exit(1)

    # Fetch identities
    ident_stmt = select(UserIdentity).where(UserIdentity.user_id == user.id)
    ident_res = await session.execute(ident_stmt)
    identities = list(ident_res.scalars().all())

    # Fetch preferences
    pref_stmt = select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user.id)
    pref_res = await session.execute(pref_stmt)
    pref = pref_res.scalars().first()
    disabled_mods = pref.disabled_modules if pref else []

    # Record admin audit
    await audit.log(
        session=session,
        action="inspect_user",
        resource=str(user.id),
        user_id=user.id,
    )
    await session.commit()

    print(f"User ID:    {user.id}")
    print(f"Locale:     {user.locale}")
    print(f"Timezone:   {user.timezone}")
    print(f"Created At: {user.created_at.isoformat()}")
    print("Identities:")
    for i in identities:
        print(f"  - Issuer: {i.issuer}, Subject: {i.subject}")
    print(f"Disabled Modules: {', '.join(disabled_mods) if disabled_mods else 'None'}")


async def flag_question(session: AsyncSession, question_id_str: str, reason: str) -> None:
    """Flag a question, incrementing flag count and quarantining if threshold reached."""
    audit = AuditLogger()
    try:
        qid = uuid.UUID(question_id_str)
    except ValueError:
        print(f"Error: Invalid question UUID '{question_id_str}'.", file=sys.stderr)
        sys.exit(1)

    stmt = select(Question).where(Question.id == qid)
    res = await session.execute(stmt)
    q = res.scalars().first()

    if q is None:
        print(f"Error: Question {qid} not found.", file=sys.stderr)
        sys.exit(1)

    q.flag_count += 1
    if q.flag_count >= 3:
        q.status = QuestionStatus.QUARANTINED
        action_desc = "quarantined (threshold >= 3)"
    else:
        q.status = QuestionStatus.FLAGGED
        action_desc = f"flagged ({q.flag_count}/3)"

    await audit.log(
        session=session,
        action="flag_question",
        resource=f"{qid}:{reason}",
    )
    await session.commit()
    print(f"Question {qid} {action_desc}. Reason: {reason}")


async def quarantine_topic(session: AsyncSession, topic_identifier: str) -> None:
    """Quarantine an entire academic topic and all its associated questions."""
    audit = AuditLogger()
    topic: Topic | None = None

    try:
        topic_uuid = uuid.UUID(topic_identifier)
        topic = await session.get(Topic, topic_uuid)
    except ValueError:
        pass

    if topic is None:
        stmt = select(Topic).where(
            (func.lower(Topic.topic_key) == topic_identifier.lower())
            | (func.lower(Topic.display_name) == topic_identifier.lower())
        )
        res = await session.execute(stmt)
        topic = res.scalars().first()

    if topic is None:
        print(f"Error: Topic '{topic_identifier}' not found.", file=sys.stderr)
        sys.exit(1)

    # Quarantine all questions for this topic
    q_stmt = select(Question).where(Question.topic_id == topic.id)
    q_res = await session.execute(q_stmt)
    questions = list(q_res.scalars().all())

    for q in questions:
        q.status = QuestionStatus.QUARANTINED

    await audit.log(
        session=session,
        action="quarantine_topic",
        resource=str(topic.id),
    )
    await session.commit()
    print(
        f"Quarantined topic '{topic.display_name}' ({topic.id}) "
        f"and {len(questions)} associated questions."
    )


async def replay_dead_letter(
    session: AsyncSession, event_id_str: str | None, replay_all: bool
) -> None:
    """Replay dead letter event(s) back into the active outbox."""
    audit = AuditLogger()
    stmt = select(DeadLetterEventRecord)

    if not replay_all:
        if not event_id_str:
            print("Error: Specify either --id <event_id> or --all.", file=sys.stderr)
            sys.exit(1)
        try:
            eid = uuid.UUID(event_id_str)
            stmt = stmt.where(DeadLetterEventRecord.id == eid)
        except ValueError:
            print(f"Error: Invalid event UUID '{event_id_str}'.", file=sys.stderr)
            sys.exit(1)

    res = await session.execute(stmt)
    dead_events = list(res.scalars().all())

    if not dead_events:
        print("No matching dead-letter events found.")
        return

    for de in dead_events:
        # Re-insert into active outbox
        new_outbox = OutboxEventRecord(
            id=uuid.uuid4(),
            aggregate=de.aggregate,
            type=de.type,
            payload=de.payload,
            retry_count=0,
            processed_at=None,
            last_error=None,
        )
        session.add(new_outbox)
        await session.delete(de)

        await audit.log(
            session=session,
            action="replay_dead_letter",
            resource=str(de.id),
        )

    await session.commit()
    print(f"Successfully replayed {len(dead_events)} dead-letter event(s) to outbox.")


async def list_audit_logs(session: AsyncSession, limit: int = 50) -> None:
    """List recent administrative and security audit trail entries."""
    stmt = select(AuditLogRecord).order_by(AuditLogRecord.created_at.desc()).limit(limit)
    res = await session.execute(stmt)
    records = list(res.scalars().all())

    if not records:
        print("No audit log records found.")
        return

    print(f"{'TIMESTAMP':<26} {'ACTION':<24} {'USER_ID':<38} {'RESOURCE'}")
    print("-" * 110)
    for r in records:
        uid = str(r.user_id) if r.user_id else "SYSTEM"
        ts = r.created_at.isoformat()
        print(f"{ts:<26} {r.action:<24} {uid:<38} {r.resource}")


async def set_feature_flag(
    session: AsyncSession,
    name: str,
    enabled: bool,
    rollout: int,
    user_override: str | None,
) -> None:
    """Update or create a persistent feature flag."""
    audit = AuditLogger()
    clean_name = name.strip()
    clean_rollout = max(0, min(100, rollout))

    overrides: dict[str, bool] = {}
    if user_override:
        parts = user_override.split("=")
        if len(parts) == 2:
            overrides[parts[0].strip()] = parts[1].strip().lower() in ("true", "1", "yes")

    stmt = select(FeatureFlagRecord).where(FeatureFlagRecord.name == clean_name)
    res = await session.execute(stmt)
    record = res.scalars().first()

    if record is None:
        record = FeatureFlagRecord(
            name=clean_name,
            enabled=enabled,
            rollout_percentage=clean_rollout,
            user_overrides=overrides,
        )
        session.add(record)
    else:
        record.enabled = enabled
        record.rollout_percentage = clean_rollout
        if overrides:
            updated_overrides = dict(record.user_overrides)
            updated_overrides.update(overrides)
            record.user_overrides = updated_overrides
        record.updated_at = datetime.now(UTC)

    await audit.log(
        session=session,
        action="set_feature_flag",
        resource=f"{clean_name}:enabled={enabled}:rollout={clean_rollout}",
    )
    await session.commit()
    print(f"Feature flag '{clean_name}' set: enabled={enabled}, rollout={clean_rollout}%.")


async def async_main() -> None:
    """Asynchronous entry point for admin CLI."""
    parser = argparse.ArgumentParser(description="Sahayak Platform Admin CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # inspect-user
    p_user = subparsers.add_parser("inspect-user", help="Inspect user and identities.")
    p_user.add_argument("user", help="User UUID or external IdP subject.")

    # flag-question
    p_flag = subparsers.add_parser("flag-question", help="Flag an academic question.")
    p_flag.add_argument("question_id", help="Question UUID.")
    p_flag.add_argument("--reason", default="content_quality", help="Reason for flagging.")

    # quarantine-topic
    p_topic = subparsers.add_parser("quarantine-topic", help="Quarantine an entire topic.")
    p_topic.add_argument("topic", help="Topic UUID, key, or display name.")

    # replay-dead-letter
    p_replay = subparsers.add_parser("replay-dead-letter", help="Replay dead-letter events.")
    p_replay.add_argument("--id", dest="event_id", default=None, help="Dead-letter event UUID.")
    p_replay.add_argument("--all", action="store_true", help="Replay all dead-letter events.")

    # audit-log
    p_audit = subparsers.add_parser("audit-log", help="Display recent audit trail.")
    p_audit.add_argument("--limit", type=int, default=50, help="Max entries to show.")

    # set-flag
    p_flag_cmd = subparsers.add_parser("set-flag", help="Manage feature flags.")
    p_flag_cmd.add_argument("name", help="Feature flag name.")
    p_flag_cmd.add_argument(
        "--enable", dest="enabled", action="store_true", default=True, help="Enable flag."
    )
    p_flag_cmd.add_argument("--disable", dest="enabled", action="store_false", help="Disable flag.")
    p_flag_cmd.add_argument("--rollout", type=int, default=100, help="Rollout percent (0-100).")
    p_flag_cmd.add_argument(
        "--override", default=None, help="User override in format <user_id>=<true|false>."
    )

    args = parser.parse_args()

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            if args.command == "inspect-user":
                await inspect_user(session, args.user)
            elif args.command == "flag-question":
                await flag_question(session, args.question_id, args.reason)
            elif args.command == "quarantine-topic":
                await quarantine_topic(session, args.topic)
            elif args.command == "replay-dead-letter":
                await replay_dead_letter(session, args.event_id, args.all)
            elif args.command == "audit-log":
                await list_audit_logs(session, args.limit)
            elif args.command == "set-flag":
                await set_feature_flag(
                    session, args.name, args.enabled, args.rollout, args.override
                )
    finally:
        await engine.dispose()


def main() -> None:
    """CLI entry point wrapper."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
