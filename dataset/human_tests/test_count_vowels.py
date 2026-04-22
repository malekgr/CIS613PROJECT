from dataset.sample_functions import count_vowels


# --- Basic cases ---

def test_count_vowels_simple():
    assert count_vowels("hello") == 2

def test_count_vowels_all_vowels():
    assert count_vowels("aeiou") == 5

def test_count_vowels_all_uppercase_vowels():
    assert count_vowels("AEIOU") == 5

def test_count_vowels_no_vowels():
    assert count_vowels("rhythm") == 0

def test_count_vowels_mixed_case():
    assert count_vowels("Hello World") == 3


# --- Edge cases ---

def test_count_vowels_empty_string():
    assert count_vowels("") == 0

def test_count_vowels_single_vowel():
    assert count_vowels("a") == 1

def test_count_vowels_single_consonant():
    assert count_vowels("z") == 0

def test_count_vowels_digits_only():
    assert count_vowels("12345") == 0

def test_count_vowels_special_chars():
    assert count_vowels("!@#$%") == 0

def test_count_vowels_spaces_only():
    assert count_vowels("   ") == 0


# --- Mixed content ---

def test_count_vowels_digits_and_letters():
    assert count_vowels("a1b2e3") == 2

def test_count_vowels_sentence():
    assert count_vowels("The quick brown fox") == 5

def test_count_vowels_repeated_vowels():
    assert count_vowels("aaaa") == 4
