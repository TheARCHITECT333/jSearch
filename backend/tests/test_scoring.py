"""Resume scoring + PDF upload. No real LLM, no real GitHub."""

import json

import pymupdf

from tests.conftest import FakeLLM

LLM_CONFIG = {"provider": "ollama", "base_url": "http://fake", "model": "fake-model"}
RESUME = "Jane Doe - backend engineer. Built a distributed queue in Go. " * 3

EVALUATION = json.dumps(
    {
        "scores": {
            "open_source": {"score": 40, "max": 35, "evidence": "none"},
            "self_projects": {"score": 20, "max": 30, "evidence": "queue"},
            "production": {"score": 15, "max": 25, "evidence": "work"},
            "technical_skills": {"score": 8, "max": 10, "evidence": "go"},
        },
        "bonus_points": {"total": 2, "breakdown": "linkedin"},
        "deductions": {"total": 3, "reasons": "no links"},
        "key_strengths": ["Go"],
        "areas_for_improvement": ["links"],
    }
)


async def test_score_clamps_and_totals(client, monkeypatch):
    fake = FakeLLM([EVALUATION])
    monkeypatch.setattr("app.main.build_llm", lambda config: fake)
    r = await client.post("/api/score", json={"resume_latex": RESUME, "llm": LLM_CONFIG})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["categories"][0]["score"] == 35  # capped
    assert body["total"] == 35 + 20 + 15 + 8 + 2 - 3
    assert body["github"] is None  # no GitHub link -> no network call
    assert "SCORING CRITERIA" in fake.calls[0][1]


async def test_score_requires_llm(client):
    r = await client.post("/api/score", json={"resume_latex": RESUME})
    assert r.status_code == 422


def _pdf(text: str, link: str | None = None) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    if link:
        page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 60, 200, 80), "uri": link})
    return doc.tobytes()


async def test_pdf_to_text_keeps_hidden_links(client):
    pdf = _pdf("Jane Doe, Software Engineer, Go and Python, five years", "https://github.com/janedoe")
    r = await client.post("/api/resume/pdf", content=pdf, headers={"Content-Type": "application/pdf"})
    assert r.status_code == 200, r.text
    assert "Jane Doe" in r.json()["text"]
    assert "https://github.com/janedoe" in r.json()["text"]


async def test_pdf_rejects_garbage(client):
    r = await client.post("/api/resume/pdf", content=b"not a pdf at all")
    assert r.status_code == 422


async def test_level_picks_rubric_and_caps(client, monkeypatch):
    senior = json.loads(EVALUATION)
    senior["scores"]["production"]["score"] = 60  # senior cap is 55
    fake = FakeLLM([json.dumps(senior)])
    monkeypatch.setattr("app.main.build_llm", lambda config: fake)
    r = await client.post(
        "/api/score", json={"resume_latex": RESUME, "llm": LLM_CONFIG, "level": "senior"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["level"] == "senior"
    caps = {c["key"]: c["max"] for c in body["categories"]}
    assert caps == {"open_source": 15, "self_projects": 10, "production": 55, "technical_skills": 20}
    assert {c["key"]: c["score"] for c in body["categories"]}["production"] == 55
    assert "Senior Software Engineer" in fake.calls[0][1]
    assert "Software Intern" not in fake.calls[0][1]


async def test_unknown_level_rejected(client):
    r = await client.post(
        "/api/score", json={"resume_latex": RESUME, "llm": LLM_CONFIG, "level": "staff"}
    )
    assert r.status_code == 422
