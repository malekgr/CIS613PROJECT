import pytest
from dataset.sample_functions import classify_triangle


# --- Equilateral ---

def test_equilateral_basic():
    assert classify_triangle(3, 3, 3) == "equilateral"

def test_equilateral_large():
    assert classify_triangle(100, 100, 100) == "equilateral"

def test_equilateral_float():
    assert classify_triangle(1.5, 1.5, 1.5) == "equilateral"


# --- Isosceles ---

def test_isosceles_ab_equal():
    assert classify_triangle(5, 5, 3) == "isosceles"

def test_isosceles_bc_equal():
    assert classify_triangle(3, 5, 5) == "isosceles"

def test_isosceles_ac_equal():
    assert classify_triangle(5, 3, 5) == "isosceles"

def test_isosceles_large():
    assert classify_triangle(100, 100, 50) == "isosceles"


# --- Scalene ---

def test_scalene_pythagorean():
    assert classify_triangle(3, 4, 5) == "scalene"

def test_scalene_generic():
    assert classify_triangle(2, 3, 4) == "scalene"

def test_scalene_large():
    assert classify_triangle(7, 8, 9) == "scalene"


# --- Invalid: non-positive sides ---

def test_invalid_zero_side_a():
    assert classify_triangle(0, 5, 5) == "invalid"

def test_invalid_zero_side_b():
    assert classify_triangle(5, 0, 5) == "invalid"

def test_invalid_zero_side_c():
    assert classify_triangle(5, 5, 0) == "invalid"

def test_invalid_negative_side():
    assert classify_triangle(-1, 5, 5) == "invalid"

def test_invalid_all_negative():
    assert classify_triangle(-1, -2, -3) == "invalid"


# --- Invalid: triangle inequality ---

def test_invalid_degenerate_ab_plus_c():
    assert classify_triangle(1, 2, 3) == "invalid"

def test_invalid_degenerate_ac_plus_b():
    assert classify_triangle(1, 3, 2) == "invalid"

def test_invalid_degenerate_bc_plus_a():
    assert classify_triangle(3, 1, 2) == "invalid"

def test_invalid_sum_less_c():
    assert classify_triangle(1, 2, 10) == "invalid"

def test_invalid_sum_less_a():
    assert classify_triangle(10, 1, 2) == "invalid"

@pytest.mark.parametrize("a,b,c", [
    (5, 5, 10),
    (10, 5, 5),
    (5, 10, 5),
])
def test_invalid_isosceles_degenerate(a, b, c):
    assert classify_triangle(a, b, c) == "invalid"
