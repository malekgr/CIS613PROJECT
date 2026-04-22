def classify_triangle(a, b, c):
    """
    Classify a triangle based on its side lengths.

    Returns:
        'equilateral' if all sides are equal
        'isosceles'   if exactly two sides are equal
        'scalene'     if all sides are different
        'invalid'     if the sides do not form a valid triangle
    """
    if a <= 0 or b <= 0 or c <= 0:
        return "invalid"
    if a + b <= c or a + c <= b or b + c <= a:
        return "invalid"
    if a == b == c:
        return "equilateral"
    if a == b or b == c or a == c:
        return "isosceles"
    return "scalene"


def factorial(n):
    """
    Return the factorial of n (n >= 0).
    Raises TypeError for non-integer input.
    Raises ValueError for negative input.
    """
    if not isinstance(n, int):
        raise TypeError("n must be an integer")
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0:
        return 1
    return n * factorial(n - 1)


def is_prime(n):
    """
    Return True if n is a prime number, False otherwise.
    Any integer less than 2 is not prime.
    """
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, int(n ** 0.5) + 1, 2):
        if n % i == 0:
            return False
    return True


def gcd(a, b):
    """
    Return the greatest common divisor of a and b using Euclid's algorithm.
    Both a and b must be non-negative integers.
    Raises ValueError if either argument is negative.
    """
    if a < 0 or b < 0:
        raise ValueError("Arguments must be non-negative")
    while b:
        a, b = b, a % b
    return a


def reverse_string(s):
    """
    Return the reverse of the given string s.
    Works with empty strings and single characters.

    Args:
        s (str): The input string.

    Returns:
        str: The reversed string.
    """
    return s[::-1]


def is_palindrome(s):
    """
    Return True if s is a palindrome, False otherwise.
    Comparison is case-insensitive and ignores leading/trailing whitespace.

    Args:
        s (str): The input string.

    Returns:
        bool: True if s is a palindrome, False otherwise.
    """
    cleaned = s.strip().lower()
    return cleaned == cleaned[::-1]


def max_in_list(lst):
    """
    Return the maximum value in the list.
    Raises ValueError if the list is empty.

    Args:
        lst (list): A non-empty list of comparable elements.

    Returns:
        The maximum element in lst.
    """
    if not lst:
        raise ValueError("List must not be empty")
    return max(lst)


def count_vowels(s):
    """
    Return the number of vowel characters (a, e, i, o, u) in s.
    Both uppercase and lowercase vowels are counted.
    Non-alphabetic characters are ignored.

    Args:
        s (str): The input string.

    Returns:
        int: The count of vowels in s.
    """
    return sum(1 for ch in s if ch.lower() in "aeiou")
