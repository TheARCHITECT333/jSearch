"""Shared test fixtures: a scripted fake LLM, app client, and a local
HTTP server serving the deterministic browser fixture site.

Tests never touch real Ollama/OpenAI or external career sites.
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import threading
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.llm.base import LLM, LLMError
from app.schemas import CandidateProfile

FIXTURE_DIR = Path(__file__).parent / "browser_fixture"


class FakeLLM(LLM):
    """Returns queued responses in order. Entries may be strings (raw LLM
    output) or exceptions (raised to simulate failures).

    Mimics real providers: generate() after close() raises RuntimeError,
    exactly like a closed httpx client - so lifecycle bugs (using an LLM
    after its search phase closed it) fail tests instead of hiding.
    """

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, system: str, user: str) -> str:
        if self._closed:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        async with self._lock:
            self.calls.append((system, user))
            if not self._responses:
                raise LLMError("FakeLLM ran out of scripted responses.")
            item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        self._closed = True


VALID_PROFILE_JSON = """
{
  "name": "Shubh Sharma",
  "summary": "Backend engineer",
  "target_roles": ["Backend Engineer", "Software Engineer"],
  "skills": {
    "languages": ["Go", "Python"],
    "frameworks": ["FastAPI"],
    "databases": ["PostgreSQL"],
    "cloud": ["AWS"],
    "infrastructure": ["Docker"],
    "tools": ["git"],
    "other": ["distributed systems"]
  },
  "experience": [
    {"company": "Acme", "title": "Senior Engineer", "duration": "2020-present",
     "highlights": ["Built payment APIs"]}
  ],
  "education": [{"institution": "IIT", "degree": "B.Tech", "year": "2019"}],
  "years_experience": 6,
  "preferred_locations": ["Bangalore", "Remote"]
}
"""

VALID_MATCH_JSON = """
{
  "overall_score": 94,
  "role_fit": 96,
  "skill_fit": 95,
  "experience_fit": 90,
  "location_fit": 100,
  "matching_skills": ["Go", "AWS", "PostgreSQL"],
  "missing_skills": ["Kubernetes"],
  "reason": "Strong backend engineering match."
}
"""


def valid_profile() -> CandidateProfile:
    import json

    return CandidateProfile.model_validate(json.loads(VALID_PROFILE_JSON))


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM([VALID_PROFILE_JSON])


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    """Point the app at an isolated SQLite file for this test."""
    from app import db

    await db.init_db(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    yield
    await db.dispose_db()


@pytest_asyncio.fixture
async def client(temp_db):
    """HTTP client bound to the FastAPI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session")
def fixture_server():
    """Serve backend/tests/browser_fixture on a random local port."""

    class _QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):  # silence test output
            pass

    handler = functools.partial(_QuietHandler, directory=str(FIXTURE_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def llm_factory_for(fake_llm):
    """Factory compatible with SearchManager.start_search(llm_factory=...)."""

    def factory(_config):
        return fake_llm

    return factory
