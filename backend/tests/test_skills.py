"""The skill files in agent/skills/: they parse, name real metrics, and cover the
app's suggested questions."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.prompt import system_prompt
from agent.skills import SKILLS_DIR, SkillError, load_skills, parse_skill, skills_prompt
from app.main import app

FRONTEND_TEXTS = Path(__file__).resolve().parents[2] / "frontend" / "data" / "lang" / "en.json"


@pytest.fixture(scope="module")
def ctx():
    with TestClient(app):
        yield app.state.agent_context


def test_every_skill_file_parses():
    skills = load_skills(strict=True)
    assert any(s.is_general for s in skills), "answer-style.md is missing"
    assert sum(not s.is_general for s in skills) >= 7


def test_backticked_metrics_exist(ctx):
    allowed = set(ctx.metrics) | {"microzone"}
    for skill in load_skills(strict=True):
        for name in re.findall(r"`([a-z0-9_]+)`", skill.body):
            assert name in allowed, f"{skill.name}.md: unknown metric `{name}`"


def test_app_suggestions_have_a_playbook():
    if not FRONTEND_TEXTS.exists():
        pytest.skip("frontend texts not found")
    texts = json.loads(FRONTEND_TEXTS.read_text(encoding="utf-8"))
    suggestions = [v for k, v in texts.items() if k.startswith("askai.suggest") and k[-1].isdigit()]
    covered = {q for s in load_skills(strict=True) for q in s.questions}
    assert suggestions
    assert [q for q in suggestions if q not in covered] == []


def test_skills_are_in_the_system_prompt(ctx):
    prompt = system_prompt(ctx)
    assert "Show on map" in prompt
    assert "Questions like:" in prompt
    assert "Where can we build green improvements quickly?" in prompt


def test_broken_skill_is_reported(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("no header here", encoding="utf-8")
    with pytest.raises(SkillError, match=r"bad\.md"):
        parse_skill(bad)
    # Outside tests a broken file is skipped instead of breaking the chat.
    good = tmp_path / "good.md"
    good.write_text("---\ntitle: Good\nquestions:\n  - Q?\n---\nDo this.", encoding="utf-8")
    skills = load_skills(tmp_path)
    assert [s.name for s in skills] == ["good"]
    assert skills_prompt(skills).count("Questions like:") == 1


def test_skills_dir_is_inside_the_backend():
    # The Dockerfile copies backend/, so skills must live there to be deployed.
    assert SKILLS_DIR.is_relative_to(Path(__file__).resolve().parents[1])
