def total(numbers):
    result = 0
    for number in numbers:
        result += number
    return result


if __name__ == "__main__":
    n = int(input())
    numbers = [int(input()) for _ in range(n)]
    print(total(numbers))
