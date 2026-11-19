"""Task 1: average(numbers).

These tests run inside the student's notebook, after all their cells, so
they use `average` by name. You can also run them locally against the
solution notebook. Each test function is one mark in the rubric row "Task 1".
"""


def test_average_of_list():
    assert "average" in globals(), "[Task 1] Define a function called average."
    assert average([2, 4, 6]) == 4, "[Task 1] average([2, 4, 6]) should be 4."


def test_average_with_decimals():
    assert abs(average([1, 2]) - 1.5) < 1e-9, "[Task 1] average([1, 2]) should be 1.5."


def test_average_of_empty_list():
    assert average([]) == 0, "[Task 1] For an empty list, return 0."
