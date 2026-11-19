"""Parse quiz.md into multiple choice questions and one coding question.

Format:

    ## Question heading (the question)
    Optional extra lines of question text.
    - [ ] wrong answer
    - [x] the one correct answer
      > Hint: shown when the student picks this answer
    - [ ] another wrong answer

    ## Coding question: <title>
    Markdown text of the coding question, any length.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TITLE_LIMIT = 60
CODING_PREFIX = "coding question:"
ANSWER_RE = re.compile(r"^- \[( |x|X)\] (.*)$")
HINT_RE = re.compile(r"^\s+> ?Hint: ?(.*)$")


class QuizFormatError(Exception):
    """quiz.md does not follow the expected format."""


@dataclass
class Answer:
    text: str
    hint: str = ""


@dataclass
class Question:
    title: str
    text: str
    answers: list[Answer]
    correct: int


@dataclass
class CodingQuestion:
    title: str
    text: str


@dataclass
class _Block:
    heading: str
    lines: list[str] = field(default_factory=list)


def _split_blocks(markdown: str) -> list[_Block]:
    blocks: list[_Block] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            blocks.append(_Block(heading=line[3:].strip()))
        elif blocks:
            blocks[-1].lines.append(line)
    return blocks


def _parse_question(block: _Block) -> Question:
    text_lines = [block.heading]
    answers: list[Answer] = []
    correct: list[int] = []
    for line in block.lines:
        m = ANSWER_RE.match(line)
        if m:
            if m.group(1).lower() == "x":
                correct.append(len(answers))
            answers.append(Answer(text=m.group(2).strip()))
            continue
        h = HINT_RE.match(line)
        if h and answers:
            answers[-1].hint = h.group(1).strip()
            continue
        if not answers:
            text_lines.append(line)
    if not answers:
        raise QuizFormatError(f'Question "{block.heading}" has no answers ("- [ ] ..." lines).')
    if len(correct) != 1:
        raise QuizFormatError(
            f'Question "{block.heading}" must have exactly one correct answer ("- [x] ..."), found {len(correct)}.'
        )
    return Question(
        title=block.heading[:TITLE_LIMIT],
        text="\n".join(text_lines).strip(),
        answers=answers,
        correct=correct[0],
    )


def parse_quiz(markdown: str) -> tuple[list[Question], CodingQuestion]:
    questions: list[Question] = []
    coding: list[CodingQuestion] = []
    for block in _split_blocks(markdown):
        if block.heading.lower().startswith(CODING_PREFIX):
            title = block.heading[len(CODING_PREFIX):].strip()
            coding.append(CodingQuestion(title=title, text="\n".join(block.lines).strip()))
        else:
            questions.append(_parse_question(block))
    if len(coding) != 1:
        raise QuizFormatError(
            f'quiz.md needs exactly one "## Coding question: <title>" section, found {len(coding)}.'
        )
    return questions, coding[0]
