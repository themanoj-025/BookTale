"""Tests for Book-Tale CLI utility functions.

Tests validation helpers, formatting, and ANSI color output.
"""

import pytest

from app.core.utils import (
    colored,
    create_table,
    format_date,
    validate_email,
    validate_isbn,
    validate_phone,
)


class TestValidateEmail:
    """Test email validation."""

    def test_valid_email(self) -> None:
        assert validate_email("user@example.com") is True

    def test_valid_with_dots(self) -> None:
        assert validate_email("user.name@example.co.uk") is True

    def test_valid_with_plus(self) -> None:
        assert validate_email("user+tag@example.com") is True

    def test_invalid_no_at(self) -> None:
        assert validate_email("userexample.com") is False

    def test_invalid_no_domain(self) -> None:
        assert validate_email("user@") is False

    def test_invalid_empty(self) -> None:
        assert validate_email("") is False


class TestValidatePhone:
    """Test phone number validation."""

    def test_valid_with_country_code(self) -> None:
        assert validate_phone("+91 98765 43210") is True

    def test_valid_simple(self) -> None:
        assert validate_phone("9876543210") is True

    def test_valid_with_dashes(self) -> None:
        assert validate_phone("987-654-3210") is True

    def test_invalid_too_short(self) -> None:
        assert validate_phone("123") is False

    def test_invalid_letters(self) -> None:
        assert validate_phone("abcdefghij") is False


class TestValidateIsbn:
    """Test ISBN validation."""

    def test_valid_isbn10(self) -> None:
        assert validate_isbn("0134685991") is True

    def test_valid_isbn13(self) -> None:
        assert validate_isbn("9780134685991") is True

    def test_valid_with_dashes(self) -> None:
        assert validate_isbn("978-0-13-468599-1") is True

    def test_invalid_too_short(self) -> None:
        assert validate_isbn("12345") is False

    def test_invalid_letters(self) -> None:
        assert validate_isbn("013468599X") is False


class TestFormatDate:
    """Test ISO date formatting."""

    def test_valid_iso(self) -> None:
        result = format_date("2024-01-15T10:30:00")
        assert "15" in result
        assert "Jan" in result
        assert "2024" in result

    def test_invalid_returns_original(self) -> None:
        assert format_date("not-a-date") == "not-a-date"

    def test_empty_string(self) -> None:
        assert format_date("") == ""


class TestColored:
    """Test ANSI color helper."""

    def test_red(self) -> None:
        result = colored("hello", "red")
        assert "hello" in result
        assert "\033[91m" in result
        assert "\033[0m" in result

    def test_green(self) -> None:
        result = colored("hello", "green")
        assert "\033[92m" in result

    def test_unknown_code(self) -> None:
        result = colored("hello", "unknown")
        assert "hello" in result
        assert "\033[0m" in result


class TestCreateTable:
    """Test Rich table creation."""

    def test_creates_table(self) -> None:
        table = create_table("Test", ["Name", "Value"], [["a", "1"], ["b", "2"]])
        assert table is not None
