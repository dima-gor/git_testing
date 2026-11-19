"""Task 2: top_three holds the three highest scores, highest first, without changing scores."""


def test_top_three_values():
    """top_three is [95, 91, 88]"""
    assert isinstance(top_three, list), "[Task 2] top_three should be a list."
    assert top_three == [95, 91, 88], "[Task 2] top_three should hold the three highest scores, highest first."


def test_scores_unchanged():
    """scores is not changed"""
    assert top_three is not None, "[Task 2] Fill in top_three first."
    assert scores == [72, 95, 64, 88, 91, 57, 80], "[Task 2] Don't change the scores list."
