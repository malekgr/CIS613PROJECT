import pytest
from dataset.sample_functions import factorial


# --- Base cases ---

def test_factorial_zero():
    assert factorial(0) == 1

def test_factorial_one():
    assert factorial(1) == 1

def test_factorial_two():
    assert factorial(2) == 2


# --- Small values ---

def test_factorial_three():
    assert factorial(3) == 6

def test_factorial_four():
    assert factorial(4) == 24

def test_factorial_five():
    assert factorial(5) == 120

def test_factorial_ten():
    assert factorial(10) == 3628800


# --- Larger values ---

def test_factorial_twelve():
    assert factorial(12) == 479001600

def test_factorial_twenty():
    assert factorial(20) == 2432902008176640000


# --- Error cases ---

def test_factorial_negative_raises_value_error():
    with pytest.raises(ValueError):
        factorial(-1)

def test_factorial_large_negative_raises_value_error():
    with pytest.raises(ValueError):
        factorial(-100)

def test_factorial_float_raises_type_error():
    with pytest.raises(TypeError):
        factorial(3.5)

def test_factorial_string_raises_type_error():
    with pytest.raises(TypeError):
        factorial("5")

def test_factorial_none_raises_type_error():
    with pytest.raises(TypeError):
        factorial(None)
