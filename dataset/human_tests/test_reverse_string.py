from dataset.sample_functions import reverse_string


# --- Basic cases ---

def test_reverse_normal_word():
    assert reverse_string("hello") == "olleh"

def test_reverse_sentence():
    assert reverse_string("hello world") == "dlrow olleh"

def test_reverse_single_char():
    assert reverse_string("a") == "a"


# --- Edge cases ---

def test_reverse_empty_string():
    assert reverse_string("") == ""

def test_reverse_palindrome_unchanged():
    assert reverse_string("racecar") == "racecar"

def test_reverse_whitespace():
    assert reverse_string("   ") == "   "

def test_reverse_leading_trailing_spaces():
    assert reverse_string("  ab  ") == "  ba  "


# --- Mixed content ---

def test_reverse_mixed_case():
    assert reverse_string("Hello") == "olleH"

def test_reverse_digits():
    assert reverse_string("12345") == "54321"

def test_reverse_special_characters():
    assert reverse_string("a!b@c") == "c@b!a"

def test_reverse_two_chars():
    assert reverse_string("ab") == "ba"
