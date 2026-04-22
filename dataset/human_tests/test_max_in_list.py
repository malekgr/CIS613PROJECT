import pytest
from dataset.sample_functions import max_in_list


# --- Normal cases ---

def test_max_positive_integers():
    assert max_in_list([1, 5, 2, 8, 3]) == 8

def test_max_negative_integers():
    assert max_in_list([-10, -5, -20, -1]) == -1

def test_max_mixed_sign():
    assert max_in_list([-3, 0, 4, -1]) == 4

def test_max_floats():
    assert max_in_list([1.1, 3.3, 2.2]) == 3.3

def test_max_strings():
    assert max_in_list(["apple", "zebra", "mango"]) == "zebra"


# --- Edge cases ---

def test_max_single_element():
    assert max_in_list([42]) == 42

def test_max_all_same():
    assert max_in_list([7, 7, 7]) == 7

def test_max_duplicates():
    assert max_in_list([3, 1, 3, 2]) == 3

def test_max_sorted_ascending():
    assert max_in_list([1, 2, 3, 4, 5]) == 5

def test_max_sorted_descending():
    assert max_in_list([5, 4, 3, 2, 1]) == 5

def test_max_single_negative():
    assert max_in_list([-99]) == -99

def test_max_zero_in_list():
    assert max_in_list([0, -1, -2]) == 0


# --- Error cases ---

def test_max_empty_list_raises_value_error():
    with pytest.raises(ValueError):
        max_in_list([])
