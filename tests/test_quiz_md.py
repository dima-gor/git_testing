import pytest

from scripts.quiz_md import QuizFormatError, parse_quiz

EXAMPLE = """\
## What does len([1, 2, 3]) return?
- [ ] 2
- [x] 3
  > Hint: Correct, len counts the elements.
- [ ] 4

## Coding question: Sum of a list
Write a program that reads numbers and prints their sum.

Use `input()`.
"""


def test_parses_example():
    questions, coding = parse_quiz(EXAMPLE)
    assert len(questions) == 1
    q = questions[0]
    assert q.title == "What does len([1, 2, 3]) return?"
    assert [a.text for a in q.answers] == ["2", "3", "4"]
    assert q.correct == 1
    assert q.answers[1].hint == "Correct, len counts the elements."
    assert q.answers[0].hint == ""
    assert coding.title == "Sum of a list"
    assert coding.text.startswith("Write a program")
    assert "Use `input()`." in coding.text


def test_extra_question_text_kept():
    md = "## Pick one\nSome context line.\n- [x] a\n- [ ] b\n\n## Coding question: C\nx\n"
    q = parse_quiz(md)[0][0]
    assert q.text == "Pick one\nSome context line."


def test_true_false_kept_in_order():
    md = "## Python is typed?\n- [ ] True\n- [x] False\n\n## Coding question: C\nx\n"
    q = parse_quiz(md)[0][0]
    assert [a.text for a in q.answers] == ["True", "False"]
    assert q.correct == 1


def test_two_correct_answers_error():
    md = "## Bad one\n- [x] a\n- [x] b\n\n## Coding question: C\nx\n"
    with pytest.raises(QuizFormatError) as e:
        parse_quiz(md)
    assert "Bad one" in str(e.value) and "exactly one" in str(e.value)


def test_no_correct_answer_error():
    md = "## None right\n- [ ] a\n- [ ] b\n\n## Coding question: C\nx\n"
    with pytest.raises(QuizFormatError) as e:
        parse_quiz(md)
    assert "None right" in str(e.value)


def test_no_answers_error():
    md = "## Empty\njust text\n\n## Coding question: C\nx\n"
    with pytest.raises(QuizFormatError) as e:
        parse_quiz(md)
    assert "Empty" in str(e.value)


def test_missing_coding_question_error():
    with pytest.raises(QuizFormatError) as e:
        parse_quiz("## Q\n- [x] a\n- [ ] b\n")
    assert "Coding question" in str(e.value)


def test_two_coding_questions_error():
    md = "## Coding question: A\nx\n## Coding question: B\ny\n"
    with pytest.raises(QuizFormatError) as e:
        parse_quiz(md)
    assert "Coding question" in str(e.value)


def test_long_title_truncated():
    heading = "A" * 80
    md = f"## {heading}\n- [x] a\n- [ ] b\n\n## Coding question: C\nx\n"
    q = parse_quiz(md)[0][0]
    assert len(q.title) == 60
    assert heading in q.text
