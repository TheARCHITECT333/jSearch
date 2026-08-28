"""Persistence tests: profile cache, seen-job reuse, search history.

The promise being tested: running the SAME search twice spends (almost) no
LLM calls the second time, and results survive backend restarts.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

import app.services.search as search_module
from app.schemas import CompanyInput, DiscoveredJob
from tests.conftest import VALID_MATCH_JSON, VALID_PROFILE_JSON, FakeLLM

LATEX = r"\documentclass{article}\begin{document}Go developer.\end{document}"
FAKE_LLM_CONFIG = {
    "provider": "ollama",
    "base_url": "http://llm.test/ollama",
    "model": "fake-model",
}
GOODCORP = {"name": "GoodCorp", "careers_url": "https://good.example/jobs"}

JOB_URL = "https://good.example/jobs/123"


def one_job(url: str = JOB_URL) -> list[dict]:
    return [
        {
            "title": "Backend Engineer",
            "url": url,
            "location": "Bangalore",
            "description": "Go + AWS",
            "requirements": ["Go"],
            "source_url": "https://good.example/jobs",
        }
    ]


def _browser_cm():
    @contextlib.asynccontextmanager
    async def cm():
        yield object()

    return cm  # the FACTORY - SearchManager does `async with browser_factory()`


async def run_search(client, monkeypatch, llm: FakeLLM, jobs=None):
    """Stub discovery + LLM factory, POST a search, wait for completion."""

    async def fake_discover(llm_arg, company, profile, browser, *, freshness="any",
                            locations=None, context_gate=None,
                            on_progress=None, on_status=None):
        return [
            DiscoveredJob.model_validate(j)
            for j in (jobs if jobs is not None else one_job())
        ]

    monkeypatch.setattr(search_module, "discover_company_jobs", fake_discover)
    manager = search_module.SearchManager(browser_factory=_browser_cm())
    monkeypatch.setattr(search_module, "search_manager", manager)
    monkeypatch.setattr("app.main.build_llm", lambda config: llm)

    started = await client.post(
        "/api/search",
        json={
            "resume_latex": LATEX,
            "companies": [GOODCORP],
            "llm": FAKE_LLM_CONFIG,
        },
    )
    assert started.status_code == 200
    search_id = started.json()["search_id"]

    deadline = asyncio.get_event_loop().time() + 5.0
    while True:
        response = await client.get(f"/api/search/{search_id}")
        status = response.json()
        if status["status"] not in ("queued", "running"):
            return search_id, status
        assert asyncio.get_event_loop().time() < deadline
        await asyncio.sleep(0.02)


def _count_calls(llm: FakeLLM, marker: str) -> int:
    return sum(1 for sys_prompt, _ in llm.calls if marker in sys_prompt)


class TestProfileCache:
    async def test_same_resume_extracts_once(self, client, monkeypatch):
        llm_a = FakeLLM([VALID_PROFILE_JSON, VALID_MATCH_JSON])
        _id1, s1 = await run_search(client, monkeypatch, llm_a)
        assert s1["status"] == "completed"
        assert _count_calls(llm_a, "resume-parsing") == 1

        # Second run has NO profile response scripted - it must not need one.
        llm_b = FakeLLM([VALID_MATCH_JSON])
        _id2, s2 = await run_search(client, monkeypatch, llm_b)
        assert s2["status"] == "completed"
        assert len(s2["results"]) == 1
        assert _count_calls(llm_b, "resume-parsing") == 0


class TestSeenJobReuse:
    async def test_second_run_skips_matcher_and_reuses_scores(
        self, client, monkeypatch
    ):
        llm_a = FakeLLM([VALID_PROFILE_JSON, VALID_MATCH_JSON])
        id1, s1 = await run_search(client, monkeypatch, llm_a)
        assert s1["status"] == "completed"
        assert _count_calls(llm_a, "strict technical recruiter") == 1

        # Second run: profile cached AND job already matched -> zero LLM calls.
        llm_b = FakeLLM([])
        id2, s2 = await run_search(client, monkeypatch, llm_b)
        assert s2["status"] == "completed"
        assert llm_b.calls == []

        assert len(s2["results"]) == 1
        first, reused = s1["results"][0], s2["results"][0]
        assert reused["job_url"] == first["job_url"]
        assert reused["match"]["overall_score"] == first["match"]["overall_score"]

        history = (await client.get("/api/searches")).json()
        assert {id1, id2} <= {row["id"] for row in history}

    async def test_expired_ttl_rematches(self, client, monkeypatch):
        llm_a = FakeLLM([VALID_PROFILE_JSON, VALID_MATCH_JSON])
        await run_search(client, monkeypatch, llm_a)

        # TTL of zero: nothing counts as recently-seen -> matcher re-runs.
        monkeypatch.setattr(search_module, "SEEN_JOB_TTL_DAYS", 0.0)

        llm_b = FakeLLM([VALID_MATCH_JSON])  # profile cached; matcher re-runs
        _id2, s2 = await run_search(client, monkeypatch, llm_b)
        assert s2["status"] == "completed"
        assert _count_calls(llm_b, "strict technical recruiter") == 1


class TestHistoryAcrossRestarts:
    async def test_completed_search_readable_after_memory_loss(
        self, client, monkeypatch
    ):
        llm = FakeLLM([VALID_PROFILE_JSON, VALID_MATCH_JSON])
        search_id, _status = await run_search(client, monkeypatch, llm)

        # Simulate a restart: replace the manager (empty in-memory state).
        monkeypatch.setattr(
            search_module,
            "search_manager",
            search_module.SearchManager(browser_factory=_browser_cm()),
        )

        # The history write lands right after the in-memory completion;
        # give it its moment.
        restored = None
        deadline = asyncio.get_event_loop().time() + 3.0
        while asyncio.get_event_loop().time() < deadline:
            response = await client.get(f"/api/search/{search_id}")
            if response.status_code == 200:
                restored = response.json()
                if restored.get("results"):
                    break
            await asyncio.sleep(0.02)

        assert restored is not None and restored["status"] == "completed"
        assert len(restored["results"]) == 1
        assert restored["results"][0]["match"]["overall_score"] == 94

    async def test_orphaned_running_search_marked_failed_on_startup(
        self, client, temp_db
    ):
        from app import db
        from app.models import Search as SearchRow
        from app.services import store

        async with db.session_factory()() as session:
            session.add(SearchRow(id="orphan-1", status="running"))
            await session.commit()

        # Re-running startup logic mimics an app restart.
        await db.init_db(db.current_url())

        restored = await store.load_search_history("orphan-1")
        assert restored is not None
        assert restored.status == "failed"
        assert restored.error is not None and "restarted" in restored.error

    async def test_unknown_id_still_404s(self, client):
        response = await client.get("/api/search/never-existed")
        assert response.status_code == 404


def _head_revision() -> str:
    """Whatever the newest migration is today - so these tests keep asserting
    "fully migrated" instead of being rewritten on every new revision."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.db import MIGRATIONS_DIR

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config).get_current_head()


class TestMigrationAdoption:
    """Upgrading a database that predates Alembic.

    Every other test starts from an empty temp file, which is exactly why
    this case escaped: a real deployment has a volume full of tables that
    the old `Base.metadata.create_all` made, with no `alembic_version`.
    Alembic reads that as "empty" and tries to create tables that exist.
    """

    @staticmethod
    def _make_legacy_db(path) -> str:
        """Build the database exactly as it looked before Alembic existed.

        Not `Base.metadata.create_all` - that builds TODAY's schema, so every
        later revision would then fail on "duplicate column". The pre-Alembic
        schema is by definition revision 0001, so run that and remove the
        version table the old code never had.
        """
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect, text

        from app.db import MIGRATIONS_DIR

        url = f"sqlite:///{path}"
        config = Config()
        config.set_main_option("script_location", str(MIGRATIONS_DIR))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "0001")

        engine = create_engine(url)
        try:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE alembic_version"))
            assert "alembic_version" not in inspect(engine).get_table_names()
            assert "searches" in inspect(engine).get_table_names()
        finally:
            engine.dispose()
        return url

    async def test_pre_alembic_database_starts_without_error(self, tmp_path):
        from app import db

        url = self._make_legacy_db(tmp_path / "legacy.db")

        await db.init_db(url)  # used to raise "table searches already exists"

        assert db.current_url() is not None
        await db.dispose_db()

    async def test_adopted_database_is_stamped_and_keeps_its_data(self, tmp_path):
        from sqlalchemy import create_engine, text

        from app import db
        from app.models import Search as SearchRow
        from app.services import store

        url = self._make_legacy_db(tmp_path / "legacy.db")

        # A row written before the upgrade must survive it.
        engine = create_engine(url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO searches (id, status, freshness, "
                        "locations_json, companies_json, created_at) VALUES "
                        "('old-1', 'completed', 'any', '[]', '[]', "
                        "'2026-01-01 00:00:00')"
                    )
                )
        finally:
            engine.dispose()

        await db.init_db(url)

        # Adopted at the baseline, then carried forward to head - not
        # left unmanaged, and not frozen at the revision it was adopted at.
        async with db.session_factory()() as session:
            revision = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
        assert revision == _head_revision()

        restored = await store.load_search_history("old-1")
        assert restored is not None and restored.id == "old-1"
        assert SearchRow is not None
        await db.dispose_db()

    async def test_recovers_from_a_half_finished_first_upgrade(self, tmp_path):
        """Alembic creates `alembic_version` BEFORE running the first
        revision, so a startup that failed part-way leaves the table present
        but empty. Checking only that the table exists is not enough - the
        recorded revision is what matters.
        """
        from sqlalchemy import create_engine, text

        from app import db

        url = self._make_legacy_db(tmp_path / "legacy.db")

        # Exactly the wreckage a failed first start leaves behind.
        engine = create_engine(url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
        finally:
            engine.dispose()

        await db.init_db(url)

        async with db.session_factory()() as session:
            revision = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
        assert revision == _head_revision()
        await db.dispose_db()

    async def test_incomplete_legacy_schema_is_refused_loudly(self, tmp_path):
        """Half a schema must not be silently stamped - the missing tables
        would never be created and would fail at query time instead."""
        from sqlalchemy import create_engine

        from app import db
        from app.models import Base, Search

        path = tmp_path / "partial.db"
        url = f"sqlite:///{path}"
        engine = create_engine(url)
        try:
            Base.metadata.create_all(engine, tables=[Search.__table__])
        finally:
            engine.dispose()

        with pytest.raises(RuntimeError, match="incomplete pre-Alembic schema"):
            await db.init_db(url)

    async def test_fresh_database_is_untouched_by_the_adoption_path(self, tmp_path):
        from sqlalchemy import text

        from app import db

        await db.init_db(f"sqlite:///{tmp_path / 'fresh.db'}")

        async with db.session_factory()() as session:
            revision = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
        assert revision == _head_revision()
        await db.dispose_db()

    async def test_second_start_is_a_no_op(self, tmp_path):
        """Restarting the container must not re-run or re-stamp anything."""
        from app import db

        url = self._make_legacy_db(tmp_path / "legacy.db")
        await db.init_db(url)
        await db.init_db(url)
        await db.init_db(url)

        assert await db.ping()
        await db.dispose_db()


class TestDatabaseUrlNormalization:
    async def test_plain_sqlite_url_upgrades_to_async_driver(self, tmp_path):
        from app import db

        # Exactly what docker-compose.yml documents:
        url = f"sqlite:///{tmp_path / 'plain.db'}"
        await db.init_db(url)

        assert str(db._engine.url).startswith("sqlite+aiosqlite")

    def test_normalize_url_forms(self):
        from app.db import _async_url

        assert _async_url("sqlite:////data/jobhunter.db") == (
            "sqlite+aiosqlite:////data/jobhunter.db"
        )
        assert _async_url("sqlite:///./jobhunter.db").startswith("sqlite+aiosqlite")
        # Already-async and non-SQLite URLs pass through untouched.
        assert _async_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"
        assert _async_url(
            "postgresql+asyncpg://u:p@localhost/db"
        ) == "postgresql+asyncpg://u:p@localhost/db"

    def test_sync_url_strips_async_drivers(self):
        """Alembic runs through a blocking driver against the same database."""
        from app.db import _sync_url

        assert _sync_url("sqlite+aiosqlite:////data/x.db") == "sqlite:////data/x.db"
        assert _sync_url("sqlite:///./x.db") == "sqlite:///./x.db"
        assert _sync_url("postgresql+asyncpg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
