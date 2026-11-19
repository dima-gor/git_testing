"""Tests run inside the student's notebook."""


def test_double():
    assert double(3) == 6, "[Task 1] double(3) should return 6."


def test_total():
    assert total == 6, "[Task 1] total should be the sum of the list."


if __name__ == "__main__":
    print("run with pytest")
