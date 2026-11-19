"""Unit tests for the coding question. They import the student's solution.py.

Each test function is one mark in the rubric row "Coding question: unit tests".
"""
from solution import total


def test_total_of_numbers():
    assert total([4, 5, 6]) == 15


def test_total_of_empty_list():
    assert total([]) == 0


def test_total_with_negative_numbers():
    assert total([-3, 10, 0, -7]) == 0
