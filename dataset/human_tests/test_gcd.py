import pytest
from dataset.sample_functions import gcd


# --- Basic cases ---

def test_gcd_coprime():
    assert gcd(7, 13) == 1

def test_gcd_one_divides_other():
    assert gcd(12, 4) == 4

def test_gcd_equal_values():
    assert gcd(9, 9) == 9

def test_gcd_small():
    assert gcd(6, 4) == 2

def test_gcd_large():
    assert gcd(270, 192) == 6


# --- Zero cases ---

def test_gcd_first_zero():
    assert gcd(0, 5) == 5

def test_gcd_second_zero():
    assert gcd(8, 0) == 8

def test_gcd_both_zero():
    assert gcd(0, 0) == 0


# --- Commutativity ---

def test_gcd_commutative():
    assert gcd(48, 18) == gcd(18, 48)


# --- Larger primes ---

def test_gcd_large_primes():
    assert gcd(97, 89) == 1

def test_gcd_multiple():
    assert gcd(100, 75) == 25


# --- Error cases ---

def test_gcd_negative_first_raises():
    with pytest.raises(ValueError):
        gcd(-1, 5)

def test_gcd_negative_second_raises():
    with pytest.raises(ValueError):
        gcd(5, -1)

def test_gcd_both_negative_raises():
    with pytest.raises(ValueError):
        gcd(-4, -6)
