"""Skills: how the agent should answer, written as Markdown files in agent/skills/.

Each file is one skill:

    ---
    title: Where green infrastructure is needed most
    questions:
      - Where is green infrastructure needed most?
      - Which areas need greenery the most?
    ---
    Steps and answer format, in plain Markdown.

- A skill WITH questions is a playbook: the agent follows it when a question is
  like one of the examples.
- A skill WITHOUT questions is a general rule for every answer (answer-style.md).
- README.md and files starting with "_" (drafts) are skipped.

The files are read again for every question, so a running local server picks
up edits straight away. On Render, push the change and the next deploy has it.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent / "skills"


@dataclass(frozen=True)
class Skill:
    name: str  # file name without .md
    title: str
    questions: tuple[str, ...]
    body: str

    @property
    def is_general(self) -> bool:
        return not self.questions


class SkillError(ValueError):
    """A skill file that can't be read; the message names the file and the problem."""


def parse_skill(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise SkillError(f"{path.name}: must start with a '---' header (title, questions)")
    end = text.find("\n---", 4)
    if end == -1:
        raise SkillError(f"{path.name}: the '---' header is not closed")
    header, body = text[4:end], text[end + 4 :].strip()

    title = ""
    questions: list[str] = []
    in_questions = False
    for line in header.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if in_questions and stripped.startswith("- "):
            questions.append(stripped[2:].strip().strip("\"'"))
            continue
        key, sep, value = stripped.partition(":")
        if not sep:
            raise SkillError(f"{path.name}: can't read header line {line!r}")
        key, value = key.strip(), value.strip()
        in_questions = key == "questions"
        if key == "title":
            title = value.strip("\"'")
        elif key != "questions":
            raise SkillError(f"{path.name}: unknown header field {key!r} (use title, questions)")

    if not title:
        raise SkillError(f"{path.name}: the header needs a title")
    if not body:
        raise SkillError(f"{path.name}: the skill has no text under the header")
    return Skill(path.stem, title, tuple(q for q in questions if q), body)


def load_skills(directory: Path = SKILLS_DIR, *, strict: bool = False) -> tuple[Skill, ...]:
    """All skills, general ones first, then by file name.

    strict=True raises on a broken file (tests); otherwise it is logged and skipped,
    so one bad edit can't take the chat down.
    """
    skills = []
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md" or path.name.startswith("_"):
            continue
        try:
            skills.append(parse_skill(path))
        except (SkillError, OSError, UnicodeDecodeError) as exc:
            if strict:
                raise
            log.warning("Skill skipped: %s", exc)
    return tuple(sorted(skills, key=lambda s: (not s.is_general, s.name)))


def skills_prompt(skills: tuple[Skill, ...]) -> str:
    """The skills as one block of the system prompt ('' when there are none)."""
    parts = []
    general = [s for s in skills if s.is_general]
    playbooks = [s for s in skills if not s.is_general]
    for skill in general:
        parts.append(f"{skill.title} (applies to every answer):\n{skill.body}")
    if playbooks:
        lines = [
            "Question playbooks. When a question matches or is close to one of these "
            "examples, follow that playbook's steps and answer format. For other "
            "questions, use the closest playbook as a guide."
        ]
        for skill in playbooks:
            examples = "; ".join(f'"{q}"' for q in skill.questions)
            lines.append(f"\n## {skill.title}\nQuestions like: {examples}\n{skill.body}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
