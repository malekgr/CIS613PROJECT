from dataset.sample_functions import is_palindrome


# --- True palindromes ---

def test_palindrome_simple():
    assert is_palindrome("racecar") is True

def test_palindrome_single_char():
    assert is_palindrome("a") is True

def test_palindrome_empty():
    assert is_palindrome("") is True

def test_palindrome_two_same_chars():
    assert is_palindrome("aa") is True

def test_palindrome_case_insensitive():
    assert is_palindrome("Racecar") is True

def test_palindrome_mixed_case():
    assert is_palindrome("AbBa") is True

def test_palindrome_with_leading_trailing_spaces():
    assert is_palindrome("  racecar  ") is True

def test_palindrome_spaces_stripped():
    assert is_palindrome("  aba  ") is True


# --- Not palindromes ---

def test_not_palindrome_simple():
    assert is_palindrome("hello") is False

def test_not_palindrome_two_diff_chars():
    assert is_palindrome("ab") is False

def test_not_palindrome_near_miss():
    assert is_palindrome("racecar1") is False


# --- Whitespace-only ---

def test_palindrome_single_space():
    assert is_palindrome(" ") is True

def test_palindrome_only_spaces():
    assert is_palindrome("   ") is True
