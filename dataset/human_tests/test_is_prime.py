import pytest
from dataset.sample_functions import is_prime


# --- Not prime: less than 2 ---

def test_is_prime_negative():
    assert is_prime(-5) is False

def test_is_prime_zero():
    assert is_prime(0) is False

def test_is_prime_one():
    assert is_prime(1) is False


# --- Small primes ---

def test_is_prime_two():
    assert is_prime(2) is True

def test_is_prime_three():
    assert is_prime(3) is True

def test_is_prime_five():
    assert is_prime(5) is True

def test_is_prime_seven():
    assert is_prime(7) is True


# --- Small composites ---

def test_is_prime_four():
    assert is_prime(4) is False

def test_is_prime_six():
    assert is_prime(6) is False

def test_is_prime_nine():
    assert is_prime(9) is False

def test_is_prime_twenty_five():
    assert is_prime(25) is False


# --- Larger primes ---

def test_is_prime_97():
    assert is_prime(97) is True

def test_is_prime_101():
    assert is_prime(101) is True


# --- Larger composites ---

def test_is_prime_100():
    assert is_prime(100) is False

def test_is_prime_square_of_prime():
    assert is_prime(49) is False
