"""SQLite persistence for job/search/profile history.

The single deliberate deviation from the original "no database" constraint:
the backend persists JOB HISTORY, SEARCH HISTORY and CACHED PROFILES so
repeat searches don't waste LLM time re-evaluating jobs already seen.
Active search execution stays in memory.

Schema changes go through Alembic (`migrations/`), never `create_all`, so
an existing database file keeps working after the models change.

The engine is created lazily so tests can point it at a temp file.
Postgres is a connection-string swap away (models use generic types).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import event, text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Search

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "sqlite:///./jobhunter.db"
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _async_url(url: str) -> str:
    """Accept any documented SQLite/Postgres URL form; async engines need an
    async driver, so plain `sqlite:` is upgraded to `sqlite+aiosqlite:`."""
    if url.startswith("sqlite:") and not url.startswith("sqlite+"):
        return url.replace("sqlite:", "sqlite+aiosqlite:", 1)
    return url


def _sync_url(url: str) -> str:
    """The same database through a blocking driver, for Alembic."""
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enable_sqlite_pragmas(engine: AsyncEngine) -> None:
    """WAL + a busy timeout, so a reader never blocks the writer and a
    concurrent write waits instead of raising 'database is locked'."""

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Revision whose schema is identical to what the pre-Alembic
# `Base.metadata.create_all` produced.
BASELINE_REVISION = "0001"

# The tables that `create_all` used to create, all four together.
_BASELINE_TABLES = frozenset({"searches", "jobs", "matches", "profiles"})


def _adoption_state(sync_url: str) -> tuple[bool, set[str]]:
    """Does this database have our schema but no revision recorded?

    Two ways to end up here, and both must be handled:

    1. The database was created by the old `Base.metadata.create_all`, so it
       has our tables and no `alembic_version` table at all.
    2. A previous startup already failed this way. Alembic creates
       `alembic_version` *before* running the first revision, so the table
       exists but is EMPTY - checking only for its presence is not enough.

    In both cases the recorded revision is None while the tables are really
    there, and replaying revision 0001 would fail on "table already exists".
    """
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine, inspect

    engine = create_engine(sync_url)
    try:
        tables = set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            revision = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()

    return revision is None and bool(tables & _BASELINE_TABLES), tables


def _run_migrations(sync_url: str) -> str | None:
    """Bring the database up to head. Blocking - call via a thread.

    Returns the revision we ended up on, so startup can log one useful line
    instead of Alembic's dozen.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", sync_url)

    needs_adoption, tables = _adoption_state(sync_url)
    if needs_adoption:
        missing = _BASELINE_TABLES - tables
        if missing:
            # Some of the baseline tables but not all: stamping would leave
            # the rest missing forever. Refuse rather than half-fix it.
            raise RuntimeError(
                "This database has an incomplete pre-Alembic schema "
                f"(missing: {', '.join(sorted(missing))}). Back it up and "
                "remove it so it can be recreated, or restore the missing "
                "tables before starting again."
            )
        logger.warning(
            "adopting a pre-Alembic database: stamping it at revision %s "
            "(its schema already matches). No data is touched.",
            BASELINE_REVISION,
            extra={"event": "db.adopted", "revision": BASELINE_REVISION},
        )
        command.stamp(config, BASELINE_REVISION)

    command.upgrade(config, "head")

    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


async def init_db(url: str | None = None) -> None:
    """Create the engine and migrate to head. Safe to call multiple times;
    a new URL replaces the previous engine (used by tests)."""
    global _engine, _session_factory

    await dispose_db()

    resolved = url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    revision = await asyncio.to_thread(_run_migrations, _sync_url(resolved))

    _engine = create_async_engine(_async_url(resolved), echo=False)
    if _engine.dialect.name == "sqlite":
        _enable_sqlite_pragmas(_engine)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    # Searches orphaned by a restart can never finish: mark them.
    async with _session_factory() as session:
        result = await session.execute(
            update(Search)
            .where(Search.status.in_(["queued", "running"]))
            .values(
                status="failed",
                error="Backend restarted mid-search.",
                completed_at=_now(),
            )
        )
        await session.commit()
        orphaned = result.rowcount or 0

    if orphaned:
        logger.warning(
            "marked %d search(es) failed - they were interrupted by a restart",
            orphaned,
            extra={"event": "db.orphans_swept", "orphaned": orphaned},
        )

    logger.info(
        "database ready at revision %s (%s)",
        revision or "none",
        _engine.url.render_as_string(hide_password=True),
        extra={"event": "db.ready", "revision": revision},
    )


async def dispose_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def ping() -> bool:
    """True when the database answers a trivial query - used by /api/health."""
    if _engine is None:
        return False
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        logger.warning("database ping failed", exc_info=True)
        return False


def current_url() -> str | None:
    return str(_engine.url) if _engine is not None else None


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _session_factory
