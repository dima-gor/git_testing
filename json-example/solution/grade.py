def letter_grade(score):
    """Return the letter grade for a score from 0 to 100."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


if __name__ == "__main__":
    score = int(input())
    print(letter_grade(score))
